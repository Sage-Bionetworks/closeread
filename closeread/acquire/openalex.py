"""OpenAlex metadata acquisition. Spec §5.1.

Captures authorships[].author.id and institution ids for every work at fetch
time — they are needed for author overlap (§5.2.1) and are not recoverable
later without re-querying.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from typing import Any

import httpx

OPENALEX = "https://api.openalex.org"

WORK_FIELDS = (
    "id,doi,title,publication_year,publication_date,type,ids,"
    "primary_location,authorships,abstract_inverted_index"
)

RETRYABLE = {429, 500, 502, 503, 504}


def _get_json(client: httpx.Client, url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET with exponential backoff: five attempts on 429/5xx (spec §9.5)."""
    delay = 1.0
    for attempt in range(5):
        try:
            resp = client.get(url, params=params, timeout=60)
        except httpx.TransportError:
            if attempt == 4:
                raise
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code in RETRYABLE:
            if attempt == 4:
                resp.raise_for_status()
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("unreachable")


def _client(mailto: str) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": f"closeread (mailto:{mailto})"})


def works_by_filter(filter_expr: str, mailto: str, per_page: int = 200) -> Iterator[dict[str, Any]]:
    """Iterate all works matching an OpenAlex filter, cursor-paginated."""
    cursor = "*"
    with _client(mailto) as client:
        while cursor:
            page = _get_json(
                client,
                f"{OPENALEX}/works",
                {
                    "filter": filter_expr,
                    "per-page": per_page,
                    "cursor": cursor,
                    "select": WORK_FIELDS,
                    "mailto": mailto,
                },
            )
            yield from page.get("results", [])
            cursor = page.get("meta", {}).get("next_cursor")


def works_by_pmids(pmids: Iterable[str], mailto: str) -> dict[str, dict[str, Any]]:
    """Resolve PMIDs to OpenAlex works. Returns {pmid: work}."""
    pmids = [p for p in pmids if p]
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(pmids), 50):
        batch = pmids[i : i + 50]
        for work in works_by_filter("pmid:" + "|".join(batch), mailto):
            pmid = _short_pmid(work.get("ids", {}).get("pmid"))
            if pmid:
                out[pmid] = work
    return out


def works_by_dois(dois: Iterable[str], mailto: str) -> dict[str, dict[str, Any]]:
    dois = [d for d in dois if d]
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(dois), 50):
        batch = dois[i : i + 50]
        for work in works_by_filter("doi:" + "|".join(batch), mailto):
            doi = _short_doi(work.get("doi"))
            if doi:
                out[doi] = work
    return out


def citing_works(work_id: str, mailto: str) -> Iterator[dict[str, Any]]:
    yield from works_by_filter(f"cites:{work_id}", mailto)


def _short_pmid(url: str | None) -> str | None:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else None


def _short_doi(url: str | None) -> str | None:
    if not url:
        return None
    return url.removeprefix("https://doi.org/").lower()


def short_id(openalex_url: str) -> str:
    """https://openalex.org/W123 -> W123"""
    return openalex_url.rstrip("/").rsplit("/", 1)[-1]


def reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for token, idxs in inverted.items():
        positions.extend((i, token) for i in idxs)
    positions.sort()
    return " ".join(tok for _, tok in positions) or None


def work_summary(work: dict[str, Any]) -> dict[str, Any]:
    """Flatten an OpenAlex work into the fields `documents.jsonl` needs."""
    ids = work.get("ids", {}) or {}
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    authorships = work.get("authorships") or []
    author_ids = [short_id(a["author"]["id"]) for a in authorships if a.get("author", {}).get("id")]
    first_last_ids = [
        short_id(a["author"]["id"])
        for a in authorships
        if a.get("author", {}).get("id") and a.get("author_position") in ("first", "last")
    ]
    institution_ids = sorted(
        {
            short_id(inst["id"])
            for a in authorships
            for inst in a.get("institutions") or []
            if inst.get("id")
        }
    )
    return {
        "doc_id": short_id(work["id"]),
        "doi": _short_doi(work.get("doi")),
        "pmid": _short_pmid(ids.get("pmid")),
        "pmcid": _short_pmcid(ids.get("pmcid")),
        "title": work.get("title"),
        "pub_date": work.get("publication_date"),
        "venue": source.get("display_name"),
        "work_type": work.get("type"),
        "author_ids": author_ids,
        "first_last_author_ids": first_last_ids,
        "institution_ids": institution_ids,
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "first_author_surname": _first_author_surname(authorships),
    }


def _short_pmcid(url: str | None) -> str | None:
    if not url:
        return None
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return tail if tail.startswith("PMC") else f"PMC{tail}"


def _first_author_surname(authorships: list[dict[str, Any]]) -> str | None:
    for a in authorships:
        if a.get("author_position") == "first":
            name = (a.get("author") or {}).get("display_name") or ""
            return name.split()[-1].lower() if name else None
    return None
