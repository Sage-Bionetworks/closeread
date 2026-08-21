from closeread.parse.jats import ParsedDocument, parse_jats
from closeread.parse.sections import SectionIndex, SectionSpan, classify_heading
from closeread.parse.chunking import Window, make_windows

__all__ = [
    "ParsedDocument",
    "parse_jats",
    "SectionIndex",
    "SectionSpan",
    "classify_heading",
    "Window",
    "make_windows",
    "run_parse",
    "load_parsed",
]


def run_parse(config, settings, log=print) -> dict[str, int]:
    """Stage 2: parse every fetched XML into text + section index files.

    Reads out/<community>/documents.jsonl and raw/fulltext/, writes one JSON
    per document under out/<community>/parsed/. Idempotent. XML that fails to
    parse is logged, skipped, and counted (spec §9.5).
    """
    import json

    from closeread.jsonl import read_jsonl

    out_dir = settings.community_dir(config.community)
    parsed_dir = out_dir / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    fulltext_dir = out_dir / "raw" / "fulltext"

    counts = {"parsed": 0, "skipped_no_fulltext": 0, "failed": 0, "cached": 0}
    for doc in read_jsonl(out_dir / "documents.jsonl"):
        if doc.get("oa_status") != "fulltext" or not doc.get("pmcid"):
            counts["skipped_no_fulltext"] += 1
            continue
        dest = parsed_dir / f"{doc['doc_id']}.json"
        if dest.exists():
            counts["cached"] += 1
            continue
        xml_path = fulltext_dir / f"{doc['pmcid']}.{doc['source_version']}.xml"
        try:
            parsed = parse_jats(xml_path.read_bytes())
        except Exception as exc:  # parse failure: log, skip, count
            log(f"parse failed for {doc['doc_id']} ({xml_path.name}): {exc}")
            counts["failed"] += 1
            continue
        dest.write_text(
            json.dumps(
                {
                    "doc_id": doc["doc_id"],
                    "doc_title": parsed.doc_title,
                    "text": parsed.text,
                    "sections": [
                        {"labels": list(s.labels), "title": s.title, "start": s.start, "end": s.end}
                        for s in parsed.sections.spans
                    ],
                },
                ensure_ascii=False,
            )
        )
        counts["parsed"] += 1
    log(f"parse: {counts}")
    return counts


def load_parsed(path) -> "ParsedDocument":
    """Read one parsed/<doc_id>.json back into a ParsedDocument."""
    import json

    data = json.loads(open(path).read())
    index = SectionIndex()
    for s in data["sections"]:
        index.add(s["labels"], s["title"], s["start"], s["end"])
    return ParsedDocument(doc_title=data.get("doc_title"), text=data["text"], sections=index)
