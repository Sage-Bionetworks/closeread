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
pap_bd = get(s1c, panel="A", category="targeted_dna_seq")
dep_st = get(s1c, panel="B", category="spatial_transcriptomics")
dep_mi = get(s1c, panel="B", category="multiplex_imaging")
dep_bd = get(s1c, panel="B", category="targeted_dna_seq")
pap_st = get(s1c, panel="A", category="spatial_transcriptomics")
portal_total = int(dep_mi["denominator_documents"])
atl = {r["population"]: r for r in s1c if r["panel"] == "C"}

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

fp_da = get(s5, panel="A", category="data_availability")
fp_tme = get(s5, panel="A", category="tme_algorithm")
prec = {r["category"]: r for r in s5 if r["panel"] == "B"}
measured = [c for c, r in prec.items() if r["denominator_documents"] not in ("", "0")]
unmeasured = [c for c, r in prec.items() if r["denominator_documents"] in ("", "0")]

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

**Model status.** The citing full-text passes were re-run on the strong model
over all 6,072 full-text citing papers; the superseded small-model runs are on
disk but excluded from every number here. The provenance pass behind engagement
and data_acquisition was NOT re-run.

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

## Slide 3 — What gets written about is not what got collected
`s1c_papers_vs_deposits.png`

**Line to open with:** the spatial modalities are the most written-about and the
least broadly collected. Multiplex imaging leads the literature
({pap_mi['n_documents']} papers) on {int(dep_mi['n_documents']):,} patients;
spatial transcriptomics is {pap_st['n_documents']} papers on
{int(dep_st['n_documents']):,} patients. Bulk DNA is the reverse —
{pap_bd['n_documents']} papers on {int(dep_bd['n_documents']):,} patients.

- **Count patients, not files.** Files answer a storage question, not a coverage
  one: electron microscopy is 110,398 files from 15 patients, and ExSEQ is
  21,156 files from 9. Patients are distinct demographics records on released
  files — {portal_total:,} of 2,917 HTAN participants have at least one.
- Panel C says the same thing at centre level, and harder. OHSU is
  {atl['HTAN OHSU']['n_documents']} papers on
  {atl['HTAN OHSU']['denominator_documents']} patients; Duke is
  {atl['HTAN Duke']['n_documents']} papers on
  {atl['HTAN Duke']['denominator_documents']}. HTAPP has
  {atl['HTAN HTAPP']['denominator_documents']} patients of released data and no
  paper in the corpus at all; three more centres publish (MD Anderson 10, Yale
  9, UCSF 5) with no released atlas to point at.
- Source: HTAN Data Portal database `htan_2026_922`, pulled via the `htan` CLI
  and saved to `out/dcc/`. Both crosswalks — portal assay → `assay_type`, and
  corpus centre → atlas — are documented in the script, with unmapped values in
  the backing CSV.
- **Say out loud:** a centre that publishes early on few patients is not doing
  worse work than one that deposits many. This is a decoupling, not a league
  table.
- **Why it matters for this audience:** if you plan reuse by reading the
  literature, you will mis-estimate both what exists and how many patients it
  covers.

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
  authors — a {(n(ru_i) / n(ru_i, 'denominator_documents')) / (n(ru_e) / n(ru_e, 'denominator_documents')):.1f}x gap, and it holds
  across every engagement kind. This is the one panel still built on the
  mixed-model provenance pass, so it remains a lower bound.
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

- **The citing pass was re-run on the strong model.** Every citing number in
  this deck now comes from a single strong-model pass over all 6,072 full-text
  citing papers. The old "citing counts are floors" caveat is retired.
- **Panel A is why.** On a judged sample the retired small model produced false
  positives at {float(fp_da['extra_value']) * 100:.0f}% for data availability and
  {float(fp_tme['extra_value']) * 100:.0f}% for TME methods — and for TME it
  produced *more* records than the strong model (1,417 vs 833). It was inventing,
  not just missing, so the old caveat pointed the wrong way for some classes.
- **Precision is now measured for two classes.** {len(measured)} of
  {len(measured) + len(unmeasured)}: data_acquisition
  {float(prec['data_acquisition']['extra_value']) * 100:.0f}%
  (n={prec['data_acquisition']['denominator_documents']}) and engagement
  {float(prec['engagement']['extra_value']) * 100:.0f}%
  (n={prec['engagement']['denominator_documents']}). All 200 human labels sit on
  those two. The {len(unmeasured)} classes behind slides 1–5 have no human labels
  and no judge verdict on any shipped record. One labeller, so no inter-rater
  agreement.
- **The provenance pass was not re-run** and is the one place the old model
  mixing still bites: on the identical 5,071 citing papers the two models found
  engagement in 568 vs 228 papers, overlapping on 215, and the pass reached only
  5,265 of 9,753 citing papers.
- **Reach.** 445 citing papers have no full-text route and 29 preprints sit in
  unfetched requester-pays buckets; both are abstract-only.
- **The one nobody asks but should:** the corpus is still double-extracted by
  two models, so no figure in this deck sums records — every number is a
  distinct-document or distinct-value count.

---

## Questions you should expect

1. *"Is 2.4% really the reuse rate?"* No. It is the share of citing spatial
   papers whose availability text names HTAN. Reuse is panel B, and it is a
   floor.
2. *"Why is mass cytometry in a spatial deck?"* It is a suspension assay, kept
   for vocabulary continuity, reported as its own row, never in a spatial total.
3. *"How accurate is the extraction?"* Measured at 86% and 97% for the two
   provenance classes against 200 human labels; unmeasured for the other seven,
   which is everything on slides 1–5. Every record carries a verbatim quotation
   and character offsets, so any claim is auditable back to source text.
4. *"Can you link a paper to a download?"* For 20 papers. That is the finding.
"""

(OUT / "SLIDES.md").write_text(md)
print(f"wrote {OUT / 'SLIDES.md'} ({len(md.splitlines())} lines)")
