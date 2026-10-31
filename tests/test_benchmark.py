"""pytest-benchmark: catch regressions on search / build_index."""
from __future__ import annotations

from pathlib import Path

import pytest

from findex.index import build_corpus
from findex.models import DocMeta, Index, Posting
from findex.score import BM25
from findex.search import search


def _tiny() -> Index:
    postings = {
        "alice": [Posting(0, 2), Posting(1, 1)],
        "rabbit": [Posting(0, 1), Posting(1, 1)],
        "garden": [Posting(1, 3)],
    }
    index = Index(
        postings,
        {0: 5, 1: 8},
        {0: DocMeta("0.txt", "a"), 1: DocMeta("1.txt", "b")},
    )
    index.ensure_arrays()
    return index


def test_bench_search(benchmark) -> None:
    index = _tiny()

    def run():
        return search(index, "alice rabbit", BM25(), k=5, with_snippet=False, backend="numpy")

    result = benchmark(run)
    assert len(result) >= 1


def test_bench_build_index(benchmark, tmp_path: Path) -> None:
    for i, text in enumerate(["alpha beta gamma", "beta delta", "gamma alice rabbit"]):
        (tmp_path / f"d{i}.txt").write_text(text, encoding="utf-8")

    def run():
        return build_corpus(tmp_path, with_positions=False, executor="serial", workers=1)

    index = benchmark(run)
    assert index.num_docs == 3
