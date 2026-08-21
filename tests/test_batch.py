"""Batch request tests per spec §9.6: generationConfig is camelCase and
maxOutputTokens is present. This guards against the §3.3 failure that cost
about 21 USD in the prototype."""

import json

from closeread.extract.batch import build_requests, estimate, generation_config, request_key
from closeread.extract.compile import load_pass
from closeread.parse.jats import parse_jats

XML = b"""<article><front><article-meta>
<title-group><article-title>T</article-title></title-group>
<abstract><p>An abstract.</p></abstract></article-meta></front>
<body><sec><title>Data availability</title><p>Data are deposited in GEO (GSE12345).</p></sec></body></article>"""


def _docs():
    return {"W1": parse_jats(XML)}


class TestCamelCase:
    def test_generation_config_keys_are_camelcase(self):
        config = generation_config(load_pass("availability"))
        assert "responseMimeType" in config
        assert "responseSchema" in config
        assert "maxOutputTokens" in config
        # The silent-failure spellings must be absent anywhere in the payload.
        blob = json.dumps(config)
        for bad in ("generation_config", "response_mime_type", "response_schema", "max_output_tokens"):
            assert bad not in blob

    def test_request_lines_use_generationConfig(self):
        lines, _ = build_requests(load_pass("availability"), _docs())
        blob = json.dumps(lines[0])
        assert '"generationConfig"' in blob
        assert "generation_config" not in blob
        assert lines[0]["request"]["generationConfig"]["maxOutputTokens"] == 16384
        assert lines[0]["request"]["generationConfig"]["temperature"] == 0


class TestRequests:
    def test_one_request_per_window_and_keys_unique(self):
        lines, index = build_requests(load_pass("availability"), _docs())
        assert len(lines) == 1  # short doc, one window
        assert set(index) == {l["key"] for l in lines}
        assert index[lines[0]["key"]]["doc_id"] == "W1"

    def test_key_roundtrip(self):
        assert request_key("W1", 0, 0) == "W1|0|0"

    def test_estimate_is_positive(self):
        lines, _ = build_requests(load_pass("availability"), _docs())
        est = estimate(lines, "gemini-3.1-pro-preview")
        assert est.n_requests == 1
        assert est.est_tokens_in > 0
        assert 0 < est.est_cost_usd < 1
