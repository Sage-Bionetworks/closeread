"""Stage 4: extract. Compiles a pass, runs the canary, submits the batch job."""

from __future__ import annotations

import sys

from closeread.config import CommunityConfig, Settings
from closeread.extract import batch as batch_mod
from closeread.extract.canary import run_canary
from closeread.extract.compile import load_pass
from closeread.jsonl import read_jsonl
from closeread.parse import ParsedDocument, load_parsed


def load_parsed_docs(
    config: CommunityConfig, settings: Settings, doc_type: str = "corpus"
) -> dict[str, ParsedDocument]:
    out_dir = settings.community_dir(config.community)
    docs: dict[str, ParsedDocument] = {}
    for doc in read_jsonl(out_dir / "documents.jsonl"):
        if doc.get("doc_type") != doc_type or doc.get("oa_status") != "fulltext":
            continue
        path = out_dir / "parsed" / f"{doc['doc_id']}.json"
        if path.exists():
            docs[doc["doc_id"]] = load_parsed(path)
    return docs


def load_abstract_docs(
    config: CommunityConfig, settings: Settings, doc_type: str = "corpus"
) -> dict[str, ParsedDocument]:
    """Abstract-pass corpus: every document with an abstract, whether or not
    full text exists (§7.4 — the abstract pass reaches documents no other pass
    can)."""
    from closeread.parse import SectionIndex

    out_dir = settings.community_dir(config.community)
    docs: dict[str, ParsedDocument] = {}
    for doc in read_jsonl(out_dir / "documents.jsonl"):
        if doc.get("doc_type") != doc_type or not doc.get("abstract"):
            continue
        text = doc["abstract"]
        index = SectionIndex()
        index.add(["abstract"], "Abstract", 0, len(text))
        docs[doc["doc_id"]] = ParsedDocument(doc_title=doc.get("title"), text=text, sections=index)
    return docs


def _anchor_windows(
    config: CommunityConfig,
    settings: Settings,
    doc_type: str,
    radius: int,
    log=print,
) -> tuple[dict[str, ParsedDocument], dict[str, list[tuple[int, int]]]]:
    """Documents and merged anchor windows for the provenance pass (§4.2.3).
    Documents without anchors are excluded from the run."""
    from closeread.candidates.anchors import (
        accession_anchors,
        citation_anchors,
        identity_anchors,
        merge_anchor_windows,
    )

    out_dir = settings.community_dir(config.community)
    corpus = [d for d in read_jsonl(out_dir / "documents.jsonl") if d["doc_type"] == "corpus"]
    corpus_dois = {d["doi"] for d in corpus if d.get("doi")}
    corpus_pmids = {d["pmid"] for d in corpus if d.get("pmid")}
    corpus_doc_ids = {d["doc_id"] for d in corpus}

    # Accessions the corpus itself mentions: generic accessions anchor only
    # when they appear in corpus text.
    corpus_accessions: set[str] = set()
    cand_path = out_dir / "candidates.jsonl"
    if cand_path.exists():
        for c in read_jsonl(cand_path):
            if c["doc_id"] in corpus_doc_ids:
                corpus_accessions.add(c["value"])

    docs_meta = {
        d["doc_id"]: d
        for d in read_jsonl(out_dir / "documents.jsonl")
        if d["doc_type"] == doc_type and d.get("oa_status") == "fulltext"
    }
    fulltext_dir = out_dir / "raw" / "fulltext"

    docs: dict[str, ParsedDocument] = {}
    windows: dict[str, list[tuple[int, int]]] = {}
    n_anchors = 0
    for doc_id, meta in docs_meta.items():
        parsed_path = out_dir / "parsed" / f"{doc_id}.json"
        if not parsed_path.exists():
            continue
        parsed = load_parsed(parsed_path)
        anchors = identity_anchors(parsed.text, config)
        anchors += accession_anchors(parsed.text, config, corpus_accessions)
        xml_path = fulltext_dir / f"{meta['pmcid']}.{meta['source_version']}.xml"
        if xml_path.exists():
            anchors += citation_anchors(xml_path, parsed, corpus_dois, corpus_pmids)
        merged = merge_anchor_windows(anchors, len(parsed.text), radius)
        if merged:
            docs[doc_id] = parsed
            windows[doc_id] = merged
            n_anchors += len(anchors)
    log(
        f"anchor windows: {sum(len(w) for w in windows.values())} windows from "
        f"{n_anchors} anchors in {len(docs)} of {len(docs_meta)} documents"
    )
    return docs, windows


def run_extract(
    config: CommunityConfig,
    settings: Settings,
    pass_name: str,
    dry_run: bool = False,
    model_override: str | None = None,
    skip_canary: bool = False,
    doc_type: str = "corpus",
    log=print,
) -> dict | None:
    compiled = load_pass(pass_name)
    if doc_type not in compiled.applies_to:
        log(f"pass {pass_name} does not apply to {doc_type} (applies_to={compiled.applies_to})")
        sys.exit(1)
    model = model_override or batch_mod.STRONG_MODEL

    windows_by_doc = None
    preamble = None
    if compiled.text_source == "abstract":
        docs = load_abstract_docs(config, settings, doc_type)
    elif compiled.text_source == "anchors":
        docs, windows_by_doc = _anchor_windows(config, settings, doc_type, compiled.anchor_radius, log)
        preamble = (
            f"The consortium of interest is {config.display_name} "
            f"(also referred to as: {', '.join(config.identity_strings)}). "
            "The text below consists of excerpts from one citing publication, "
            "selected around mentions of that consortium, its accessions, or its papers."
        )
    else:
        docs = load_parsed_docs(config, settings, doc_type)
    if not docs:
        log("no parsed documents found; run acquire and parse first")
        sys.exit(1)

    lines, key_index = batch_mod.build_requests(compiled, docs, windows_by_doc, preamble)
    est = batch_mod.estimate(lines, model)
    log(f"pass={pass_name} model={model} documents={len(docs)}")
    log(est.describe())

    if dry_run:
        log("dry run: nothing submitted")
        return None

    if skip_canary:
        log("WARNING: canary skipped by flag")
        canary_passed = False
    else:
        canary_passed = run_canary(lines, key_index, docs, compiled, model, settings, config.community, log=log)
        if not canary_passed:
            log("canary FAILED: fan-out not submitted (rule 6.9)")
            sys.exit(1)

    run_id = batch_mod.next_run_id(settings, config.community, pass_name)
    handoff = batch_mod.submit(
        lines, key_index, run_id, model, compiled, settings, config.community, canary_passed
    )
    log(f"submitted run {run_id} as batch job {handoff['batch_job_name']}")
    log(f"collect with: closeread collect --run {run_id}")
    return handoff
