"""Stage 7: judge. Spec §5.8.

The judge model must differ from the extractor (the two disagreed on 43
percent of prototype records; agreement between identical models measures
nothing). Judging is per document, not per record: all of a document's records
go in one request, with the document's candidates as additional evidence.
Verdicts are stored; rejected records are never deleted (rule 6.6).
"""

from __future__ import annotations

import datetime as dt
import json
import time
from typing import Any

from closeread.config import Settings
from closeread.extract import batch as batch_mod
from closeread.jsonl import read_jsonl, write_jsonl
from closeread.parse import load_parsed

CONTEXT_CHARS = 400

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdicts": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "record_id": {"type": "STRING"},
                    "verdict": {"type": "STRING"},
                    "confidence": {"type": "NUMBER"},
                    "reason": {"type": "STRING"},
                },
                "required": ["record_id", "verdict", "confidence", "reason"],
            },
        }
    },
    "required": ["verdicts"],
}

VERDICT_VALUES = {"confirmed", "rejected", "uncertain"}


def _judge_prompt(doc_records: list[dict], contexts: dict[str, str], candidates: list[dict]) -> str:
    lines = [
        "You are auditing records extracted from one scientific publication by another model.",
        "For each record decide: does the quoted text, in its context, actually support the",
        "record's attribute values and its extraction class?",
        "",
        "Verdicts: confirmed (the text supports it), rejected (the text does not support it,",
        "or the attributes misread the text), uncertain (the text is ambiguous).",
        "Give a confidence in [0,1] and a one-sentence reason.",
        "Judge every record. Return one verdict per record_id, exactly as given.",
        "",
        "Regular-expression candidates found in this document (evidence of strings, not of",
        "meaning — an accession can be a release or an acquisition; the verb decides):",
        json.dumps(candidates, ensure_ascii=False) if candidates else "(none)",
        "",
        "Records:",
    ]
    for r in doc_records:
        lines.append(
            json.dumps(
                {
                    "record_id": r["record_id"],
                    "extraction_class": r["extraction_class"],
                    "source_quote": r["source_quote"],
                    "source_section": r["source_section"],
                    "attributes": r["attributes"],
                    "context": contexts.get(r["record_id"], ""),
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


def run_judge(
    run_id: str,
    settings: Settings,
    judge_model: str | None = None,
    log=print,
) -> dict[str, Any] | None:
    handoff = json.loads(batch_mod.find_handoff(run_id, settings).read_text())
    community = handoff["community"]
    out_dir = settings.community_dir(community)
    extractor_model = handoff["model"]
    if judge_model is None:
        judge_model = (
            batch_mod.STRONG_MODEL if extractor_model != batch_mod.STRONG_MODEL else batch_mod.SMALL_MODEL
        )
    if judge_model == extractor_model:
        raise SystemExit(
            f"judge model must differ from extractor model ({extractor_model}); pass a different --model"
        )

    records = [
        r
        for r in read_jsonl(out_dir / "bronze" / f"records_{run_id}.jsonl")
        if r["source_quote"]  # absence records are bookkeeping, not claims
    ]
    if not records:
        log("no records to judge")
        return None

    candidates_by_doc: dict[str, list[dict]] = {}
    cand_path = out_dir / "candidates.jsonl"
    if cand_path.exists():
        for c in read_jsonl(cand_path):
            candidates_by_doc.setdefault(c["doc_id"], []).append(
                {"kind": c["kind"], "value": c["value"], "section": c["section"]}
            )

    by_doc: dict[str, list[dict]] = {}
    for r in records:
        by_doc.setdefault(r["doc_id"], []).append(r)

    lines = []
    for doc_id, doc_records in sorted(by_doc.items()):
        parsed_path = out_dir / "parsed" / f"{doc_id}.json"
        contexts: dict[str, str] = {}
        if parsed_path.exists():
            text = load_parsed(parsed_path).text
            for r in doc_records:
                lo = max(0, r["char_start"] - CONTEXT_CHARS)
                hi = min(len(text), r["char_end"] + CONTEXT_CHARS)
                contexts[r["record_id"]] = text[lo:hi]
        prompt = _judge_prompt(doc_records, contexts, candidates_by_doc.get(doc_id, []))
        lines.append(
            {
                "key": doc_id,
                "request": {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseSchema": _RESPONSE_SCHEMA,
                        "temperature": 0,
                        "maxOutputTokens": 32768,
                    },
                },
            }
        )

    est = batch_mod.estimate(lines, judge_model)
    log(f"judge: {len(records)} records in {len(lines)} documents, model {judge_model}")
    log(est.describe())

    # Canary (rule 6.9): two real requests; assert STOP + valid verdicts.
    from google.genai import types

    client = batch_mod._client()
    jdir = out_dir / "judge"
    jdir.mkdir(parents=True, exist_ok=True)
    tag = f"{run_id}_judge_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"

    def _submit(sub_lines: list[dict], name: str):
        p = jdir / f"{name}.requests.jsonl"
        with open(p, "w") as fh:
            for l in sub_lines:
                fh.write(json.dumps(l, ensure_ascii=False) + "\n")
        up = client.files.upload(
            file=str(p), config=types.UploadFileConfig(display_name=name, mime_type="application/jsonl")
        )
        return client.batches.create(
            model=judge_model, src=up.name, config=types.CreateBatchJobConfig(display_name=name)
        )

    def _await(job):
        while True:
            job = client.batches.get(name=job.name)
            state = batch_mod.job_state(job)
            if "SUCCEEDED" in state or "FAILED" in state or "CANCELLED" in state or "EXPIRED" in state:
                return job, state
            time.sleep(20)

    canary_job = _submit(lines[:2], f"{tag}_canary")
    canary_job, state = _await(canary_job)
    if "SUCCEEDED" not in state:
        log(f"judge canary ended {state}; nothing submitted")
        raise SystemExit(1)
    cpath = jdir / f"{tag}_canary.responses.jsonl"
    batch_mod.download_responses({"batch_job_name": canary_job.name}, cpath)
    ok = 0
    for _key, finish, text, _u in batch_mod.iter_responses(cpath):
        if finish != "STOP":
            continue
        try:
            vs = json.loads(text)["verdicts"]
            if vs and all(v["verdict"] in VERDICT_VALUES for v in vs):
                ok += 1
        except (json.JSONDecodeError, KeyError):
            pass
    if ok < 2:
        log("judge canary failed assertions; nothing submitted")
        raise SystemExit(1)
    log("judge canary passed")

    job = _submit(lines, tag)
    log(f"judge batch submitted: {job.name}; collect with closeread judge-collect --run {run_id} --job-tag {tag}")
    (jdir / f"{tag}.handoff.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "community": community,
                "judge_model": judge_model,
                "extractor_model": extractor_model,
                "batch_job_name": job.name,
                "tag": tag,
                "n_requests": len(lines),
                "n_records": len(records),
                "submitted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    return {"tag": tag, "job": job.name}


def collect_judge(run_id: str, tag: str, settings: Settings, log=print) -> dict[str, Any]:
    hits = list(settings.out_dir.glob(f"*/judge/{tag}.handoff.json"))
    if not hits:
        raise FileNotFoundError(f"no judge handoff for tag {tag}")
    handoff = json.loads(hits[0].read_text())
    jdir = hits[0].parent
    rpath = jdir / f"{tag}.responses.jsonl"
    batch_mod.download_responses(handoff, rpath)

    verdicts: list[dict[str, Any]] = []
    n_bad = 0
    for _key, finish, text, _u in batch_mod.iter_responses(rpath):
        if finish != "STOP":
            n_bad += 1
            continue
        try:
            for v in json.loads(text)["verdicts"]:
                if v.get("verdict") in VERDICT_VALUES:
                    verdicts.append(
                        {
                            "record_id": v["record_id"],
                            "verdict": v["verdict"],
                            "confidence": v.get("confidence"),
                            "reason": v.get("reason"),
                            "judge_model": handoff["judge_model"],
                            "run_id": run_id,
                            "tag": tag,
                        }
                    )
        except (json.JSONDecodeError, KeyError):
            n_bad += 1
    dest = jdir / f"verdicts_{run_id}_{tag}.jsonl"
    write_jsonl(dest, verdicts)
    from collections import Counter

    summary = {
        "verdicts": len(verdicts),
        "by_verdict": dict(Counter(v["verdict"] for v in verdicts)),
        "bad_responses": n_bad,
    }
    log(f"{summary} -> {dest}")

    from closeread.normalise.vocab import apply_to_silver

    apply_to_silver(settings, handoff["community"], log=log)
    return summary
