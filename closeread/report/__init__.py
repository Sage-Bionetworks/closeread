"""Stage 8: report."""

from __future__ import annotations

import json

from closeread.config import CommunityConfig, Settings


def run_report(config: CommunityConfig, settings: Settings, run_ids: list[str], log=print) -> None:
    from closeread.report.figures import render_f7
    from closeread.report.render import build_gold_class_tables, render_f8

    report_dir = settings.report_dir
    figures_dir = report_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = report_dir / "figure_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    build_gold_class_tables(settings, config.community, run_ids, log=log)

    availability_runs = [r for r in run_ids if "_availability_" in r]
    if availability_runs:
        entry = render_f7(settings, config.community, availability_runs)
        manifest[entry["figure"]] = entry
        log(f"rendered {entry['figure']}: {entry['n_records']} records, denominators {entry['denominators']}")

    gold_dir = settings.community_dir(config.community) / "gold"
    from closeread.report.corpus_figures import render_f1, render_f2, render_f3

    for cls_csv, renderer in (
        ("object_format.csv", render_f1),
        ("cell_typing.csv", render_f2),
        ("tme_algorithm.csv", render_f3),
    ):
        if (gold_dir / cls_csv).exists():
            entry = renderer(gold_dir, figures_dir, run_ids)
            manifest[entry["figure"]] = entry
            log(f"rendered {entry['figure']}: {entry['n_records']} records")

    entry = render_f8(settings, config.community, run_ids, figures_dir)
    manifest[entry["figure"]] = entry
    log(f"rendered {entry['figure']}: {entry['n_records']} records")

    manifest_path.write_text(json.dumps(manifest, indent=2))
    log(f"figures -> {figures_dir}")
