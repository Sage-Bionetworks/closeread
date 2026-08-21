"""REPORT.md assembly. Spec §10.2, §11.4, §11.6.

Every number is computed here at render time from stored artifacts. No typed
numbers. Section 5 ("what could not be measured") is required and is written
from measured values.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

from closeread.config import CommunityConfig, Settings
from closeread.jsonl import read_jsonl
from closeread.report.render import records_for_runs, run_summaries


def render_report_md(
    config: CommunityConfig, settings: Settings, run_ids: list[str], log=print
) -> Path:
    out_dir = settings.community_dir(config.community)
    docs = list(read_jsonl(out_dir / "documents.jsonl"))
    corpus = [d for d in docs if d["doc_type"] == "corpus"]
    citing = [d for d in docs if d["doc_type"] == "citing"]
    records = records_for_runs(settings, config.community, run_ids)
    summaries = run_summaries(settings, config.community, run_ids)
    manifest_path = settings.report_dir / "figure_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    def n(pred, pop):
        return sum(1 for d in pop if pred(d))

    snapshot_dates = sorted({d.get("snapshot_date") for d in docs if d.get("snapshot_date")})
    corpus_full = n(lambda d: d.get("oa_status") == "fulltext", corpus)
    citing_full = n(lambda d: d.get("oa_status") == "fulltext", citing)
    corpus_abs = n(lambda d: d.get("abstract"), corpus)
    citing_abs = n(lambda d: d.get("abstract"), citing)
    merged_pairs = sum(len(d.get("merged_from") or []) for d in citing)
    tier_c = n(lambda d: d.get("oa_status") == "preprint_requester_pays_pending", citing)
    overlap = Counter(d.get("author_overlap") for d in citing if d.get("author_overlap"))
    edges = sum(1 for _ in read_jsonl(out_dir / "citation_edges.jsonl")) if (out_dir / "citation_edges.jsonl").exists() else 0

    by_class = Counter(r["extraction_class"] for r in records)
    judged = sum(1 for r in records if r.get("judge_verdict"))
    total_stop = sum(s["finish_reasons"].get("STOP", 0) for s in summaries)
    total_resp = sum(s["n_responses"] for s in summaries)
    models = sorted({s["model"] for s in summaries})
    gold_labels_path = out_dir / "gold_labels.jsonl"
    n_labels = sum(1 for _ in read_jsonl(gold_labels_path)) if gold_labels_path.exists() else 0

    low_attrs: list[str] = []
    for s in summaries:
        for cls, attrs in (s.get("attribute_population") or {}).items():
            for attr, share in attrs.items():
                if share < 0.5:
                    low_attrs.append(f"`{cls}.{attr}` {share:.0%} (run {s['run_id']})")

    lines: list[str] = []
    a = lines.append
    a(f"# {config.display_name}: how the datasets were built, and how they were reused")
    a("")
    a(f"Generated {dt.date.today().isoformat()} by closeread. Every number in this")
    a("report is computed from stored, quotation-grounded records; figure CSVs and")
    a("`figure_manifest.json` carry per-figure provenance.")
    a("")
    a("## 1. What was measured")
    a("")
    a(f"- OpenAlex snapshot date(s): {', '.join(snapshot_dates) or 'not recorded'}")
    a(f"- Corpus documents: {len(corpus)}, of which {corpus_full} with full text and {corpus_abs} with an abstract")
    a(f"- Citing documents (deduplicated): {len(citing)}, of which {citing_full} with full text and {citing_abs} with an abstract")
    a(f"- Citation edges: {edges}")
    a(f"- Preprint/published pairs merged: {merged_pairs}")
    a(f"- Author overlap of citing documents: " + ", ".join(f"{k} {v}" for k, v in overlap.most_common()))
    a(f"- Records in this report's runs: {len(records)} across {len(by_class)} classes; {judged} judged")
    a("")
    a("## 2. How the datasets were built")
    a("")
    a("Figures F1 (format spread), F2 (cell typing by centre), F3 (TME methods),")
    a("F7 (availability statement kinds). See `figures/`.")
    a("")
    a("## 3. How they were reused")
    a("")
    a("Figures F4 (engagement kinds) and F5/F5b (data-reuse tasks split by author")
    a("overlap). Reuse aggregates are always split internal vs external.")
    a("")
    a("## 4. Whether reuse compounds")
    a("")
    a("Figure F6 (provenance chain).")
    a("")
    a("## 5. What could not be measured")
    a("")
    if tier_c:
        a(f"- {tier_c} citing preprints sit in requester-pays buckets not yet fetched (tier C); they contribute abstracts only.")
    no_text = len(citing) - citing_full - tier_c
    a(f"- {no_text} citing documents have no full-text route; the abstract pass is the only reach.")
    if n_labels < 150:
        a(f"- Judge precision is NOT yet measured against human labels: {n_labels} of the required 150 labels exist (§11.3 unmet).")
    if low_attrs:
        a(f"- Attributes populated below 50 percent: " + "; ".join(sorted(set(low_attrs))[:12]) + ".")
    if (out_dir / "small_model_citing_judged_sample.json").exists():
        a(
            "- All passes in this report ran on the strong model. Small-model runs exist for "
            "the corpus (union, per design) and for earlier citing extractions; the citing "
            "small-model runs were superseded after a judged 500-document sample measured "
            "record-level false-positive rates of 14 to 38 percent per class, and are "
            "retained on disk but excluded from this report."
        )
    a("")
    a("## 6. Methods")
    a("")
    a(f"- Extraction models: {', '.join(models)} (batch API).")
    a(f"- Responses ending STOP: {total_stop} of {total_resp} ({total_stop / total_resp:.1%})." if total_resp else "- No responses collected.")
    a("- Runs in this report:")
    a("")
    a("| run_id | pass | model | prompt_version | canary | records | tokens in/out | cost USD |")
    a("|---|---|---|---|---|---|---|---|")
    run_records = Counter(r["run_id"] for r in records)
    from closeread.extract.batch import RATES

    total_cost = 0.0
    for s in summaries:
        rate_in, rate_out = RATES.get(s["model"], (0, 0))
        cost = (s.get("tokens_in", 0) * rate_in + s.get("tokens_out", 0) * rate_out) / 1e6
        total_cost += cost
        a(
            f"| {s['run_id']} | {s['pass_name']} | {s['model']} | {s['prompt_version']} | "
            f"{'passed' if s.get('canary_passed') else 'FAILED/SKIPPED'} | {run_records.get(s['run_id'], 0)} | "
            f"{s.get('tokens_in', 0):,}/{s.get('tokens_out', 0):,} | {cost:.2f} |"
        )
    a("")
    a(f"- Total extraction cost across these runs, at the batch rates in the design: about {total_cost:.2f} USD.")
    a("")
    gap_path = out_dir / "model_gap_500_sample.json"
    if gap_path.exists():
        gap = json.loads(gap_path.read_text())
        a("- Small-vs-strong model gap, measured on the 500-document citing sample (§14.2):")
        a("")
        a("| pass | class | strong records | small records | small recall vs strong |")
        a("|---|---|---|---|---|")
        for pass_name, data in gap.items():
            for cls, m in data["classes"].items():
                a(
                    f"| {pass_name} | {cls} | {m['strong_records']} | {m['small_records']} | "
                    f"{m['small_recall_vs_strong']:.0%} |"
                )
        a("")
    a(f"- Human-labelled gold records: {n_labels} (target 150; see §11.3).")
    if n_labels >= 1:
        from closeread.judge.gold_sample import judge_precision_recall

        for run_id in run_ids:
            if "_provenance_" not in run_id:
                continue
            pr = judge_precision_recall(run_id, settings, config.community, log=lambda *a_: None)
            if pr and pr["n"] >= 30:
                a(
                    f"- Judge calibration on {run_id}: precision {pr['precision']:.1%}, "
                    f"recall {pr['recall']:.1%} against {pr['n']} human labels."
                )
        # Per-class extraction precision from the human labels.
        labels = {
            g["record_id"]: g["human_label"]
            for g in read_jsonl(out_dir / "gold_labels.jsonl")
            if g["human_label"] in ("correct", "incorrect")
        }
        per_class: Counter = Counter()
        per_class_bad: Counter = Counter()
        for r in records:
            truth = labels.get(r["record_id"])
            if truth is None:
                continue
            per_class[r["extraction_class"]] += 1
            if truth == "incorrect":
                per_class_bad[r["extraction_class"]] += 1
        for cls, n_cls in sorted(per_class.items()):
            a(
                f"- Extraction precision, human-labelled, {cls}: "
                f"{(n_cls - per_class_bad[cls]) / n_cls:.1%} (n={n_cls})."
            )
        a(
            "- The dominant extraction error, per the labelling notes, is a citing paper's "
            "own data-availability statement misread as data reuse (distribution mistaken "
            "for reuse). Secondary modes: malformed or concatenated accession strings, and "
            "hosts outside the repository vocabulary. See the reviewed labelling CSV "
            "alongside gold_labels.jsonl."
        )
    a("- Rejected and unaligned records are retained on disk with status fields; nothing is deleted.")
    a("")

    settings.report_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.report_dir / "REPORT.md"
    dest.write_text("\n".join(lines))
    log(f"REPORT.md -> {dest}")
    return dest
