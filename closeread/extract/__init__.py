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

    docs = load_parsed_docs(config, settings, doc_type)
    if not docs:
        log("no parsed documents found; run acquire and parse first")
        sys.exit(1)

    lines, key_index = batch_mod.build_requests(compiled, docs)
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
