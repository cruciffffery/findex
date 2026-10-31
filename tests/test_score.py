from __future__ import annotations

from findex.models import DocMeta, Index, Posting
from findex.score import BM25, TfIdf, pick_scorer


def _index() -> Index:
    postings = {
        "rare": [Posting(0, 1)],
        "common": [Posting(0, 1), Posting(1, 1)],
    }
    meta = {0: DocMeta("short", "short"), 1: DocMeta("long", "long")}
    return Index(postings, {0: 10, 1: 10_000}, meta)


def test_bm25_rare_beats_common() -> None:
    index = _index()
    bm = BM25()
    assert bm("rare", Posting(0, 1), index) > bm("common", Posting(0, 1), index)


def test_bm25_saturation() -> None:
    index = _index()
    bm = BM25()
    first = bm("rare", Posting(0, 1), index)
    step20 = bm("rare", Posting(0, 20), index) - bm("rare", Posting(0, 19), index)
    assert step20 < first


def test_bm25_short_beats_long() -> None:
    index = _index()
    bm = BM25()
    assert bm("rare", Posting(0, 1), index) > bm("rare", Posting(1, 1), index)
    flat = BM25(b=0)
    assert flat("rare", Posting(0, 1), index) == flat("rare", Posting(1, 1), index)


def test_tfidf_positive() -> None:
    index = _index()
    assert TfIdf()("rare", Posting(0, 2), index) > 0


def test_pick_scorer() -> None:
    assert isinstance(pick_scorer("bm25"), BM25)
    assert isinstance(pick_scorer("tfidf"), TfIdf)
