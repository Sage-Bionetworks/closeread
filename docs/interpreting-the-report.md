# Interpreting the report

Every figure in `out/report/` is computed at render time from stored records.
Each figure ships with a CSV of the plotted data (same base name) and an entry
in `figure_manifest.json` recording its run identifiers, record count,
denominator definition, and filters. No figure contains a typed number.

## Reading any figure

- **The denominator is printed on the figure.** A share without its
  denominator is not reported.
- **All figures read the same view**: records joined to documents, with
  judge-rejected records excluded. No figure applies its own filter.
- **Absence is recorded, not implied.** A document with no availability
  statement contributes an explicit `no_statement` record (46 percent of
  corpus documents in the prototype had no availability text; without absence
  records a missing extraction and a real silence look identical).
- **Reuse aggregates are split by `author_overlap`** (internal vs external at
  minimum). A combined figure overstates external adoption.

## The figures

| Figure | What it shows | Denominator | Caveat |
|---|---|---|---|
| F1 | format spread per assay and level | records in `gold/object_format.csv` | formats are canonicalised; raw forms in the CSV |
| F2 | cell-typing divergence across groups | cell-typing steps | steps, not papers |
| F3 | TME method categories, consortium vs reusers | records per doc_type | citing side needs the provenance pass |
| F4 | engagement kinds, with combinations | citing documents with records | multi-valued; documents count in every kind they show |
| F5/F5b | data-reuse tasks and internal/external over time | judged reuse records | precision from F8 applies |
| F6 | provenance chain stage counts | varies per stage; printed per bar | each stage's definition is in the manifest |
| F7 | availability statement kinds | documents with full text, per doc_type | a document can use several statement kinds |
| F8 | coverage and measured precision per class | all non-rejected records | **read this first**; every other figure states a result, F8 states how far to trust it |

## Precision

Classes are only trustworthy to the precision F8 reports. A class below 50
percent precision is removed from the report or carries its precision printed
next to every use (§11.3). Until the human-labelled gold set exists, F8 shows
"precision not yet measured" — that is a statement of fact, not a rendering
bug.
