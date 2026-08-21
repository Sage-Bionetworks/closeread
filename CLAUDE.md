# closeread — build

The specification is `/Users/ataylor/Documents/projects/htan2/htan-pubs-fulltext/closeread-design.md`.
Read §3 (six measured prototype failures) before changing extraction, batch, or
vocabulary code. That reference folder is read-only: read its data artifacts,
never write there, never port its code.

Rules that gate every change:
- Every shipped record has a verbatim quotation + character offsets (rule 6.1).
- Regex candidates never decide meaning (rule / §3.2).
- Canary before every fan-out; `--dry-run` before every spend (rules 6.8, 6.9).
- Gemini batch requests use camelCase `generationConfig` (§3.3) — guarded by a test.
- Prompt, response schema, and validator all compile from one pass YAML (rule 6.10).
- Never delete records; status fields instead (rule 6.6).
- §15 numbers are prototype measurements, not results — never copy them into outputs.

Use `uv run` for everything (`uv run pytest`, `uv run closeread ...`).
Credentials: `GEMINI_API_KEY` in `.env` (gitignored), AWS profile `htan-dev`
for requester-pays buckets. Never commit either.
