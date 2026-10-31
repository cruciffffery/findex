from __future__ import annotations

from pathlib import Path

import pytest

from findex.index import build_corpus
from findex.models import Index

FIX_CORPUS = Path(__file__).resolve().parent / "corpus"


@pytest.fixture(scope="session")
def tiny_corpus() -> Path:
    return FIX_CORPUS


@pytest.fixture(scope="session")
def tiny_index(tiny_corpus: Path) -> Index:
    return build_corpus(tiny_corpus, with_positions=True)
