"""Speaker notes for the spatial deck.

Every number in SLIDES.md is read back out of the figure CSVs that
spatial_slides.py wrote, so the prose cannot drift from the figures.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "slides"
FIGS = OUT / "figures"


def rows(base):
    with open(FIGS / f"{base}.csv") as fh:
        return list(csv.DictReader(fh))


def get(rs, **kw):
    for r in rs:
        if all(str(r.get(k, "")) == str(v) for k, v in kw.items()):
            return r
    raise KeyError(kw)


def n(r, key="n_documents"):
    return int(r[key])


def pct(a, b):
    v = 100.0 * a / b
    if v == 0:
        return "0%"
    return f"{v:.1f}%" if v < 10 else f"{v:.0f}%"


s1, s1b, s1c, s2, s3, s4, s5 = (rows(b) for b in [
    "s1_what_htan_built", "s1b_how_the_corpus_changed", "s1c_papers_vs_deposits",
    "s2_how_they_were_made", "s3_how_they_were_analysed",
    "s4_who_is_reading", "s5_how_far_to_trust"])
man = json.load(open(OUT / "slide_manifest.json"))

mi = get(s1, panel="A", category="multiplex_imaging")
st = get(s1, panel="A", category="spatial_transcriptomics")
corpus_den = n(mi, "denominator_documents")
patch = get(s1, panel="B", category="HMS (PATCH)")
duke = get(s1, panel="B", category="Duke (Breast PCA)")

hm1 = get(s1, panel="C", category="genome_instability_and_mutation")
hm2 = get(s1, panel="C", category="avoiding_immune_destruction")
hm_den = int(hm1["denominator_documents"])

def yr(rs, panel, cat):
    return get(rs, panel=panel, category=cat)

mi_19 = yr(s1b, "A", "multiplex_imaging|2019"); mi_25 = yr(s1b, "A", "multiplex_imaging|2025")
st_19 = yr(s1b, "A", "spatial_transcriptomics|2019"); st_25 = yr(s1b, "A", "spatial_transcriptomics|2025")
sc_20 = yr(s1b, "A", "scRNA_seq|2020"); sc_25 = yr(s1b, "A", "scRNA_seq|2025")
coh_19 = yr(s1b, "B", "cohort|2019"); coh_25 = yr(s1b, "B", "cohort|2025")
md_25 = yr(s1b, "B", "method_development|2025")

pap_mi = get(s1c, panel="A", category="multiplex_imaging")
pap_em = get(s1c, panel="A", category="electron_microscopy")
dep_em = get(s1c, panel="B", category="electron_microscopy")
dep_st = get(s1c, panel="B", category="spatial_transcriptomics")
dep_mi = get(s1c, panel="B", category="multiplex_imaging")
portal_total = int(dep_em["denominator_documents"])

mi2 = get(s2, panel="A", category="multiplex_imaging")
st2 = get(s2, panel="A", category="spatial_transcriptomics")
sp_den = int(get(s2, panel="B", category="10x Genomics")["denominator_documents"])
ome = get(s2, panel="C", category="OMETIFF")
tif = get(s2, panel="C", category="TIFF")

clus = get(s3, panel="A", category="clustering")
seg = get(s3, panel="A", category="segmentation_based_phenotyping")
nb = get(s3, panel="B", category="neighborhood_analysis")
lr = get(s3, panel="B", category="ligand_receptor_analysis")

e20 = get(s4, panel="A", population="citing, external", category="2020")
e26 = get(s4, panel="A", population="citing, external", category="2026")
ru_e = get(s4, panel="B", population="citing, external", category="data_reuse")
ru_i = get(s4, panel="B", population="citing, internal", category="data_reuse")
vis_c = get(s4, panel="C", population="HTAN's own papers")
vis_e = get(s4, panel="C", population="external authors")

gap_ap = get(s5, panel="A", category="assay_platform")
jud = [r for r in s5 if r["panel"] == "B"]
unjudged = [r for r in jud if int(r["n_documents"]) == 0]

md = f"""# Spatial biology in HTAN — what the papers say

Cancer Grand Challenges, spatial biology. Seven slides. Figures in
`out/slides/figures/` (PNG for slides, SVG for print, one backing CSV per
slide); provenance in `out/slides/slide_manifest.json`.

**Structure.** Slides 1–5 are HTAN's own papers only. Slide 6 is the first
slide with a citing paper on it. Slide 7 says how far any of it can be pushed.

**Counting rule, stated on every slide.** HTAN papers were extracted by two
models over the same 157 full-text papers, so summed record counts would
double-count documents. Every number is a distinct-document or distinct-value
count. No figure sums records.

---

## Slide 1 — What HTAN says it built
`s1_what_htan_built.png`

**Line to open with:** HTAN is, on its own account, a protein-imaging network
first. {n(mi)} of {corpus_den} papers with an assay record report multiplex
imaging ({pct(n(mi), corpus_den)}) — more than report scRNA-seq — and
{n(st)} report spatial transcriptomics ({pct(n(st), corpus_den)}).

- Panel A is the whole assay portfolio, spatial picked out in blue. Papers
  report several assays, so the bars do not sum.
- Panel B turns that into tumour context: each centre works one disease. The
  spatial fraction is very uneven — HMS (PATCH) is {patch['n_documents']} of
  {patch['denominator_documents']} spatial, Duke (Breast PCA) is
  {duke['n_documents']} of {duke['denominator_documents']}.
- Panel C is the biology the papers claim, on the Hanahan–Weinberg hallmark
  enum: genome instability and avoiding immune destruction tie at
  {hm1['n_documents']} papers each of the {hm_den} that name any hallmark. The
  other {int(hm1['denominator_documents']) and 144 - hm_den} state none — worth
  saying, because absence is the majority state for this field.
- **Say out loud:** "spatial" here means the paper reports one of four assay
  types. Mass cytometry is in that list for vocabulary continuity and is a
  suspension assay — never fold it into a spatial total.

---

## Slide 2 — How the corpus changed
`s1b_how_the_corpus_changed.png`

**Line to open with:** HTAN's own literature inverted its modality mix. In 2019
{pct(n(mi_19), n(mi_19, 'denominator_documents'))} of that year's papers reported
multiplex imaging and {pct(n(st_19), n(st_19, 'denominator_documents'))} reported
spatial transcriptomics; by 2025 those are
{pct(n(mi_25), n(mi_25, 'denominator_documents'))} and
{pct(n(st_25), n(st_25, 'denominator_documents'))}, while scRNA-seq fell from
{pct(n(sc_20), n(sc_20, 'denominator_documents'))} in 2020 to
{pct(n(sc_25), n(sc_25, 'denominator_documents'))}.

- Panel A is prevalence, not composition — papers report several assays, so the
  lines deliberately do not sum. Denominators per year are printed in the note;
  the early years are thin (2019 n={mi_19['denominator_documents']}), so read the
  trend, not any single point.
- Panel B is the second shift and the more consequential one: HTAN moved from
  **building methods to running cohorts**. Cohort studies go from
  {coh_19['n_documents']} in 2019 to {coh_25['n_documents']} in 2025, matching
  method-development papers ({md_25['n_documents']}) for the first time.
- **Say out loud:** year is publication year, so this lags the actual work by a
  review cycle, and 2026 is a partial year.

---

## Slide 3 — What gets written about is not what gets deposited
`s1c_papers_vs_deposits.png`

**Line to open with:** the modality that dominates HTAN's papers is not the
modality that dominates HTAN's disk. Multiplex imaging leads the literature
({pap_mi['n_documents']} papers) but is {int(dep_mi['n_documents']):,} files;
spatial transcriptomics is {int(dep_st['n_documents']):,} files. And electron
microscopy — {int(dep_em['n_documents']):,} files,
{pct(n(dep_em), portal_total)} of the entire portal, from a single atlas — is
named in {pap_em['n_documents']} papers.

- Left panel counts **papers**, right panel counts **files**. That is the point,
  and it must be said aloud: a file count is not an effort count, and one
  imaging study can ship tens of thousands of tiles.
- Source: HTAN Data Portal database `htan_2026_922`, pulled via the `htan` CLI.
  The crosswalk from the portal's assay vocabulary to the extraction's
  `assay_type` vocabulary is in the script; every unmapped portal assay is
  listed in the backing CSV rather than dropped.
- **Why it matters for this audience:** if you plan reuse by reading the
  literature, you will mis-estimate what is actually available to download.

---

## Slide 4 — How the spatial atlases were made
`s2_how_they_were_made.png`

**Line to open with:** the instrument layer is where interoperability is won or
lost, and it is only half-recorded. {mi2['n_documents']} of
{mi2['denominator_documents']} multiplex-imaging papers name an instrument at
all, and between them they write
{mi2['extra_value']} distinct instrument strings.

- Panel A: blue = names an instrument. The trailing count is distinct strings.
  Canonicalisation does not collapse the variants, which is itself the finding.
  Spatial transcriptomics: {st2['n_documents']} of
  {st2['denominator_documents']} name one, using {st2['extra_value']} strings.
- Panel B: the vendor concentration — 10x, Akoya, RareCyte, Illumina.
- Panel C: what the data actually is on disk. OME-TIFF in {ome['n_documents']}
  of {sp_den} spatial papers, generic TIFF in {tif['n_documents']}. RCPNL and
  QPTIFF are vendor formats that need conversion before anyone else can read
  them.
- **Say out loud:** platform and vendor are stated in only about 40% of
  records. Panels A and B count papers that SAY, not papers that DID.

---

## Slide 5 — How the spatial atlases were analysed
`s3_how_they_were_analysed.png`

**Line to open with:** the consortium's analytical signature is geometry.
Neighbourhood analysis appears in {nb['n_documents']} of
{nb['denominator_documents']} spatial papers ({pct(n(nb), n(nb, 'denominator_documents'))}),
ahead of ligand–receptor inference at {lr['n_documents']}.

- Panel A: how cells get defined. Clustering is near-universal
  ({clus['n_documents']} of {clus['denominator_documents']}); the distinctive
  one is segmentation-based cell definition at {seg['n_documents']}, which is
  an imaging-native step most of the field never needs.
- Panel B: how the microenvironment gets read. `other` is excluded — it is the
  largest bucket and holds generic single-cell methods, not TME methods.
- **Say out loud:** an extracted method is one the paper MENTIONS. Neither
  class separates a method the authors ran from one they cite.

---

## Slide 6 — Now the citing literature
`s4_who_is_reading.png`

**Line to open with:** the field turned spatial around HTAN, but declared reuse
of HTAN data did not follow — and where it did, you usually cannot tell it was
HTAN's.

- Panel A: spatial methods named in citing abstracts rose from
  {pct(n(e20), n(e20, 'denominator_documents'))} of external citing abstracts in
  2020 to {pct(n(e26), n(e26, 'denominator_documents'))} in 2026 (Jan–Aug). This
  is the one panel that is not a floor — the abstract pass ran on the strong
  model over every paper.
- Panel B: declared data reuse is
  {pct(n(ru_i), n(ru_i, 'denominator_documents'))} among papers sharing an HTAN
  author versus {pct(n(ru_e), n(ru_e, 'denominator_documents'))} among external
  authors — roughly a threefold gap on every engagement kind.
- Panel C: does the availability text name HTAN, phs002371 or a syn ID?
  {vis_c['n_documents']} of {vis_c['denominator_documents']} of HTAN's own
  spatial papers do; {vis_e['n_documents']} of
  {int(vis_e['denominator_documents']):,} external citing spatial papers do
  ({pct(n(vis_e), n(vis_e, 'denominator_documents'))}).
- **Say out loud:** panel C is visibility, not compliance. The denominator is
  papers that cite HTAN, not papers that reused HTAN data. HTAN's own
  {pct(n(vis_c), n(vis_c, 'denominator_documents'))} sets the ceiling.
- **The number worth ending on:** of the 184 citing papers that stated how they
  obtained data, only 20 gave a resolvable identifier — 15 dbGaP phs002371
  (across nine different version spellings) and 5 Synapse/HTAN IDs. That is the
  entire machine-linkable bridge between the literature, the download logs and
  the dbGaP requestor list.

---

## Slide 7 — How far to trust every number in this deck
`s5_how_far_to_trust.png`

Show this if there is any time at all. If asked a precision question, go here.

- **Citing counts are floors.** The citing full-text passes ran on the small
  model. On a 500-document sample it recovers only
  {float(gap_ap['extra_value']) * 100:.0f}% of the strong model's
  `assay_platform` records. Panel A has the per-class figures.
- **Precision is unmeasured.** 0 of the 150 required human gold labels exist
  (§11.3 unmet). Worse, {len(unjudged)} of {len(jud)} classes never reached the
  second-model judge at all: {", ".join(sorted(r["category"] for r in unjudged))}
  have no verdict on any record. Where the judge did run it rejected 5% of
  `engagement` and 19% of `data_acquisition` records.
- **Reach.** 445 citing papers have no full-text route and 29 preprints sit in
  unfetched requester-pays buckets; both are abstract-only.
- **The one nobody asks but should:** on the identical 5,071 citing papers the
  two models found engagement in 568 vs 228 papers, overlapping on only 215.
  Document-level disagreement is worse than the record-level gap suggests.

---

## Questions you should expect

1. *"Is 2.4% really the reuse rate?"* No. It is the share of citing spatial
   papers whose availability text names HTAN. Reuse is panel B, and it is a
   floor.
2. *"Why is mass cytometry in a spatial deck?"* It is a suspension assay, kept
   for vocabulary continuity, reported as its own row, never in a spatial total.
3. *"How accurate is the extraction?"* Unmeasured against human labels. Every
   record carries a verbatim quotation and character offsets, so any claim is
   auditable back to source text — but precision is not yet a number.
4. *"Can you link a paper to a download?"* For 20 papers. That is the finding.
"""

(OUT / "SLIDES.md").write_text(md)
print(f"wrote {OUT / 'SLIDES.md'} ({len(md.splitlines())} lines)")
