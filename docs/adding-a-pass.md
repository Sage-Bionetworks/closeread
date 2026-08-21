# Adding a pass

A pass is one extraction job over one small set of related classes. Passes are
split because class dilution is measured and real: adding a fifth class to a
four-class prompt cost 58 percent of one class's recall in the prototype. To
widen the extraction surface, add a pass — then re-measure recall on the
classes that already worked.

## The pass YAML

One file under `schemas/passes/` is the single source for the prompt, the
Gemini response schema, and the post-hoc validator (rule 6.10). The compiler
(`closeread/extract/compile.py`) generates all three; nothing else defines any
of them.

```yaml
pass: availability          # pass name, used in run_ids
version: 1.0.0              # becomes prompt_version and schema_version
applies_to: [corpus, citing]
sections: null              # null = whole document. A list of section labels
                            # is a COST CONTROL for the citing corpus only —
                            # scoping loses recall (§4.2.1).
window_chars: 30000
text_source: full_text      # or "abstract" (abstract pass only; one document
                            # per request, never packed)
classes:
  data_availability:
    absence_attributes: {statement_kind: no_statement}   # optional, rule 6.3
    description: >
      Instructions the model reads. Say what one record is.
    attributes:
      accession:      {type: string}            # free text
      repository:     {vocabulary: repository}  # closed list from schemas/vocabularies/
      key_methods:    {type: array, vocabulary: key_methods}  # multi-valued
    examples:
      - text: "Sequencing data are deposited in Synapse (syn12345678)."
        extractions:
          - span: "deposited in Synapse (syn12345678)"   # MUST appear verbatim in text
            accession: syn12345678
            repository: Synapse
```

## Rules the tests enforce

- Every example `span` appears verbatim in its example `text`.
- Every example attribute value is in its vocabulary (or `not_stated`).
- Every example demonstrates every attribute (attribute completeness comes
  from the prompt, §3.4).
- Prompt, response schema, and validator list the same classes.

## Vocabularies

Closed lists live in `schemas/vocabularies/<name>.yaml`. They are NOT enforced
as enums in the response schema: a value outside the list must surface in
`enum_drift` (rule 6.5), not be forced into the list or mapped to `other`.
Do not hand-write large canonicalisation dictionaries — that is what the
`normalise` stage's generated mapping table is for (§3.6).

## Before spending

`closeread extract --pass <name> --dry-run` prints request count and cost.
The canary then submits two real batch requests and asserts finishReason,
attribute completeness, and quote alignment before the fan-out goes out.
