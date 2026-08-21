"""Stage 1: acquire. Orchestration for corpus (M2) and citing (M7) acquisition."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from closeread.acquire import openalex, pmc
from closeread.config import CommunityConfig, Settings
from closeread.jsonl import write_jsonl
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

    docs_path = out_dir / "documents.jsonl"
    write_jsonl(docs_path, documents)
    n_full = sum(1 for d in documents if d.oa_status == "fulltext")
    n_abs = sum(1 for d in documents if d.abstract)
    log(
        f"documents: {len(documents)}  fulltext: {n_full}  with abstract: {n_abs}  "
        f"bytes fetched: {bytes_fetched:,}  -> {docs_path}"
    )
    return documents


def parsed_dir(settings: Settings, community: str) -> Path:
    return settings.community_dir(community) / "parsed"
