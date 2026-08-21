"""Gold tables and figures. Spec §10.

Figure rules (§10.4): every number computed at render time; plotted data
written to a CSV with the same base name; denominator printed on the figure;
colour never the only encoding; SVG for print and PNG for slides.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from closeread.config import CommunityConfig, Settings

# First categorical hue of the validated default palette (dataviz reference).
BAR_COLOR = "#2a78d6"
INK = "#1f2937"
MUTED = "#6b7280"

STATEMENT_KIND_ORDER = [
    "full_deposit",
    "partial_deposit",
    "available_on_request",
    "within_paper",
    "third_party_restricted",
    "no_statement",
]


def _records_paths(settings: Settings, community: str, run_ids: list[str]) -> list[str]:
    """Silver records when they exist, bronze otherwise (pre-judge milestones)."""
    out = settings.community_dir(community)
    paths: list[str] = []
    for run_id in run_ids:
        silver = out / "silver" / f"records_{run_id}.jsonl"
        bronze = out / "bronze" / f"records_{run_id}.jsonl"
        if silver.exists():
            paths.append(str(silver))
        elif bronze.exists():
            paths.append(str(bronze))
        else:
            raise FileNotFoundError(f"no records for run {run_id}")
    return paths


def connect(settings: Settings, community: str, run_ids: list[str]) -> duckdb.DuckDBPyConnection:
    """The shared view (§8.5). Every figure reads gold tables built from this
    view; no figure applies its own filter."""
    con = duckdb.connect()
    paths = _records_paths(settings, community, run_ids)
    docs_path = str(settings.community_dir(community) / "documents.jsonl")
    con.execute(
        f"CREATE VIEW records AS SELECT * FROM read_json_auto({paths!r}, union_by_name=true)"
    )
    con.execute(f"CREATE VIEW documents AS SELECT * FROM read_json_auto('{docs_path}')")
    con.execute(
        """
        CREATE VIEW v_records AS
        SELECT r.*, d.doc_type, d.group_key, d.pub_date, d.venue
        FROM records r JOIN documents d USING (doc_id)
        WHERE r.judge_verdict IS DISTINCT FROM 'rejected'
        """
    )
    return con


def build_gold_availability(
    con: duckdb.DuckDBPyConnection, settings: Settings, community: str
) -> Path:
    """gold/availability.csv — one row per availability record."""
    gold_dir = settings.community_dir(community) / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    dest = gold_dir / "availability.csv"
    con.execute(
        f"""
        COPY (
            SELECT
                doc_id, doc_type, group_key, pub_date, venue,
                extraction_class,
                attributes.statement_kind AS statement_kind,
                attributes.direction      AS direction,
                attributes.repository     AS repository,
                attributes.accession      AS accession,
                source_section, source_quote, alignment_status,
                judge_verdict, run_id
            FROM v_records
            WHERE extraction_class IN ('data_availability', 'code_availability')
        ) TO '{dest}' (HEADER)
        """
    )
    return dest


def render_f7(
    settings: Settings,
    community: str,
    run_ids: list[str],
    figures_dir: Path | None = None,
) -> dict:
    """F7: availability statement kinds, corpus against citing (§10.3).

    Unit: documents. A document counts once per statement kind it uses.
    Denominators (documents with full text, per doc_type) print on the panel.
    Facets, not overlays: one panel per (extraction_class, doc_type).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    con = connect(settings, community, run_ids)
    gold_path = build_gold_availability(con, settings, community)

    rows = con.execute(
        """
        SELECT doc_type, extraction_class, statement_kind,
               count(DISTINCT doc_id) AS n_docs
        FROM read_csv_auto(?)
        WHERE statement_kind IS NOT NULL
        GROUP BY ALL
        """,
        [str(gold_path)],
    ).fetchall()
    denominators = dict(
        con.execute(
            "SELECT doc_type, count(DISTINCT doc_id) FROM v_records GROUP BY doc_type"
        ).fetchall()
    )
    judged_share = con.execute(
        "SELECT round(avg(CASE WHEN judge_verdict IS NOT NULL THEN 1 ELSE 0 END), 3) FROM v_records"
    ).fetchone()[0]

    figures_dir = figures_dir or settings.report_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    doc_types = sorted({r[0] for r in rows})
    classes = ["data_availability", "code_availability"]
    counts = {(dt, cls, kind): n for dt, cls, kind, n in rows}

    fig, axes = plt.subplots(
        len(classes),
        max(len(doc_types), 1),
        figsize=(5.4 * max(len(doc_types), 1), 3.1 * len(classes)),
        squeeze=False,
    )
    for i, cls in enumerate(classes):
        for j, dt in enumerate(doc_types):
            ax = axes[i][j]
            values = [counts.get((dt, cls, k), 0) for k in STATEMENT_KIND_ORDER]
            y = range(len(STATEMENT_KIND_ORDER))
            ax.barh(y, values, height=0.62, color=BAR_COLOR)
            ax.set_yticks(list(y))
            ax.set_yticklabels([k.replace("_", " ") for k in STATEMENT_KIND_ORDER], fontsize=8.5, color=INK)
            ax.invert_yaxis()
            for yi, v in zip(y, values):
                if v:
                    ax.text(v, yi, f" {v}", va="center", fontsize=8.5, color=INK)
            denom = denominators.get(dt, 0)
            ax.set_title(
                f"{cls.replace('_', ' ')} — {dt} (n = {denom} documents)",
                fontsize=9.5, color=INK, loc="left",
            )
            ax.spines[["top", "right"]].set_visible(False)
            ax.spines[["left", "bottom"]].set_color(MUTED)
            ax.tick_params(colors=MUTED, labelsize=8)
            ax.set_xlabel("documents", fontsize=8.5, color=MUTED)
    fig.suptitle(
        "F7 — Availability statement kinds"
        f"   (judged share of records: {judged_share:.0%})" if judged_share else
        "F7 — Availability statement kinds   (no records judged yet)",
        fontsize=11, color=INK, x=0.01, ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    base = figures_dir / "f7_availability"
    fig.savefig(f"{base}.svg")
    fig.savefig(f"{base}.png", dpi=200)
    plt.close(fig)

    # The plotted data, same base name (§10.4 rule 2).
    import csv as _csv

    with open(f"{base}.csv", "w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["doc_type", "extraction_class", "statement_kind", "n_docs", "denominator_docs"])
        for dt in doc_types:
            for cls in classes:
                for kind in STATEMENT_KIND_ORDER:
                    w.writerow([dt, cls, kind, counts.get((dt, cls, kind), 0), denominators.get(dt, 0)])

    manifest_entry = {
        "figure": "f7_availability",
        "run_ids": run_ids,
        "n_records": con.execute("SELECT count(*) FROM read_csv_auto(?)", [str(gold_path)]).fetchone()[0],
        "denominators": {str(k): v for k, v in denominators.items()},
        "denominator_definition": "documents with full text contributing at least one availability record (absence records included)",
        "judged_share": judged_share,
        "filters": "v_records: judge_verdict IS DISTINCT FROM 'rejected'",
    }
    con.close()
    return manifest_entry
