# closeread: design and build specification

Version 1.0. Date 2026-08-21. Status: ready to build.

---

## 1. Purpose and scope

### 1.1 What this document is

This is the build specification for a new Python package. It replaces an earlier
prototype. It records what the prototype measured, and what those measurements
require the new design to do.

Read section 3 before writing code. Section 3 lists six failures from the
prototype. Each failure cost time or money. Each one has a corresponding rule in
this specification.

### 1.2 The name

**closeread.** Close reading is the term for textual analysis in which every
claim is anchored in the text itself. That is the distinguishing property of
this software. It does not count citations or match keywords. It reads passages
and ties every extracted fact to a verbatim quotation with character offsets.

The name is community-neutral, so a second consortium does not require renaming.

### 1.3 What the software does

The software reads the full text of scientific publications. It extracts
structured, evidence-linked facts about two things:

1. How a research consortium built its datasets.
2. How other researchers reused those datasets.

It writes those facts to files, and renders one report with figures.

### 1.4 Scope

| In scope | Out of scope |
|---|---|
| One community: HTAN | Running a second community |
| Output: one report with figures | A web service or API |
| Support a preprint and a conference talk | A production pipeline |
| Reusable design | Proven reusability |

The target outputs are a preprint and a talk at the Cancer Grand Challenges
spatial biology conference. Every number in the report must be traceable to a
quotation in a source document.

### 1.5 Build location

Build in a new, empty repository.

The directory `/Users/ataylor/Documents/projects/htan2/htan-pubs-fulltext` is
reference material only. It contains the prototype, prior data artifacts, and
design notes. Read it. Do not write to it. Do not copy its code.

### 1.6 Reusability

HTAN is the first community. The design should allow a second community, such as
the Cancer Complexity Knowledge Portal, to be added by editing configuration
files instead of code.

This is a design intention. It has not been tested. Section 11.5 states the bar.

---

## 2. Glossary

Use these terms consistently. Do not introduce synonyms.

| Term | Definition |
|---|---|
| **community** | A research consortium and its publications. HTAN is one community. |
| **corpus document** | A publication authored by the community. |
| **citing document** | A publication that cites at least one corpus document. |
| **pass** | One extraction job over one set of classes and one set of document sections. |
| **class** | One type of extracted fact, for example `cell_typing`. |
| **record** | One extracted fact. One row. Has one verbatim quotation and its character offsets. |
| **candidate** | One regular-expression match in a document. Evidence of a string, not of a meaning. |
| **judge** | A model that reviews a record and returns a verdict. |
| **run** | One execution of one pass over one community. Has a `run_id`. |
| **anchor window** | A span of text around a mention of the community, used to scope extraction. |

---

## 3. Findings from the prototype

Six measured findings. Each one produces a rule.

### 3.1 Adding classes to a prompt reduces recall

A fifth class was added to a prompt that had four. No other change was made. The
`object_format` class fell from 219 records to 92, a loss of 58 percent.

**Rule.** Split extraction into passes. One pass carries a small number of
related classes. To widen the extraction surface, add a pass, then measure
recall on the classes that already worked.

### 3.2 A pattern match does not carry meaning

A regular expression found 80 accession identifiers in corpus text. An earlier
draft of this document treated them as datasets the corpus released. That was
wrong. The verb decides the meaning:

| Text | Meaning |
|---|---|
| "read counts are available from GEO with accession GSE117616" | release |
| "we obtained preprocessed count matrices from GEO (GSE178431)" | acquisition |
| "we downloaded the Ennis et al. data from GSE227903" | acquisition |
| "raw data can be assessed in GEO with accession GSE72857" | release |

Section does not disambiguate either. 46 of the 80 identifiers never appear in
an availability section. Releases appear in Methods sections. Acquisitions
appear in availability sections.

**Rule.** Regular expressions produce candidates. Candidates locate text and
measure extractor recall. Candidates never decide meaning. A model decides
meaning, and a judge checks the model.

### 3.3 Request configuration can be silently ignored

The prototype sent `generation_config` in snake_case to the Gemini batch REST
endpoint. The endpoint ignored it. No response schema and no output limit were
applied.

Consequences: output reached about 4,600 tokens per request instead of about
350. One run produced 19.3 million output tokens, which was 89 percent of its
cost. Two attributes were empty in every record. Record counts and alignment
rates looked normal.

**Rule.** Send a canary before every fan-out. See section 6.9.

### 3.4 Attribute completeness comes from the prompt

A three-way test compared a request with a proto-shaped response schema, a
request with camelCase configuration, and a request with no schema at all. All
three returned complete attributes. The change that fixed the problem was a
prompt instruction:

> Every attribute key must appear in the output. Use `not_stated` when the text
> does not give a value. Never combine several attributes into one string.

**Rule.** State attribute completeness in the prompt. Also mark attributes
`required` in the response schema. Do not rely on the schema alone.

### 3.5 Two classification axes were merged

An earlier prototype classified the *kind* of citation: data reuse, method
reuse, background, comparison. A later prototype classified the *purpose*:
reproduce, new question, benchmark, train. Each replaced the other. Both are
needed. Kind and purpose are independent.

**Rule.** Keep kind and purpose as separate fields. Allow multiple values per
document. See section 7.3.

### 3.6 Hand-written vocabulary dictionaries do not scale

The prototype contained seven canonicalisation dictionaries. Two rounds of
manual editing reduced unmapped `assay_name` values from 45 percent to 14
percent. Every run still produced new unmapped values. One prototype pass
observed 673 distinct software names.

**Rule.** Do not write vocabulary dictionaries. Generate a mapping table with a
model, over the set of distinct values. See section 6.7.

---

## 4. Architecture

### 4.1 Stage sequence

```
1  acquire     OpenAlex metadata, then full text
2  parse       JATS to plain text plus a section index
3  candidates  regular-expression matches
4  extract     one batch job per pass
5  collect     harvest, align spans, write records
6  normalise   map surface forms to canonical forms
7  judge       adjudicate records
8  report      build figures and REPORT.md
```

Each stage reads files and writes files. Each stage can run alone. Each stage is
idempotent: running it twice with the same inputs gives the same outputs.

### 4.2 Passes

| Pass | Classes | Text read | Corpora |
|---|---|---|---|
| `availability` | `data_availability`, `code_availability` | whole document | both |
| `measurement` | `assay_platform`, `object_format` | whole document | both |
| `analysis` | `cell_typing`, `tme_algorithm` | whole document | both |
| `provenance` | `data_acquisition`, `engagement` | anchor windows | citing only |
| `abstract` | `abstract_claim` | abstract | both |

### 4.2.1 Passes read whole documents by default

An earlier draft scoped each pass to named sections. That is dropped. Three
reasons.

**Facts are not where the section name predicts.** Section 3.2 measured this
directly. Release statements appear in Methods sections. Acquisition statements
appear in availability sections. 46 of 80 accession identifiers never appear in
an availability section at all. A pass scoped to availability sections would
have missed most of them, and the miss would look identical to a document that
says nothing.

**Section labelling is itself unreliable.** Headings vary: "STAR Methods",
"Online Methods", "Experimental Procedures". Combined headings such as "Data and
code availability" broke the prototype parser and hid 17 documents' code
sections. Some journals place availability statements outside the article body
entirely. Scoping makes every parser defect a silent recall loss.

**Scoping does not fix class dilution.** The 219 to 92 loss in section 3.1
happened inside single 30,000-character windows. It is caused by the number of
competing classes in one prompt, not by document length. Splitting into passes
fixes it. Scoping does not.

**Cost does not justify it on the corpus.** Measured:

| Population | Whole document, per pass | Four full-text passes | Saved by scoping |
|---|---|---|---|
| corpus, 157 documents | 0.23 USD | 0.92 USD | about 0.46 USD |
| citing, 5,197 documents | 8.92 USD | 26.77 USD | about 13.38 USD |

On the corpus the saving is under one US dollar and not worth a recall risk. On
the citing side it is material.

**Rule.** Read whole documents. Section scoping is available as a cost control,
set per pass in the pass definition, and used only on the citing corpus when a
run would otherwise be too expensive. When it is used, the run summary records
which sections were read, so that a low record count can be attributed.

### 4.2.2 The section index is still required

Dropping section scoping does not drop section labelling. The index is needed
for three things:

1. `source_section` on every record, which is part of the provenance stamp.
2. Reporting where a class of fact is usually found, which is a finding in its
   own right.
3. Optional scoping, above.

Section shares, measured over 60 corpus documents, mean length 48,791
characters:

| Section | Share of text |
|---|---|
| methods | 34.6% |
| results | 33.6% |
| other | 11.6% |
| discussion | 10.1% |
| introduction | 6.8% |
| abstract | 2.9% |
| data availability | 1.1% |

### 4.2.3 Anchor windows are not section scoping

The `provenance` pass reads anchor windows rather than whole documents. This is
proximity scoping, not section scoping, and it is justified by a different
measurement: reading whole citing documents for consortium-specific claims gave
57 percent attribution precision, because the model attributed any reuse in the
document to the consortium. Anchor windows are retained.

### 4.2.4 Model selection

Quality is the objective. Cost needs a decision from the project owner only
above about 200 US dollars. Below that, take the higher-quality option.

| Stage | Model | Reason |
|---|---|---|
| corpus passes, all | strong model | 157 documents. The premium over a small model is about 8 USD. There is no reason to use a weaker model here. |
| provenance, anchor windows | strong model | This is the least reliable extraction in the prototype at 57 percent attribution precision. It is where model quality matters most. |
| abstract pass | strong model, unpacked | See 4.2.5. |
| citing full-text passes | small model, with a 500-document strong-model sample | A strong model on all 5,197 documents costs about 326 USD against about 41 USD. The sample measures the gap for about 31 USD. See 14.2. |
| judge | strong model, per record | Must differ from the extractor. See 5.8. |
| normalise | strong model | Runs over distinct values only. Negligible cost. |

**Corpus dual-model extraction.** Running both a small and a strong model over
the corpus and taking the union of records costs about 10 USD in total.
Disagreements go to the judge. This raises recall and gives a free per-class
measurement of small-model reliability, which then informs whether the small
model is acceptable on the citing corpus. Recommended.

### 4.2.5 Do not pack abstracts

An earlier draft packed 10 abstracts per request to amortise prompt overhead.
That saved about 17 US dollars and introduced a quality risk: several documents
in one context can bleed claims between each other, and the failure is hard to
detect because the output is well-formed.

Send one abstract per request. The cost difference does not justify the risk.

### 4.3 Layers

| Layer | Contents | Format | Rebuildable |
|---|---|---|---|
| raw | model responses, fetched XML | JSONL, XML | no, immutable |
| bronze | records, aligned, not normalised | JSONL | from raw |
| silver | records, normalised and judged | JSONL | from bronze |
| gold | one flat table per class and per figure | CSV | from silver |

Changing a vocabulary or a judge threshold rebuilds silver and gold. It does not
require a new extraction run.

---

## 5. Stage contracts

Each stage below states its inputs, outputs, and failure behaviour.

### 5.1 acquire

**Input.** A community configuration file. A corpus seed list of publication
identifiers.

**Output.** `documents.jsonl`, `citation_edges.jsonl`, and one XML file per
fetched document under `raw/fulltext/`.

**Steps.**

1. Resolve each corpus document in OpenAlex. Record the OpenAlex Work ID.
2. Query OpenAlex for works citing each corpus document. Deduplicate by Work ID.
   Capture `authorships[].author.id` and institution identifiers for every work,
   corpus and citing. These are needed for section 5.2.1 and are not recoverable
   later without re-querying.
3. Deduplicate preprint and published pairs. See section 5.2.
4. Fetch full text. See the acquisition tiers below.
5. Fetch the abstract for every work, whether or not full text exists.

**Acquisition tiers.**

| Tier | Population | Source | Cost |
|---|---|---|---|
| A | preprint with a published version already in the set | no fetch; merge the records | none |
| B | document in PubMed Central | `s3://pmc-oa-opendata`, unsigned | none |
| C | preprint not in PubMed Central | `s3://biorxiv-src-monthly`, `s3://medrxiv-src-monthly` | requester pays |
| D | no full text available | abstract only | none |

The bioRxiv and medRxiv buckets are requester-pays. Unsigned access returns
`AccessDenied`. Use AWS profile `htan-dev`. Log bytes transferred per run.

Two routes were tested and rejected. The bioRxiv REST API returns metadata but
not full text. Europe PMC indexes preprints under `PPR` identifiers but returns
HTTP 404 for `fullTextXML`.

**Failure behaviour.** A document that cannot be fetched is recorded in
`documents.jsonl` with `oa_status = "unavailable"`. The stage does not stop.
Retry HTTP 429 and 5xx with exponential backoff, five attempts.

### 5.2 Preprint deduplication

Measured population: 1,917 preprints among 9,799 citing works.

| Group | Count |
|---|---|
| preprint with a published version already in the citing set | 684 |
| orphan preprint, present in PubMed Central | about 404 |
| orphan preprint, not in PubMed Central | about 830 |
| Research Square and SSRN, no bulk full text route | about 146 |

The 684 pairs are a correctness problem, not a coverage problem. Without
deduplication the same study appears twice in every denominator.

**Match rule.** Normalise the title: lowercase, remove non-alphanumeric
characters, truncate to 90 characters. Two works match if normalised titles are
equal and at least one of DOI prefix or first-author surname also matches. Keep
the published version. Record the collapsed Work ID in `merged_from`.

### 5.2.1 Author overlap

Citing documents must be classified by their relationship to the consortium.
Reuse by a consortium member is a different finding from reuse by an outside
group, and an aggregate that merges the two overstates external adoption.

**Method.** OpenAlex returns `authorships[].author.id` for every work. Collect
the set of author identifiers for all corpus documents. For each citing
document, intersect its author identifiers with that set. This is an exact
identifier match. Do not match on names: the prototype held author strings such
as "Santagata S", and initials collide.

**Field.** `author_overlap` on each citing document, one of:

| Value | Definition |
|---|---|
| `is_corpus_document` | the citing work is itself a corpus document |
| `shared_senior_author` | first or last author of the citing work also authored a corpus document |
| `shared_author` | any author overlap, but not first or last |
| `external` | no author overlap |

Also record `n_shared_authors` and `shared_author_ids`.

**Requirement.** Every reuse aggregate is reported split by `author_overlap`, at
minimum as internal against external. A single combined figure is not
sufficient.

**Cost.** None. This uses metadata already fetched in stage 5.1 and needs no
model.

**Known value.** The prototype found 58 of 1,711 substantive citing works were
themselves corpus documents. Author-level overlap will be larger, and has not
been measured.

**Optional extension.** OpenAlex also returns institution identifiers. The same
intersection over institutions gives `institution_overlap`, which separates "a
different group at the same centre" from "a different centre entirely". Cheap to
add; not required.

### 5.3 parse

**Input.** One JATS XML file.

**Output.** Plain text, and a section index. The section index maps character
ranges to section labels.

**Requirements.**

1. Remove reference lists, figures, tables, and formulas before extracting text.
2. Label each section: `abstract`, `introduction`, `methods`, `results`,
   `discussion`, `data_availability`, `code_availability`, `other`.
3. A heading that names both data and code, for example "Data and code
   availability", receives **both** labels. The prototype used first-match-wins
   and lost code sections: 17 documents used a combined heading, and only 9 of
   157 documents showed a code section while 53 contained code availability
   text.
4. Nested availability sections take priority over the enclosing section.
5. Character offsets must be stable. `text[start:end]` must return the section.

### 5.4 candidates

**Input.** Parsed text and section index.

**Output.** `candidates.jsonl`.

**Patterns.** Accession identifiers, repository URLs, grant identifiers.
Patterns come from the community configuration file. Do not add software or
platform name lists. See section 3.6.

**Uses.**

1. Locate anchor windows for the `provenance` pass.
2. Measure extractor recall. A candidate span that no record covers is a
   possible miss. Count these and report the count.

Candidates never decide meaning. See section 3.2.

### 5.5 extract

**Input.** Parsed documents, a pass definition, a community configuration.

**Output.** A batch job, and a handoff file recording the job identity.

**Steps.**

1. Select documents for the pass.
2. Select text for each document. Whole document by default. Sections only if
   the pass definition sets `sections`, which is a cost control.
3. Split text into windows if it exceeds the window size.
4. Render one prompt per window from the pass definition.
5. Run the canary. See section 6.9.
6. Submit the batch job. Write the handoff file. Stop.

The stage does not wait for the job. Waiting is a separate command.

**Request format.** Use camelCase keys. See section 3.3.

```json
{"generationConfig": {
   "responseMimeType": "application/json",
   "responseSchema": { },
   "temperature": 0,
   "maxOutputTokens": 16384}}
```

**Short-text passes pack several documents per request.** An abstract is about
310 tokens. A prompt is about 2,000 tokens. One abstract per request wastes most
of the request on prompt text. Pack 10 abstracts per request and key each result
to its document.

### 5.6 collect

**Input.** A handoff file.

**Output.** `bronze/records_<run_id>.jsonl`,
`bronze/rejected_<run_id>.jsonl`, and a run summary.

**Steps.**

1. Check job state. Stop if the job has not succeeded.
2. Download responses.
3. Parse each response.
4. Align each quotation against the source text. Compute character offsets.
5. Write records with offsets to `records`. Write records without offsets to
   `rejected`.
6. Deduplicate on `(doc_id, class, char_start, char_end)`.
7. Count responses with `finishReason == "MAX_TOKENS"`. Report the count.

**Rule.** A record without character offsets is never written to `records`. In
the prototype this filter removed a hallucinated quotation on its first test.

### 5.7 normalise

**Input.** All records for a value set, for example every `assay_name` value.

**Output.** `vocab_map.jsonl`, containing `surface_form` and `canonical_form`.

**Method.** Collect the distinct values. Send them to a model in batches. Ask
for a canonical form for each. Write the mapping table. Apply the table to
records deterministically.

Cost scales with the number of distinct values, not the number of records.

| Value set | Distinct values | Records |
|---|---|---|
| assay and modality strings | 653 | 4,840 |
| software names | 673 | 1,295 |
| platform strings | 84 | 206 |

**Rule.** Never overwrite a raw value. Write the canonical value to a separate
field. See section 8.3.

### 5.8 judge

**Input.** Records from the `provenance` pass, grouped by document. The
document's candidates.

**Output.** A verdict per record: `confirmed`, `rejected`, or `uncertain`. Plus
a confidence value and a short reason.

**Requirements.**

1. The judge model must differ from the extractor model. In the prototype the
   two disagreed on 43 percent of records. Agreement measures nothing.
2. The judge receives the document's candidates as additional evidence.
3. Judge per document, not per record. All windows for a document go in one
   request. This is cheaper and lets the judge compare windows.
4. Store verdicts. Do not delete rejected records.

**Calibration.** Judge accuracy must be measured against human labels, not
against another model. Candidates provide a sampling frame for choosing which
documents to label. A random sample of 150 documents from 5,197 would contain
few reusers. A sample drawn from candidate-bearing documents contains many.

### 5.9 report

**Input.** Gold tables.

**Output.** `REPORT.md`, figure files, and one CSV per figure.

See section 10.

---

## 6. Rules

Numbered for reference in code review.

**6.1 Ground every record.** Every record carries a verbatim quotation, its
character offsets, and its section. Records without offsets do not ship.

**6.2a Split reuse by author overlap.** Every reuse aggregate reports internal
and external separately. See 5.2.1.

**6.2 Declare every denominator.** A reported share carries its numerator, its
denominator, a definition of the denominator, and the share of records that were
judged. The prototype used three different denominators for one figure.

**6.3 Record absence.** When a document contains no availability statement,
write a record with `statement_kind = "no_statement"`. Do not write nothing. 46
percent of corpus documents contain no availability text. Without an explicit
record, a missing extraction and a real silence look identical.

**6.4 Keep raw and canonical values side by side.** Normalisation adds a field.
It does not replace one.

**6.5 Record vocabulary drift.** A value outside a closed list is written to an
`enum_drift` field. It is never silently mapped to `other`. One prototype run
produced 24 real vendor names this way.

**6.6 Never delete.** Rejected records, unaligned records, and superseded runs
remain on disk with a status field.

**6.7 Generate vocabularies, do not write them.** See section 5.7.

**6.8 Dry run before spending.** Every command that submits a job supports
`--dry-run`. The dry run prints request count, estimated input tokens, estimated
output tokens, and estimated cost. Its purpose is to catch an accidental
order-of-magnitude error, not to shave cost.

**6.9 Canary before fan-out.** Submit two requests through the real batch path.
Assert three things: `finishReason == "STOP"`; every attribute key is present in
the response; at least one quotation aligns to the source text. If any assertion
fails, do not submit the fan-out. This check costs a few cents. Its absence cost
about 21 US dollars in the prototype.

**6.10 One source for prompt, schema, and validator.** Generate all three from
the pass definition file. In the prototype a prompt declared 14 classes while
its examples demonstrated 5, and only the 5 were ever produced.

---

## 7. Extraction schemas

Schemas live in YAML files. They are not Python. See section 9.2 for the file
format.

### 7.1 Why corpus and citing schemas differ

The same class name means different things in each corpus. In a corpus document,
`assay_platform` means "the consortium used this assay". In a citing document it
means "this paper used this assay", which may be unrelated to the consortium.

The prototype merged the two and could not separate them afterwards.

### 7.2 Corpus classes

| Class | Records |
|---|---|
| `assay_platform` | assay type, assay name, instrument, vendor |
| `object_format` | data objects produced, and their file formats |
| `cell_typing` | one record per cell-typing step |
| `tme_algorithm` | microenvironment analysis methods |
| `data_availability` | how the document says its data can be obtained |
| `code_availability` | how the document says its code can be obtained |
| `abstract_claim` | main claim, hypothesis, result, methods |

**`assay_platform` separates three levels.** The prototype merged them.

| Field | Meaning | Example |
|---|---|---|
| `assay_type` | modality class | `multiplex_imaging` |
| `assay_name` | named assay or chemistry | `CODEX` |
| `platform` | vendor instrument | `Akoya PhenoCycler-Fusion` |
| `vendor` | manufacturer | `Akoya` |

Measured in the prototype: 857 records from 157 documents. `assay_type`
populated in 100 percent, `assay_name` 96 percent, `vendor` 48 percent,
`platform` 27 percent.

**`data_availability` fields.**

| Field | Values |
|---|---|
| `accession` | free text |
| `repository` | Synapse, dbGaP, GEO, SRA, EGA, portal, CRDC, Zenodo, figshare, cellxgene, supplementary, not_deposited, not_stated |
| `access_tier` | open, controlled, registered, on_request, not_stated |
| `access_mechanism` | direct_download, application, data_use_agreement, contact_author, portal_login, cloud_bucket, not_stated |
| `statement_kind` | full_deposit, partial_deposit, available_on_request, within_paper, third_party_restricted, no_statement |
| `direction` | released, acquired |

`direction` exists because of section 3.2. The same accession in the same
section can mean either.

**`code_availability` fields.** `url`, `host`, `license`, `version_or_doi`,
`statement_kind`, `what_the_code_does`.

Measured coverage: 58 of 157 corpus documents have a data availability section.
9 have a code availability section, but 53 contain code availability text. 73
documents contain no availability text at all.

### 7.3 Citing classes

Citing documents are read at two scopes.

**Scope 1, whole document.** What the paper is in its own right. Its own
contribution and its own methods. Used only to compare consortium authors with
reusers.

**Scope 2, anchor windows.** Everything about the consortium. Extracted only
from text near an anchor. Anchors are of three kinds:

1. A citation marker resolving to a corpus document.
2. A community identity string, for example "HTAN".
3. An accession identifier.

Reading whole documents for consortium-specific claims caused 57 percent
attribution precision in the prototype.

**`engagement` fields.**

| Field | Values |
|---|---|
| `engagement_kind` | **multiple values allowed**: background_citation, data_reuse, method_reuse, tool_reuse, comparison, new_data_alongside |
| `data_task` | set only when `data_reuse` is present: validation, integration, meta_analysis, benchmark_input, training_data, new_hypothesis, atlas_extension |
| `method_detail` | set when `method_reuse` or `tool_reuse` is present |
| `judge_verdict` | confirmed, rejected, uncertain |

A document's labels are the union of its window labels. Do not reduce them to a
single value.

**`reproduce` is not a value.** The prototype measured it at 5 percent
precision: 1 of 22 records was correct. The rest were laboratory or processing
boilerplate such as "reprocessed as previously described". The useful axis is
data reuse against method reuse, and the task the data served.

**`data_acquisition` fields.** `accession`, `repository`, `access_route`.

**Citing documents also carry `data_availability` and `code_availability`.** A
citing document that reuses consortium data and then deposits a derived dataset
extends the provenance chain. Measured: 1,907 of 5,197 citing documents have a
data availability section, 1,672 name an accession, and 1,564 name a GitHub
repository.

### 7.4 Abstract class

`abstract_claim` runs on both corpora and reaches documents that have no full
text.

| Field | Values |
|---|---|
| `main_claim` | verbatim-anchored headline assertion |
| `hypothesis` | stated question, if given |
| `core_result` | key result |
| `cancer_hallmark` | the 14 Hanahan-Weinberg hallmarks |
| `key_methods` | **multiple values allowed**: single_cell, spatial_transcriptomics, spatial_proteomics, multiplex_imaging, histology, bulk_omics, genomics, epigenomics, proteomics, metabolomics, multi_omic_integration, computational_method, clinical, other |
| `study_design` | cross_sectional, longitudinal, case_control, cohort, method_development, reanalysis, review, not_stated |
| `cancer_type` | free text |
| `organ_system` | free text |
| `evidence_scope` | abstract_only, full_text |

**`key_methods` is coarser than `assay_type` on purpose.** An abstract says
"spatial transcriptomics". It rarely says "10x Visium HD". Applying the fine
vocabulary to abstract text would create precision that the source does not
contain.

**Coverage.** Corpus: 166 of 169 documents have an abstract; 157 have full text.
Citing: about 9,799 works have an abstract; 5,197 have full text. The abstract
pass is the only pass that reaches the other 4,600.

**Calibration.** For documents with both an abstract and full text, compare
`key_methods` against a coarsened `assay_type` from the `measurement` pass. The
agreement rate on that overlap is the error estimate for documents that have
only an abstract.

---

## 8. Data model

### 8.1 Storage formats

JSONL is canonical. CSV is the deliverable. DuckDB is optional.

| Layer | Format | Reason |
|---|---|---|
| raw, bronze, silver | JSONL | records nest; JSONL appends, streams, and diffs by line |
| gold | CSV, one file per class | opens in Excel; loads in R with one line |
| query | DuckDB views over the above | no import step; optional |

Measured size: the prototype produced 14,382 records in 23 MB. This design
projects 60,000 to 115,000 records, about 35 MB. At this size a columnar format
gives no measurable benefit and costs accessibility.

```sql
CREATE VIEW records AS SELECT * FROM read_json_auto('silver/records_*.jsonl');
CREATE VIEW v_cell_typing AS SELECT * FROM read_csv_auto('gold/cell_typing.csv');
```

**Acceptance test.** A person who has never used DuckDB can open
`gold/cell_typing.csv` in Excel and see the numbers the report quotes.

### 8.2 Identifiers

| Key | Definition |
|---|---|
| `doc_id` | OpenAlex Work ID, for example `W2968352143` |
| `record_id` | `sha1(doc_id + class + char_start + char_end + run_id)`, first 16 hex characters |
| `edge_id` | `sha1(citing_doc_id + cited_doc_id)`, first 16 hex characters |
| `run_id` | `{community}_{pass}_{YYYYMMDD}_{NNN}`, for example `htan_availability_20260821_001` |

`run_id` is assigned by the `extract` command. It is unique. It appears in every
record produced by that run.

### 8.3 Record schema

One row per extracted fact.

| Field | Type | Null | Notes |
|---|---|---|---|
| `record_id` | string | no | see 8.2 |
| `run_id` | string | no | |
| `doc_id` | string | no | |
| `community` | string | no | |
| `pass_name` | string | no | |
| `extraction_class` | string | no | |
| `source_quote` | string | no | verbatim |
| `char_start` | integer | no | |
| `char_end` | integer | no | |
| `source_section` | string | no | `unknown` if not resolved |
| `alignment_status` | string | no | `match_exact`, `match_fuzzy`, `match_lesser` |
| `attributes` | object | no | raw values, keys defined by the class |
| `attributes_canonical` | object | yes | null until `normalise` runs |
| `enum_drift` | array of string | no | empty array if none |
| `candidate_support` | boolean | no | a candidate span falls inside this record |
| `judge_verdict` | string | yes | null until `judge` runs |
| `judge_confidence` | number | yes | |
| `judge_reason` | string | yes | |
| `extractor_model` | string | no | |
| `prompt_version` | string | no | |
| `schema_version` | string | no | |
| `evidence_scope` | string | no | `full_text` or `abstract_only` |

### 8.4 Other tables

```
documents      doc_id, doc_type, community, pmid, pmcid, doi, title, pub_date,
               venue, oa_status, source_version, group_key, merged_from,
               snapshot_date, author_ids, institution_ids, author_overlap,
               n_shared_authors
citation_edges edge_id, citing_doc_id, cited_doc_id
candidates     doc_id, kind, value, char_start, char_end, section
vocab_map      value_set, surface_form, canonical_form, mapping_version
runs           run_id, community, pass_name, model, prompt_version,
               schema_version, submitted_at, n_requests, tokens_in, tokens_out,
               cost_estimate, canary_passed
gold_labels    record_id, human_label, labeller, labelled_at
```

`group_key` holds the grouping axis for figures. For HTAN it holds the centre
name, derived from grant number and last author. Do not read the HTAN portal
publication manifest; it is not trusted for which files, assays, or formats
belong to a document.

`gold_labels` is a separate table so that human labels survive re-extraction.

### 8.5 The shared view

Define the join once:

```sql
CREATE VIEW v_records AS
SELECT r.*, d.doc_type, d.group_key, d.pub_date, d.venue
FROM records r JOIN documents d USING (doc_id)
WHERE r.judge_verdict IS DISTINCT FROM 'rejected';
```

Every figure reads gold tables built from this view. No figure applies its own
filter. This is what keeps denominators consistent.

---

## 9. Package

### 9.1 Layout

```
closeread/
  cli.py              click entry point
  config.py           typed settings
  acquire/            openalex.py  pmc.py  biorxiv.py  dedup.py
  parse/              jats.py  sections.py  chunking.py
  candidates/         patterns.py
  extract/            compile.py  batch.py  canary.py
  collect/            harvest.py  align.py
  normalise/          vocab.py
  judge/              adjudicate.py
  report/             figures.py  render.py
  models.py           pydantic models for every table in section 8

schemas/
  passes/             availability.yaml  measurement.yaml  analysis.yaml
                      provenance.yaml  abstract.yaml
  vocabularies/       assay_type.yaml  vendor.yaml  data_task.yaml  ...

communities/
  htan.yaml
  cckp.yaml           illustrative sketch, not tested

tests/
docs/
```

**Runtime.** Python 3.11 or later. Dependencies: `click`, `pydantic`, `httpx`,
`boto3`, `lxml`, `pyyaml`, `google-genai`, `langextract`, `duckdb`,
`matplotlib`, `pytest`.

**Credentials.** `GEMINI_API_KEY` in the environment. AWS profile `htan-dev` for
requester-pays buckets. Never commit either.

### 9.2 Pass definition format

```yaml
pass: availability
version: 1.0.0
applies_to: [corpus, citing]
sections: null          # null means read the whole document; a list is a cost control
window_chars: 30000
classes:
  data_availability:
    description: how this document says its data can be obtained
    attributes:
      accession:      {type: string}
      repository:     {vocabulary: repository}
      statement_kind: {vocabulary: availability_statement}
      direction:      {vocabulary: release_or_acquire}
    examples:
      - text: "Sequencing data are deposited in Synapse (syn12345678)."
        extractions:
          - span: "deposited in Synapse (syn12345678)"
            accession: syn12345678
            repository: Synapse
            direction: released
```

The compiler reads this file and produces three artifacts: the rendered prompt,
the response schema, and the post-hoc validator. One source prevents the drift
described in rule 6.10.

Example spans must appear verbatim in the example text. A test asserts this.

### 9.3 Community configuration format

```yaml
community: htan
display_name: Human Tumor Atlas Network
corpus:
  seed: data/corpus_seed.csv
  group_by: htan_centre
identity_strings: ["HTAN", "Human Tumor Atlas Network"]
accession_patterns:
  synapse:  'syn\d{7,9}'
  dbgap:    'phs\d{6}'
  internal: 'HTA\d{1,2}[_-]\d+'
portals: ["humantumoratlas.org", "data.humantumoratlas.org"]
passes: [availability, measurement, analysis, provenance, abstract]
aws_profile_requester_pays: htan-dev
```

### 9.4 Command line

```
closeread acquire     --community htan
closeread parse       --community htan
closeread candidates  --community htan
closeread extract     --community htan --pass availability [--dry-run]
closeread status      --run <run_id>
closeread collect     --run <run_id>
closeread normalise   --value-set assay_name
closeread judge       --run <run_id>
closeread report      --runs <run_id> ...
```

### 9.5 Error handling

| Condition | Behaviour |
|---|---|
| HTTP 429 or 5xx | retry with exponential backoff, five attempts, then record failure and continue |
| document fetch fails | write `oa_status = "unavailable"`, continue |
| XML fails to parse | log, skip document, count in the run summary |
| batch job fails | leave the handoff file; `collect` refuses to run and prints the state |
| response is truncated | write to `rejected`, count, and offer `closeread extract --repair --run <id>` |
| quotation does not align | write to `rejected`, never to `records` |
| canary fails | exit non-zero, submit nothing |

No stage deletes an earlier stage's output.

### 9.6 Tests

| Area | Test |
|---|---|
| pass definitions | every example span appears verbatim in its example text |
| pass definitions | every example attribute value is in its vocabulary |
| compiler | prompt, response schema, and validator all list the same classes |
| batch request | `generationConfig` is camelCase; `maxOutputTokens` is present |
| parse | a combined "Data and code availability" heading yields both labels |
| parse | `text[start:end]` returns the indexed section |
| chunking | windows cover the whole document; offsets locate in the parent |
| align | a verbatim quotation aligns; an invented quotation is rejected |
| records | every record carries the full provenance field set |
| normalise | raw values are preserved; canonical values are added |

### 9.7 Documentation

| File | Contents |
|---|---|
| `README.md` | what the package measures and what it does not, in the first paragraph |
| `docs/getting-started.md` | install, credentials, one complete run of the cheapest pass |
| `docs/adding-a-pass.md` | the pass YAML reference |
| `docs/adding-a-community.md` | the community YAML reference, worked through with CCKP |
| `docs/interpreting-the-report.md` | what each figure means, its denominator, its precision caveat |

---

## 10. Report

### 10.1 Output layout

```
out/report/
  REPORT.md
  figures/f1_format_spread.svg  f1_format_spread.png  f1_format_spread.csv
  figures/...
  figure_manifest.json
```

`figure_manifest.json` maps each figure to its run identifiers, record count, and
the filters applied.

### 10.2 Report sections

1. What was measured. Counts, snapshot date, coverage.
2. How the datasets were built. Figures 1 to 3.
3. How they were reused. Figures 4 and 5.
4. Whether reuse compounds. Figure 6.
5. What could not be measured. Coverage gaps, classes below the precision bar,
   populations without full text.
6. Methods. Models, versions, gold set, judge calibration.

Section 5 is required. It is not a disclaimer.

### 10.3 Figures

The figure list below is provisional. Figure design will change once real
records exist, so treat this as a statement of which gold tables must be built,
not as a specification of the plots. Build the gold tables first. Design the
plots against real data.

| Figure | Content | Gold table | Key columns |
|---|---|---|---|
| F1 | format spread, assay by level, cell shows distinct format count | `gold/object_format.csv` | assay_name, level, format, group_key |
| F2 | cell-typing divergence, group by step, with label vocabulary | `gold/cell_typing.csv` | group_key, step, algorithm, label_vocabulary |
| F3 | TME method categories, consortium authors against reusers | `gold/tme_algorithm.csv` | doc_type, category, name |
| F4 | engagement kinds, showing combinations | `gold/engagement.csv` | doc_id, engagement_kind |
| F5 | data reuse task breakdown, split by author overlap | `gold/engagement.csv` | data_task, judge_verdict, author_overlap |
| F5b | internal against external reuse over time | `gold/engagement.csv` | author_overlap, pub_date |
| F6 | provenance chain: enumerated, full text, candidates, judged reusers, derived deposits | `gold/chain.csv` | stage, n |
| F7 | availability statement kinds, corpus against citing | `gold/availability.csv` | doc_type, statement_kind |
| F8 | coverage and measured precision per class | `gold/coverage.csv` | pass_name, class, n, precision |

Figure 8 is required. Every other figure states a result. Figure 8 states how
far to trust them.

### 10.4 Figure rules

These hold whatever the plots end up looking like.

1. Compute every number at render time. No figure contains a typed number.
2. Write the plotted data to a CSV with the same base name.
3. Print the denominator on the figure, not only in the caption.
4. Do not use colour as the only encoding.
5. Write SVG for print and PNG for slides.

---

## 11. Success conditions

A condition that is not met is reported as not met. It is not relaxed.

### 11.1 Acquisition
- OpenAlex re-queried. `snapshot_date` recorded in the report.
- Preprint pairs deduplicated. Count of merged pairs reported.
- At least 95 percent of works have full text or an abstract.
- Every fetched document records the source version retrieved.

### 11.2 Extraction
- Every shipped record has a verbatim quotation and character offsets.
- At least 99 percent of responses end with `finishReason == "STOP"`.
- The canary passed before every fan-out.
- Attribute population reported per class. Any attribute below 50 percent
  populated is flagged in the report.

### 11.3 Precision
- At least 150 human-labelled reuse records exist.
- Judge precision and recall measured against those labels.
- Every reported share carries its denominator and its judged share.
- Any class measured below 50 percent precision is removed, or its precision is
  printed next to every use of it.

### 11.4 Reproducibility
- The report regenerates from stored records with no typed numbers.
- Re-running from the same run identifiers reproduces the same numbers. Byte
  identity is not required.
- Run identifiers, model identifiers, and versions appear in the report.

### 11.5 Reusability
- Community specifics live in `communities/*.yaml`, not in code.
- `docs/adding-a-community.md` describes CCKP concretely.
- Any remaining hard-coded community strings are listed in the documentation as
  known limitations.

This is a design intention, not a tested claim. A second corpus will probably
break assumptions in accession patterns, section headings, and the grouping axis.

### 11.6 Deliverable
- One `REPORT.md` readable by a person with no prior context.
- Every figure has a backing CSV and a provenance note.
- The limitations section is written from measured values.

---

## 12. Build order

Build in this order. Each milestone is independently useful.

| # | Milestone | Done when |
|---|---|---|
| 1 | config, models, parse, tests | a JATS file yields text and a correct section index |
| 2 | acquire, PMC tier only | corpus documents fetched with versions recorded |
| 3 | pass compiler and canary | a pass YAML renders a prompt and passes the canary |
| 4 | extract, collect, align for one pass | the `availability` pass runs end to end on the corpus, about 0.25 US dollars |
| 5 | gold tables and one figure | F7 renders from real records |
| 6 | remaining corpus passes | measurement, analysis, abstract |
| 7 | citing acquisition, including preprints | tiers A to D complete |
| 8 | candidates and the provenance pass | anchor windows drive extraction |
| 9 | normalise | vocabulary map generated and applied |
| 10 | judge and gold labels | precision measured against human labels |
| 11 | full report | all eight figures, all sections |

Milestone 4 is the first end-to-end proof. A whole-document `availability` pass
over the 157 corpus documents costs about 0.25 US dollars. Prove the
architecture there before spending on the citing corpus, which is about 40 times
larger.

---

## 13. Open questions

1. **Gold set ownership.** Who produces the human labels, and to what protocol.
   This is the only item that blocks a success condition (11.3). Everything else
   can be built without it.
2. **Model for the citing full-text passes.** A strong model costs about 326 USD
   against about 41 USD for a small one, taking the total to about 439 USD. This
   is the only decision above the 200 USD threshold. Settle it with the
   500-document strong-model sample in 14.2, which is already budgeted.
3. **Pass granularity.** Five passes is inferred from a single measurement of
   class dilution. The recall curve for two, five, and eight passes is worth
   measuring on the corpus, where a full run costs about 1 USD.

---

## 14. Budget

Quality is the objective. Cost needs a decision from the project owner only
above about 200 US dollars. Below that, choose the higher-quality option without
asking.

Rates: small model 0.125 and 0.75 USD per million tokens; strong model 1.00 and
6.00. Both at batch rates. Verify before running; rates change.

### 14.1 Recommended configuration

| Stage | Model | Cost |
|---|---|---|
| corpus, 3 full-text passes | strong | 8.93 |
| corpus, dual-model union with a small model | both | 1.12 |
| provenance, anchor windows | strong | 39.93 |
| provenance, dual-model union | both | 4.99 |
| abstract, 9,799 documents, one per request | strong | 51.22 |
| citing, 3 full-text passes | small | 40.80 |
| citing, strong-model sample of 500 documents | strong | 31.40 |
| judge, per record | strong | 10.14 |
| second independent judge, agreement required | strong | 10.14 |
| normalise | strong | 0.50 |
| **total** | | **about 199 USD** |

This sits just under the threshold and includes every quality measure that fits.

### 14.2 The strong-model sample replaces a guess

An earlier draft proposed inferring citing-corpus model choice from a corpus
comparison. That is unsound. Corpus documents are consortium papers; citing
documents are heterogeneous. The comparison would not transfer.

Instead, run all three citing passes with the strong model on a random sample of
500 citing documents, about 31 USD. Compare records against the small-model
output on the same 500. This measures the recall and precision gap directly, on
the population it applies to.

If the gap is small, the small model stands and nothing more is spent. If the
gap is large, escalate.

### 14.3 The escalation, above the threshold

Running the strong model on all 5,197 citing documents costs about 326 USD
instead of 41. The total becomes about **439 USD**. This is the only decision in
the design above 200 USD, and it should be taken on the evidence from 14.2, not
in advance.

### 14.4 Quality measures included

Every one of these was excluded in an earlier draft to save money. All are now
included.

| Measure | Cost | Buys |
|---|---|---|
| whole documents, no section scoping | 13 | recall; facts are not where section names predict |
| one abstract per request | 17 | no cross-contamination between documents |
| judge per record | 7 | finer adjudication |
| strong model on the corpus | 8 | recall on 157 documents that anchor every corpus figure |
| citing measurement and analysis passes | 24 | the consortium-against-reuser comparison |
| corpus dual-model union | 1 | recall, plus a per-class reliability measurement |
| provenance dual-model union | 5 | recall on the least reliable extraction in the prototype |
| second independent judge | 10 | precision on the reuse claims |
| strong-model citing sample | 31 | evidence for the 326 USD decision |

### 14.5 Comparison with the prototype

The prototype billed 27.93 USD, of which about 21 was waste from two
misconfigured runs. The canary in rule 6.9 prevents that class of loss. Waste is
worth eliminating. A quality compromise to save tens of dollars is not.

---

## 15. Reference: prototype measurements

**These are not results. Do not quote them.**

Every value below came from prototype runs in August 2026. They are recorded so
that a builder can size a run, sanity-check an early output, and recognise a
number that has gone badly wrong. They are not findings and they must not appear
in the report.

Expect them to change on a rerun, several of them substantially:

| Reason | Effect |
|---|---|
| the citation graph is re-pulled | corpus and citing counts move; the prototype snapshot was 2026-06-01 |
| preprint deduplication is new | citing counts fall; 684 pairs collapse |
| whole documents replace section scoping | record counts rise |
| a strong model replaces a small one on the corpus | record counts rise |
| passes are split differently | per-class counts move; class dilution was measured at 58 percent for one change |
| vocabularies changed between runs | unmapped-value rates are not comparable across versions |
| the judge is new | any precision figure below is a prototype audit, not a calibrated measurement |

Two values are structural rather than sample-dependent, and should hold: mean
characters per token (about 4.15), and the section share profile of a
biomedical article.

Two values are the load-bearing evidence for design decisions in section 3, and
would need re-measuring before being relied on again: the 219 to 92 class
dilution, and the 57 percent attribution precision.

The report generates its own numbers from its own run. Nothing here feeds it.

### Corpora
| Value | Count |
|---|---|
| corpus documents | 169 |
| corpus documents with full text | 157 |
| corpus documents with an abstract | 166 |
| unique citing works | 9,799 |
| citation edges | 11,645 |
| citing works with full text in PMC | 5,197 |
| citing preprints | 1,917 |
| citing preprints with a published version in the set | 684 |
| substantive citing works that are themselves corpus documents | 58 of 1,711 |
| distinct corpus authors, prototype, name-based | 1,390 |

### Documents
| Value | Measure |
|---|---|
| mean corpus document length | 48,791 characters |
| mean abstract length | 1,241 characters |
| characters per token | 4.1 to 4.2 |

### Availability
| Value | Corpus | Citing |
|---|---|---|
| data availability section present | 58 of 157 | 1,907 of 5,197 |
| code availability section present | 9 of 157 | 203 of 5,197 |
| any accession named | not measured | 1,672 of 5,197 |
| GitHub repository named | not measured | 1,564 of 5,197 |
| no availability text at all | 73 of 157 | not measured |

### Extraction quality
| Value | Measure |
|---|---|
| `object_format` records, four classes in prompt | 219 |
| `object_format` records, five classes in prompt | 92 |
| `object_format` records after vocabulary fixes | 127 |
| `assay_name` unmapped, before vocabulary fixes | 45% |
| `assay_name` unmapped, after vocabulary fixes | 14% |
| `tme_algorithm` category unmapped, after fixes | 7% |
| cell-typing steps using an ontology | 0 of 393 |
| distinct clustering implementations | 40 |

### Reuse
| Value | Measure |
|---|---|
| citing documents the model called reusers | 1,030 |
| attribution precision, judged against a stronger model | 57% |
| `reproduce` label precision | 1 of 22 |
| citing documents naming the community with no identifier | 101 |
| citing documents with a community-specific identifier | 77 |
| citing documents quoting an accession also present in corpus text | 117 |

### Cost
| Value | Measure |
|---|---|
| total billed, prototype | 27.93 US dollars |
| waste from misconfigured runs | about 21 US dollars |
| output tokens, misconfigured run | 19.3 million |
| output tokens, corrected run, same input | 0.12 million |
