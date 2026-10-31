from __future__ import annotations

import logging
import math
from typing import Protocol

from findex.models import Index, Posting

log = logging.getLogger(__name__)


class Scorer(Protocol):
    def __call__(self, term: str, posting: Posting, index: Index) -> float: ...


class TfIdf:
    def __call__(self, term: str, posting: Posting, index: Index) -> float:
        df = index.df(term)
        if df == 0:
            return 0.0
        idf = math.log(index.num_docs / df)
        return (1.0 + math.log(posting.tf)) * idf


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    def __call__(self, term: str, posting: Posting, index: Index) -> float:
        df = index.df(term)
        if df == 0:
            return 0.0
        idf = math.log(index.num_docs / df)
        dl = index.doc_length(posting.doc_id)
        avg = index.avg_doc_length or 1.0
        length_norm = 1.0 - self.b + self.b * dl / avg
        tf = posting.tf
        return idf * (tf * (self.k1 + 1.0)) / (tf + self.k1 * length_norm)


def pick_scorer(name: str) -> Scorer:
    key = name.casefold()
    if key == "tfidf":
        return TfIdf()
    if key == "bm25":
        return BM25()
    raise ValueError(f"unknown scorer: {name}")
