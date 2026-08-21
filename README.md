# closeread

closeread reads the full text of scientific publications and extracts
structured facts about how a research consortium built its datasets and how
other researchers reused them — and every extracted fact is tied to a verbatim
quotation with character offsets in the source document. It does **not** count
citations, match keywords as meaning, or report any number that cannot be
traced to a quotation. Regular-expression matches only locate text; a model
decides meaning, and a second model judges it.

HTAN is the first community. Community specifics live in `communities/*.yaml`.

## Pipeline

```
acquire → parse → candidates → extract → collect → normalise → judge → report
```

Each stage reads files and writes files, runs alone, and is idempotent.
Layers: `raw` (immutable) → `bronze` (aligned records) → `silver` (normalised,
judged) → `gold` (flat CSVs, one per class and figure).

## Quick start

```bash
uv sync
echo 'GEMINI_API_KEY=...' > .env
uv run closeread acquire --community htan
uv run closeread parse   --community htan
uv run closeread extract --community htan --pass availability --dry-run
uv run closeread extract --community htan --pass availability   # canary gates the fan-out
uv run closeread collect --run <run_id>
uv run closeread report  --runs <run_id>
```

Every submitting command supports `--dry-run` (request count and cost
estimate) and is gated by a two-request canary through the real batch path.

See `docs/` for credentials, pass definitions, and adding a community. The
full design specification lives outside this repo (see `CLAUDE.md`).
