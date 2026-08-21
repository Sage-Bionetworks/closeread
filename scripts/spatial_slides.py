"""Spatial-biology slide figures for the Cancer Grand Challenges meeting.

Corpus first: slides 1-3 describe only what HTAN's own 168 papers say they
built. Slide 4 extends to the 9,753 citing papers. Slide 5 states how far any
of it can be trusted.

Every number is computed here at render time from the gold CSVs,
documents.jsonl, the run handoffs and model_gap_500_sample.json. No number is
typed into a figure. Each slide writes PNG, SVG and a backing CSV, plus an
entry in slide_manifest.json.

COUNTING RULE, applied everywhere and stated on every slide:
  Corpus papers were extracted twice (strong and small model over the same 157
  full-text papers) and the provenance pass ran both models over the same
  5,071 citing papers, so summed record counts would double-count documents.
  Every count in this deck is a distinct-DOCUMENT or distinct-VALUE count.
  No figure sums records.
"""

from __future__ import annotations

import csv
import glob
import json
import os
import textwrap
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "out" / "htan" / "gold"
HTAN = ROOT / "out" / "htan"
OUT = ROOT / "out" / "slides"
FIGS = OUT / "figures"

# dataviz reference palette, categorical slots 1-3 (light). Validated with
# scripts/validate_palette.js --pairs all: every check passes (worst CVD dE
# 9.2, worst normal-vision dE 24.0). The aqua slot is below 3:1 contrast on the
# light surface, so the relief rule applies: every bar carries a visible label.
BLUE = "#2a78d6"     # HTAN corpus
ORANGE = "#eb6834"   # citing, external authors
AQUA = "#1baf7a"     # citing, shared HTAN authorship
INK = "#1f2937"
MUTED = "#6b7280"
GRID = "#e5e7eb"
PALE = "#c8d8ef"     # de-emphasised bars in a corpus-only panel

STRONG_MODEL = "gemini-3.1-pro-preview"
SPATIAL = ("multiplex_imaging", "spatial_transcriptomics",
           "imaging_mass_cytometry", "mass_cytometry")
SP_SQL = "(" + ",".join(f"'{s}'" for s in SPATIAL) + ")"
NICE = {"multiplex_imaging": "multiplex imaging",
        "spatial_transcriptomics": "spatial transcriptomics",
        "imaging_mass_cytometry": "imaging mass cytometry",
        "mass_cytometry": "mass cytometry"}

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": GRID, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "svg.fonttype": "none",
    "figure.facecolor": "white", "axes.facecolor": "white"})

MANIFEST: dict[str, dict] = {}


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for name in ["assay_platform", "abstract_claim", "cell_typing", "tme_algorithm",
                 "engagement", "data_acquisition", "object_format",
                 "data_availability", "code_availability"]:
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM "
                    f"read_csv_auto('{GOLD / (name + '.csv')}', header=true, all_varchar=true)")
    con.execute(f"CREATE VIEW documents AS SELECT * FROM read_json_auto('{HTAN / 'documents.jsonl'}')")
    con.execute(f"""CREATE VIEW spatial_corpus AS SELECT DISTINCT doc_id FROM assay_platform
                    WHERE doc_type = 'corpus' AND assay_type IN {SP_SQL}""")
    con.execute(f"""CREATE VIEW spatial_citing AS SELECT DISTINCT doc_id FROM assay_platform
                    WHERE doc_type = 'citing' AND assay_type IN {SP_SQL}""")
    return con


def q(con, sql):
    return con.execute(sql).fetchall()


DCC = ROOT / "out" / "dcc"

# Crosswalk from the DCC portal's assayName vocabulary to the closeread
# assay_type vocabulary. Written out rather than fuzzy-matched, because the two
# vocabularies were authored independently and any mapping is a judgement call
# that a reader must be able to audit. Assays with no closeread counterpart map
# to None and are reported separately, never dropped silently.
PORTAL_TO_ASSAY_TYPE = {
    "CyCIF": "multiplex_imaging", "CODEX": "multiplex_imaging",
    "MxIF": "multiplex_imaging", "mIHC": "multiplex_imaging",
    "MIBI": "multiplex_imaging", "RareCyte Orion": "multiplex_imaging",
    "SABER": "multiplex_imaging",
    "IMC": "imaging_mass_cytometry",
    "MERFISH": "spatial_transcriptomics", "ExSEQ": "spatial_transcriptomics",
    "10X Visium": "spatial_transcriptomics",
    "NanoString GeoMX DSP": "spatial_transcriptomics",
    "Slide-seq": "spatial_transcriptomics", "Slide-seq V2": "spatial_transcriptomics",
    "10X Xenium ISS": "spatial_transcriptomics",
    "scRNA-seq": "scRNA_seq", "scATAC-seq": "scATAC_seq",
    "Bulk RNA-seq": "bulk_RNA_seq", "Bulk DNA": "targeted_dna_seq",
    "scDNA-seq": "scDNA_seq", "H&E": "histology", "Imaging": "histology",
    "Electron Microscopy": "electron_microscopy",
    "Bulk Methylation-seq": "methylation_profiling",
    "LC-MS/MS": "mass_spectrometry_proteomics",
    "LC-MS3": "mass_spectrometry_proteomics",
    "Mass Spectrometry": "mass_spectrometry_proteomics",
    "Shotgun MS (lipidomics)": "mass_spectrometry_proteomics",
    "RPPA": "mass_spectrometry_proteomics",
    "HI-C-seq": None, "Accessory Manifest": None,
}


# Corpus centre (documents.group_key) -> portal atlas_name. Also a judgement
# call, also auditable: several centres publish under a name the portal does
# not carry as a released atlas, and those are reported, not dropped.
CENTRE_TO_ATLAS = {
    "HMS (PATCH)": "HTAN HMS", "OHSU (Metastatic)": "HTAN OHSU",
    "OHSU (Pancreatic)": "HTAN OHSU", "CHOP (Pediatric)": "HTAN CHOP",
    "Duke (Breast PCA)": "HTAN Duke", "Vanderbilt (CRC)": "HTAN Vanderbilt",
    "Vanderbilt (CRC 3D)": "HTAN Vanderbilt", "Stanford (FAP)": "HTAN Stanford",
    "WashU": "HTAN WUSTL", "MSK (Metastasis)": "HTAN MSK",
    "Boston U (Lung PCA)": "HTAN BU", "HMS (DFCI)": "HTAN DFCI",
    "DFCI DCC": "HTAN DFCI",
    # publish in the corpus but have no released atlas in the portal
    "MD Anderson (Gastric)": None, "Yale (Lymphoma)": None, "UCSF (Skin)": None,
}


def _read_dcc(name: str) -> list[dict]:
    with open(DCC / name) as fh:
        return list(csv.DictReader(fh))


def portal_participants_by_assay_type() -> tuple[dict[str, int], int, int]:
    """(participants per closeread assay_type, unmapped-group participants,
    total participants with a released file).

    Participants, not files: a file count is dominated by tiling — electron
    microscopy is 110,398 files from 15 patients — so files answer a storage
    question, not a coverage one. Counts come from distinct demographicsIds on
    released files, so they are set operations per assay group and must never
    be summed across groups.
    """
    mapped = {r["assay_type"]: int(r["participants"])
              for r in _read_dcc("portal_assaytype_participants.csv")}
    unmapped = mapped.pop("__unmapped__", 0)
    total = int(_read_dcc("portal_totals.csv")[0].get("participants_with_files", 0) or 0)
    return mapped, unmapped, total


def provenance_attempted() -> set[str]:
    docs: set[str] = set()
    for p in glob.glob(str(HTAN / "runs" / "*provenance*.handoff.json")):
        docs |= {v["doc_id"] for v in json.load(open(p)).get("key_index", {}).values()}
    return docs


# --------------------------------------------------------------------------
# one panel = one question

def titled(ax, title, note, wrap=62, pad_lines=5):
    """Title + wrapped note, with a fixed reserved height so every panel on a
    slide has its title on the same baseline."""
    txt = "\n".join(textwrap.wrap(" ".join(note.split()), wrap))
    ax.set_title(title, loc="left", fontsize=11.5, color=INK,
                 pad=13 + 11 * max(pad_lines, txt.count("\n") + 1), fontweight="bold")
    ax.text(0, 1.015, txt, transform=ax.transAxes, fontsize=8.6, color=MUTED,
            va="bottom", ha="left", linespacing=1.45)


def panel(ax, labels, values, denom, title, note, colour=BLUE, unit="papers",
          highlight=None, xpad=1.42, wrap=62, pad_lines=5):
    """A single horizontal bar chart. Value labels are always drawn, so colour
    is never the only encoding."""
    y = list(range(len(labels)))
    cols = [colour if (highlight is None or l in highlight) else PALE for l in labels]
    ax.barh(y, values, color=cols, height=0.66)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10, color=INK)
    ax.invert_yaxis()
    top = max(values) if values and max(values) else 1
    for i, v in enumerate(values):
        ax.text(v + top * 0.022, i, f"{v}   {100.0 * v / denom:.0f}%",
                va="center", fontsize=9, color=INK)
    ax.set_xlim(0, top * xpad)
    ax.set_xlabel(f"{unit}   (denominator {denom})", fontsize=9, color=MUTED)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    titled(ax, title, note, wrap=wrap, pad_lines=pad_lines)


def deck(fig, title, sub):
    fig.text(0.008, 0.982, title, fontsize=16, color=INK, va="top", ha="left",
             fontweight="bold")
    fig.text(0.008, 0.930, sub, fontsize=10.5, color=MUTED, va="top", ha="left")


def footer(fig, text):
    lines = []
    for para in text.split("\n"):
        lines.extend(textwrap.wrap(" ".join(para.split()), 190) or [""])
    fig.text(0.008, 0.012, "\n".join(lines), fontsize=8.0, color=MUTED,
             va="bottom", ha="left", linespacing=1.55)


def save(fig, base, rows, fields, manifest):
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGS / f"{base}.png", dpi=200)
    fig.savefig(FIGS / f"{base}.svg")
    plt.close(fig)
    with open(FIGS / f"{base}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows([{f: r.get(f, "") for f in fields} for r in rows])
    MANIFEST[base] = manifest
    print(f"  figures/{base}.{{png,svg,csv}}  ({len(rows)} rows)")


ROW = lambda **kw: kw
FIELDS = ["slide", "panel", "population", "category", "n_documents",
          "denominator_documents", "extra_measure", "extra_value"]

CORPUS_RULE = ("Counting rule: distinct documents only — HTAN papers were extracted by two "
               "models, so no figure sums records.")
C_PRECISION = ("Judge precision is NOT measured against human labels (0 of 150 gold labels; "
               "design §11.3 unmet) and 7 of 9 extraction classes were never adjudicated at "
               "all. Every share here is precision-unvalidated.")
C_FLOOR = ("Citing-side counts are FLOORS: those passes ran on the small model, which recovers "
           "42–56% of strong-model records for these classes on a 500-document sample.")
C_REACH = ("29 citing preprints in unfetched requester-pays buckets and 445 citing papers with "
           "no full-text route are abstract-only.")


# ==========================================================================
# SLIDE 1 -- what HTAN built (corpus only)

def slide1(con):
    fig = plt.figure(figsize=(13.33, 7.5))
    deck(fig, "What HTAN says it built",
         "HTAN's own 168 papers only. No citing papers on this slide.")
    gs = fig.add_gridspec(1, 3, left=0.148, right=0.972, top=0.735, bottom=0.165,
                          wspace=1.12)
    rows = []

    # A -- the whole assay portfolio, with the four spatial modalities picked out
    ap = q(con, """SELECT assay_type, count(DISTINCT doc_id) FROM assay_platform
                   WHERE doc_type = 'corpus' AND assay_type NOT IN ('not_stated', 'other')
                   GROUP BY 1 ORDER BY 2 DESC LIMIT 12""")
    den = q(con, "SELECT count(DISTINCT doc_id) FROM assay_platform WHERE doc_type = 'corpus'")[0][0]
    labels = [NICE.get(a, a.replace("_", " ")) for a, _ in ap]
    hl = {NICE[s] for s in SPATIAL}
    panel(fig.add_subplot(gs[0, 0]), labels, [n for _, n in ap], den,
          "A — Assay portfolio",
          f"HTAN papers reporting each assay. Spatial modalities in blue, the rest in grey. "
          f"{den} of 168 corpus papers carry an assay record; papers report several assays.",
          colour=BLUE, highlight=hl, wrap=40)
    rows += [ROW(slide=1, panel="A", population="HTAN corpus", category=a,
                 n_documents=n, denominator_documents=den) for a, n in ap]

    # B -- which centres, and therefore which tumour contexts, are spatial
    ce = q(con, """WITH c AS (SELECT d.doc_id, trim(u) AS centre
                              FROM documents d, UNNEST(string_split(d.group_key, ';')) t(u)
                              WHERE d.doc_type = 'corpus' AND d.group_key IS NOT NULL)
                   SELECT centre, count(DISTINCT c.doc_id),
                          count(DISTINCT CASE WHEN s.doc_id IS NOT NULL THEN c.doc_id END)
                   FROM c LEFT JOIN spatial_corpus s USING (doc_id)
                   GROUP BY 1 HAVING count(DISTINCT c.doc_id) >= 5 ORDER BY 3 DESC""")
    axB = fig.add_subplot(gs[0, 1])
    y = list(range(len(ce)))
    axB.barh(y, [r[1] for r in ce], color=PALE, height=0.66)
    axB.barh(y, [r[2] for r in ce], color=BLUE, height=0.66)
    axB.set_yticks(y)
    axB.set_yticklabels([r[0] for r in ce], fontsize=10, color=INK)
    axB.invert_yaxis()
    for i, r in enumerate(ce):
        axB.text(r[1] + 0.6, i, f"{r[2]} of {r[1]}", va="center", fontsize=9, color=INK)
    axB.set_xlim(0, max(r[1] for r in ce) * 1.42)
    axB.set_xlabel("papers from this centre", fontsize=9, color=MUTED)
    axB.spines[["top", "right", "left"]].set_visible(False)
    axB.tick_params(length=0)
    axB.grid(axis="x", color=GRID, linewidth=0.7)
    axB.set_axisbelow(True)
    axB.legend(handles=[Patch(facecolor=BLUE, label="reports a spatial assay"),
                        Patch(facecolor=PALE, label="does not")],
               frameon=False, fontsize=8.6, loc="lower right",
               bbox_to_anchor=(1.0, 1.005), ncol=2, handlelength=1.1)
    note = ("Each HTAN centre works one tumour context, so this is also the tumour-type view. "
            "A paper spanning several centres counts in each, so the bars overlap. "
            "Centres with fewer than 5 papers omitted.")
    titled(axB, "B — Tumour context, by centre", note, wrap=40)
    rows += [ROW(slide=1, panel="B", population="HTAN corpus", category=r[0],
                 n_documents=r[2], denominator_documents=r[1],
                 extra_measure="papers from centre", extra_value=r[1]) for r in ce]

    # C -- the biology the papers claim, on the Hanahan-Weinberg hallmark enum.
    # Multi-valued, so explode; 'not_stated' documents are reported in the note
    # rather than dropped, because absence is the majority state here.
    hm = q(con, """SELECT trim(u) AS v, count(DISTINCT doc_id)
                   FROM abstract_claim, UNNEST(string_split(cancer_hallmark, ';')) t(u)
                   WHERE doc_type = 'corpus' AND trim(u) NOT IN ('', 'not_stated')
                   GROUP BY 1 ORDER BY 2 DESC""")
    hm_den = q(con, """SELECT count(DISTINCT doc_id) FROM abstract_claim,
                       UNNEST(string_split(cancer_hallmark, ';')) t(u)
                       WHERE doc_type = 'corpus' AND trim(u) NOT IN ('', 'not_stated')""")[0][0]
    hm_all = q(con, "SELECT count(DISTINCT doc_id) FROM abstract_claim WHERE doc_type = 'corpus'")[0][0]
    hlab = {"genome_instability_and_mutation": "genome instability\n& mutation",
            "avoiding_immune_destruction": "avoiding immune\ndestruction",
            "sustaining_proliferative_signaling": "sustaining proliferative\nsignalling",
            "activating_invasion_and_metastasis": "invasion & metastasis",
            "tumor_promoting_inflammation": "tumour-promoting\ninflammation",
            "nonmutational_epigenetic_reprogramming": "nonmutational epigenetic\nreprogramming",
            "deregulating_cellular_metabolism": "deregulated metabolism",
            "unlocking_phenotypic_plasticity": "phenotypic plasticity",
            "resisting_cell_death": "resisting cell death",
            "inducing_or_accessing_vasculature": "vasculature",
            "evading_growth_suppressors": "evading growth\nsuppressors",
            "polymorphic_microbiomes": "polymorphic microbiomes",
            "enabling_replicative_immortality": "replicative immortality"}
    panel(fig.add_subplot(gs[0, 2]), [hlab.get(v, v.replace("_", " ")) for v, _ in hm],
          [n for _, n in hm], hm_den, "C — Which hallmark",
          f"Cancer hallmark claimed in the abstract. {hm_den} of {hm_all} corpus papers name "
          f"one; the other {hm_all - hm_den} state none. Multi-valued, so bars do not sum.",
          colour=BLUE, wrap=40)
    rows += [ROW(slide=1, panel="C", population="HTAN corpus", category=v,
                 n_documents=nn, denominator_documents=hm_den) for v, nn in hm]

    footer(fig, f"{CORPUS_RULE}  {C_PRECISION}  Slide 7 carries the full caveats.")
    save(fig, "s1_what_htan_built", rows, FIELDS, {
        "slide": 1, "population": "HTAN corpus only",
        "A": {"class": "assay_platform", "denominator": f"{den} corpus papers with an assay record",
              "filters": "assay_type not in (not_stated, other); top 12", "judged": False},
        "B": {"class": "documents.group_key + assay_platform",
              "denominator": "papers per centre (group_key split on ';')",
              "filters": "centres with >=5 papers", "judged": False},
        "C": {"class": "abstract_claim", "attribute": "cancer_hallmark",
              "model": STRONG_MODEL,
              "denominator": "corpus papers naming >=1 hallmark",
              "filters": "multi-valued, exploded on ';'; not_stated excluded from bars "
                         "and reported in the note", "judged": False},
        "counting_rule": "distinct documents only"})


# ==========================================================================
# SLIDE 1b -- how the corpus changed (corpus only)

def slide1b(con):
    fig = plt.figure(figsize=(13.33, 7.5))
    tot = q(con, "SELECT count(DISTINCT doc_id) FROM abstract_claim WHERE doc_type = 'corpus'")[0][0]
    deck(fig, "How the corpus changed",
         f"HTAN's own {tot} papers with an abstract record, by year of publication. "
         f"Still no citing papers.")
    gs = fig.add_gridspec(1, 2, left=0.075, right=0.978, top=0.735, bottom=0.185,
                          wspace=0.30)
    rows = []
    YEARS = [str(y) for y in range(2019, 2027)]

    def year_series(sql, keys, den_sql):
        got = {(y, k): n for y, k, n in q(con, sql)}
        den = dict(q(con, den_sql))
        return got, den

    # A -- assay mix over time. Lines, not a stack: a paper reports several
    # assays, so the shares do not partition and a stacked area would lie.
    mods = ["multiplex_imaging", "spatial_transcriptomics", "scRNA_seq", "histology"]
    got, den = year_series(
        f"""SELECT substr(pub_date, 1, 4), assay_type, count(DISTINCT doc_id)
            FROM assay_platform WHERE doc_type = 'corpus'
              AND assay_type IN ({",".join(repr(m) for m in mods)})
            GROUP BY 1, 2""",
        mods,
        """SELECT substr(pub_date, 1, 4), count(DISTINCT doc_id) FROM assay_platform
           WHERE doc_type = 'corpus' GROUP BY 1""")
    axA = fig.add_subplot(gs[0, 0])
    cols = {"multiplex_imaging": BLUE, "spatial_transcriptomics": AQUA,
            "scRNA_seq": ORANGE, "histology": MUTED}
    ends = {}
    for m in mods:
        ys = [100.0 * got.get((y, m), 0) / den[y] if den.get(y) else 0 for y in YEARS]
        axA.plot(range(len(YEARS)), ys, marker="o", markersize=5, linewidth=2.2,
                 color=cols[m])
        ends[m] = ys[-1]
        for i, y in enumerate(YEARS):
            rows.append(ROW(slide="1b", panel="A", population="HTAN corpus",
                            category=f"{m}|{y}", n_documents=got.get((y, m), 0),
                            denominator_documents=den.get(y, 0)))
    # direct labels at the right edge, pushed apart so two lines ending on the
    # same value cannot print on top of each other
    placed = []
    for m, v in sorted(ends.items(), key=lambda kv: -kv[1]):
        yy = v
        while any(abs(yy - p) < 5.5 for p in placed):
            yy -= 5.5
        placed.append(yy)
        axA.plot([len(YEARS) - 1, len(YEARS) - 0.72], [v, yy], color=cols[m],
                 linewidth=0.9, alpha=0.6)
        axA.text(len(YEARS) - 0.62, yy, NICE.get(m, m.replace("_", " ")),
                 fontsize=9.2, color=cols[m], va="center", fontweight="bold")
    axA.set_xticks(range(len(YEARS)))
    axA.set_xticklabels([y if y != "2026" else "2026*" for y in YEARS], fontsize=9.5)
    axA.set_xlim(-0.3, len(YEARS) + 1.9)
    axA.set_ylim(0, 100)
    axA.set_ylabel("% of that year's HTAN papers", fontsize=9, color=MUTED)
    axA.spines[["top", "right"]].set_visible(False)
    axA.grid(axis="y", color=GRID, linewidth=0.7)
    axA.set_axisbelow(True)
    axA.tick_params(length=0)
    denom_line = " · ".join(f"{y}: {den.get(y, 0)}" for y in YEARS)
    titled(axA, "A — The modality mix inverted",
           f"Papers per year with an assay record — {denom_line}. *2026 is partial. "
           f"Papers report several assays, so the lines do not sum to 100%: this is "
           f"prevalence, not composition.", wrap=88)

    # B -- study design over time
    designs = ["method_development", "cohort", "review", "longitudinal", "cross_sectional"]
    got2, den2 = year_series(
        f"""SELECT substr(pub_date, 1, 4), study_design, count(DISTINCT doc_id)
            FROM abstract_claim WHERE doc_type = 'corpus'
              AND study_design IN ({",".join(repr(d) for d in designs)})
            GROUP BY 1, 2""",
        designs,
        """SELECT substr(pub_date, 1, 4), count(DISTINCT doc_id) FROM abstract_claim
           WHERE doc_type = 'corpus' AND study_design NOT IN ('', 'not_stated')
           GROUP BY 1""")
    axB = fig.add_subplot(gs[0, 1])
    w = 0.16
    dcols = {"method_development": BLUE, "cohort": AQUA, "review": ORANGE,
             "longitudinal": "#4a3aa7", "cross_sectional": MUTED}
    for j, d in enumerate(designs):
        xs = [i + (j - 2) * w for i in range(len(YEARS))]
        vals = [got2.get((y, d), 0) for y in YEARS]
        axB.bar(xs, vals, width=w, color=dcols[d],
                label=d.replace("_", " "))
        for i, y in enumerate(YEARS):
            rows.append(ROW(slide="1b", panel="B", population="HTAN corpus",
                            category=f"{d}|{y}", n_documents=got2.get((y, d), 0),
                            denominator_documents=den2.get(y, 0)))
    axB.set_xticks(range(len(YEARS)))
    axB.set_xticklabels([y if y != "2026" else "2026*" for y in YEARS], fontsize=9.5)
    axB.set_ylabel("HTAN papers", fontsize=9, color=MUTED)
    axB.spines[["top", "right"]].set_visible(False)
    axB.grid(axis="y", color=GRID, linewidth=0.7)
    axB.set_axisbelow(True)
    axB.tick_params(length=0)
    axB.legend(frameon=False, fontsize=8.6, loc="upper left", ncol=2,
               handlelength=1.0, labelspacing=0.3)
    axB.set_ylim(0, max(got2.values()) * 1.75)
    titled(axB, "B — From building methods to running cohorts",
           f"Study design stated in the abstract, counts not shares. "
           f"{sum(den2.values())} corpus papers state a design; the rest state none. "
           f"Method development stays flat in absolute terms while cohort studies grow.",
           wrap=88)

    footer(fig, f"{CORPUS_RULE}  {C_PRECISION}  Year is publication year, so the shift lags "
                f"the work by the review cycle, and 2026 is a partial year. "
                f"Slide 7 carries the full caveats.")
    save(fig, "s1b_how_the_corpus_changed", rows, FIELDS, {
        "slide": "1b", "population": "HTAN corpus only",
        "A": {"class": "assay_platform", "denominator": "corpus papers per year with an "
              "assay record", "judged": False},
        "B": {"class": "abstract_claim", "attribute": "study_design",
              "model": STRONG_MODEL,
              "denominator": "corpus papers per year stating a design", "judged": False},
        "counting_rule": "distinct documents only"})


# ==========================================================================
# SLIDE 1c -- what gets written about vs what gets deposited

def slide1c(con):
    fig = plt.figure(figsize=(13.33, 7.5))
    deck(fig, "What gets written about is not what got collected",
         "HTAN's own papers against the HTAN Data Portal's released data, "
         "counted in patients.")
    gs = fig.add_gridspec(1, 3, left=0.152, right=0.965, top=0.735, bottom=0.205,
                          wspace=0.90, width_ratios=[1.0, 1.0, 1.15])
    rows = []

    parts, unmapped_p, total_p = portal_participants_by_assay_type()
    papers = dict(q(con, """SELECT assay_type, count(DISTINCT doc_id) FROM assay_platform
                            WHERE doc_type = 'corpus'
                              AND assay_type NOT IN ('not_stated', 'other') GROUP BY 1"""))
    paper_den = q(con, "SELECT count(DISTINCT doc_id) FROM assay_platform "
                       "WHERE doc_type = 'corpus'")[0][0]
    shared = sorted((t for t in parts if t in papers), key=lambda t: -papers[t])[:10]
    SHORTEN = {"mass_spectrometry_proteomics": "mass spec proteomics",
               "imaging_mass_cytometry": "imaging mass cytom."}
    lab = {t: SHORTEN.get(t, NICE.get(t, t.replace("_", " "))) for t in shared}

    # A -- papers
    panel(fig.add_subplot(gs[0, 0]), [lab[t] for t in shared],
          [papers[t] for t in shared], paper_den, "A — Papers",
          f"HTAN papers reporting each modality, of {paper_den} corpus papers with an "
          f"assay record.", colour=BLUE, unit="papers", wrap=38)
    rows += [ROW(slide="1c", panel="A", population="HTAN corpus papers", category=t,
                 n_documents=papers[t], denominator_documents=paper_den,
                 extra_measure="unit", extra_value="papers") for t in shared]

    # B -- patients, same modality order, so the two panels read as one figure
    axB = fig.add_subplot(gs[0, 1])
    y = list(range(len(shared)))
    vals = [parts[t] for t in shared]
    axB.barh(y, vals, color=ORANGE, height=0.66)
    axB.set_yticks(y)
    axB.set_yticklabels([lab[t] for t in shared], fontsize=10, color=INK)
    axB.invert_yaxis()
    for i, v in enumerate(vals):
        axB.text(v + max(vals) * 0.025, i, f"{v:,}", va="center", fontsize=9, color=INK)
    axB.set_xlim(0, max(vals) * 1.34)
    axB.set_xlabel(f"patients   (of {total_p:,} with released data)", fontsize=9, color=MUTED)
    axB.spines[["top", "right", "left"]].set_visible(False)
    axB.tick_params(length=0)
    axB.grid(axis="x", color=GRID, linewidth=0.7)
    axB.set_axisbelow(True)
    em_p, em_pap = parts.get("electron_microscopy", 0), papers.get("electron_microscopy", 0)
    titled(axB, "B — Patients",
           f"Patients with released data of each modality, portal database "
           f"htan_2026_922. Same order as panel A. Counted as distinct patients, not "
           f"files: electron microscopy is 110,398 files from {em_p} patients.", wrap=38)
    rows += [ROW(slide="1c", panel="B", population="HTAN Data Portal", category=t,
                 n_documents=parts[t], denominator_documents=total_p,
                 extra_measure="unit", extra_value="patients") for t in shared]

    # C -- the same decoupling at centre level
    centre_papers = dict(q(con, """SELECT trim(u), count(DISTINCT d.doc_id)
                                   FROM documents d, UNNEST(string_split(d.group_key, ';')) t(u)
                                   WHERE d.doc_type = 'corpus' AND d.group_key IS NOT NULL
                                   GROUP BY 1"""))
    atlas_parts = {r["atlas_name"]: int(r["participants"])
                   for r in _read_dcc("portal_atlas_participants.csv")}
    by_atlas: dict[str, int] = {}
    no_atlas = []
    for centre, n_pap in centre_papers.items():
        a = CENTRE_TO_ATLAS.get(centre, "__unknown__")
        if a is None:
            no_atlas.append((centre, n_pap))
        elif a != "__unknown__":
            by_atlas[a] = by_atlas.get(a, 0) + n_pap

    axC = fig.add_subplot(gs[0, 2])
    # label offsets are staggered by hand where atlases collide near the origin
    NUDGE = {"HTAN SRRS": (10, -3), "HTAN TNP SARDANA": (10, -13),
             "HTAN TNP - TMA": (9, 5), "HTAN HTAPP": (9, 4),
             "HTAN MSK": (9, -10), "HTAN DFCI": (9, -10), "HTAN BU": (9, 5),
             "HTAN HMS": (9, -11), "HTAN Vanderbilt": (9, 5),
             "HTAN CHOP": (-9, 6), "HTAN OHSU": (9, -4),
             "HTAN Stanford": (10, 4), "HTAN WUSTL": (9, 4), "HTAN Duke": (9, 0)}
    for a, pt in sorted(atlas_parts.items(), key=lambda kv: -kv[1]):
        pap = by_atlas.get(a, 0)
        colour = BLUE if pap else MUTED
        axC.scatter([pap], [pt], s=64, color=colour, zorder=4,
                    edgecolor="white", linewidth=1.2)
        dx, dy = NUDGE.get(a, (9, 4))
        axC.annotate(a.replace("HTAN ", ""), (pap, pt), textcoords="offset points",
                     xytext=(dx, dy), ha=("left" if dx > 0 else "right"),
                     fontsize=8.6, color=INK if pap else MUTED, zorder=5)
        rows.append(ROW(slide="1c", panel="C", population=a, category="atlas",
                        n_documents=pap, denominator_documents=pt,
                        extra_measure="patients_with_released_data", extra_value=pt))
    axC.set_xlim(-2.5, 35)
    axC.set_ylim(-95, 950)
    axC.set_yticks([0, 200, 400, 600, 800])
    axC.set_xlabel("papers from that centre", fontsize=9, color=MUTED)
    axC.set_ylabel("patients with released data", fontsize=9, color=MUTED)
    axC.spines[["top", "right"]].set_visible(False)
    axC.grid(color=GRID, linewidth=0.7)
    axC.set_axisbelow(True)
    axC.tick_params(length=0)
    miss = ", ".join(f"{c.split(' (')[0]} ({n})" for c, n in
                     sorted(no_atlas, key=lambda kv: -kv[1]))
    titled(axC, "C — Same at centre level",
           f"One point per released atlas. Grey = an atlas with no paper in the corpus. "
           f"Three centres publish but have no released atlas, so they cannot be "
           f"plotted — {miss} papers. Centre-to-atlas mapping is in the script.",
           wrap=44)

    footer(fig, f"{CORPUS_RULE}  {C_PRECISION}  Patients are distinct demographics records "
                f"on released files; {total_p:,} of 2,917 HTAN participants have at least one "
                f"released file linked this way. Panels A and B count different things on "
                f"purpose — papers and patients — and a centre that publishes early on few "
                f"patients is not doing worse work than one that deposits many. The portal's "
                f"assay vocabulary and the extraction's assay_type vocabulary were authored "
                f"independently; both crosswalks are in the script and unmapped values are in "
                f"the backing CSV. Portal snapshot htan_2026_922; corpus snapshot 2026-08-21. "
                f"Slide 7 carries the full caveats.")
    save(fig, "s1c_papers_vs_deposits", rows, FIELDS, {
        "slide": "1c",
        "A": {"class": "assay_platform", "unit": "papers",
              "denominator": f"{paper_den} corpus papers"},
        "B": {"source": "HTAN Data Portal ClickHouse htan_2026_922 via htan CLI",
              "unit": "patients (distinct demographicsIds on released files)",
              "denominator": f"{total_p} participants with a released file",
              "crosswalk": "PORTAL_TO_ASSAY_TYPE / SQL multiIf in the pull",
              "unmapped_group_participants": unmapped_p},
        "C": {"unit": "papers vs patients per atlas",
              "crosswalk": "CENTRE_TO_ATLAS in scripts/spatial_slides.py",
              "centres_with_no_released_atlas": [c for c, _ in no_atlas]},
        "counting_rule": "distinct documents (A), distinct patients (B, C); never summed "
                         "across modality groups because patients overlap"})


# ==========================================================================
# SLIDE 2 -- how the spatial atlases were made (corpus only)

def slide2(con):
    fig = plt.figure(figsize=(13.33, 7.5))
    n_sp = q(con, "SELECT count(*) FROM spatial_corpus")[0][0]
    deck(fig, "How the spatial atlases were made",
         f"The {n_sp} HTAN papers reporting a spatial assay. Still no citing papers.")
    gs = fig.add_gridspec(1, 3, left=0.145, right=0.972, top=0.705, bottom=0.165,
                          wspace=0.58)
    rows = []

    # A -- is the instrument named at all, and how many distinct names appear
    inst = q(con, f"""SELECT assay_type, count(DISTINCT doc_id),
                 count(DISTINCT CASE WHEN coalesce(nullif(platform, ''), 'not_stated')
                                     <> 'not_stated' THEN doc_id END),
                 count(DISTINCT CASE WHEN coalesce(nullif(platform, ''), 'not_stated')
                                     <> 'not_stated' THEN lower(regexp_replace(
                     coalesce(nullif(canonical_platform, ''), platform), '[ _.-]', '', 'g')) END)
              FROM assay_platform WHERE doc_type = 'corpus' AND assay_type IN {SP_SQL}
              GROUP BY 1 ORDER BY 2 DESC""")
    axA = fig.add_subplot(gs[0, 0])
    y = list(range(len(inst)))
    axA.barh(y, [r[1] for r in inst], color=PALE, height=0.62)
    axA.barh(y, [r[2] for r in inst], color=BLUE, height=0.62)
    axA.set_yticks(y)
    axA.set_yticklabels([NICE[r[0]] for r in inst], fontsize=10, color=INK)
    axA.invert_yaxis()
    for i, r in enumerate(inst):
        axA.text(r[1] + 1.2, i, f"{r[2]} of {r[1]}  ·  {r[3]} names",
                 va="center", fontsize=8.6, color=INK)
    axA.set_xlim(0, max(r[1] for r in inst) * 1.95)
    axA.set_xlabel("papers reporting this assay", fontsize=9, color=MUTED)
    axA.spines[["top", "right", "left"]].set_visible(False)
    axA.tick_params(length=0)
    axA.grid(axis="x", color=GRID, linewidth=0.7)
    axA.set_axisbelow(True)
    axA.legend(handles=[Patch(facecolor=BLUE, label="names the instrument"),
                        Patch(facecolor=PALE, label="does not")],
               frameon=False, fontsize=8.6, loc="lower right", handlelength=1.1)
    note = ("Blue = papers naming a specific instrument. The trailing count is how many "
            "DISTINCT instrument strings those papers use between them — canonicalisation "
            "does not collapse the variants.")
    titled(axA, "A — Is the instrument named?", note, wrap=44)
    rows += [ROW(slide=2, panel="A", population="HTAN spatial corpus", category=r[0],
                 n_documents=r[2], denominator_documents=r[1],
                 extra_measure="distinct instrument strings", extra_value=r[3]) for r in inst]

    # B -- vendors
    ven = q(con, f"""SELECT coalesce(nullif(canonical_vendor, ''), vendor) AS v,
                            count(DISTINCT doc_id) FROM assay_platform
              WHERE doc_type = 'corpus' AND assay_type IN {SP_SQL}
                AND coalesce(nullif(vendor, ''), 'not_stated') <> 'not_stated'
              GROUP BY 1 ORDER BY 2 DESC LIMIT 10""")
    ven_docs = q(con, f"""SELECT count(DISTINCT doc_id) FROM assay_platform
              WHERE doc_type = 'corpus' AND assay_type IN {SP_SQL}
                AND coalesce(nullif(vendor, ''), 'not_stated') <> 'not_stated'""")[0][0]
    panel(fig.add_subplot(gs[0, 1]), [v for v, _ in ven], [n for _, n in ven], n_sp,
          "B — Whose instruments",
          f"Vendors named in the {n_sp} spatial papers. {ven_docs} of {n_sp} name any vendor; "
          f"the other {n_sp - ven_docs} name none. Top 10 shown.", colour=BLUE, wrap=42)
    rows += [ROW(slide=2, panel="B", population="HTAN spatial corpus", category=v,
                 n_documents=n, denominator_documents=n_sp) for v, n in ven]

    # C -- what the data is on disk
    fam = q(con, """SELECT upper(regexp_replace(coalesce(nullif(canonical_format, ''), format),
                                                '[ _.-]', '', 'g')) AS f,
                           count(DISTINCT doc_id) FROM object_format
              JOIN spatial_corpus USING (doc_id)
              WHERE coalesce(nullif(format, ''), 'not_stated') <> 'not_stated'
              GROUP BY 1 ORDER BY 2 DESC LIMIT 10""")
    fam_docs = q(con, """SELECT count(DISTINCT doc_id) FROM object_format
              JOIN spatial_corpus USING (doc_id)
              WHERE coalesce(nullif(format, ''), 'not_stated') <> 'not_stated'""")[0][0]
    panel(fig.add_subplot(gs[0, 2]), [f for f, _ in fam], [n for _, n in fam], n_sp,
          "C — What it is on disk",
          f"File formats named in the {n_sp} spatial papers. Only {fam_docs} of {n_sp} name any "
          f"format at all. OME-TIFF is the imaging container; RCPNL and QPTIFF are vendor "
          f"formats. Top 10 shown.", colour=BLUE, wrap=42)
    rows += [ROW(slide=2, panel="C", population="HTAN spatial corpus", category=f,
                 n_documents=n, denominator_documents=n_sp) for f, n in fam]

    footer(fig, f"{CORPUS_RULE}  {C_PRECISION}  Platform and vendor are stated in only about "
                f"40% of extracted records, so panels A and B count papers that SAY, not papers "
                f"that DID. Slide 7 carries the full caveats.")
    save(fig, "s2_how_they_were_made", rows, FIELDS, {
        "slide": 2, "population": f"{n_sp} HTAN corpus papers with a spatial assay",
        "A": {"class": "assay_platform", "attributes": "assay_type, platform, canonical_platform",
              "denominator": "papers reporting that spatial assay", "judged": False},
        "B": {"class": "assay_platform", "attributes": "vendor, canonical_vendor",
              "denominator": f"{n_sp} spatial corpus papers", "judged": False},
        "C": {"class": "object_format", "attributes": "format, canonical_format",
              "denominator": f"{n_sp} spatial corpus papers", "judged": False},
        "counting_rule": "distinct documents and distinct values only"})


# ==========================================================================
# SLIDE 3 -- how the spatial atlases were analysed (corpus only)

def slide3(con):
    fig = plt.figure(figsize=(13.33, 7.5))
    n_sp = q(con, "SELECT count(*) FROM spatial_corpus")[0][0]
    deck(fig, "How the spatial atlases were analysed",
         f"The same {n_sp} HTAN spatial papers. Still no citing papers.")
    gs = fig.add_gridspec(1, 2, left=0.185, right=0.975, top=0.735, bottom=0.155,
                          wspace=0.70)
    rows = []

    ct = q(con, """SELECT step, count(DISTINCT doc_id) FROM cell_typing
                   JOIN spatial_corpus USING (doc_id) WHERE step <> 'not_stated'
                   GROUP BY 1 ORDER BY 2 DESC""")
    ct_den = q(con, """SELECT count(DISTINCT doc_id) FROM cell_typing
                       JOIN spatial_corpus USING (doc_id)""")[0][0]
    lab = {"segmentation_based_phenotyping": "segmentation-based\ncell definition"}
    panel(fig.add_subplot(gs[0, 0]), [lab.get(s, s.replace("_", " ")) for s, _ in ct],
          [n for _, n in ct], ct_den, "A — How cells are defined",
          f"{ct_den} of the {n_sp} spatial papers describe a cell-typing step. Papers use "
          f"several steps, so bars do not sum to {ct_den}.", colour=BLUE, wrap=70)
    rows += [ROW(slide=3, panel="A", population="HTAN spatial corpus", category=s,
                 n_documents=n, denominator_documents=ct_den) for s, n in ct]

    tme = q(con, """SELECT category, count(DISTINCT doc_id) FROM tme_algorithm
                    JOIN spatial_corpus USING (doc_id)
                    WHERE category NOT IN ('not_stated', 'other',
                                           'segmentation_based_phenotyping')
                    GROUP BY 1 ORDER BY 2 DESC""")
    tme_den = q(con, """SELECT count(DISTINCT doc_id) FROM tme_algorithm
                        JOIN spatial_corpus USING (doc_id)""")[0][0]
    tlab = {"tumor_microenvironment_classification": "TME classification",
            "ecotype_or_community_detection": "ecotype / community\ndetection",
            "cell_cell_interaction": "cell–cell interaction",
            "ligand_receptor_analysis": "ligand–receptor analysis"}
    panel(fig.add_subplot(gs[0, 1]), [tlab.get(c, c.replace("_", " ")) for c, _ in tme],
          [n for _, n in tme], tme_den, "B — How the microenvironment is read",
          f"{tme_den} of the {n_sp} spatial papers describe a microenvironment method. "
          f"'other' is excluded: it is the largest bucket and holds generic single-cell "
          f"methods, not TME methods.", colour=BLUE, wrap=70)
    rows += [ROW(slide=3, panel="B", population="HTAN spatial corpus", category=c,
                 n_documents=n, denominator_documents=tme_den) for c, n in tme]

    footer(fig, f"{CORPUS_RULE}  {C_PRECISION}  An extracted method is one the paper MENTIONS; "
                f"neither class distinguishes a method the authors ran from one they cite. "
                f"Slide 7 carries the full caveats.")
    save(fig, "s3_how_they_were_analysed", rows, FIELDS, {
        "slide": 3, "population": f"{n_sp} HTAN corpus papers with a spatial assay",
        "A": {"class": "cell_typing", "attribute": "step",
              "denominator": f"{ct_den} spatial corpus papers with a cell_typing record",
              "judged": False},
        "B": {"class": "tme_algorithm", "attribute": "category",
              "denominator": f"{tme_den} spatial corpus papers with a tme_algorithm record",
              "filters": "category not in (not_stated, other, segmentation_based_phenotyping)",
              "judged": False},
        "counting_rule": "distinct documents only"})


# ==========================================================================
# SLIDE 4 -- now the citing literature

def slide4(con):
    fig = plt.figure(figsize=(13.33, 7.5))
    deck(fig, "Now the citing literature: who is reading the map",
         "9,753 papers cite HTAN. Everything on this slide is a lower bound.")
    gs = fig.add_gridspec(1, 3, left=0.070, right=0.978, top=0.735, bottom=0.165,
                          wspace=0.46, width_ratios=[1.25, 1.0, 0.95])
    rows = []

    # A -- the field turns spatial (abstract pass, strong model, widest reach)
    tr = q(con, """WITH ex AS (
              SELECT doc_id, CASE WHEN author_overlap = 'external' THEN 'external'
                                  ELSE 'internal' END AS grp,
                     CAST(substr(pub_date, 1, 4) AS INT) AS yr, trim(u) AS v
              FROM abstract_claim, UNNEST(string_split(key_methods, ';')) t(u)
              WHERE doc_type = 'citing' AND CAST(substr(pub_date, 1, 4) AS INT) BETWEEN 2020 AND 2026),
            f AS (SELECT doc_id, grp, yr,
                    max(CASE WHEN v IN ('spatial_transcriptomics','multiplex_imaging',
                                        'spatial_proteomics') THEN 1 ELSE 0 END) sp
                  FROM ex GROUP BY 1,2,3)
            SELECT grp, yr, count(DISTINCT doc_id),
                   count(DISTINCT CASE WHEN sp = 1 THEN doc_id END)
            FROM f GROUP BY 1,2 ORDER BY 1,2""")
    by = {}
    for g, yr, n, ns in tr:
        by.setdefault(g, {})[yr] = (n, ns)
    years = sorted(by["external"])
    axA = fig.add_subplot(gs[0, 0])
    w = 0.38
    for off, (g, colour, lbl) in enumerate([("external", ORANGE, "external authors"),
                                            ("internal", AQUA, "shared HTAN authorship")]):
        xs = [i + (off - 0.5) * w for i in range(len(years))]
        vals = [100.0 * by[g][y][1] / by[g][y][0] for y in years]
        bars = axA.bar(xs, vals, width=w, color=colour, label=lbl)
        bars[-1].set_hatch("///")
        bars[-1].set_edgecolor("white")
        for x, v in zip(xs, vals):
            axA.text(x, v + 1.0, f"{v:.0f}", ha="center", fontsize=8.4, color=INK)
    axA.set_xticks(range(len(years)))
    axA.set_xticklabels([str(y) if y != 2026 else "2026*" for y in years], fontsize=9.5)
    axA.set_ylim(0, 50)
    axA.set_ylabel("% of that year's citing abstracts", fontsize=9, color=MUTED)
    axA.spines[["top", "right"]].set_visible(False)
    axA.grid(axis="y", color=GRID, linewidth=0.7)
    axA.set_axisbelow(True)
    axA.tick_params(length=0)
    axA.legend(frameon=False, fontsize=9, loc="upper left", handlelength=1.1)
    tot = sum(v[0] for g in by for v in by[g].values())
    note = (f"Share of citing abstracts naming a spatial method. {tot:,} citing papers "
            f"2020–2026. *2026 is Jan–Aug. This is the one panel NOT a floor: the abstract "
            f"pass ran on the strong model over every paper.")
    titled(axA, "A — The field turns spatial", note, wrap=56)
    rows += [ROW(slide=4, panel="A", population=f"citing, {g}", category=str(y),
                 n_documents=by[g][y][1], denominator_documents=by[g][y][0])
             for g in by for y in years]

    # B -- declared engagement, external vs shared authorship
    attempted = provenance_attempted()
    con.execute("CREATE OR REPLACE TABLE prov_attempted (doc_id VARCHAR)")
    con.executemany("INSERT INTO prov_attempted VALUES (?)", [(d,) for d in sorted(attempted)])
    base = """WITH b AS (SELECT p.doc_id, CASE WHEN d.author_overlap = 'external'
                            THEN 'external' ELSE 'internal' END AS grp
                  FROM prov_attempted p JOIN documents d USING (doc_id)
                  JOIN spatial_citing s USING (doc_id) WHERE d.doc_type = 'citing'),
              ek AS (SELECT DISTINCT doc_id, trim(u) AS kind FROM engagement,
                     UNNEST(string_split(engagement_kind, ';')) t(u))"""
    eden = dict(q(con, base + " SELECT grp, count(*) FROM b GROUP BY 1"))
    eng = {(g, k): n for g, k, n in q(con, base + """ SELECT b.grp, ek.kind,
              count(DISTINCT b.doc_id) FROM b JOIN ek USING (doc_id) GROUP BY 1,2""")}
    kinds = ["background_citation", "data_reuse", "comparison", "method_reuse", "tool_reuse"]
    axB = fig.add_subplot(gs[0, 1])
    y = list(range(len(kinds)))
    hh = 0.36
    for off, (g, colour, lbl) in enumerate(
            [("internal", AQUA, f"shared HTAN authorship, n={eden['internal']}"),
             ("external", ORANGE, f"external authors, n={eden['external']:,}")]):
        vals = [100.0 * eng.get((g, k), 0) / eden[g] for k in kinds]
        ys = [i + (0.5 - off) * hh for i in y]
        axB.barh(ys, vals, height=hh, color=colour)
        for j, (yy, v, k) in enumerate(zip(ys, vals, kinds)):
            # the two series are direct-labelled on the top category instead of
            # carrying a legend box, so identity is never colour-alone
            tail = f"   {lbl}" if j == 0 else ""
            axB.text(v + 0.3, yy, f"{v:.1f}%  ({eng.get((g, k), 0)}){tail}",
                     va="center", fontsize=8.4, color=INK)
        rows.extend(ROW(slide=4, panel="B", population=f"citing, {g}", category=k,
                        n_documents=eng.get((g, k), 0), denominator_documents=eden[g])
                    for k in kinds)
    axB.set_yticks(y)
    axB.set_yticklabels([k.replace("_", " ") for k in kinds], fontsize=10, color=INK)
    axB.invert_yaxis()
    axB.set_xlim(0, 31)
    axB.set_xticks([0, 5, 10, 15, 20])
    axB.set_xlabel("% of spatial citing papers read", fontsize=9, color=MUTED)
    axB.spines[["top", "right", "left"]].set_visible(False)
    axB.tick_params(length=0)
    axB.grid(axis="x", color=GRID, linewidth=0.7)
    axB.set_axisbelow(True)
    note = (f"Reuse is declared three times more often by papers with an HTAN author. "
            f"The provenance pass read {len(attempted):,} of 9,753 citing papers; these bars "
            f"use the {eden['external'] + eden['internal']:,} of those that are spatial.")
    titled(axB, "B — What citing papers did", note, wrap=44)

    # C -- can you even tell it was HTAN's data?
    vis = q(con, """WITH b AS (SELECT a.*, CASE WHEN a.author_overlap = 'external'
                        THEN 'external' ELSE 'internal' END AS grp
                    FROM data_availability a JOIN spatial_citing s USING (doc_id)),
                  g AS (SELECT grp, doc_id, bool_or(
                      regexp_matches(coalesce(accession, ''), '(?i)phs002371')
                      OR regexp_matches(coalesce(accession, ''), '(?i)^syn[0-9]{5,}')
                      OR lower(coalesce(source_quote, '')) LIKE '%htan%'
                      OR lower(coalesce(source_quote, '')) LIKE '%human tumor atlas%') AS h
                    FROM b GROUP BY 1, 2)
                  SELECT grp, count(*), count(*) FILTER (h) FROM g GROUP BY 1""")
    vm = {g: (d, h) for g, d, h in vis}
    corpus_vis = q(con, """WITH g AS (SELECT doc_id, bool_or(
                      regexp_matches(coalesce(accession, ''), '(?i)phs002371')
                      OR regexp_matches(coalesce(accession, ''), '(?i)^syn[0-9]{5,}')
                      OR lower(coalesce(source_quote, '')) LIKE '%htan%'
                      OR lower(coalesce(source_quote, '')) LIKE '%human tumor atlas%') AS h
                    FROM data_availability JOIN spatial_corpus USING (doc_id) GROUP BY 1)
                  SELECT count(*), count(*) FILTER (h) FROM g""")[0]
    order = [("HTAN's own papers", corpus_vis[1], corpus_vis[0], BLUE),
             ("shared HTAN authorship", vm["internal"][1], vm["internal"][0], AQUA),
             ("external authors", vm["external"][1], vm["external"][0], ORANGE)]
    axC = fig.add_subplot(gs[0, 2])
    pct = [100.0 * h / d for _, h, d, _ in order]
    axC.barh(range(3), pct, color=[c for *_, c in order], height=0.50)
    axC.set_yticks(range(3))
    axC.set_yticklabels([l for l, *_ in order], fontsize=10, color=INK)
    axC.invert_yaxis()
    for i, (_, h, d, _) in enumerate(order):
        axC.text(pct[i] + 1.0, i, f"{pct[i]:.1f}%   ({h} of {d:,})", va="center",
                 fontsize=9, color=INK)
        rows.append(ROW(slide=4, panel="C", population=order[i][0],
                        category="availability text names HTAN",
                        n_documents=h, denominator_documents=d))
    axC.set_ylim(2.7, -0.7)
    axC.set_xlim(0, 68)
    axC.set_xlabel("% of spatial papers", fontsize=9, color=MUTED)
    axC.spines[["top", "right", "left"]].set_visible(False)
    axC.tick_params(length=0)
    axC.grid(axis="x", color=GRID, linewidth=0.7)
    axC.set_axisbelow(True)
    note = ("Does the availability text name HTAN, phs002371 or a syn ID? This is "
            "VISIBILITY, not compliance — the denominator is papers that cite HTAN, not "
            "papers that reused HTAN data. HTAN's own 40% sets the ceiling.")
    titled(axC, "C — Can you tell it was HTAN?", note, wrap=42)

    footer(fig, f"{C_FLOOR}  {C_PRECISION}  {C_REACH}  Citing a paper is not using its data. "
                f"Of the 184 citing papers that stated how they got data, only 20 gave a "
                f"resolvable identifier — 15 dbGaP phs002371 and 5 Synapse/HTAN IDs.")
    save(fig, "s4_who_is_reading", rows, FIELDS, {
        "slide": 4, "population": "9,753 citing papers",
        "A": {"class": "abstract_claim", "model": "gemini-3.1-pro-preview (strong)",
              "denominator": "citing papers 2020-2026 with an abstract record",
              "note": "not subject to the small-model gap", "judged": False},
        "B": {"class": "engagement", "denominator":
              "spatial citing papers the provenance pass attempted", "judged": True,
              "judge_rejected": "77/1437 = 5.4%"},
        "C": {"class": "data_availability", "denominator":
              "spatial papers with a data_availability record", "judged": False},
        "counting_rule": "distinct documents only"})


# ==========================================================================
# SLIDE 5 -- how far to trust it

def slide5(con):
    fig = plt.figure(figsize=(13.33, 7.5))
    deck(fig, "How far to trust every number in this deck",
         "Slides 1–6 state results. This one states how far they can be pushed.")
    gs = fig.add_gridspec(1, 3, left=0.135, right=0.978, top=0.700, bottom=0.185,
                          wspace=0.62)
    rows = []

    gap = json.load(open(HTAN / "model_gap_500_sample.json"))
    flat = sorted(((c, v) for p in gap.values() for c, v in p["classes"].items()),
                  key=lambda kv: kv[1]["small_recall_vs_strong"])
    n_s = list(gap.values())[0]["n_sample_docs"]
    axA = fig.add_subplot(gs[0, 0])
    vals = [100 * v["small_recall_vs_strong"] for _, v in flat]
    axA.barh(range(len(flat)), vals, color=ORANGE, height=0.62)
    axA.set_yticks(range(len(flat)))
    axA.set_yticklabels([c.replace("_", " ") for c, _ in flat], fontsize=10, color=INK)
    axA.invert_yaxis()
    for i, v in enumerate(vals):
        axA.text(v + 2, i, f"misses {100 - v:.0f}%", va="center", fontsize=9, color=INK)
        rows.append(ROW(slide=5, panel="A", population="500-document sample",
                        category=flat[i][0], n_documents="", denominator_documents=n_s,
                        extra_measure="small_recall_vs_strong",
                        extra_value=flat[i][1]["small_recall_vs_strong"]))
    axA.axvline(100, color=MUTED, linewidth=0.9, linestyle=(0, (3, 3)))
    axA.set_xlim(0, 138)
    axA.set_xlabel("small-model recall vs the strong model", fontsize=9, color=MUTED)
    axA.spines[["top", "right", "left"]].set_visible(False)
    axA.tick_params(length=0)
    axA.grid(axis="x", color=GRID, linewidth=0.7)
    axA.set_axisbelow(True)
    titled(axA, "A — Citing counts are floors",
           f"Measured on {n_s} sampled citing papers: how much of what the strong model "
           f"finds the small model misses. Slide 6 panel A is exempt.", wrap=42)

    jr = q(con, f"""SELECT extraction_class, count(*),
                 sum(CASE WHEN judge_verdict IS NOT NULL THEN 1 ELSE 0 END),
                 sum(CASE WHEN judge_verdict = 'rejected' THEN 1 ELSE 0 END)
              FROM read_json_auto('{HTAN / 'silver' / '*.jsonl'}', union_by_name=true)
              GROUP BY 1 ORDER BY 2 DESC""")
    axB = fig.add_subplot(gs[0, 1])
    sh = [100.0 * r[2] / r[1] for r in jr]
    axB.barh(range(len(jr)), sh, color=[AQUA if s else GRID for s in sh], height=0.62)
    axB.set_yticks(range(len(jr)))
    axB.set_yticklabels([r[0].replace("_", " ") for r in jr], fontsize=10, color=INK)
    axB.invert_yaxis()
    for i, r in enumerate(jr):
        txt = (f"all {r[1]:,} judged, {100.0 * r[3] / r[2]:.0f}% rejected" if r[2]
               else f"none of {r[1]:,} judged")
        axB.text(max(sh[i], 0) + 4, i, txt, va="center", fontsize=8.4, color=INK)
        rows.append(ROW(slide=5, panel="B", population="all stored records",
                        category=r[0], n_documents=r[2], denominator_documents=r[1],
                        extra_measure="records_rejected", extra_value=r[3]))
    axB.set_xlim(0, 260)
    axB.set_xticks([0, 50, 100])
    axB.set_xlabel("% of records carrying a judge verdict", fontsize=9, color=MUTED)
    axB.spines[["top", "right", "left"]].set_visible(False)
    axB.tick_params(length=0)
    axB.grid(axis="x", color=GRID, linewidth=0.7)
    axB.set_axisbelow(True)
    titled(axB, "B — Precision is unmeasured",
           "0 of the 150 required human gold labels exist (§11.3 unmet). Only two of nine "
           "classes ever reached the second-model judge; the other seven have no verdict on "
           "any record.", wrap=42)

    reach = {(d, s): n for d, s, n in q(con, "SELECT doc_type, oa_status, count(*) "
                                             "FROM documents GROUP BY 1, 2")}
    order = ["fulltext", "abstract_only", "unavailable", "preprint_requester_pays_pending"]
    nice = {"fulltext": "full text read", "abstract_only": "abstract only",
            "unavailable": "no full-text route",
            "preprint_requester_pays_pending": "requester-pays, not fetched"}
    cmap = {"fulltext": BLUE, "abstract_only": AQUA, "unavailable": ORANGE,
            "preprint_requester_pays_pending": GRID}
    axC = fig.add_subplot(gs[0, 2])
    tot = {d: sum(n for (dd, _), n in reach.items() if dd == d) for d in ("corpus", "citing")}
    for j, dt in enumerate(("corpus", "citing")):
        left = 0.0
        for s in order:
            v = reach.get((dt, s), 0)
            if not v:
                continue
            p = 100.0 * v / tot[dt]
            axC.barh([j], [p], left=left, height=0.40, color=cmap[s], edgecolor="white",
                     linewidth=1.6)
            if p > 8:
                axC.text(left + p / 2, j, f"{v:,}", ha="center", va="center", fontsize=9,
                         color="white" if s != "abstract_only" else INK)
            left += p
            rows.append(ROW(slide=5, panel="C", population=dt, category=s,
                            n_documents=v, denominator_documents=tot[dt]))
    axC.set_yticks([0, 1])
    axC.set_yticklabels([f"HTAN corpus\nn = {tot['corpus']:,}",
                         f"citing\nn = {tot['citing']:,}"], fontsize=10, color=INK,
                        linespacing=1.4)
    axC.set_ylim(1.75, -0.75)
    axC.set_xlim(0, 100)
    axC.set_xlabel("% of documents", fontsize=9, color=MUTED)
    axC.spines[["top", "right", "left"]].set_visible(False)
    axC.tick_params(length=0)
    axC.grid(axis="x", color=GRID, linewidth=0.7)
    axC.set_axisbelow(True)
    axC.legend(handles=[Patch(facecolor=cmap[s], label=nice[s]) for s in order],
               frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0.0, 0.62),
               handlelength=1.1, labelspacing=0.45)
    titled(axC, "C — What could be read",
           f"{reach.get(('citing', 'unavailable'), 0)} citing papers have no full-text route "
           f"and {reach.get(('citing', 'preprint_requester_pays_pending'), 0)} preprints sit "
           f"in unfetched requester-pays buckets. Both are abstract-only.", wrap=42)

    footer(fig, "On the identical 5,071 citing papers the two models found engagement in 568 "
                "vs 228 papers, overlapping on only 215 — document-level disagreement is worse "
                "than the record-level gap in panel A suggests. " + CORPUS_RULE)
    save(fig, "s5_how_far_to_trust", rows, FIELDS, {
        "slide": 5,
        "A": {"source": "model_gap_500_sample.json", "denominator": f"{n_s} sampled citing papers"},
        "B": {"source": "silver/records_*.jsonl", "denominator": "all stored records per class"},
        "C": {"source": "documents.jsonl", "denominator": "all documents per doc_type"},
        "counting_rule": "this slide counts records on purpose: it is about record provenance"})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    for fn in (slide1, slide1b, slide1c, slide2, slide3, slide4, slide5):
        print(f"{fn.__name__}:")
        fn(con)
    json.dump({
        "generated_from": "scripts/spatial_slides.py",
        "community": "htan",
        "structure": "slides 1-3 are HTAN corpus only; slide 4 adds citing papers; "
                     "slide 5 is the caveat slide",
        "spatial_assay_types": list(SPATIAL),
        "spatial_document_definition":
            "a document with >=1 non-rejected assay_platform record whose assay_type is in "
            "spatial_assay_types",
        "counting_rule":
            "distinct-document and distinct-value counts only. Corpus papers were extracted "
            "twice (strong + small model over the same 157 full-text papers) and the "
            "provenance pass ran both models over the same 5,071 citing papers, so summed "
            "record counts would double-count documents. No figure sums records.",
        "palette": {"source": "dataviz reference palette, categorical slots 1-3 (light)",
                    "corpus": BLUE, "citing_shared_author": AQUA, "citing_external": ORANGE,
                    "validated": "validate_palette.js --pairs all: all checks pass"},
        "standing_caveats": {"precision": C_PRECISION, "floors": C_FLOOR, "reach": C_REACH},
        "figures": MANIFEST}, open(OUT / "slide_manifest.json", "w"), indent=2)
    print(f"\nwrote {OUT / 'slide_manifest.json'}")


if __name__ == "__main__":
    main()
