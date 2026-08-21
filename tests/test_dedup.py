"""Dedup (§5.2) and author overlap (§5.2.1) tests."""

from closeread.acquire.dedup import (
    classify_author_overlap,
    dedup_preprints,
    is_preprint,
    normalise_title,
)


def _work(doc_id, title, doi, work_type="article", surname="smith", authors=None, first_last=None):
    return {
        "doc_id": doc_id,
        "title": title,
        "doi": doi,
        "work_type": work_type,
        "first_author_surname": surname,
        "author_ids": authors or [],
        "first_last_author_ids": first_last or [],
    }


class TestNormaliseTitle:
    def test_lowercase_alnum_truncated(self):
        assert normalise_title("Spatial Atlas: of the Tumor!") == "spatialatlasofthetumor"
        assert len(normalise_title("x y " * 100)) == 90

    def test_empty(self):
        assert normalise_title(None) == ""


class TestDedup:
    def test_pair_collapses_keeps_published(self):
        pub = _work("W1", "A spatial atlas of colon cancer", "10.1038/xyz", authors=["A1"])
        pre = _work("W2", "A Spatial Atlas of Colon Cancer.", "10.1101/2023.01.01", "preprint", authors=["A2"])
        kept, n = dedup_preprints([pub, pre])
        assert n == 1
        assert [w["doc_id"] for w in kept] == ["W1"]
        assert kept[0]["merged_from"] == ["W2"]
        assert kept[0]["author_ids"] == ["A1", "A2"]

    def test_title_match_alone_insufficient(self):
        pub = _work("W1", "Single cell analysis", "10.1038/x", surname="smith")
        pre = _work("W2", "Single cell analysis", "10.1101/y", "preprint", surname="jones")
        kept, n = dedup_preprints([pub, pre])
        assert n == 0
        assert len(kept) == 2

    def test_surname_match_collapses(self):
        pub = _work("W1", "Single cell analysis", "10.1038/x", surname="smith")
        pre = _work("W2", "Single cell analysis", "10.1101/y", "preprint", surname="smith")
        _, n = dedup_preprints([pub, pre])
        assert n == 1

    def test_orphan_preprint_kept(self):
        pre = _work("W2", "Unpublished work", "10.1101/z", "preprint")
        kept, n = dedup_preprints([pre])
        assert n == 0 and len(kept) == 1

    def test_biorxiv_doi_prefix_is_preprint(self):
        assert is_preprint(_work("W1", "t", "10.1101/2023.1", "article"))
        assert not is_preprint(_work("W1", "t", "10.1038/x", "article"))


class TestAuthorOverlap:
    CORPUS_DOCS = {"W100"}
    CORPUS_AUTHORS = {"A1", "A2", "A3"}

    def _classify(self, **kw):
        return classify_author_overlap(_work(**kw), self.CORPUS_DOCS, self.CORPUS_AUTHORS)

    def test_corpus_document(self):
        r = classify_author_overlap(
            _work(doc_id="W100", title="t", doi="d", authors=["A1"]),
            self.CORPUS_DOCS,
            self.CORPUS_AUTHORS,
        )
        assert r["author_overlap"] == "is_corpus_document"

    def test_external(self):
        r = self._classify(doc_id="W5", title="t", doi="d", authors=["B1", "B2"])
        assert r["author_overlap"] == "external"
        assert r["n_shared_authors"] == 0

    def test_shared_senior(self):
        r = self._classify(doc_id="W5", title="t", doi="d", authors=["A1", "B1"], first_last=["A1"])
        assert r["author_overlap"] == "shared_senior_author"
        assert r["shared_author_ids"] == ["A1"]

    def test_shared_middle_author(self):
        r = self._classify(doc_id="W5", title="t", doi="d", authors=["A2", "B1"], first_last=["B1"])
        assert r["author_overlap"] == "shared_author"
