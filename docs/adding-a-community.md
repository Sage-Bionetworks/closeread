# Adding a community

Community specifics live in `communities/<name>.yaml`, not in code. This page
works the format through with CCKP (the Cancer Complexity Knowledge Portal).
Reusability is a design intention, not a tested claim: a second corpus will
probably stress accession patterns, section headings, and the grouping axis.

## The community YAML

```yaml
community: cckp
display_name: Cancer Complexity Knowledge Portal
corpus:
  seed: data/cckp_corpus_seed.csv   # csv with pmid, doi, pmcid, title + a grouping column
  group_by: grant_theme             # the column that becomes group_key
identity_strings: ["Cancer Complexity Knowledge Portal", "CCKP", "MC2 Center"]
accession_patterns:                 # regexes; candidates only, never meaning (§3.2)
  synapse: 'syn\d{7,9}'
  geo:     'GSE\d{4,7}'
portals: ["cancercomplexity.synapse.org"]
passes: [availability, measurement, analysis, provenance, abstract]
aws_profile_requester_pays: htan-dev
```

## What each field drives

| Field | Consumed by |
|---|---|
| `corpus.seed` | `acquire` — resolved against OpenAlex; the seed is identifiers, everything else is re-queried |
| `corpus.group_by` | `group_key` on documents; the grouping axis for figures |
| `identity_strings` | anchor windows in the `provenance` pass |
| `accession_patterns` | the `candidates` stage; recall measurement and anchors |
| `portals` | candidate URL patterns |
| `passes` | which pass YAMLs apply |

## Steps

1. Build a seed CSV with one row per corpus publication (pmid or doi required).
2. Write `communities/cckp.yaml` as above.
3. `closeread acquire --community cckp` then `parse`, `candidates`.
4. Dry-run the availability pass; run the canary; extract.

## Known limitations (hard-coded community strings)

- The seed-column names `pmid`, `doi`, `pmcid`, `title` are fixed; only the
  grouping column is configurable.
- Section-heading patterns in `closeread/parse/sections.py` are biomedical
  (JATS from PMC). A community outside PMC needs a new acquisition tier.
- Preprint DOI prefixes in `closeread/acquire/dedup.py` cover bioRxiv,
  medRxiv, Research Square, and SSRN only.
