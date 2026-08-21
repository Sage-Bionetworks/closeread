"""Stage 8: report."""

from __future__ import annotations

import json

from closeread.config import CommunityConfig, Settings


def run_report(config: CommunityConfig, settings: Settings, run_ids: list[str], log=print) -> None:
    from closeread.report.figures import render_f7

    report_dir = settings.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = report_dir / "figure_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    entry = render_f7(settings, config.community, run_ids)
    manifest[entry["figure"]] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log(f"rendered {entry['figure']}: {entry['n_records']} records, denominators {entry['denominators']}")
    log(f"figures -> {report_dir / 'figures'}")
