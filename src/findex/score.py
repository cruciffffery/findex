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


import math as _math

import numpy as np


def add_bm25_term(
    scores: np.ndarray,
    index: Index,
    term: str,
    *,
    k1: float = 1.5,
    b: float = 0.75,
    allow: set[int] | None = None,
    seen: np.ndarray | None = None,
) -> None:
    doc_ids, tfs = index.arrays_for(term)
    if doc_ids.size == 0:
        return
    if allow is not None:
        keep = np.fromiter(allow, dtype=np.int32, count=len(allow))
        mask = np.isin(doc_ids, keep)
        if not mask.any():
            return
        doc_ids = doc_ids[mask]
        tfs = tfs[mask]
    df = index.df(term)
    if df == 0:
        return
    idf = _math.log(index.num_docs / df)
    tf = tfs.astype(np.float64)
    dl = index.length_vector[doc_ids].astype(np.float64)
    avg = index.avg_doc_length or 1.0
    denom = k1 * (1.0 - b + b * dl / avg)
    scores[doc_ids] += idf * tf * (k1 + 1.0) / (tf + denom)
    if seen is not None:
        seen[doc_ids] = True


def add_tfidf_term(
    scores: np.ndarray,
    index: Index,
    term: str,
    *,
    allow: set[int] | None = None,
    seen: np.ndarray | None = None,
) -> None:
    doc_ids, tfs = index.arrays_for(term)
    if doc_ids.size == 0:
        return
    if allow is not None:
        keep = np.fromiter(allow, dtype=np.int32, count=len(allow))
        mask = np.isin(doc_ids, keep)
        if not mask.any():
            return
        doc_ids = doc_ids[mask]
        tfs = tfs[mask]
    df = index.df(term)
    if df == 0:
        return
    idf = _math.log(index.num_docs / df)
    tf = tfs.astype(np.float64)
    scores[doc_ids] += (1.0 + np.log(tf)) * idf
    if seen is not None:
        seen[doc_ids] = True


def pick_topk(
    scores: np.ndarray,
    k: int,
    *,
    seen: np.ndarray | None = None,
) -> list[tuple[int, float]]:
    # argpartition top-k; ties → lower doc_id first
    if seen is not None:
        nz = np.flatnonzero(seen)
    else:
        nz = np.flatnonzero(scores)
    if nz.size == 0:
        return []
    if nz.size <= k:
        chosen = nz
    else:
        part = np.argpartition(scores[nz], -k)[-k:]
        chosen = nz[part]
    order = np.lexsort((chosen, -scores[chosen]))
    chosen = chosen[order]
    return [(int(i), float(scores[i])) for i in chosen]

