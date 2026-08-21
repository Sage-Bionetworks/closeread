"""Figures F1-F3: how the datasets were built. Spec §10.3.

Designed against real gold tables (not speculative). Shared rules: numbers
computed at render time, CSV with same base name, denominator on the figure,
counts printed in cells (colour never the only encoding), SVG + PNG.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from closeread.report.figures import BAR_COLOR, INK, MUTED


def _read_gold(path: Path) -> list[dict[str, str]]:
    with open(path) as fh:
        return list(csv.DictReader(fh))


def _save(fig, base: Path, rows: list[dict], fieldnames: list[str]) -> None:
    fig.savefig(f"{base}.svg")
    fig.savefig(f"{base}.png", dpi=200)
    plt.close(fig)
    with open(f"{base}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _pick(row: dict[str, str], canonical: str, raw: str) -> str:
    return row.get(canonical) or row.get(raw) or ""


def _heatmap(ax, matrix, row_labels, col_labels, title, denom_note):
    import numpy as np

    arr = np.array(matrix, dtype=float)
    masked = np.ma.masked_equal(arr, 0)
    ax.imshow(masked, cmap="Blues", aspect="auto", vmin=0)
    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=45, ha="right", fontsize=7.5, color=INK)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=7.5, color=INK)
    vmax = arr.max() if arr.size else 1
    for i in range(len(row_labels)):
        for j in range(len(col_labels)):
            v = int(arr[i][j])
            if v:
                ax.text(j, i, str(v), ha="center", va="center", fontsize=6.5,
                        color="white" if v > vmax * 0.6 else INK)
    ax.set_title(f"{title}\n{denom_note}", loc="left", fontsize=9.5, color=INK)
    ax.tick_params(colors=MUTED)


def render_f1(gold_dir: Path, figures_dir: Path, run_ids: list[str]) -> dict:
    """F1: format spread — distinct formats per assay and level."""
    rows = _read_gold(gold_dir / "object_format.csv")
    usable = [
        r for r in rows
        if r.get("doc_type") == "corpus"
        and _pick(r, "canonical_format", "format") not in ("", "not_stated")
    ]
    formats: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in usable:
        assay = _pick(r, "canonical_assay_name", "assay_name")
        if assay in ("", "not_stated"):
            assay = "(assay not stated)"
        level = r.get("level") or "not_stated"
        formats[(assay, level)].add(_pick(r, "canonical_format", "format"))

    assay_totals = Counter()
    for (assay, _lvl), fmts in formats.items():
        assay_totals[assay] += len(fmts)
    top_assays = [a for a, _ in assay_totals.most_common(18)]
    levels = ["raw", "processed", "derived", "annotation", "visualization", "not_stated"]

    matrix = [[len(formats.get((a, l), ())) for l in levels] for a in top_assays]
    n_docs = len({r["doc_id"] for r in usable})
    fig, ax = plt.subplots(figsize=(7.4, 0.34 * len(top_assays) + 2.2))
    _heatmap(
        ax, matrix, top_assays, [l.replace("_", " ") for l in levels],
        "F1 — Distinct file formats per assay and processing level",
        f"n = {len(usable)} records with a stated format, {n_docs} corpus documents; top {len(top_assays)} assays",
    )
    fig.tight_layout()
    out_rows = [
        {"assay_name": a, "level": l, "n_distinct_formats": len(formats.get((a, l), ())),
         "formats": ";".join(sorted(formats.get((a, l), ())))}
        for a in top_assays for l in levels
    ]
    _save(fig, figures_dir / "f1_format_spread", out_rows,
          ["assay_name", "level", "n_distinct_formats", "formats"])
    return {"figure": "f1_format_spread", "run_ids": run_ids, "n_records": len(usable),
            "denominator_definition": "object_format records with a stated format",
            "filters": "format != not_stated"}


def render_f2(gold_dir: Path, figures_dir: Path, run_ids: list[str]) -> dict:
    """F2: cell-typing divergence — groups by step, with distinct algorithms."""
    rows = _read_gold(gold_dir / "cell_typing.csv")
    steps = ["clustering", "marker_based_annotation", "reference_mapping", "manual_annotation",
             "classifier", "deconvolution", "segmentation_based_phenotyping", "other"]
    groups = sorted({r["group_key"] for r in rows if r["group_key"]})
    docs_by = defaultdict(set)
    algos_by_step: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["group_key"] and r["step"] in steps:
            docs_by[(r["group_key"], r["step"])].add(r["doc_id"])
        algo = _pick(r, "canonical_algorithm", "algorithm")
        if algo not in ("", "not_stated"):
            algos_by_step[r["step"]].add(algo)

    matrix = [[len(docs_by.get((g, s), ())) for s in steps] for g in groups]
    n_docs = len({r["doc_id"] for r in rows})
    fig, ax = plt.subplots(figsize=(7.4, 0.32 * len(groups) + 2.4))
    col_labels = [f"{s.replace('_', ' ')}\n({len(algos_by_step.get(s, ()))} algos)" for s in steps]
    _heatmap(
        ax, matrix, groups, col_labels,
        "F2 — Cell-typing steps by centre (documents)",
        f"n = {len(rows)} cell-typing records from {n_docs} corpus documents",
    )
    fig.tight_layout()
    out_rows = [
        {"group_key": g, "step": s, "n_docs": len(docs_by.get((g, s), ()))}
        for g in groups for s in steps
    ]
    _save(fig, figures_dir / "f2_cell_typing", out_rows, ["group_key", "step", "n_docs"])
    return {"figure": "f2_cell_typing", "run_ids": run_ids, "n_records": len(rows),
            "denominator_definition": "cell_typing records joined to documents with a group_key",
            "filters": "none"}


def render_f3(gold_dir: Path, figures_dir: Path, run_ids: list[str]) -> dict:
    """F3: TME method categories, consortium authors against reusers."""
    rows = _read_gold(gold_dir / "tme_algorithm.csv")
    doc_types = sorted({r["doc_type"] for r in rows if r["doc_type"]})
    cats = [c for c, _ in Counter(r["category"] for r in rows if r["category"] not in ("", "not_stated")).most_common()]
    counts = Counter((r["doc_type"], r["category"]) for r in rows)
    denoms = {dt: len({r["doc_id"] for r in rows if r["doc_type"] == dt}) for dt in doc_types}

    fig, axes = plt.subplots(1, max(len(doc_types), 1), figsize=(5.2 * max(len(doc_types), 1), 0.42 * len(cats) + 1.8), squeeze=False)
    for j, dt in enumerate(doc_types):
        ax = axes[0][j]
        values = [counts.get((dt, c), 0) for c in cats]
        y = range(len(cats))
        ax.barh(y, values, height=0.62, color=BAR_COLOR)
        for yi, v in zip(y, values):
            if v:
                ax.text(v, yi, f" {v}", va="center", fontsize=8, color=INK)
        ax.set_yticks(list(y))
        ax.set_yticklabels([c.replace("_", " ") for c in cats], fontsize=8, color=INK)
        ax.invert_yaxis()
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlabel("records", fontsize=8, color=MUTED)
        ax.set_title(f"{dt} (n = {denoms[dt]} documents)", loc="left", fontsize=9.5, color=INK)
    fig.suptitle("F3 — Tumour-microenvironment method categories", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out_rows = [
        {"doc_type": dt, "category": c, "n_records": counts.get((dt, c), 0), "denominator_docs": denoms[dt]}
        for dt in doc_types for c in cats
    ]
    _save(fig, figures_dir / "f3_tme_methods", out_rows, ["doc_type", "category", "n_records", "denominator_docs"])
    return {"figure": "f3_tme_methods", "run_ids": run_ids, "n_records": len(rows),
            "denominator_definition": "tme_algorithm records; document denominators per doc_type printed per panel",
            "filters": "category != not_stated for the category axis"}
