"""Section labelling and the section index. Spec §5.3.

A heading that names both data and code (for example "Data and code
availability") receives both labels. Nested availability sections take
priority over the enclosing section, implemented here as narrowest-span-wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

LABELS = (
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "data_availability",
    "code_availability",
    "other",
)

# Availability is checked independently of the exclusive labels so that a
# combined heading collects both labels (spec §5.3.3).
_DATA_AVAIL = re.compile(
    r"(\bdata\b[^.]{0,40}\bavailab|\bavailab[^.]{0,40}\bdata\b"
    r"|\bdata\s+(access|sharing|deposition)|\baccession\s+(number|code)s?\b)",
    re.IGNORECASE,
)
_CODE_AVAIL = re.compile(
    r"(\b(code|software)\b[^.]{0,40}\bavailab|\bavailab[^.]{0,40}\b(code|software)\b)",
    re.IGNORECASE,
)

# Exclusive labels, first match wins among these only.
_EXCLUSIVE = [
    ("methods", re.compile(
        r"(\bmethods?\b|\bexperimental\s+procedures\b|\bmaterials\b|\bstar\W*methods\b|\bonline\s+methods\b)",
        re.IGNORECASE)),
    ("results", re.compile(r"\bresults?\b|\bfindings\b", re.IGNORECASE)),
    ("discussion", re.compile(r"\bdiscussion\b|\bconclusions?\b", re.IGNORECASE)),
    ("introduction", re.compile(r"\bintroduction\b|\bbackground\b", re.IGNORECASE)),
    ("abstract", re.compile(r"\babstract\b", re.IGNORECASE)),
]

# JATS sec-type attribute values seen in PMC.
_SEC_TYPE_MAP = {
    "data-availability": ["data_availability"],
    "code-availability": ["code_availability"],
    "materials|methods": ["methods"],
    "methods": ["methods"],
    "results": ["results"],
    "discussion": ["discussion"],
    "intro": ["introduction"],
    "conclusions": ["discussion"],
}


def classify_heading(title: str | None, sec_type: str | None = None) -> list[str]:
    """Return zero or more labels for a heading. Empty list means unclassified."""
    labels: list[str] = []
    if sec_type and sec_type.lower() in _SEC_TYPE_MAP:
        labels.extend(_SEC_TYPE_MAP[sec_type.lower()])
    if title:
        if _DATA_AVAIL.search(title) and "data_availability" not in labels:
            labels.append("data_availability")
        if _CODE_AVAIL.search(title) and "code_availability" not in labels:
            labels.append("code_availability")
        if not labels:
            for label, pattern in _EXCLUSIVE:
                if pattern.search(title):
                    labels.append(label)
                    break
    return labels


@dataclass(frozen=True)
class SectionSpan:
    labels: tuple[str, ...]
    title: str
    start: int
    end: int

    def __len__(self) -> int:
        return self.end - self.start


@dataclass
class SectionIndex:
    """Maps character ranges to section labels. Narrowest span wins (§5.3.4)."""

    spans: list[SectionSpan] = field(default_factory=list)

    def add(self, labels: list[str] | tuple[str, ...], title: str, start: int, end: int) -> None:
        self.spans.append(SectionSpan(tuple(labels), title, start, end))

    def spans_at(self, offset: int) -> list[SectionSpan]:
        covering = [s for s in self.spans if s.start <= offset < s.end]
        covering.sort(key=len)
        return covering

    def labels_at(self, offset: int) -> tuple[str, ...]:
        covering = self.spans_at(offset)
        return covering[0].labels if covering else ()

    def section_at(self, offset: int) -> str:
        labels = self.labels_at(offset)
        return labels[0] if labels else "unknown"

    def shares(self, text_length: int) -> dict[str, float]:
        """Share of text per label, using each offset's narrowest span."""
        counts: dict[str, int] = {}
        # Compute over span boundaries rather than per character.
        boundaries = sorted({0, text_length, *(s.start for s in self.spans), *(s.end for s in self.spans)})
        for lo, hi in zip(boundaries, boundaries[1:]):
            label = self.section_at(lo)
            counts[label] = counts.get(label, 0) + (hi - lo)
        return {k: v / text_length for k, v in counts.items()} if text_length else {}
