"""Preprint deduplication (§5.2) and author overlap (§5.2.1).

Dedup match rule: normalise the title (lowercase, remove non-alphanumeric,
truncate to 90 characters); two works match if normalised titles are equal and
at least one of DOI prefix or first-author surname also matches. Keep the
published version; record the collapsed Work ID in `merged_from`.

Author overlap is an exact OpenAlex author-ID intersection. Never match on
names: initials collide ("Santagata S").
"""

from __future__ import annotations

import re
from typing import Any

from closeread.models import AuthorOverlap

_NON_ALNUM = re.compile(r"[^a-z0-9]")

PREPRINT_TYPES = {"preprint"}
PREPRINT_DOI_PREFIXES = {"10.1101", "10.21203", "10.2139"}  # bioRxiv/medRxiv, Research Square, SSRN


def normalise_title(title: str | None) -> str:
    if not title:
        return ""
    return _NON_ALNUM.sub("", title.lower())[:90]


def doi_prefix(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.split("/", 1)[0]


def is_preprint(work: dict[str, Any]) -> bool:
    if work.get("work_type") in PREPRINT_TYPES:
        return True
    prefix = doi_prefix(work.get("doi"))
    return prefix in PREPRINT_DOI_PREFIXES


def dedup_preprints(works: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Collapse preprint/published pairs. Input rows are work_summary dicts
    (plus anything else); returns (kept rows, n merged). Kept published rows
    gain merged_from listing the collapsed preprint Work IDs and the union of
    author ids."""
    published: dict[str, list[dict[str, Any]]] = {}
    for w in works:
        if not is_preprint(w):
            published.setdefault(normalise_title(w.get("title")), []).append(w)

    kept: list[dict[str, Any]] = []
    n_merged = 0
    for w in works:
        if not is_preprint(w):
            kept.append(w)
            continue
        candidates = published.get(normalise_title(w.get("title")), []) if normalise_title(w.get("title")) else []
        match = None
        for c in candidates:
            same_prefix = doi_prefix(w.get("doi")) == doi_prefix(c.get("doi"))
            same_surname = (
                w.get("first_author_surname")
                and w.get("first_author_surname") == c.get("first_author_surname")
            )
            if same_prefix or same_surname:
                match = c
                break
        if match is None:
            kept.append(w)  # orphan preprint: stays in the set
            continue
        n_merged += 1
        match.setdefault("merged_from", []).append(w["doc_id"])
        match["author_ids"] = sorted(set(match.get("author_ids") or []) | set(w.get("author_ids") or []))
    return kept, n_merged


def classify_author_overlap(
    citing: dict[str, Any],
    corpus_doc_ids: set[str],
    corpus_author_ids: set[str],
) -> dict[str, Any]:
    """author_overlap, n_shared_authors, shared_author_ids for one citing work."""
    if citing["doc_id"] in corpus_doc_ids:
        overlap = AuthorOverlap.is_corpus_document
        shared = sorted(set(citing.get("author_ids") or []) & corpus_author_ids)
    else:
        shared = sorted(set(citing.get("author_ids") or []) & corpus_author_ids)
        if not shared:
            overlap = AuthorOverlap.external
        elif set(citing.get("first_last_author_ids") or []) & corpus_author_ids:
            overlap = AuthorOverlap.shared_senior_author
        else:
            overlap = AuthorOverlap.shared_author
    return {
        "author_overlap": overlap.value,
        "n_shared_authors": len(shared),
        "shared_author_ids": shared,
    }
