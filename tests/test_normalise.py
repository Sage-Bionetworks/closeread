"""Normalise tests per spec §9.6: raw values are preserved; canonical values
are added."""

import json

from closeread.config import Settings
from closeread.jsonl import read_jsonl, write_jsonl
from closeread.normalise.vocab import apply_to_silver, collect_distinct_values


def _record(doc_id, cls, attrs, record_id="r1"):
    return {
        "record_id": record_id,
        "run_id": "htan_measurement_20260821_001",
        "doc_id": doc_id,
        "community": "htan",
        "pass_name": "measurement",
        "extraction_class": cls,
        "source_quote": "q",
        "char_start": 0,
        "char_end": 1,
        "source_section": "methods",
        "alignment_status": "match_exact",
        "attributes": attrs,
        "attributes_canonical": None,
        "enum_drift": [],
        "candidate_support": False,
        "judge_verdict": None,
        "judge_confidence": None,
        "judge_reason": None,
        "extractor_model": "m",
        "prompt_version": "1.0.0",
        "schema_version": "1.0.0",
        "evidence_scope": "full_text",
    }


def _setup(tmp_path):
    settings = Settings(out_dir=tmp_path)
    out = tmp_path / "htan"
    write_jsonl(
        out / "bronze" / "records_htan_measurement_20260821_001.jsonl",
        [
            _record("W1", "assay_platform", {"assay_type": "scRNA_seq", "assay_name": "10x scRNAseq", "platform": None, "vendor": "10X"}, "r1"),
            _record("W1", "assay_platform", {"assay_type": "scRNA_seq", "assay_name": "Chromium 3' v3", "platform": None, "vendor": "10x Genomics"}, "r2"),
        ],
    )
    write_jsonl(
        out / "vocab_map.jsonl",
        [
            {"value_set": "assay_name", "surface_form": "10x scRNAseq", "canonical_form": "Chromium scRNA-seq", "mapping_version": "v"},
            {"value_set": "vendor", "surface_form": "10X", "canonical_form": "10x Genomics", "mapping_version": "v"},
        ],
    )
    return settings, out


class TestNormalise:
    def test_raw_preserved_canonical_added(self, tmp_path):
        settings, out = _setup(tmp_path)
        apply_to_silver(settings, "htan", log=lambda *a: None)
        rows = list(read_jsonl(out / "silver" / "records_htan_measurement_20260821_001.jsonl"))
        r1 = next(r for r in rows if r["record_id"] == "r1")
        assert r1["attributes"]["assay_name"] == "10x scRNAseq"  # raw untouched
        assert r1["attributes_canonical"]["assay_name"] == "Chromium scRNA-seq"
        assert r1["attributes_canonical"]["vendor"] == "10x Genomics"

    def test_unmapped_value_maps_to_itself(self, tmp_path):
        settings, out = _setup(tmp_path)
        apply_to_silver(settings, "htan", log=lambda *a: None)
        rows = list(read_jsonl(out / "silver" / "records_htan_measurement_20260821_001.jsonl"))
        r2 = next(r for r in rows if r["record_id"] == "r2")
        assert r2["attributes_canonical"]["assay_name"] == "Chromium 3' v3"

    def test_collect_distinct_skips_not_stated(self, tmp_path):
        settings, out = _setup(tmp_path)
        values = collect_distinct_values(settings, "htan", "assay_name")
        assert values == ["10x scRNAseq", "Chromium 3' v3"]

    def test_bronze_files_untouched(self, tmp_path):
        settings, out = _setup(tmp_path)
        before = (out / "bronze" / "records_htan_measurement_20260821_001.jsonl").read_text()
        apply_to_silver(settings, "htan", log=lambda *a: None)
        after = (out / "bronze" / "records_htan_measurement_20260821_001.jsonl").read_text()
        assert before == after
