"""Gold-label sampling and scoring. Spec §5.8 calibration, §11.3.

Candidates provide the sampling frame: a random sample of citing documents
would contain few reusers; a sample drawn from candidate-bearing documents
contains many. Human labels live in gold_labels.jsonl, a separate table so
they survive re-extraction.
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path

from closeread.config import Settings
from closeread.jsonl import read_jsonl, write_jsonl


def export_label_sample(
    run_id: str,
    settings: Settings,
    community: str,
    size: int = 200,
    dest: Path | None = None,
    log=print,
) -> Path:
    """Write a labelling CSV for one run, oversampling candidate-supported
    records. The labeller fills `human_label` with correct / incorrect /
    unsure, then `import_labels` ingests it."""
    out_dir = settings.community_dir(community)
    records = [
        r
        for r in read_jsonl(out_dir / "bronze" / f"records_{run_id}.jsonl")
        if r["source_quote"]
    ]
    rng = random.Random(f"{run_id}_gold_sample")
    supported = [r for r in records if r.get("candidate_support")]
    rest = [r for r in records if not r.get("candidate_support")]
    rng.shuffle(supported)
    rng.shuffle(rest)
    chosen = (supported + rest)[:size]

    dest = dest or out_dir / f"gold_label_sample_{run_id}.csv"
    with open(dest, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["record_id", "doc_id", "extraction_class", "source_quote", "attributes",
             "source_section", "human_label", "labeller", "notes"]
        )
        for r in chosen:
            w.writerow(
                [r["record_id"], r["doc_id"], r["extraction_class"], r["source_quote"],
                 str(r["attributes"]), r["source_section"], "", "", ""]
            )
    log(f"label sample ({len(chosen)} records, {len(supported)} candidate-supported) -> {dest}")
    return dest


def import_labels(csv_path: Path, settings: Settings, community: str, log=print) -> int:
    out_dir = settings.community_dir(community)
    dest = out_dir / "gold_labels.jsonl"
    existing = list(read_jsonl(dest)) if dest.exists() else []
    seen = {(g["record_id"], g["labeller"]) for g in existing}
    added = 0
    with open(csv_path) as fh:
        for row in csv.DictReader(fh):
            label = (row.get("human_label") or "").strip().lower()
            if label not in ("correct", "incorrect", "unsure"):
                continue
            key = (row["record_id"], row.get("labeller") or "unknown")
            if key in seen:
                continue
            existing.append(
                {
                    "record_id": row["record_id"],
                    "human_label": label,
                    "labeller": row.get("labeller") or "unknown",
                    "labelled_at": dt.date.today().isoformat(),
                }
            )
            added += 1
    write_jsonl(dest, existing)
    log(f"imported {added} labels ({len(existing)} total) -> {dest}")
    return added


def judge_precision_recall(
    run_id: str, settings: Settings, community: str, log=print
) -> dict | None:
    """Judge precision/recall against human labels (§11.3). Positive class:
    judge said confirmed; truth: human said correct."""
    out_dir = settings.community_dir(community)
    labels = {
        g["record_id"]: g["human_label"]
        for g in read_jsonl(out_dir / "gold_labels.jsonl")
        if g["human_label"] in ("correct", "incorrect")
    } if (out_dir / "gold_labels.jsonl").exists() else {}
    silver = out_dir / "silver" / f"records_{run_id}.jsonl"
    source = silver if silver.exists() else out_dir / "bronze" / f"records_{run_id}.jsonl"
    tp = fp = fn = tn = 0
    for r in read_jsonl(source):
        truth = labels.get(r["record_id"])
        verdict = r.get("judge_verdict")
        if truth is None or verdict not in ("confirmed", "rejected"):
            continue
        if verdict == "confirmed" and truth == "correct":
            tp += 1
        elif verdict == "confirmed" and truth == "incorrect":
            fp += 1
        elif verdict == "rejected" and truth == "correct":
            fn += 1
        else:
            tn += 1
    n = tp + fp + fn + tn
    if n == 0:
        log("no overlapping human labels and judge verdicts yet")
        return None
    result = {
        "n": n,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }
    log(str(result))
    return result
