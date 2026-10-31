from __future__ import annotations

from findex.models import DocMeta, Index, Posting
from findex.score import BM25
from findex.search import boolean_search, search


def _index() -> Index:
    postings = {
        "a": [Posting(0, 1), Posting(1, 1), Posting(2, 1)],
        "b": [Posting(1, 1), Posting(2, 1)],
        "c": [Posting(2, 1)],
    }
    meta = {i: DocMeta(str(i), str(i)) for i in range(4)}
    lengths = {i: 1 for i in range(4)}
    return Index(postings, lengths, meta)


def test_frozen_records_go_in_a_set() -> None:
    found = {Posting(1, 2), DocMeta("a", "b")}
    assert Posting(1, 2) in found
    assert DocMeta("a", "b") in found


def test_merge_and_set_agree() -> None:
    index = _index()
    queries = ("a b", "a OR c", "a NOT b", "NOT a")
    expect = ([1, 2], [0, 1, 2], [0], [3])
    for query, hits in zip(queries, expect, strict=True):
        assert boolean_search(index, query, "merge") == hits
        assert boolean_search(index, query, "set") == hits


def test_ranked_search_returns_results() -> None:
    index = _index()
    hits = search(index, "a b", BM25(), k=5)
    assert hits
    assert hits[0].score >= hits[-1].score
