from __future__ import annotations

import logging
from pathlib import Path

import pytest

from findex.models import DocMeta, Index, Posting
from findex.score import BM25
from findex.search import boolean_search, search
from findex.store import open_index, save_pickle


def _index() -> Index:
    postings = {
        "rare": [Posting(0, 1)],
        "common": [Posting(0, 1), Posting(1, 1)],
    }
    meta = {0: DocMeta("short", "short"), 1: DocMeta("long", "long")}
    return Index(postings, {0: 10, 1: 10_000}, meta)


def test_mapping_protocol() -> None:
    index = _index()
    assert len(index) == 2
    assert "rare" in index and "missing" not in index
    assert index["rare"][0].doc_id == 0
    with pytest.raises(KeyError):
        index["missing"]
    assert set(index) == {"rare", "common"}
    assert repr(index) == "Index(terms=2, docs=2)"
    assert index.num_docs == 2
    assert index.df("common") == 2 and index.df("nope") == 0
    assert index.avg_doc_length == 5005


def test_tiny_index_build(tiny_index: Index) -> None:
    assert tiny_index.num_docs == 3
    assert "alice" in tiny_index
    assert "frankenstein" in tiny_index
    assert "darcy" in tiny_index
    for hits in tiny_index.postings.values():
        ids = [p.doc_id for p in hits]
        assert ids == sorted(ids)


def test_boolean_on_tiny(tiny_index: Index) -> None:
    hits = boolean_search(tiny_index, "alice rabbit", "merge")
    assert hits == boolean_search(tiny_index, "alice rabbit", "set")
    assert hits


def test_open_index_closes_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "i.pkl"
    save_pickle(_index(), path)
    closed: dict[str, bool] = {}
    real_open = type(path).open

    def tracking(self: Path, *args: object, **kwargs: object):  # noqa: ANN001
        handle = real_open(self, *args, **kwargs)
        real_close = handle.close

        def close() -> None:
            closed["ok"] = True
            real_close()

        handle.close = close  # type: ignore[method-assign]
        return handle

    monkeypatch.setattr(type(path), "open", tracking)
    with pytest.raises(RuntimeError):
        with open_index(path):
            raise RuntimeError("boom")
    assert closed.get("ok")


def test_cache_hit_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    index = _index()
    with caplog.at_level(logging.DEBUG, logger="findex"):
        search(index, "rare", BM25(), k=5)
        search(index, "rare", BM25(), k=5)
    assert caplog.text.count("cache miss rare") == 1
    assert "cache hit rare" in caplog.text


def test_timed_keeps_the_name() -> None:
    assert search.__name__ == "search"
