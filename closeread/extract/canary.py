"""Canary before fan-out (rule 6.9).

Submit two requests through the real batch path. Assert three things:
finishReason == "STOP"; every attribute key is present; at least one quotation
aligns to the source text. If any assertion fails, the fan-out is not
submitted. This check costs a few cents; its absence cost about 21 USD in the
prototype.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from typing import Any

from closeread.collect.align import align_quote
from closeread.config import Settings
from closeread.extract import batch as batch_mod
from closeread.extract.compile import CompiledPass
from closeread.parse import ParsedDocument

POLL_SECONDS = 20
TIMEOUT_SECONDS = 45 * 60


def pick_canary_lines(
    lines: list[dict[str, Any]],
    key_index: dict[str, dict[str, Any]],
    docs: dict[str, ParsedDocument],
    n: int = 2,
    identity_strings: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Prefer windows likely to yield extractions, so the canary's
    quote-alignment assertion has something to align: windows containing an
    identity string (anchor passes), then windows overlapping an availability
    section."""

    def window_text(key: str) -> str:
        info = key_index[key]
        return docs[info["doc_id"]].text[info["window_start"] : info["window_end"]]

    def has_identity(key: str) -> bool:
        text = window_text(key)
        return any(s in text for s in identity_strings)

    def has_target(key: str) -> bool:
        info = key_index[key]
        parsed = docs[info["doc_id"]]
        return any(
            ("data_availability" in s.labels or "code_availability" in s.labels)
            and s.start < info["window_end"]
            and s.end > info["window_start"]
            for s in parsed.sections.spans
        )

    preferred = []
    if identity_strings:
        preferred = [l for l in lines if has_identity(l["key"])]
    preferred += [l for l in lines if has_target(l["key"])]
    chosen: list[dict[str, Any]] = []
    seen_docs: set[str] = set()
    for line in preferred + lines:
        doc_id = key_index[line["key"]]["doc_id"]
        if doc_id in seen_docs:
            continue
        chosen.append(line)
        seen_docs.add(doc_id)
        if len(chosen) == n:
            break
    return chosen


def run_canary(
    lines: list[dict[str, Any]],
    key_index: dict[str, dict[str, Any]],
    docs: dict[str, ParsedDocument],
    compiled: CompiledPass,
    model: str,
    settings: Settings,
    community: str,
    log=print,
    identity_strings: tuple[str, ...] = (),
) -> bool:
    from google.genai import types

    canary_lines = pick_canary_lines(lines, key_index, docs, identity_strings=identity_strings)
    if len(canary_lines) < 2:
        log("canary: fewer than 2 requests available")
        return False

    rdir = batch_mod.runs_dir(settings, community)
    rdir.mkdir(parents=True, exist_ok=True)
    tag = f"{community}_{compiled.name}_canary_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"
    input_path = rdir / f"{tag}.requests.jsonl"
    with open(input_path, "w") as fh:
        for line in canary_lines:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    client = batch_mod._client()
    uploaded = client.files.upload(
        file=str(input_path),
        config=types.UploadFileConfig(display_name=tag, mime_type="application/jsonl"),
    )
    job = client.batches.create(
        model=model,
        src=uploaded.name,
        config=types.CreateBatchJobConfig(display_name=tag),
    )
    log(f"canary: submitted 2 requests as {job.name}; polling every {POLL_SECONDS}s")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    state = ""
    while time.monotonic() < deadline:
        job = client.batches.get(name=job.name)
        state = batch_mod.job_state(job)
        if "SUCCEEDED" in state or "FAILED" in state or "CANCELLED" in state or "EXPIRED" in state:
            break
        time.sleep(POLL_SECONDS)
    if "SUCCEEDED" not in state:
        log(f"canary: job ended in state {state} — fan-out will NOT be submitted")
        return False

    responses_path = rdir / f"{tag}.responses.jsonl"
    batch_mod.download_responses({"batch_job_name": job.name}, responses_path)

    checks = {"finish_stop": True, "attributes_complete": True, "quote_aligned": False}
    n_responses = 0
    for key, finish, text, _usage in batch_mod.iter_responses(responses_path):
        n_responses += 1
        if finish != "STOP":
            checks["finish_stop"] = False
            log(f"canary: {key} finishReason={finish}")
            continue
        try:
            parsed_json = json.loads(text)
        except json.JSONDecodeError as exc:
            checks["attributes_complete"] = False
            log(f"canary: {key} response is not valid JSON: {exc}")
            continue
        issues = compiled.validate_response(parsed_json)
        if issues:
            checks["attributes_complete"] = False
            log(f"canary: {key} validation issues: {issues[:5]}")
        doc_text = docs[key_index[key]["doc_id"]].text
        for cls_name in compiled.classes:
            for item in parsed_json.get(cls_name) or []:
                quote = item.get("source_quote") or ""
                if quote and align_quote(quote, doc_text, hint=key_index[key]["window_start"]):
                    checks["quote_aligned"] = True

    passed = n_responses == len(canary_lines) and all(checks.values())
    report = {"tag": tag, "job": job.name, "state": state, "n_responses": n_responses, **checks, "passed": passed}
    (rdir / f"{tag}.canary.json").write_text(json.dumps(report, indent=2))
    log(f"canary: {report}")
    return passed
