"""Collect tests per spec §9.6: every record carries the full provenance field
set; unaligned records go to rejected; absence records are written (rule 6.3)."""

import json

import pytest

from closeread.collect import run_collect
from closeread.config import Settings
from closeread.jsonl import read_jsonl

DOC_TEXT = (
    "Introduction\n\nWe study tumours.\n\n"
    "Data availability\n\nSequencing data are deposited in GEO (GSE11111) under open access."
)

RESPONSE_PAYLOAD = {
    "data_availability": [
        {
            "source_quote": "deposited in GEO (GSE11111)",
            "accession": "GSE11111",
            "repository": "GEO",
            "access_tier": "open",
            "access_mechanism": "direct_download",
            "statement_kind": "full_deposit",
            "direction": "released",
        },
        {
            "source_quote": "this sentence was invented by the model",
            "accession": "not_stated",
            "repository": "GEO",
            "access_tier": "not_stated",
            "access_mechanism": "not_stated",
            "statement_kind": "full_deposit",
            "direction": "released",
        },
    ],
    "code_availability": [],
}


@pytest.fixture()
def run(tmp_path):
    settings = Settings(out_dir=tmp_path)
    out = tmp_path / "htan"
    run_id = "htan_availability_20260821_001"
    (out / "parsed").mkdir(parents=True)
    (out / "parsed" / "W1.json").write_text(
        json.dumps(
            {
                "doc_id": "W1",
                "doc_title": "T",
                "text": DOC_TEXT,
                "sections": [
                    {"labels": ["introduction"], "title": "Introduction", "start": 0, "end": 31},
                    {"labels": ["data_availability"], "title": "Data availability", "start": 33, "end": len(DOC_TEXT)},
                ],
            }
        )
    )
    (out / "runs").mkdir()
    (out / "runs" / f"{run_id}.handoff.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "community": "htan",
                "pass_name": "availability",
                "model": "test-model",
                "prompt_version": "1.0.0",
                "schema_version": "1.0.0",
                "n_requests": 1,
                "batch_job_name": "batches/test",
                "sections_read": None,
                "key_index": {"W1|0|0": {"doc_id": "W1", "window_index": 0, "window_start": 0, "window_end": len(DOC_TEXT)}},
            }
        )
    )
    responses = out / "raw" / "batch" / f"{run_id}.responses.jsonl"
    responses.parent.mkdir(parents=True)
    responses.write_text(
        json.dumps(
            {
                "key": "W1|0|0",
                "response": {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": json.dumps(RESPONSE_PAYLOAD)}]},
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 100},
                },
            }
        )
        + "\n"
    )
    summary = run_collect(run_id, settings, log=lambda *a, **k: None)
    records = list(read_jsonl(out / "bronze" / f"records_{run_id}.jsonl"))
    rejected = list(read_jsonl(out / "bronze" / f"rejected_{run_id}.jsonl"))
    return summary, records, rejected


PROVENANCE_FIELDS = (
    "record_id",
    "run_id",
    "doc_id",
    "community",
    "pass_name",
    "extraction_class",
    "source_quote",
    "char_start",
    "char_end",
    "source_section",
    "alignment_status",
    "attributes",
    "enum_drift",
    "extractor_model",
    "prompt_version",
    "schema_version",
    "evidence_scope",
)


class TestCollect:
    def test_aligned_record_shipped_with_offsets(self, run):
        _, records, _ = run
        real = [r for r in records if r["source_quote"]]
        assert len(real) == 1
        r = real[0]
        assert DOC_TEXT[r["char_start"] : r["char_end"]] == r["source_quote"]
        assert r["source_section"] == "data_availability"

    def test_invented_quote_rejected_never_shipped(self, run):
        _, records, rejected = run
        assert all("invented by the model" not in r["source_quote"] for r in records)
        assert any(r["reject_reason"] == "quote_not_in_source" for r in rejected)

    def test_full_provenance_field_set(self, run):
        _, records, _ = run
        for r in records:
            for field in PROVENANCE_FIELDS:
                assert field in r, f"record missing {field}"

    def test_absence_record_written_for_silent_class(self, run):
        _, records, _ = run
        absence = [r for r in records if r["extraction_class"] == "code_availability"]
        assert len(absence) == 1
        assert absence[0]["attributes"]["statement_kind"] == "no_statement"
        assert absence[0]["source_quote"] == ""

    def test_summary_counts(self, run):
        summary, _, _ = run
        assert summary["stop_share"] == 1.0
        assert summary["records"] == 2
        assert summary["extracted_records"] == 1
        assert summary["absence_records"] == 1
        assert summary["rejected"] == 1
        assert summary["attribute_population"]["data_availability"]["repository"] == 1.0
