"""Parse tests per spec §9.6."""

from pathlib import Path

import pytest

from closeread.parse import make_windows, parse_jats
from closeread.parse.jats import parse_jats_file, source_version_from_name
from closeread.parse.sections import classify_heading

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = (FIXTURES / "synthetic_combined.xml").read_bytes()


@pytest.fixture(scope="module")
def synthetic():
    return parse_jats(SYNTHETIC)


@pytest.fixture(scope="module")
def real_corpus():
    return parse_jats_file(FIXTURES / "PMC12098973.1.xml")


class TestDropTags:
    def test_dropped_content_absent(self, synthetic):
        assert "MUST NOT APPEAR" not in synthetic.text

    def test_body_text_present(self, synthetic):
        assert "twelve cell states" in synthetic.text
        assert "Akoya PhenoCycler-Fusion" in synthetic.text

    def test_xref_markers_kept(self, synthetic):
        assert "[1]" in synthetic.text


class TestSectionLabels:
    def test_combined_heading_yields_both_labels(self, synthetic):
        pos = synthetic.text.index("syn26644864")
        labels = synthetic.sections.labels_at(pos)
        assert "data_availability" in labels
        assert "code_availability" in labels

    def test_nested_availability_beats_methods(self, synthetic):
        pos = synthetic.text.index("syn26644864")
        assert synthetic.sections.section_at(pos) in ("data_availability", "code_availability")

    def test_nested_plain_subsection_inherits_parent(self, synthetic):
        pos = synthetic.text.index("Mesmer")
        assert synthetic.sections.section_at(pos) == "methods"

    def test_standard_sections(self, synthetic):
        text = synthetic.text
        assert synthetic.sections.section_at(text.index("harmonised assays")) == "introduction"
        assert synthetic.sections.section_at(text.index("twelve cell states")) == "results"
        assert synthetic.sections.section_at(text.index("cross-centre comparison")) == "discussion"
        assert synthetic.sections.section_at(text.index("This abstract summarises")) == "abstract"

    def test_offsets_are_stable(self, synthetic):
        for span in synthetic.sections.spans:
            assert synthetic.text[span.start : span.end].strip() != ""
            assert 0 <= span.start < span.end <= len(synthetic.text)


class TestClassifyHeading:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Data and code availability", ["data_availability", "code_availability"]),
            ("Data availability", ["data_availability"]),
            ("Code availability", ["code_availability"]),
            ("Availability of data and materials", ["data_availability"]),
            ("STAR Methods", ["methods"]),
            ("Online Methods", ["methods"]),
            ("Experimental Procedures", ["methods"]),
            ("Results", ["results"]),
            ("Introduction", ["introduction"]),
            ("Discussion", ["discussion"]),
        ],
    )
    def test_headings(self, title, expected):
        assert classify_heading(title) == expected

    def test_unknown_heading_unclassified(self):
        assert classify_heading("Ethics approval") == []


class TestRealDocument:
    def test_parses_and_labels(self, real_corpus):
        assert len(real_corpus.text) > 10_000
        labels = {label for span in real_corpus.sections.spans for label in span.labels}
        assert "abstract" in labels
        assert "methods" in labels or "results" in labels

    def test_no_reference_list_noise(self, real_corpus):
        # A reference list would inject long runs of "et al." lines.
        assert real_corpus.text.count("et al") < 200

    def test_offsets_stable(self, real_corpus):
        span = real_corpus.sections.spans[0]
        assert real_corpus.text[span.start : span.end] == real_corpus.text[span.start : span.end]

    def test_citing_fixture_parses(self):
        doc = parse_jats_file(FIXTURES / "PMC11996304.1.xml")
        assert doc.text


class TestChunking:
    def test_single_window_when_short(self):
        assert make_windows(100, 30_000) == [make_windows(100, 30_000)[0]]
        w = make_windows(100, 30_000)
        assert len(w) == 1 and w[0].start == 0 and w[0].end == 100

    def test_windows_cover_document(self):
        windows = make_windows(100_000, 30_000, 1_500)
        assert windows[0].start == 0
        assert windows[-1].end == 100_000
        for a, b in zip(windows, windows[1:]):
            assert b.start < a.end  # overlap, no gaps

    def test_offsets_locate_in_parent(self):
        text = "x" * 50_000 + "MARKER" + "y" * 40_000
        windows = make_windows(len(text), 30_000, 1_500)
        hits = [w for w in windows if "MARKER" in w.slice(text)]
        assert hits
        for w in hits:
            local = w.slice(text).index("MARKER")
            assert text[w.start + local : w.start + local + 6] == "MARKER"

    def test_invalid_params_rejected(self):
        with pytest.raises(ValueError):
            make_windows(100, 0)
        with pytest.raises(ValueError):
            make_windows(100, 1000, 1000)


class TestSourceVersion:
    def test_version_extracted(self):
        assert source_version_from_name("PMC12098973.1.xml") == "1"
        assert source_version_from_name("PMC123.319.xml") == "319"
        assert source_version_from_name("PMC123.efetch.xml") is None
