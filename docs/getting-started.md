# Getting started

## Install

```bash
uv sync
```

Python 3.11+. All commands run through `uv run`.

## Credentials

| Credential | Used by | Setup |
|---|---|---|
| `GEMINI_API_KEY` | extract, collect, normalise, judge | put `GEMINI_API_KEY=...` in `.env` at the repo root (gitignored). Never commit it. |
| AWS profile `htan-dev` | citing-preprint acquisition (tier C, requester-pays bioRxiv/medRxiv buckets) | `aws sso login --profile htan-dev` |

The PMC bucket (tier B) is unsigned; corpus acquisition needs no AWS login.

## One complete run of the cheapest pass

```bash
uv run closeread acquire --community htan     # OpenAlex + PMC full text (free)
uv run closeread parse   --community htan     # JATS -> text + section index (free)

# Always dry-run first (rule 6.8):
uv run closeread extract --community htan --pass availability --dry-run

# Submit. A two-request canary through the real batch path gates the fan-out
# (rule 6.9). With the small model this costs about 0.4 USD:
uv run closeread extract --community htan --pass availability --model gemini-3.1-flash-lite

uv run closeread status  --run <run_id>       # poll until SUCCEEDED
uv run closeread collect --run <run_id>       # align quotes, write bronze records
uv run closeread report  --runs <run_id>      # gold tables + F7
```

Outputs land under `out/htan/`: `documents.jsonl`, `parsed/`, `runs/`
(handoffs + summaries), `raw/batch/` (immutable responses),
`bronze/records_*.jsonl`, `gold/*.csv`, and `out/report/figures/`.
