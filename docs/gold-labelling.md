# Gold-set labelling protocol

Human labels are the only ground truth in this system. Judge precision and
recall are measured against them (§11.3: at least 150 labelled reuse records).
Labels live in `gold_labels.jsonl`, separate from records, so they survive
re-extraction.

## The task

You are given a CSV produced by `closeread gold-sample --run <run_id>`. Each
row is one extracted record: a verbatim quotation from a citing paper, the
extraction class, and the attributes the model assigned. For each row, fill in:

- `human_label`: one of `correct`, `incorrect`, `unsure`
- `labeller`: your name or initials (same value on every row you label)
- `notes`: optional, but write one whenever you pick `incorrect` or `unsure`

Then import with:

```bash
uv run closeread gold-import --csv <file> --community htan
```

## What "correct" means

Judge the record, not the paper. A record is `correct` when BOTH hold:

1. **The quotation supports the class.** An `engagement` record labelled
   `data_reuse` is correct only if the quoted text says the authors actually
   used the consortium's data, not merely cited a consortium paper for
   background. A `data_acquisition` record is correct only if the text says
   the authors obtained the consortium's data.
2. **The attributes read the text correctly.** For engagement: is every listed
   `engagement_kind` supported, and is `data_task` right when data_reuse is
   present? For data_acquisition: are accession and repository what the text
   says?

Mark `incorrect` when either fails. Common failure modes to watch for:

- **Attribution errors.** The text describes reuse of someone else's dataset
  near a mention of the consortium. If the reused data is not the
  consortium's, the record is incorrect. This was the prototype's largest
  error class.
- **Distribution mistaken for reuse.** A citing paper's own data-availability
  statement ("datasets used in this study are available under GSE…", "data are
  deposited in dbGaP phs…") is where data was shared, not reuse of it. This
  was the dominant error in the first labelling round (10 of 15 incorrect).
- **Boilerplate mistaken for reuse.** "Processed as previously described" or
  citation of a method paper is not data reuse.
- **Kind inflation.** Text supports `background_citation` but the record also
  claims `data_reuse`. If any listed kind is unsupported, the record is
  incorrect (note which kind failed).
- **Direction errors.** Releasing vs acquiring confused.

Mark `unsure` when the quotation is genuinely ambiguous even after reading the
context. Don't force it; `unsure` rows are excluded from precision arithmetic,
and a high unsure rate is itself a finding.

## Ground rules

- Judge only against the quoted text and, if needed, the source paper itself.
  Do not use outside knowledge of the group or dataset.
- Do not look at the model's `judge_verdict` (it is not in the CSV for this
  reason). Your label must be independent of the judge you are calibrating.
- Label every row you open; skipped rows are indistinguishable from unfinished
  work.
- If two people label, work independently and both import (the `labeller`
  column keeps you separate); agreement is then measurable.

## What happens with the labels

`closeread gold-import` writes them to `out/htan/gold_labels.jsonl`. Judge
precision/recall computes automatically
(`closeread.judge.gold_sample.judge_precision_recall`), figure F8 fills in its
per-class precision, and any class below 50 percent precision is removed from
the report or carries its precision printed next to every use (§11.3).
