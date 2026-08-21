"""Compiler and pass-definition tests per spec §9.6 and rule 6.10."""

import pytest

from closeread.extract.compile import PASSES_DIR, load_pass

PASS_FILES = sorted(PASSES_DIR.glob("*.yaml"))


@pytest.fixture(scope="module")
def availability():
    return load_pass("availability")


@pytest.mark.parametrize("pass_file", PASS_FILES, ids=lambda p: p.stem)
class TestEveryPassDefinition:
    def test_example_spans_verbatim(self, pass_file):
        compiled = load_pass(pass_file)
        for cls in compiled.classes.values():
            for ex in cls.examples:
                for extraction in ex["extractions"]:
                    assert extraction["span"] in ex["text"], (
                        f"{compiled.name}/{cls.name}: span not verbatim in example text: "
                        f"{extraction['span']!r}"
                    )

    def test_example_attributes_in_vocabulary(self, pass_file):
        compiled = load_pass(pass_file)
        for cls in compiled.classes.values():
            for ex in cls.examples:
                for extraction in ex["extractions"]:
                    for attr_name, value in extraction.items():
                        if attr_name == "span":
                            continue
                        spec = cls.attributes.get(attr_name)
                        assert spec is not None, f"{cls.name}: example uses unknown attribute {attr_name}"
                        if spec.values:
                            elements = value if isinstance(value, list) else [value]
                            for el in elements:
                                assert str(el) in spec.values or str(el) == "not_stated", (
                                    f"{cls.name}.{attr_name}: example value {el!r} not in vocabulary"
                                )

    def test_example_attributes_complete(self, pass_file):
        # §3.4: attribute completeness is demonstrated, not just stated.
        compiled = load_pass(pass_file)
        for cls in compiled.classes.values():
            for ex in cls.examples:
                for extraction in ex["extractions"]:
                    missing = set(cls.attributes) - set(extraction)
                    assert not missing, f"{cls.name}: example missing attributes {missing}"


class TestOneSource:
    def test_prompt_schema_validator_list_same_classes(self, availability):
        prompt = availability.prompt("dummy text")
        schema = availability.response_schema()
        for cls_name in availability.classes:
            assert f"## {cls_name}" in prompt
            assert cls_name in schema["properties"]
            assert cls_name in schema["required"]
        # validator: a payload missing a class key is flagged
        issues = availability.validate_response({})
        for cls_name in availability.classes:
            assert any(cls_name in i for i in issues)

    def test_prompt_states_attribute_completeness(self, availability):
        prompt = availability.prompt("x")
        assert "Every attribute key must appear" in prompt
        assert "not_stated" in prompt

    def test_schema_marks_attributes_required(self, availability):
        schema = availability.response_schema()
        for cls_name, cls in availability.classes.items():
            required = schema["properties"][cls_name]["items"]["required"]
            assert set(required) == {"source_quote", *cls.attributes}

    def test_document_text_embedded(self, availability):
        assert "UNIQUE_SENTINEL_1234" in availability.prompt("UNIQUE_SENTINEL_1234")


class TestValidatorAndDrift:
    def test_valid_response_passes(self, availability):
        payload = {
            "data_availability": [
                {
                    "source_quote": "q",
                    "accession": "syn1",
                    "repository": "Synapse",
                    "access_tier": "open",
                    "access_mechanism": "direct_download",
                    "statement_kind": "full_deposit",
                    "direction": "released",
                }
            ],
            "code_availability": [],
        }
        assert availability.validate_response(payload) == []

    def test_missing_attribute_flagged(self, availability):
        payload = {"data_availability": [{"source_quote": "q"}], "code_availability": []}
        assert any("missing attribute" in i for i in availability.validate_response(payload))

    def test_enum_drift_captured_not_mapped(self, availability):
        attrs = {
            "accession": "x",
            "repository": "Vitessce Data Portal",  # outside the closed list
            "access_tier": "open",
            "access_mechanism": "direct_download",
            "statement_kind": "full_deposit",
            "direction": "released",
        }
        drift = availability.enum_drift("data_availability", attrs)
        assert drift == ["repository=Vitessce Data Portal"]

    def test_in_vocabulary_no_drift(self, availability):
        attrs = {
            "accession": "x",
            "repository": "GEO",
            "access_tier": "open",
            "access_mechanism": "direct_download",
            "statement_kind": "full_deposit",
            "direction": "acquired",
        }
        assert availability.enum_drift("data_availability", attrs) == []
