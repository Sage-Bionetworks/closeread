"""Anchor-window tests (§4.2.3, §7.3)."""

from pathlib import Path

from closeread.candidates.anchors import (
    Anchor,
    accession_anchors,
    citation_anchors,
    identity_anchors,
    merge_anchor_windows,
)
from closeread.config import CommunityConfig, CorpusConfig
from closeread.parse import parse_jats

CONFIG = CommunityConfig(
    community="htan",
    display_name="Human Tumor Atlas Network",
    corpus=CorpusConfig(seed="data/corpus_seed.csv", group_by="htan_centre"),
    identity_strings=["HTAN", "Human Tumor Atlas Network"],
    accession_patterns={"synapse": r"syn\d{7,9}", "geo": r"GSE\d{4,7}"},
    portals=["humantumoratlas.org"],
)

XML = b"""<article>
  <front><article-meta><title-group><article-title>T</article-title></title-group></article-meta></front>
  <body>
    <sec><title>Introduction</title>
      <p>Prior atlases mapped tumours <xref ref-type="bibr" rid="r1">[1]</xref> and immune states <xref ref-type="bibr" rid="r2">[2]</xref> in depth across many cohorts and modalities.</p>
    </sec>
    <sec><title>Methods</title>
      <p>We reused HTAN imaging data from syn1234567 and compared against GSE11111 and GSE99999 count matrices for the full analysis.</p>
    </sec>
  </body>
  <back><ref-list>
    <ref id="r1"><mixed-citation><pub-id pub-id-type="doi">10.1016/j.ccell.2020.1</pub-id></mixed-citation></ref>
    <ref id="r2"><mixed-citation><pub-id pub-id-type="pmid">99999999</pub-id></mixed-citation></ref>
  </ref-list></back>
</article>"""


def _parsed(tmp_path):
    xml_path = tmp_path / "PMC1.1.xml"
    xml_path.write_bytes(XML)
    return xml_path, parse_jats(XML)


class TestAnchors:
    def test_identity_anchor_found(self, tmp_path):
        _, parsed = _parsed(tmp_path)
        anchors = identity_anchors(parsed.text, CONFIG)
        assert anchors
        assert parsed.text[anchors[0].start : anchors[0].end] == "HTAN"

    def test_community_accession_always_anchors(self, tmp_path):
        _, parsed = _parsed(tmp_path)
        anchors = accession_anchors(parsed.text, CONFIG, corpus_accessions=set())
        values = {parsed.text[a.start : a.end] for a in anchors}
        assert "syn1234567" in values

    def test_generic_accession_anchors_only_when_corpus_released(self, tmp_path):
        _, parsed = _parsed(tmp_path)
        none = accession_anchors(parsed.text, CONFIG, corpus_accessions=set())
        values_none = {parsed.text[a.start : a.end] for a in none}
        assert "GSE11111" not in values_none
        some = accession_anchors(parsed.text, CONFIG, corpus_accessions={"GSE11111"})
        values_some = {parsed.text[a.start : a.end] for a in some}
        assert "GSE11111" in values_some
        assert "GSE99999" not in values_some

    def test_citation_marker_resolves_to_corpus(self, tmp_path):
        xml_path, parsed = _parsed(tmp_path)
        anchors = citation_anchors(
            xml_path, parsed, corpus_dois={"10.1016/j.ccell.2020.1"}, corpus_pmids=set()
        )
        assert len(anchors) == 1
        # The anchor sits inside the introduction paragraph.
        assert "Prior atlases" in parsed.text[max(0, anchors[0].start - 60) : anchors[0].end + 60]

    def test_non_corpus_citation_ignored(self, tmp_path):
        xml_path, parsed = _parsed(tmp_path)
        anchors = citation_anchors(xml_path, parsed, corpus_dois={"10.9999/other"}, corpus_pmids=set())
        assert anchors == []


class TestMergeWindows:
    def test_overlapping_anchors_merge(self):
        anchors = [Anchor(100, 104, "identity_string"), Anchor(150, 160, "accession")]
        windows = merge_anchor_windows(anchors, text_length=10_000, radius=100)
        assert windows == [(0, 260)]

    def test_distant_anchors_stay_separate(self):
        anchors = [Anchor(100, 104, "identity_string"), Anchor(5_000, 5_004, "accession")]
        windows = merge_anchor_windows(anchors, text_length=10_000, radius=100)
        assert len(windows) == 2

    def test_bounds_clamped(self):
        windows = merge_anchor_windows([Anchor(10, 14, "x")], text_length=50, radius=100)
        assert windows == [(0, 50)]

    def test_empty(self):
        assert merge_anchor_windows([], 100) == []
