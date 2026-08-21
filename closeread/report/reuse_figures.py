"""Figures F4-F6: how the datasets were reused. Spec §10.3, rule 6.2a.

Every reuse aggregate is split by author_overlap, at minimum internal vs
external. A document's engagement labels are the union of its window labels.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from closeread.jsonl import read_jsonl
from closeread.report.figures import BAR_COLOR, INK, MUTED

EXTERNAL = "external"
INTERNAL_VALUES = ("is_corpus_document", "shared_senior_author", "shared_author")

# Second categorical hue (validated default palette) for the internal split.
BAR_COLOR_2 = "#e07a29"


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


def _internal(row: dict[str, str]) -> str:
    return "internal" if row.get("author_overlap") in INTERNAL_VALUES else "external"


def render_f4(gold_dir: Path, figures_dir: Path, run_ids: list[str]) -> dict:
    """F4: engagement kinds, showing combinations. Unit: documents; a
    document's kinds are the union of its window labels."""
    rows = _read_gold(gold_dir / "engagement.csv")
    kinds_by_doc: dict[str, set[str]] = defaultdict(set)
    judged = Counter()
    for r in rows:
        if r.get("judge_verdict") == "rejected":
            continue
        for k in (r.get("engagement_kind") or "").split(";"):
            if k:
                kinds_by_doc[r["doc_id"]].add(k)
        judged[bool(r.get("judge_verdict"))] += 1

    combos = Counter(tuple(sorted(v)) for v in kinds_by_doc.values())
    top = combos.most_common(14)
    n_docs = len(kinds_by_doc)
    judged_share = judged[True] / (judged[True] + judged[False]) if (judged[True] + judged[False]) else 0

    fig, ax = plt.subplots(figsize=(7.6, 0.38 * len(top) + 1.8))
    y = range(len(top))
    ax.barh(y, [n for _, n in top], height=0.62, color=BAR_COLOR)
    for yi, (_, n) in zip(y, top):
        ax.text(n, yi, f" {n}", va="center", fontsize=8, color=INK)
    ax.set_yticks(list(y))
    ax.set_yticklabels([" + ".join(k.replace("_", " ") for k in combo) for combo, _ in top], fontsize=8, color=INK)
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("documents", fontsize=8, color=MUTED)
    ax.set_title(
        f"F4 — Engagement-kind combinations\n(n = {n_docs} citing documents with engagement "
        f"records; {judged_share:.0%} of records judged)",
        loc="left", fontsize=9.5, color=INK,
    )
    fig.tight_layout()
    out_rows = [{"combination": "+".join(c), "n_docs": n} for c, n in combos.most_common()]
    _save(fig, figures_dir / "f4_engagement_kinds", out_rows, ["combination", "n_docs"])
    return {"figure": "f4_engagement_kinds", "run_ids": run_ids, "n_records": len(rows),
            "denominator_definition": "citing documents with at least one non-rejected engagement record",
            "judged_share": round(judged_share, 3),
            "filters": "judge_verdict != rejected"}


def render_f5(gold_dir: Path, figures_dir: Path, run_ids: list[str]) -> dict:
    """F5: data-reuse task breakdown, split by author overlap (rule 6.2a)."""
    rows = [
        r for r in _read_gold(gold_dir / "engagement.csv")
        if "data_reuse" in (r.get("engagement_kind") or "") and r.get("judge_verdict") != "rejected"
    ]
    tasks = [t for t, _ in Counter(
        r.get("data_task") for r in rows if r.get("data_task") not in ("", "not_stated", None)
    ).most_common()]
    docs = {(_internal(r), r.get("data_task"), r["doc_id"]) for r in rows}
    counts = Counter((g, t) for g, t, _ in docs)
    denoms = Counter(g for g in (_internal(r) for r in rows))

    fig, ax = plt.subplots(figsize=(7.4, 0.5 * len(tasks) + 1.8))
    y = list(range(len(tasks)))
    h = 0.36
    for offset, (grp, colour) in enumerate((("external", BAR_COLOR), ("internal", BAR_COLOR_2))):
        vals = [counts.get((grp, t), 0) for t in tasks]
        pos = [yi + (offset - 0.5) * h for yi in y]
        ax.barh(pos, vals, height=h, color=colour, label=f"{grp}")
        for pi, v in zip(pos, vals):
            if v:
                ax.text(v, pi, f" {v}", va="center", fontsize=7.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([t.replace("_", " ") for t in tasks], fontsize=8.5, color=INK)
    ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("documents", fontsize=8, color=MUTED)
    ax.set_title(
        "F5 — Data-reuse tasks, split by author overlap\n"
        f"(records: external {denoms.get('external', 0)}, internal {denoms.get('internal', 0)}; unit: documents)",
        loc="left", fontsize=9.5, color=INK,
    )
    fig.tight_layout()
    out_rows = [
        {"author_overlap_group": g, "data_task": t, "n_docs": counts.get((g, t), 0)}
        for g in ("external", "internal") for t in tasks
    ]
    _save(fig, figures_dir / "f5_data_reuse_tasks", out_rows, ["author_overlap_group", "data_task", "n_docs"])
    return {"figure": "f5_data_reuse_tasks", "run_ids": run_ids, "n_records": len(rows),
            "denominator_definition": "documents with a non-rejected data_reuse engagement record and a stated data_task",
            "filters": "engagement_kind contains data_reuse; judge_verdict != rejected"}


def render_f5b(gold_dir: Path, figures_dir: Path, run_ids: list[str]) -> dict:
    """F5b: internal against external reuse over time (facets, one per group)."""
    rows = [
        r for r in _read_gold(gold_dir / "engagement.csv")
        if "data_reuse" in (r.get("engagement_kind") or "") and r.get("judge_verdict") != "rejected"
        and (r.get("pub_date") or "")[:4].isdigit()
    ]
    docs = {(r["doc_id"], _internal(r), int(r["pub_date"][:4])) for r in rows}
    years = sorted({y for _, _, y in docs})
    counts = Counter((g, y) for _, g, y in docs)

    fig, axes = plt.subplots(2, 1, figsize=(6.8, 4.6), sharex=True)
    for ax, (grp, colour) in zip(axes, (("external", BAR_COLOR), ("internal", BAR_COLOR_2))):
        vals = [counts.get((grp, y), 0) for y in years]
        ax.bar(range(len(years)), vals, color=colour, width=0.66)
        for xi, v in enumerate(vals):
            if v:
                ax.text(xi, v, str(v), ha="center", va="bottom", fontsize=7.5, color=INK)
        total = sum(vals)
        ax.set_title(f"{grp} (n = {total} documents)", loc="left", fontsize=9, color=INK)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=8)
    axes[-1].set_xticks(range(len(years)))
    axes[-1].set_xticklabels([str(y) for y in years], fontsize=8, color=INK)
    fig.suptitle("F5b — Data-reusing documents per publication year", x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out_rows = [
        {"author_overlap_group": g, "year": y, "n_docs": counts.get((g, y), 0)}
        for g in ("external", "internal") for y in years
    ]
    _save(fig, figures_dir / "f5b_reuse_over_time", out_rows, ["author_overlap_group", "year", "n_docs"])
    return {"figure": "f5b_reuse_over_time", "run_ids": run_ids, "n_records": len(rows),
            "denominator_definition": "documents with a non-rejected data_reuse record and a publication year",
            "filters": "engagement_kind contains data_reuse; judge_verdict != rejected"}


def render_f6(
    settings, community: str, gold_dir: Path, figures_dir: Path, run_ids: list[str]
) -> dict:
    """F6: provenance chain — enumerated, full text, candidate-bearing,
    judged reusers, derived deposits. Each stage's definition prints on the bar."""
    out_dir = settings.community_dir(community)
    docs = list(read_jsonl(out_dir / "documents.jsonl"))
    citing = [d for d in docs if d["doc_type"] == "citing"]
    citing_ids = {d["doc_id"] for d in citing}
    full = {d["doc_id"] for d in citing if d.get("oa_status") == "fulltext"}

    cand_docs = set()
    if (out_dir / "candidates.jsonl").exists():
        for c in read_jsonl(out_dir / "candidates.jsonl"):
            if c["doc_id"] in citing_ids:
                cand_docs.add(c["doc_id"])

    eng_path = gold_dir / "engagement.csv"
    reusers, confirmed_reusers, derived = set(), set(), set()
    if eng_path.exists():
        for r in _read_gold(eng_path):
            if "data_reuse" in (r.get("engagement_kind") or "") and r.get("judge_verdict") != "rejected":
                reusers.add(r["doc_id"])
                if r.get("judge_verdict") == "confirmed":
                    confirmed_reusers.add(r["doc_id"])
    avail_path = gold_dir / "data_availability.csv"
    if avail_path.exists():
        for r in _read_gold(avail_path):
            if (
                r.get("doc_type") == "citing"
                and r["doc_id"] in reusers
                and r.get("direction") == "released"
                and r.get("statement_kind") not in ("no_statement", "")
            ):
                derived.add(r["doc_id"])

    stages = [
        ("citing works enumerated", len(citing)),
        ("with full text", len(full)),
        ("with a regex candidate", len(cand_docs & full)),
        ("data reusers (model, non-rejected)", len(reusers)),
        ("data reusers (judge-confirmed)", len(confirmed_reusers)),
        ("reusers depositing derived data", len(derived)),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    y = range(len(stages))
    ax.barh(y, [n for _, n in stages], height=0.62, color=BAR_COLOR)
    for yi, (label, n) in zip(y, stages):
        ax.text(n, yi, f" {n}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(list(y))
    ax.set_yticklabels([s for s, _ in stages], fontsize=8.5, color=INK)
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("documents", fontsize=8, color=MUTED)
    ax.set_title("F6 — Provenance chain (each bar is a distinct document count)", loc="left", fontsize=9.5, color=INK)
    fig.tight_layout()
    out_rows = [{"stage": s, "n": n} for s, n in stages]
    _save(fig, figures_dir / "f6_chain", out_rows, ["stage", "n"])
    return {"figure": "f6_chain", "run_ids": run_ids, "n_records": sum(n for _, n in stages),
            "denominator_definition": "per-stage document counts; definitions are the bar labels",
            "filters": "data_reuse from engagement.csv; derived deposits from citing data_availability released records"}
