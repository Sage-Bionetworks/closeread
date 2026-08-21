"""Stage 1: acquire. Orchestration for corpus (M2) and citing (M7) acquisition."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from closeread.acquire import openalex, pmc
from closeread.config import CommunityConfig, Settings
from closeread.jsonl import read_jsonl, write_jsonl
from closeread.models import Document


def _today() -> str:
    return dt.date.today().isoformat()


def read_seed(config: CommunityConfig) -> list[dict[str, str]]:
    with open(config.seed_path()) as fh:
        return list(csv.DictReader(fh))


def acquire_corpus(config: CommunityConfig, settings: Settings, log=print) -> list[Document]:
    """Resolve the corpus seed in OpenAlex and fetch full text (tier B only).

    Writes documents.jsonl and raw/fulltext/*.xml under out/<community>/.
    A document that cannot be fetched is recorded with oa_status="unavailable";
    the stage does not stop (spec §5.1).
    """
    seed = read_seed(config)
    snapshot_date = _today()
    log(f"seed rows: {len(seed)}")

    works_by_pmid = openalex.works_by_pmids([r.get("pmid", "") for r in seed], settings.openalex_mailto)
    log(f"resolved by pmid: {len(works_by_pmid)}")
    missing = [r for r in seed if r.get("pmid") not in works_by_pmid]
    works_by_doi = openalex.works_by_dois(
        [r.get("doi", "") for r in missing], settings.openalex_mailto
    )
    if missing:
        log(f"fallback resolved by doi: {len(works_by_doi)} of {len(missing)}")

    out_dir = settings.community_dir(config.community)
    fulltext_dir = out_dir / "raw" / "fulltext"
    s3 = pmc.unsigned_client()

    documents: list[Document] = []
    bytes_fetched = 0
    group_col = config.corpus.group_by
    for row in seed:
        work = works_by_pmid.get(row.get("pmid", "")) or works_by_doi.get(
            (row.get("doi") or "").lower()
        )
        if work is None:
            documents.append(
                Document(
                    doc_id=f"pmid:{row.get('pmid')}" if row.get("pmid") else f"doi:{row.get('doi')}",
                    doc_type="corpus",
                    community=config.community,
                    pmid=row.get("pmid") or None,
                    doi=row.get("doi") or None,
                    title=row.get("title") or None,
                    group_key=row.get(group_col) or None,
                    oa_status="unresolved",
                    snapshot_date=snapshot_date,
                )
            )
            continue
        s = openalex.work_summary(work)
        pmcid = s["pmcid"] or row.get("pmcid") or None
        oa_status = "abstract_only" if s["abstract"] else "unavailable"
        source_version = None
        if pmcid:
            fetched = pmc.fetch_jats(s3, pmcid, fulltext_dir)
            if fetched:
                path, source_version = fetched
                bytes_fetched += path.stat().st_size
                oa_status = "fulltext"
        documents.append(
            Document(
                doc_id=s["doc_id"],
                doc_type="corpus",
                community=config.community,
                pmid=s["pmid"] or row.get("pmid") or None,
                pmcid=pmcid,
                doi=s["doi"] or row.get("doi") or None,
                title=s["title"] or row.get("title") or None,
                pub_date=s["pub_date"],
                venue=s["venue"],
                oa_status=oa_status,
                source_version=source_version,
                group_key=row.get(group_col) or None,
                snapshot_date=snapshot_date,
                author_ids=s["author_ids"],
                institution_ids=s["institution_ids"],
                abstract=s["abstract"] or row.get("abstract") or None,
            )
        )

    # Two seed rows can resolve to the same OpenAlex work (e.g. a preprint
    # and its published version). Keep one row per doc_id, preferring the
    # fulltext one.
    by_id: dict[str, Document] = {}
    for d in documents:
        cur = by_id.get(d.doc_id)
        if cur is None or (d.oa_status == "fulltext" and cur.oa_status != "fulltext"):
            by_id[d.doc_id] = d
    if len(by_id) < len(documents):
        log(f"collapsed {len(documents) - len(by_id)} duplicate doc_id rows")
    documents = list(by_id.values())

    _backfill_abstracts(documents, settings, log)

    docs_path = out_dir / "documents.jsonl"
    write_jsonl(docs_path, documents)
    n_full = sum(1 for d in documents if d.oa_status == "fulltext")
    n_abs = sum(1 for d in documents if d.abstract)
    log(
        f"documents: {len(documents)}  fulltext: {n_full}  with abstract: {n_abs}  "
        f"bytes fetched: {bytes_fetched:,}  -> {docs_path}"
    )
    return documents


def _backfill_abstracts(documents: list[Document], settings: Settings, log=print) -> None:
    """PubMed abstract fallback for works with neither full text nor an
    OpenAlex abstract (§5.1 step 5: fetch the abstract for every work)."""
    targets = [d for d in documents if d.oa_status != "fulltext" and not d.abstract and d.pmid]
    if not targets:
        return
    got = pmc.fetch_abstracts([d.pmid for d in targets], settings.openalex_mailto, log=log)
    n = 0
    for d in targets:
        if d.pmid in got:
            d.abstract = got[d.pmid]
            d.oa_status = "abstract_only"
            n += 1
    log(f"abstract backfill via PubMed: {n} of {len(targets)}")


def parsed_dir(settings: Settings, community: str) -> Path:
    return settings.community_dir(community) / "parsed"


def acquire_tier_c(config: CommunityConfig, settings: Settings, log=print) -> None:
    """Tier C: fetch pending bioRxiv/medRxiv preprints from the requester-pays
    buckets (spec §5.1). Scans month folders implied by posting dates, then
    extracts only the JATS entry per package. Logs bytes transferred."""
    from collections import defaultdict

    from closeread.acquire import biorxiv as brx

    out_dir = settings.community_dir(config.community)
    docs = list(read_jsonl(out_dir / "documents.jsonl"))
    pending = [
        d for d in docs
        if d.get("oa_status") == "preprint_requester_pays_pending" and d.get("doi") and d.get("pub_date")
    ]
    if not pending:
        log("no tier-C preprints pending")
        return
    profile = config.aws_profile_requester_pays or "htan-dev"
    s3 = brx.requester_pays_client(profile)
    meter = brx.TransferMeter()
    fulltext_dir = out_dir / "raw" / "fulltext"
    fulltext_dir.mkdir(parents=True, exist_ok=True)

    by_month: dict[str, dict[str, dict]] = defaultdict(dict)  # prefix -> article_id -> doc row
    for d in pending:
        by_month[brx.month_prefix(d["pub_date"])][brx.article_id_from_doi(d["doi"])] = d

    fetched: dict[str, str] = {}  # doc_id -> filename
    for bucket in (brx.BIORXIV_BUCKET, brx.MEDRXIV_BUCKET):
        remaining_months = {
            prefix: {aid: d for aid, d in wanted.items() if d["doc_id"] not in fetched}
            for prefix, wanted in by_month.items()
        }
        remaining_months = {p: w for p, w in remaining_months.items() if w}
        if not remaining_months:
            break
        log(f"scanning {bucket}: {sum(len(w) for w in remaining_months.values())} preprints across {len(remaining_months)} months")
        for prefix, wanted in sorted(remaining_months.items()):
            try:
                found = brx.scan_month(s3, bucket, prefix, set(wanted), meter, log=log)
            except Exception as exc:  # noqa: BLE001 — a bad month must not stop the stage
                log(f"  {bucket}/{prefix}: scan failed: {exc}")
                continue
            for aid, entry in found.items():
                doc = wanted[aid]
                try:
                    xml = brx.fetch_entry_xml(s3, bucket, entry, meter)
                except Exception as exc:  # noqa: BLE001
                    log(f"  fetch failed {entry.key}: {exc}")
                    continue
                dest = fulltext_dir / f"{doc['doc_id']}.preprint.xml"
                dest.write_bytes(xml)
                fetched[doc["doc_id"]] = dest.name

    for d in docs:
        if d["doc_id"] in fetched:
            d["oa_status"] = "fulltext"
            d["source_version"] = "meca"
    write_jsonl(out_dir / "documents.jsonl", docs)
    log(
        f"tier C: fetched {len(fetched)} of {len(pending)} pending preprints; "
        f"{meter.requests:,} requester-pays requests, {meter.bytes / 1e9:.2f} GB transferred"
    )


CITING_WORK_FIELDS = (
    "id,doi,title,publication_year,publication_date,type,ids,"
    "primary_location,authorships,abstract_inverted_index,referenced_works"
)

# Read-only reference cache of previously fetched citing JATS (999 MB in the
# prototype repo). Hits are copied in; misses fall through to S3.
REFERENCE_CITING_CACHE = Path(
    "/Users/ataylor/Documents/projects/htan2/htan-pubs-fulltext/citing_jats"
)


def acquire_citing(config: CommunityConfig, settings: Settings, log=print) -> None:
    """Citing-side acquisition (§5.1 steps 2-5, §5.2, §5.2.1). Tiers:
    A merged preprint (no fetch), B PMC, C bioRxiv/medRxiv requester-pays,
    D abstract only."""
    from closeread.acquire.dedup import classify_author_overlap, dedup_preprints
    from closeread.models import CitationEdge, make_edge_id

    out_dir = settings.community_dir(config.community)
    existing = list(read_jsonl(out_dir / "documents.jsonl"))
    corpus_rows = [d for d in existing if d["doc_type"] == "corpus"]
    corpus_ids = {d["doc_id"] for d in corpus_rows}
    corpus_author_ids = {a for d in corpus_rows for a in d.get("author_ids") or []}
    snapshot_date = _today()

    # 1. Enumerate citing works, deduplicated by Work ID; capture edges from
    #    referenced_works ∩ corpus.
    citing: dict[str, dict] = {}
    edges: dict[str, CitationEdge] = {}
    id_list = sorted(corpus_ids)
    for i in range(0, len(id_list), 50):
        batch = id_list[i : i + 50]
        for work in openalex.works_by_filter(
            "cites:" + "|".join(batch), settings.openalex_mailto, select=CITING_WORK_FIELDS
        ):
            s = openalex.work_summary(work)
            refs = {openalex.short_id(r) for r in work.get("referenced_works") or []}
            cited = refs & corpus_ids
            for cited_id in cited:
                eid = make_edge_id(s["doc_id"], cited_id)
                edges[eid] = CitationEdge(edge_id=eid, citing_doc_id=s["doc_id"], cited_doc_id=cited_id)
            if s["doc_id"] not in citing:
                s["work_type"] = work.get("type")
                citing[s["doc_id"]] = s
        log(f"citing enumeration: {len(citing)} works, {len(edges)} edges after {min(i + 50, len(id_list))}/{len(id_list)} corpus ids")

    write_jsonl(out_dir / "citation_edges.jsonl", edges.values())

    # 2. Preprint/published dedup (§5.2).
    works = list(citing.values())
    n_before = len(works)
    kept, n_merged = dedup_preprints(works)
    log(f"preprint dedup: {n_before} -> {len(kept)} citing works ({n_merged} pairs merged)")

    # 3. Resolve PMCIDs: OpenAlex does not return them.
    pmcid_map = pmc.pmids_to_pmcids(
        [s["pmid"] for s in kept if s.get("pmid") and not s.get("pmcid")],
        settings.openalex_mailto,
        log=log,
    )
    for s in kept:
        if not s.get("pmcid") and s.get("pmid"):
            s["pmcid"] = pmcid_map.get(s["pmid"])
    log(f"pmcids resolved: {sum(1 for s in kept if s.get('pmcid'))} of {len(kept)}")

    # 4. Tiers B/C/D + author overlap.
    fulltext_dir = out_dir / "raw" / "fulltext"
    s3 = pmc.unsigned_client()
    ref_cache = REFERENCE_CITING_CACHE if REFERENCE_CITING_CACHE.exists() else None
    documents: list[Document] = []
    n_full = n_cache = bytes_fetched = 0
    tier_c_pending = 0
    for s in kept:
        if s["doc_id"] in corpus_ids:
            continue  # the citing work is itself a corpus document; already recorded
        overlap = classify_author_overlap(s, corpus_ids, corpus_author_ids)
        oa_status = "abstract_only" if s["abstract"] else "unavailable"
        source_version = None
        if s["pmcid"]:
            fetched = pmc.fetch_jats(s3, s["pmcid"], fulltext_dir, reference_cache=ref_cache)
            if fetched:
                path, source_version = fetched
                oa_status = "fulltext"
                n_full += 1
        elif s["doi"] and s["doi"].startswith("10.1101/"):
            # tier C: bioRxiv/medRxiv requester-pays; needs the AWS profile.
            oa_status = "preprint_requester_pays_pending"
            tier_c_pending += 1
        documents.append(
            Document(
                doc_id=s["doc_id"],
                doc_type="citing",
                community=config.community,
                pmid=s["pmid"],
                pmcid=s["pmcid"],
                doi=s["doi"],
                title=s["title"],
                pub_date=s["pub_date"],
                venue=s["venue"],
                oa_status=oa_status,
                source_version=source_version,
                merged_from=s.get("merged_from") or [],
                snapshot_date=snapshot_date,
                author_ids=s.get("author_ids") or [],
                institution_ids=s.get("institution_ids") or [],
                abstract=s["abstract"],
                is_preprint=s.get("work_type") == "preprint",
                **overlap,
            )
        )

    _backfill_abstracts(documents, settings, log)

    all_rows = corpus_rows + [json_ready for json_ready in (d.model_dump() for d in documents)]
    write_jsonl(out_dir / "documents.jsonl", all_rows)
    n_abs = sum(1 for d in documents if d.abstract)
    log(
        f"citing documents: {len(documents)}  fulltext: {n_full}  with abstract: {n_abs}  "
        f"tier-C pending (needs aws sso login): {tier_c_pending}  merged pairs: {n_merged}"
    )
    from collections import Counter

    log(f"author_overlap: {Counter(d.author_overlap.value for d in documents if d.author_overlap)}")
