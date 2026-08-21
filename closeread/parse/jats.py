"""JATS XML to plain text plus a section index. Spec §5.3.

Requirements implemented here:
1. Reference lists, figures, tables, and formulas are removed before text
   extraction.
2. Every section receives one or more labels from the closed label set.
3. A combined heading ("Data and code availability") receives both labels.
4. Nested availability sections take priority over the enclosing section
   (narrowest-span-wins in the index).
5. Character offsets are stable: ``text[start:end]`` returns the section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from closeread.parse.sections import SectionIndex, classify_heading

DROP_TAGS = (
    "ref-list",
    "table-wrap",
    "table-wrap-group",
    "fig",
    "fig-group",
    "graphic",
    "inline-graphic",
    "inline-formula",
    "disp-formula",
    "tex-math",
    "supplementary-material",
    "media",
)
# `xref` is intentionally kept: citation markers in running text are anchor
# material for the provenance pass (spec §7.3).

_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _element_text(el: etree._Element) -> str:
    return _clean(" ".join(el.itertext()))


@dataclass
class ParsedDocument:
    doc_title: str | None
    text: str
    sections: SectionIndex


class _Builder:
    """Accumulates text chunks separated by blank lines, tracking offsets."""

    SEP = "\n\n"

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.length = 0

    def append(self, chunk: str) -> None:
        chunk = _clean(chunk)
        if not chunk:
            return
        if self.parts:
            self.length += len(self.SEP)
        self.parts.append(chunk)
        self.length += len(chunk)

    @property
    def pos(self) -> int:
        """Offset where the next appended chunk would start."""
        return self.length + (len(self.SEP) if self.parts else 0)

    def text(self) -> str:
        return self.SEP.join(self.parts)


def _sec_title(sec: etree._Element) -> str | None:
    title_el = sec.find("title")
    if title_el is None:
        return None
    return _element_text(title_el) or None


def _process_sec(sec: etree._Element, inherited: tuple[str, ...], builder: _Builder, index: SectionIndex) -> None:
    title = _sec_title(sec)
    sec_type = sec.get("sec-type") or sec.get("notes-type")
    labels = classify_heading(title, sec_type)
    if not labels:
        labels = list(inherited) if inherited else ["other"]

    start = builder.pos
    if title:
        builder.append(title)
    for child in sec:
        tag = etree.QName(child).localname if isinstance(child.tag, str) else None
        if tag in ("sec", "notes"):
            _process_sec(child, tuple(labels), builder, index)
        elif tag == "title":
            continue
        elif tag is not None:
            builder.append(_element_text(child))
    end = builder.length
    if end > start:
        index.add(labels, title or "", start, end)


def parse_jats(xml_bytes: bytes) -> ParsedDocument:
    parser = etree.XMLParser(huge_tree=True, recover=True, remove_comments=True)
    root = etree.fromstring(xml_bytes, parser=parser)
    if root is None:
        raise ValueError("XML did not yield a document")
    article = root if etree.QName(root).localname == "article" else root.find(".//article")
    if article is None:
        raise ValueError("no <article> element found")

    etree.strip_elements(article, *DROP_TAGS, with_tail=False)

    title_el = article.find(".//front//article-title")
    doc_title = _element_text(title_el) if title_el is not None else None

    builder = _Builder()
    index = SectionIndex()

    front = article.find("front")
    if front is not None:
        for abstract in front.iter("abstract"):
            start = builder.pos
            builder.append(_element_text(abstract))
            if builder.length > start:
                index.add(["abstract"], "Abstract", start, builder.length)

    body = article.find("body")
    if body is not None:
        loose_start: int | None = None
        for child in body:
            tag = etree.QName(child).localname if isinstance(child.tag, str) else None
            if tag == "sec":
                if loose_start is not None:
                    index.add(["other"], "", loose_start, builder.length)
                    loose_start = None
                _process_sec(child, (), builder, index)
            elif tag is not None:
                if loose_start is None:
                    loose_start = builder.pos
                builder.append(_element_text(child))
        if loose_start is not None and builder.length > loose_start:
            index.add(["other"], "", loose_start, builder.length)

    back = article.find("back")
    if back is not None:
        for child in back:
            tag = etree.QName(child).localname if isinstance(child.tag, str) else None
            if tag in ("sec", "notes"):
                _process_sec(child, (), builder, index)
            elif tag in ("ack",):
                start = builder.pos
                builder.append(_element_text(child))
                if builder.length > start:
                    index.add(["other"], "Acknowledgements", start, builder.length)

    return ParsedDocument(doc_title=doc_title, text=builder.text(), sections=index)


def parse_jats_file(path: str | Path) -> ParsedDocument:
    return parse_jats(Path(path).read_bytes())


_VERSION_RE = re.compile(r"PMC\d+\.(\d+)\.xml$")


def source_version_from_name(filename: str) -> str | None:
    """PMC<id>.<version>.xml -> version string, for `source_version` (§11.1)."""
    m = _VERSION_RE.search(filename)
    return m.group(1) if m else None
