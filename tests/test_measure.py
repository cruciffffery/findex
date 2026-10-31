from __future__ import annotations

from pathlib import Path

import pytest

from findex.measure import corpus_stats, token_list


def test_corpus_stats(tiny_corpus: Path) -> None:
    stats = corpus_stats(tiny_corpus, top=5)
    assert stats.document_count == 3
    assert stats.token_count > 0
    assert stats.vocabulary > 0
    assert len(stats.frequent_terms) <= 5


def test_token_list() -> None:
    assert token_list("Hello, world") == ["hello", "world"]


@pytest.mark.slow
def test_stats_on_resources() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "resources"
    if not any(root.glob("*.txt")):
        pytest.skip("no resources")
    stats = corpus_stats(root, top=3)
    assert stats.document_count >= 1
