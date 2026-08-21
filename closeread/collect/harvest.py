"""Stage 5: collect. Harvest batch responses, align spans, write records.

A record without character offsets is never written to records (§5.6).
Absence records are written per rule 6.3. Nothing is deleted (rule 6.6).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from closeread.collect.align import align_quote
from closeread.config import Settings
from closeread.extract import batch as batch_mod
from closeread.extract.compile import CompiledPass, load_pass
from closeread.jsonl import write_jsonl
from closeread.models import (
    AlignmentStatus,
    EvidenceScope,
    Record,
    RejectedRecord,
    make_record_id,
)
from closeread.parse import ParsedDocument, load_parsed

_STATUS_RANK = {
    AlignmentStatus.match_exact: 0,
    AlignmentStatus.match_fuzzy: 1,
    AlignmentStatus.match_lesser: 2,
}


def run_collect(run_id: str, settings: Settings, log=print) -> dict[str, Any]:
    handoff_path = batch_mod.find_handoff(run_id, settings)
    handoff = json.loads(handoff_path.read_text())
    community = handoff["community"]
    out_dir = settings.community_dir(community)

    compiled = load_pass(handoff["pass_name"])
    if compiled.version != handoff["prompt_version"]:
        log(
            f"WARNING: pass YAML version {compiled.version} differs from run prompt_version "
            f"{handoff['prompt_version']}; validating with the current YAML"
        )

    responses_path = out_dir / "raw" / "batch" / f"{run_id}.responses.jsonl"
    batch_mod.download_responses(handoff, responses_path)

    key_index: dict[str, dict[str, Any]] = handoff["key_index"]
    doc_ids = {info["doc_id"] for info in key_index.values()}
    parsed_docs: dict[str, ParsedDocument] = {}
    if compiled.text_source == "abstract":
        from closeread.config import load_community
        from closeread.extract import load_abstract_docs

        config = load_community(community)
        for doc_type in ("corpus", "citing"):
            for doc_id, parsed in load_abstract_docs(config, settings, doc_type).items():
                if doc_id in doc_ids:
                    parsed_docs[doc_id] = parsed
        scope = EvidenceScope.abstract_only
    else:
        for doc_id in doc_ids:
            p = out_dir / "parsed" / f"{doc_id}.json"
            if p.exists():
                parsed_docs[doc_id] = load_parsed(p)
        scope = EvidenceScope.full_text

    # Candidate spans per doc, for candidate_support (§8.3). Candidates locate
    # text; they never decide meaning.
    candidate_spans: dict[str, list[tuple[int, int]]] = {}
    cand_path = out_dir / "candidates.jsonl"
    if cand_path.exists():
        from closeread.jsonl import read_jsonl as _read

        for c in _read(cand_path):
            candidate_spans.setdefault(c["doc_id"], []).append((c["char_start"], c["char_end"]))

    def has_candidate_support(doc_id: str, start: int, end: int) -> bool:
        return any(start <= cs and ce <= end for cs, ce in candidate_spans.get(doc_id, []))

    stamp = {
        "run_id": run_id,
        "community": community,
        "pass_name": handoff["pass_name"],
        "extractor_model": handoff["model"],
        "prompt_version": handoff["prompt_version"],
        "schema_version": handoff["schema_version"],
    }

    records: list[Record] = []
    rejected: list[RejectedRecord] = []
    finish_reasons: Counter[str] = Counter()
    tokens_in = tokens_out = 0
    n_responses = 0

    def reject(doc_id: str, cls: str, quote: str, attrs: dict[str, Any], reason: str) -> None:
        rejected.append(
            RejectedRecord(
                record_id=make_record_id(doc_id, cls, -1, -1, run_id),
                doc_id=doc_id,
                extraction_class=cls,
                source_quote=quote,
                attributes=attrs,
                enum_drift=[],
                reject_reason=reason,
                evidence_scope=scope,
                **stamp,
            )
        )

    for key, finish, text, usage in batch_mod.iter_responses(responses_path):
        n_responses += 1
        finish_reasons[finish or "NONE"] += 1
        tokens_in += usage.get("promptTokenCount") or 0
        tokens_out += usage.get("candidatesTokenCount") or 0
        info = key_index.get(key)
        if info is None:
            log(f"WARNING: response key {key} not in handoff index")
            continue
        doc_id = info["doc_id"]
        parsed = parsed_docs.get(doc_id)
        if parsed is None:
            log(f"WARNING: no parsed text for {doc_id}")
            continue

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            reason = "truncated_max_tokens" if finish == "MAX_TOKENS" else "unparsable_response"
            reject(doc_id, "*", text[:200], {}, reason)
            continue

        for cls_name, cls in compiled.classes.items():
            for item in payload.get(cls_name) or []:
                if not isinstance(item, dict):
                    continue
                quote = (item.get("source_quote") or "").strip()
                attrs = {a: item.get(a) for a in cls.attributes}
                if not quote:
                    reject(doc_id, cls_name, "", attrs, "empty_quote")
                    continue
                aligned = align_quote(quote, parsed.text, hint=info["window_start"])
                if aligned is None:
                    reject(doc_id, cls_name, quote, attrs, "quote_not_in_source")
                    continue
                records.append(
                    Record(
                        record_id=make_record_id(doc_id, cls_name, aligned.start, aligned.end, run_id),
                        doc_id=doc_id,
                        extraction_class=cls_name,
                        source_quote=parsed.text[aligned.start : aligned.end],
                        char_start=aligned.start,
                        char_end=aligned.end,
                        source_section=parsed.sections.section_at(aligned.start),
                        alignment_status=aligned.status,
                        attributes=attrs,
                        enum_drift=compiled.enum_drift(cls_name, attrs),
                        candidate_support=has_candidate_support(doc_id, aligned.start, aligned.end),
                        evidence_scope=scope,
                        **stamp,
                    )
                )

    # Deduplicate on (doc_id, class, char_start, char_end); prefer better alignment.
    records.sort(key=lambda r: _STATUS_RANK[r.alignment_status])
    seen: set[tuple[str, str, int, int]] = set()
    deduped: list[Record] = []
    for r in records:
        k = (r.doc_id, r.extraction_class, r.char_start, r.char_end)
        if k not in seen:
            seen.add(k)
            deduped.append(r)
    n_dupes = len(records) - len(deduped)

    # Absence records (rule 6.3).
    n_absence = 0
    for cls_name, cls in compiled.classes.items():
        if not cls.absence_attributes:
            continue
        docs_with = {r.doc_id for r in deduped if r.extraction_class == cls_name}
        for doc_id in sorted(doc_ids - docs_with):
            attrs = {a: None for a in cls.attributes} | dict(cls.absence_attributes)
            deduped.append(
                Record(
                    record_id=make_record_id(doc_id, cls_name, 0, 0, run_id),
                    doc_id=doc_id,
                    extraction_class=cls_name,
                    source_quote="",
                    char_start=0,
                    char_end=0,
                    source_section="none",
                    alignment_status=AlignmentStatus.match_exact,
                    attributes=attrs,
                    enum_drift=[],
                    evidence_scope=scope,
                    **stamp,
                )
            )
            n_absence += 1

    bronze = out_dir / "bronze"
    records_path = bronze / f"records_{run_id}.jsonl"
    rejected_path = bronze / f"rejected_{run_id}.jsonl"
    write_jsonl(records_path, deduped)
    write_jsonl(rejected_path, rejected)

    # Attribute population per class (§11.2).
    population: dict[str, dict[str, float]] = {}
    for cls_name, cls in compiled.classes.items():
        cls_records = [
            r for r in deduped if r.extraction_class == cls_name and r.source_quote
        ]
        if not cls_records:
            continue
        population[cls_name] = {
            attr: round(
                sum(
                    1
                    for r in cls_records
                    if r.attributes.get(attr) not in (None, "", "not_stated")
                )
                / len(cls_records),
                3,
            )
            for attr in cls.attributes
        }

    n_stop = finish_reasons.get("STOP", 0)
    summary = {
        "run_id": run_id,
        "n_responses": n_responses,
        "n_requests": handoff["n_requests"],
        "finish_reasons": dict(finish_reasons),
        "stop_share": round(n_stop / n_responses, 4) if n_responses else 0.0,
        "max_tokens_count": finish_reasons.get("MAX_TOKENS", 0),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "records": len(deduped),
        "extracted_records": len(deduped) - n_absence,
        "absence_records": n_absence,
        "rejected": len(rejected),
        "duplicates_removed": n_dupes,
        "alignment": dict(Counter(r.alignment_status.value for r in deduped if r.source_quote)),
        "attribute_population": population,
        "sections_read": handoff.get("sections_read"),
    }
    summary_path = out_dir / "runs" / f"{run_id}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log(json.dumps(summary, indent=2))
    log(f"records -> {records_path}")
    return summary
