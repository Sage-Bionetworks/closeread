"""REPORT.md rendering and generic gold tables. Spec §10.

Every number is computed at render time from stored records and run
summaries. No typed numbers (§11.4). Section 5, "what could not be measured",
is required and is written from measured values.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any

from closeread.config import CommunityConfig, Settings
from closeread.jsonl import read_jsonl


def records_for_runs(settings: Settings, community: str, run_ids: list[str]) -> list[dict[str, Any]]:
    out = settings.community_dir(community)
    rows: list[dict[str, Any]] = []
    for run_id in run_ids:
        silver = out / "silver" / f"records_{run_id}.jsonl"
        bronze = out / "bronze" / f"records_{run_id}.jsonl"
        path = silver if silver.exists() else bronze
        if not path.exists():
            raise FileNotFoundError(f"no records for run {run_id}")
        rows.extend(read_jsonl(path))
    return rows


def load_documents(settings: Settings, community: str) -> dict[str, dict[str, Any]]:
    return {
        d["doc_id"]: d for d in read_jsonl(settings.community_dir(community) / "documents.jsonl")
    }


def build_gold_class_tables(
    settings: Settings, community: str, run_ids: list[str], log=print
) -> dict[str, Path]:
    """One flat CSV per extraction class (§4.3 gold layer). Raw attribute
    values and canonical values sit side by side (rule 6.4)."""
    records = [r for r in records_for_runs(settings, community, run_ids) if r["judge_verdict"] != "rejected"]
    docs = load_documents(settings, community)
    gold_dir = settings.community_dir(community) / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)

    by_class: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_class.setdefault(r["extraction_class"], []).append(r)

    paths: dict[str, Path] = {}
    for cls, cls_records in sorted(by_class.items()):
        attr_keys = sorted({k for r in cls_records for k in r["attributes"]})
        canon_keys = sorted(
            {k for r in cls_records for k in (r.get("attributes_canonical") or {})}
        )
        dest = gold_dir / f"{cls}.csv"
        with open(dest, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(
                ["doc_id", "doc_type", "group_key", "pub_date", "venue", "author_overlap"]
                + attr_keys
                + [f"canonical_{k}" for k in canon_keys]
                + ["source_section", "source_quote", "alignment_status", "judge_verdict",
                   "enum_drift", "evidence_scope", "run_id", "record_id"]
            )
            for r in cls_records:
                d = docs.get(r["doc_id"], {})
                canon = r.get("attributes_canonical") or {}
                w.writerow(
                    [r["doc_id"], d.get("doc_type"), d.get("group_key"), d.get("pub_date"),
                     d.get("venue"), d.get("author_overlap")]
                    + [_flat(r["attributes"].get(k)) for k in attr_keys]
                    + [_flat(canon.get(k)) for k in canon_keys]
                    + [r["source_section"], r["source_quote"], r["alignment_status"],
                       r["judge_verdict"], ";".join(r["enum_drift"]), r["evidence_scope"],
                       r["run_id"], r["record_id"]]
                )
        paths[cls] = dest
        log(f"gold/{cls}.csv: {len(cls_records)} records")
    return paths


def _flat(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ";".join(str(x) for x in v)
    return str(v)


def run_summaries(settings: Settings, community: str, run_ids: list[str]) -> list[dict[str, Any]]:
    out = settings.community_dir(community) / "runs"
    summaries = []
    for run_id in run_ids:
        p = out / f"{run_id}.summary.json"
        if p.exists():
            s = json.loads(p.read_text())
            h = json.loads((out / f"{run_id}.handoff.json").read_text())
            s["model"] = h["model"]
            s["pass_name"] = h["pass_name"]
            s["prompt_version"] = h["prompt_version"]
            s["canary_passed"] = h.get("canary_passed")
            summaries.append(s)
    return summaries


def render_f8(settings: Settings, community: str, run_ids: list[str], figures_dir: Path) -> dict:
    """F8: coverage and measured precision per class. Precision cells stay
    empty until human labels exist — an empty cell is a statement, not a bug."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from closeread.report.figures import BAR_COLOR, INK, MUTED

    records = records_for_runs(settings, community, run_ids)
    gold_labels_path = settings.community_dir(community) / "gold_labels.jsonl"
    labels = {g["record_id"]: g for g in read_jsonl(gold_labels_path)} if gold_labels_path.exists() else {}

    per_class: dict[str, dict[str, Any]] = {}
    for r in records:
        c = per_class.setdefault(
            r["extraction_class"], {"n": 0, "judged": 0, "labelled": 0, "label_correct": 0}
        )
        c["n"] += 1
        if r.get("judge_verdict"):
            c["judged"] += 1
        g = labels.get(r["record_id"])
        if g:
            c["labelled"] += 1
            if g["human_label"] == "correct":
                c["label_correct"] += 1

    classes = sorted(per_class)
    fig, ax = plt.subplots(figsize=(7.2, 0.5 * len(classes) + 1.6))
    y = range(len(classes))
    ax.barh(y, [per_class[c]["n"] for c in classes], height=0.6, color=BAR_COLOR)
    for yi, c in zip(y, classes):
        d = per_class[c]
        precision = f"precision {d['label_correct'] / d['labelled']:.0%} (n={d['labelled']})" if d["labelled"] else "precision not yet measured"
        ax.text(d["n"], yi, f" {d['n']} records — {precision}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(list(y))
    ax.set_yticklabels([c.replace("_", " ") for c in classes], fontsize=9, color=INK)
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("records", fontsize=8.5, color=MUTED)
    ax.set_title(
        f"F8 — Coverage and measured precision per class (runs: {len(run_ids)})",
        loc="left", fontsize=10.5, color=INK,
    )
    fig.tight_layout()
    base = figures_dir / "f8_coverage"
    fig.savefig(f"{base}.svg")
    fig.savefig(f"{base}.png", dpi=200)
    plt.close(fig)
    with open(f"{base}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["extraction_class", "n_records", "n_judged", "n_labelled", "n_label_correct"])
        for c in classes:
            d = per_class[c]
            w.writerow([c, d["n"], d["judged"], d["labelled"], d["label_correct"]])
    return {
        "figure": "f8_coverage",
        "run_ids": run_ids,
        "n_records": sum(d["n"] for d in per_class.values()),
        "denominator_definition": "all non-rejected records in the listed runs",
        "filters": "none",
    }
