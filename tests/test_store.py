from __future__ import annotations

from pathlib import Path

from findex.models import DocMeta, Index, Posting
from findex.store import load_json, load_pickle, save_json, save_pickle


def _index() -> Index:
    postings = {
        "a": [Posting(0, 1, (0,)), Posting(1, 2, (1, 2))],
        "b": [Posting(1, 1)],
    }
    meta = {0: DocMeta("p0", "t0"), 1: DocMeta("p1", "t1")}
    return Index(postings, {0: 3, 1: 4}, meta)


def test_pickle_roundtrip(tmp_path: Path) -> None:
    index = _index()
    path = tmp_path / "i.pkl"
    save_pickle(index, path)
    loaded = load_pickle(path)
    assert loaded == index


def test_json_roundtrip(tmp_path: Path) -> None:
    index = _index()
    path = tmp_path / "i.json"
    save_json(index, path)
    assert load_json(path) == index
