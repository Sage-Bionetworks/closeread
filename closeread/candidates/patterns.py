"""Stage 3: candidates. Regular-expression matches over parsed text.

Candidates locate text and measure extractor recall. Candidates never decide
meaning (§3.2): 46 of 80 accessions in the prototype never appeared in an
availability section, and the verb — not the pattern — decides release vs
acquisition. No software or platform name lists (§3.6).
"""

from __future__ import annotations

import re

from closeread.config import CommunityConfig
from closeread.models import Candidate
from closeread.parse import ParsedDocument

# Repository/portal URL patterns are community-independent in shape; the
# community config contributes its accession patterns and portal hosts.
_GENERIC_URL_PATTERNS = {
    "github_url": r"https?://(?:www\.)?github\.com/[\w.\-]+(?:/[\w.\-]+)?",
    "zenodo_url": r"https?://(?:www\.)?(?:doi\.org/10\.5281/zenodo\.\d+|zenodo\.org/records?/\d+)",
}


def compile_patterns(config: CommunityConfig) -> dict[str, re.Pattern[str]]:
    patterns: dict[str, str] = dict(config.accession_patterns)
    patterns.update(_GENERIC_URL_PATTERNS)
    for host in config.portals:
        key = f"portal_{host.split('.')[0]}"
        patterns[key] = rf"https?://{re.escape(host)}[\w\-./%?=&#]*|\b{re.escape(host)}\b"
    return {kind: re.compile(pat) for kind, pat in patterns.items()}


def find_candidates(
    doc_id: str, parsed: ParsedDocument, patterns: dict[str, re.Pattern[str]]
) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[tuple[str, int, int]] = set()
    for kind, pattern in patterns.items():
        for m in pattern.finditer(parsed.text):
            key = (kind, m.start(), m.end())
            if key in seen:
                continue
            seen.add(key)
            out.append(
                Candidate(
                    doc_id=doc_id,
                    kind=kind,
                    value=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    section=parsed.sections.section_at(m.start()),
                )
            )
    out.sort(key=lambda c: (c.char_start, c.kind))
    return out


def uncovered_candidates(
    candidates: list[dict], records: list[dict]
) -> list[dict]:
    """Candidate spans no record covers: possible extraction misses (§5.4).
    Count these and report the count."""
    spans_by_doc: dict[str, list[tuple[int, int]]] = {}
    for r in records:
        if r.get("source_quote"):
            spans_by_doc.setdefault(r["doc_id"], []).append((r["char_start"], r["char_end"]))
    misses = []
    for c in candidates:
        covered = any(
            s <= c["char_start"] and c["char_end"] <= e
            for s, e in spans_by_doc.get(c["doc_id"], [])
        )
        if not covered:
            misses.append(c)
    return misses
