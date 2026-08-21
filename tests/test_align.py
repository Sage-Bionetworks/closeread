"""Alignment tests per spec §9.6: a verbatim quotation aligns; an invented
quotation is rejected."""

from closeread.collect.align import align_quote
from closeread.models import AlignmentStatus

TEXT = (
    "Introduction\n\nTumour atlases require harmonised assays.\n\n"
    "Data availability\n\nSequencing data are deposited in Synapse (syn12345678) "
    "and imaging data are in the HTAN portal.\n\n"
    "Sequencing data are deposited in Synapse (syn99999999) for the validation cohort."
)


class TestAlign:
    def test_verbatim_quote_aligns_exact(self):
        a = align_quote("deposited in Synapse (syn12345678)", TEXT)
        assert a is not None
        assert a.status == AlignmentStatus.match_exact
        assert TEXT[a.start : a.end] == "deposited in Synapse (syn12345678)"

    def test_invented_quote_rejected(self):
        assert align_quote("data are available on Zenodo record 42", TEXT) is None

    def test_whitespace_difference_is_fuzzy(self):
        a = align_quote("deposited in  Synapse\n(syn12345678)", TEXT)
        assert a is not None
        assert a.status == AlignmentStatus.match_fuzzy
        assert "syn12345678" in TEXT[a.start : a.end]

    def test_case_difference_is_lesser(self):
        a = align_quote("SEQUENCING DATA ARE DEPOSITED in Synapse (syn12345678)", TEXT)
        assert a is not None
        assert a.status == AlignmentStatus.match_lesser

    def test_curly_quote_tolerated(self):
        text = "The authors’ data are shared."
        a = align_quote("The authors' data are shared.", text)
        assert a is not None

    def test_hint_picks_nearest_occurrence(self):
        near_end = align_quote("Sequencing data are deposited in Synapse", TEXT, hint=len(TEXT) - 10)
        near_start = align_quote("Sequencing data are deposited in Synapse", TEXT, hint=0)
        assert near_end is not None and near_start is not None
        assert near_end.start > near_start.start

    def test_empty_quote_rejected(self):
        assert align_quote("", TEXT) is None
        assert align_quote("   ", TEXT) is None
