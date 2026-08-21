"""Gemini batch submission. Spec §5.5, §3.3.

Request configuration uses camelCase keys (`generationConfig`,
`responseMimeType`, `responseSchema`, `maxOutputTokens`). The batch REST
endpoint SILENTLY IGNORES snake_case keys — this cost the prototype ~21 USD
(§3.3). A unit test locks the casing.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closeread.config import Settings, gemini_api_key
from closeread.extract.compile import CompiledPass
from closeread.parse import ParsedDocument, make_windows

STRONG_MODEL = "gemini-3.1-pro-preview"
SMALL_MODEL = "gemini-3.1-flash-lite"

# Batch rates, USD per million tokens (input, output). Spec §14; verify before running.
RATES = {
    STRONG_MODEL: (1.00, 6.00),
    SMALL_MODEL: (0.125, 0.75),
}
CHARS_PER_TOKEN = 4.15  # structural, §15
EST_OUTPUT_TOKENS_PER_REQUEST = 400  # corrected prototype run measured ~350


def generation_config(compiled: CompiledPass) -> dict[str, Any]:
    return {
        "responseMimeType": "application/json",
        "responseSchema": compiled.response_schema(),
        "temperature": 0,
        "maxOutputTokens": 16384,
    }


def request_key(doc_id: str, window_index: int, window_start: int) -> str:
    return f"{doc_id}|{window_index}|{window_start}"


def build_requests(
    compiled: CompiledPass,
    docs: dict[str, ParsedDocument],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """One request per (document, window). Returns (request lines, key index)."""
    config = generation_config(compiled)
    lines: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for doc_id, parsed in docs.items():
        for window in make_windows(len(parsed.text), compiled.window_chars):
            key = request_key(doc_id, window.index, window.start)
            prompt = compiled.prompt(window.slice(parsed.text))
            lines.append(
                {
                    "key": key,
                    "request": {
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": config,
                    },
                }
            )
            index[key] = {
                "doc_id": doc_id,
                "window_index": window.index,
                "window_start": window.start,
                "window_end": window.end,
            }
    return lines, index


@dataclass
class CostEstimate:
    n_requests: int
    est_tokens_in: int
    est_tokens_out: int
    est_cost_usd: float

    def describe(self) -> str:
        return (
            f"requests: {self.n_requests}  est input tokens: {self.est_tokens_in:,}  "
            f"est output tokens: {self.est_tokens_out:,}  est cost: ${self.est_cost_usd:.2f}"
        )


def estimate(lines: list[dict[str, Any]], model: str) -> CostEstimate:
    rate_in, rate_out = RATES.get(model, RATES[STRONG_MODEL])
    chars = sum(len(l["request"]["contents"][0]["parts"][0]["text"]) for l in lines)
    tokens_in = int(chars / CHARS_PER_TOKEN)
    tokens_out = EST_OUTPUT_TOKENS_PER_REQUEST * len(lines)
    cost = (tokens_in * rate_in + tokens_out * rate_out) / 1e6
    return CostEstimate(len(lines), tokens_in, tokens_out, cost)


_CLIENT = None


def _client():
    """Module-cached client: a temporary Client can be garbage-collected
    mid-call, closing its httpx session under retry."""
    global _CLIENT
    if _CLIENT is None:
        from google import genai

        _CLIENT = genai.Client(api_key=gemini_api_key())
    return _CLIENT


def runs_dir(settings: Settings, community: str) -> Path:
    return settings.community_dir(community) / "runs"


def next_run_id(settings: Settings, community: str, pass_name: str) -> str:
    """{community}_{pass}_{YYYYMMDD}_{NNN}, unique per §8.2."""
    date = dt.date.today().strftime("%Y%m%d")
    prefix = f"{community}_{pass_name}_{date}_"
    existing = [p.stem.removesuffix(".handoff") for p in runs_dir(settings, community).glob(f"{prefix}*.handoff.json")]
    ns = [int(e.rsplit("_", 1)[-1]) for e in existing if e.rsplit("_", 1)[-1].isdigit()]
    return f"{prefix}{(max(ns) + 1 if ns else 1):03d}"


def submit(
    lines: list[dict[str, Any]],
    key_index: dict[str, dict[str, Any]],
    run_id: str,
    model: str,
    compiled: CompiledPass,
    settings: Settings,
    community: str,
    canary_passed: bool,
) -> dict[str, Any]:
    """Upload the request JSONL, create the batch job, write the handoff. Stop.

    The stage does not wait for the job (spec §5.5).
    """
    from google.genai import types

    rdir = runs_dir(settings, community)
    rdir.mkdir(parents=True, exist_ok=True)
    input_path = rdir / f"{run_id}.requests.jsonl"
    with open(input_path, "w") as fh:
        for line in lines:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    client = _client()
    uploaded = client.files.upload(
        file=str(input_path),
        config=types.UploadFileConfig(display_name=run_id, mime_type="application/jsonl"),
    )
    job = client.batches.create(
        model=model,
        src=uploaded.name,
        config=types.CreateBatchJobConfig(display_name=run_id),
    )
    est = estimate(lines, model)
    handoff = {
        "run_id": run_id,
        "community": community,
        "pass_name": compiled.name,
        "model": model,
        "prompt_version": compiled.version,
        "schema_version": compiled.version,
        "submitted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_requests": len(lines),
        "est_tokens_in": est.est_tokens_in,
        "est_tokens_out": est.est_tokens_out,
        "cost_estimate": est.est_cost_usd,
        "canary_passed": canary_passed,
        "batch_job_name": job.name,
        "input_file": str(input_path),
        "uploaded_file": uploaded.name,
        "sections_read": compiled.sections,
        "key_index": key_index,
    }
    handoff_path = rdir / f"{run_id}.handoff.json"
    handoff_path.write_text(json.dumps(handoff, indent=2))
    return handoff


def find_handoff(run_id: str, settings: Settings) -> Path:
    hits = list(settings.out_dir.glob(f"*/runs/{run_id}.handoff.json"))
    if not hits:
        raise FileNotFoundError(f"no handoff file for run {run_id}")
    return hits[0]


def get_job(batch_job_name: str):
    return _client().batches.get(name=batch_job_name)


def job_state(job) -> str:
    state = getattr(job, "state", None)
    return getattr(state, "name", str(state))


def print_status(run_id: str, settings: Settings) -> None:
    handoff = json.loads(find_handoff(run_id, settings).read_text())
    job = get_job(handoff["batch_job_name"])
    print(f"{run_id}: {job_state(job)}  (job {handoff['batch_job_name']})")


def download_responses(handoff: dict[str, Any], dest: Path) -> Path:
    """Download batch results to the raw layer. Immutable once written."""
    if dest.exists():
        return dest
    client = _client()
    job = client.batches.get(name=handoff["batch_job_name"])
    state = job_state(job)
    if "SUCCEEDED" not in state:
        raise RuntimeError(f"batch job state is {state}; collect refuses to run (spec §9.5)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload: bytes | None = None
    dest_info = getattr(job, "dest", None)
    file_name = getattr(dest_info, "file_name", None)
    if file_name:
        payload = client.files.download(file=file_name)
    if payload is not None:
        dest.write_bytes(payload)
    else:
        inlined = getattr(dest_info, "inlined_responses", None) or []
        with open(dest, "w") as fh:
            for r in inlined:
                fh.write(json.dumps(r.model_dump() if hasattr(r, "model_dump") else r) + "\n")
    return dest


def iter_responses(path: Path):
    """Yield (key, finish_reason, text, usage) per response line."""
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            key = data.get("key") or data.get("custom_id") or ""
            response = data.get("response") or {}
            candidates = response.get("candidates") or []
            finish = candidates[0].get("finishReason") if candidates else None
            parts = (candidates[0].get("content") or {}).get("parts") if candidates else None
            text = "".join(p.get("text", "") for p in parts or [])
            usage = response.get("usageMetadata") or {}
            yield key, finish, text, usage
