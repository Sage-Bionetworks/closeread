"""Quotation alignment. A record without character offsets is never written to
records (spec §5.6). Alignment is deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from closeread.models import AlignmentStatus


@dataclass(frozen=True)
class Alignment:
    start: int
    end: int
    status: AlignmentStatus


def _flexible_pattern(quote: str) -> re.Pattern[str]:
    """Whitespace-tolerant pattern: tokens escaped, gaps match any whitespace.
    Also tolerates straight/curly quote and hyphen/dash variants."""
    tokens = quote.split()
    escaped = []
    for tok in tokens:
        e = re.escape(tok)
        e = e.replace(r"'", "['‘’]").replace(r"\"", "[\"“”]")
        e = e.replace(r"\-", "[-‐‑‒–—]")
        escaped.append(e)
    return re.compile(r"\s+".join(escaped))


def _pick_nearest(matches: list[tuple[int, int]], hint: int | None) -> tuple[int, int]:
    if hint is None or len(matches) == 1:
        return matches[0]
    return min(matches, key=lambda m: abs(m[0] - hint))


def align_quote(quote: str, text: str, hint: int | None = None) -> Alignment | None:
    """Locate a quotation in text. Exact, then whitespace-tolerant, then
    case-insensitive. None when the quotation does not appear: the record is
    rejected, never shipped."""
    quote = quote.strip()
    if not quote:
        return None

    matches = [(m, m + len(quote)) for m in _find_all(text, quote)]
    if matches:
        start, end = _pick_nearest(matches, hint)
        return Alignment(start, end, AlignmentStatus.match_exact)

    pattern = _flexible_pattern(quote)
    fuzzy = [(m.start(), m.end()) for m in pattern.finditer(text)]
    if fuzzy:
        start, end = _pick_nearest(fuzzy, hint)
        return Alignment(start, end, AlignmentStatus.match_fuzzy)

    ci = [(m.start(), m.end()) for m in re.compile(pattern.pattern, re.IGNORECASE).finditer(text)]
    if ci:
        start, end = _pick_nearest(ci, hint)
        return Alignment(start, end, AlignmentStatus.match_lesser)

    return None


def _find_all(text: str, needle: str) -> list[int]:
    out: list[int] = []
    i = text.find(needle)
    while i != -1:
        out.append(i)
        i = text.find(needle, i + 1)
    return out
