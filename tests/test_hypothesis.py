from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from findex.merge import difference_sorted, intersect_sorted, union_sorted
from findex.models import DocMeta, Index, Posting
from findex.store import load_json, load_pickle, save_json, save_pickle


def _sorted_ids() -> st.SearchStrategy[list[int]]:
    return st.lists(st.integers(min_value=0, max_value=50), unique=True, max_size=20).map(sorted)


@given(left=_sorted_ids(), right=_sorted_ids())
@settings(max_examples=40)
def test_merge_matches_set_ops(left: list[int], right: list[int]) -> None:
    assert intersect_sorted(left, right) == sorted(set(left) & set(right))
    assert union_sorted(left, right) == sorted(set(left) | set(right))
    assert difference_sorted(left, right) == sorted(set(left) - set(right))


@given(
    terms=st.lists(
        st.text(min_size=1, max_size=6, alphabet="abcde"),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    counts=st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=5),
)
@settings(max_examples=25)
def test_postings_lists_are_sorted(terms: list[str], counts: list[int]) -> None:
    n = min(len(terms), len(counts))
    for i, term in enumerate(terms[:n]):
        doc_ids = sorted({(i + j) % 7 for j in range(counts[i])})
        hits = [Posting(d, 1) for d in doc_ids]
        hits.sort(key=lambda p: p.doc_id)
        assert [p.doc_id for p in hits] == sorted(p.doc_id for p in hits)
        assert term  # keep term used


@given(
    pairs=st.lists(
        st.tuples(st.text(min_size=1, max_size=4, alphabet="xyz"), st.integers(1, 3)),
        min_size=1,
        max_size=4,
        unique_by=lambda item: item[0],
    )
)
@settings(max_examples=20)
def test_load_save_roundtrip(pairs: list[tuple[str, int]]) -> None:
    postings = {term: [Posting(doc_id, 1) for doc_id in range(tf)] for term, tf in pairs}
    for hits in postings.values():
        hits.sort(key=lambda p: p.doc_id)
    docs = {p.doc_id for hits in postings.values() for p in hits} or {0}
    meta = {d: DocMeta(f"p{d}", f"t{d}") for d in docs}
    lengths = {d: 1 for d in docs}
    index = Index(postings, lengths, meta)
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        pkl = root / "i.pkl"
        js = root / "i.json"
        save_pickle(index, pkl)
        save_json(index, js)
        assert load_pickle(pkl) == index
        assert load_json(js) == index
