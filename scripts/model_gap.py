"""§14.2: measure the small-vs-strong gap on the 500-document citing sample.

Compares each pass's strong-model sample run against the small-model full run
restricted to the same documents. Span match: same doc, same class,
overlapping character range. Prints per-pass and per-class recall of the small
model against the strong model, and vice versa.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from closeread.config import Settings
from closeread.jsonl import read_jsonl

PAIRS = [  # (strong sample run, small full run)
    ("htan_availability_20260821_004", "htan_availability_20260821_003"),
    ("htan_measurement_20260821_004", "htan_measurement_20260821_003"),
    ("htan_analysis_20260821_004", "htan_analysis_20260821_003"),
]

settings = Settings()
out = settings.community_dir("htan")


def load(run_id: str, docs: set[str] | None = None) -> dict[tuple[str, str], list[tuple[int, int]]]:
    spans: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for r in read_jsonl(out / "bronze" / f"records_{run_id}.jsonl"):
        if not r["source_quote"]:
            continue
        if docs is not None and r["doc_id"] not in docs:
            continue
        spans[(r["doc_id"], r["extraction_class"])].append((r["char_start"], r["char_end"]))
    return spans


def covered(span: tuple[int, int], others: list[tuple[int, int]]) -> bool:
    s, e = span
    return any(os < e and s < oe for os, oe in others)


report: dict[str, dict] = {}
for strong_run, small_run in PAIRS:
    handoff = json.loads((out / "runs" / f"{strong_run}.handoff.json").read_text())
    sample_docs = {i["doc_id"] for i in handoff["key_index"].values()}
    strong = load(strong_run)
    small = load(small_run, docs=sample_docs)

    classes = sorted({k[1] for k in strong} | {k[1] for k in small})
    pass_name = handoff["pass_name"]
    report[pass_name] = {"n_sample_docs": len(sample_docs), "classes": {}}
    for cls in classes:
        s_spans = [(k[0], sp) for k, v in strong.items() if k[1] == cls for sp in v]
        m_spans = [(k[0], sp) for k, v in small.items() if k[1] == cls for sp in v]
        small_by_doc = defaultdict(list)
        for d, sp in m_spans:
            small_by_doc[d].append(sp)
        strong_by_doc = defaultdict(list)
        for d, sp in s_spans:
            strong_by_doc[d].append(sp)
        strong_covered = sum(1 for d, sp in s_spans if covered(sp, small_by_doc.get(d, [])))
        small_covered = sum(1 for d, sp in m_spans if covered(sp, strong_by_doc.get(d, [])))
        report[pass_name]["classes"][cls] = {
            "strong_records": len(s_spans),
            "small_records": len(m_spans),
            "small_recall_vs_strong": round(strong_covered / len(s_spans), 3) if s_spans else None,
            "strong_recall_vs_small": round(small_covered / len(m_spans), 3) if m_spans else None,
        }

print(json.dumps(report, indent=2))
dest = out / "model_gap_500_sample.json"
dest.write_text(json.dumps(report, indent=2))
print(f"-> {dest}", file=sys.stderr)
