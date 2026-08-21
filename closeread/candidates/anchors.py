"""Anchor windows for the provenance pass. Spec §4.2.3, §7.3.

Reading whole citing documents for consortium-specific claims gave 57 percent
attribution precision in the prototype: the model attributed any reuse in the
document to the consortium. The provenance pass therefore reads only text near
an anchor. Anchors are of three kinds:

1. a citation marker resolving to a corpus document (via the JATS ref-list),
2. a community identity string ("HTAN"),
3. an accession identifier that the corpus itself released, or a
   community-specific accession pattern.

This is proximity scoping, not section scoping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from closeread.candidates.patterns import compile_patterns
from closeread.config import CommunityConfig
from closeread.parse import ParsedDocument

# Community-specific accession kinds anchor on their own; generic accessions
# (GEO, SRA) anchor only when the corpus itself released the value.
COMMUNITY_KINDS_HINT = ("synapse", "dbgap", "internal")


@dataclass(frozen=True)
class Anchor:
    start: int
    end: int
    kind: str  # citation_marker | identity_string | accession


def identity_anchors(text: str, config: CommunityConfig) -> list[Anchor]:
    out = []
    for s in config.identity_strings:
        for m in re.finditer(re.escape(s), text):
            out.append(Anchor(m.start(), m.end(), "identity_string"))
    return out


def accession_anchors(
    text: str, config: CommunityConfig, corpus_accessions: set[str]
) -> list[Anchor]:
    out = []
    for kind, pattern in compile_patterns(config).items():
        community_specific = kind in COMMUNITY_KINDS_HINT or kind.startswith("portal_")
        for m in pattern.finditer(text):
            if community_specific or m.group(0) in corpus_accessions:
                out.append(Anchor(m.start(), m.end(), "accession"))
    return out


def _ref_identifiers(article: etree._Element) -> dict[str, dict[str, str]]:
    """ref-list id -> {doi, pmid} before the ref-list is stripped."""
    refs: dict[str, dict[str, str]] = {}
    for ref in article.iter("ref"):
        rid = ref.get("id")
        if not rid:
            continue
        ids: dict[str, str] = {}
        for pub_id in ref.iter("pub-id"):
            t = (pub_id.get("pub-id-type") or "").lower()
            v = (pub_id.text or "").strip()
            if t == "doi" and v:
                ids["doi"] = v.lower().removeprefix("https://doi.org/")
            elif t == "pmid" and v:
                ids["pmid"] = v
        if ids:
            refs[rid] = ids
    return refs


def citation_anchors(
    xml_path: Path,
    parsed: ParsedDocument,
    corpus_dois: set[str],
    corpus_pmids: set[str],
) -> list[Anchor]:
    """Positions of citation markers whose reference resolves to a corpus
    document. The xref's containing paragraph is located in the parsed text;
    exact-marker position within the paragraph is best-effort."""
    parser = etree.XMLParser(huge_tree=True, recover=True, remove_comments=True)
    root = etree.fromstring(xml_path.read_bytes(), parser=parser)
    if root is None:
        return []
    article = root if etree.QName(root).localname == "article" else root.find(".//article")
    if article is None:
        return []
    refs = _ref_identifiers(article)
    corpus_rids = {
        rid
        for rid, ids in refs.items()
        if ids.get("doi") in corpus_dois or ids.get("pmid") in corpus_pmids
    }
    if not corpus_rids:
        return []

    ws = re.compile(r"\s+")
    anchors: list[Anchor] = []
    seen_paragraphs: set[int] = set()
    for xref in article.iter("xref"):
        rids = set((xref.get("rid") or "").split())
        if not (rids & corpus_rids):
            continue
        # Locate the containing paragraph's cleaned text in the parsed text.
        p = xref.getparent()
        while p is not None and etree.QName(p).localname not in ("p", "title"):
            p = p.getparent()
        if p is None:
            continue
        para_text = ws.sub(" ", " ".join(p.itertext())).strip()
        if len(para_text) < 20:
            continue
        pos = parsed.text.find(para_text[:180])
        if pos == -1 or pos in seen_paragraphs:
            continue
        seen_paragraphs.add(pos)
        marker = ws.sub(" ", " ".join(xref.itertext())).strip()
        offset = para_text.find(marker) if marker else -1
        start = pos + (offset if 0 <= offset < 180 else 0)
        anchors.append(Anchor(start, start + max(len(marker), 1), "citation_marker"))
    return anchors


def merge_anchor_windows(
    anchors: list[Anchor], text_length: int, radius: int = 1500
) -> list[tuple[int, int]]:
    """Expand anchors by ±radius and merge overlapping windows."""
    if not anchors:
        return []
    spans = sorted((max(0, a.start - radius), min(text_length, a.end + radius)) for a in anchors)
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged
