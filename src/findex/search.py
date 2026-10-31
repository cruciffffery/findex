from __future__ import annotations

import functools
import heapq
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import numpy as np

from findex.deco import timed
from findex.fuse import fuse_ranks
from findex.merge import (
    difference_set,
    difference_sorted,
    intersect_set,
    intersect_sorted,
    union_set,
    union_sorted,
)
from findex.models import Index, SearchResult
from findex.query import parse, query_terms
from findex.score import (
    BM25,
    Scorer,
    TfIdf,
    add_bm25_term,
    add_tfidf_term,
    pick_scorer,
    pick_topk,
)
from findex.vectors import VectorBank, encode_query

log = logging.getLogger(__name__)

EngineName = Literal["merge", "set"]
SearchMode = Literal["keyword", "semantic", "hybrid"]
ScoreBackend = Literal["loop", "numpy"]

_OPS = {
    "merge": {"AND": intersect_sorted, "OR": union_sorted, "NOT": difference_sorted},
    "set": {"AND": intersect_set, "OR": union_set, "NOT": difference_set},
}


def _doc_ids(index: Index, term: str) -> list[int]:
    hits = index.postings.get(term)
    if not hits:
        return []
    return [hit.doc_id for hit in hits]


def boolean_search(index: Index, query: str, engine: EngineName) -> list[int]:
    universe = sorted(index.doc_meta)
    ops = _OPS[engine]
    result: list[int] | None = None
    pending = "AND"

    for token in query.split():
        upper = token.upper()
        if upper in ops:
            pending = upper
            continue
        ids = _doc_ids(index, token.casefold())
        if result is None:
            result = ops["NOT"](universe, ids) if pending == "NOT" else ids
        else:
            result = ops[pending](result, ids)
        pending = "AND"

    return result if result is not None else []


def _id_cache(index: Index) -> Callable[[str], tuple[int, ...]]:
    cached = getattr(index, "_match_ids", None)
    if callable(cached):
        return cached  # type: ignore[no-any-return]

    @functools.lru_cache(maxsize=256)
    def match_ids(query: str) -> tuple[int, ...]:
        log.debug("cache miss %s", query)
        return tuple(sorted(parse(query).evaluate(index)))

    index._match_ids = match_ids  # type: ignore[attr-defined]
    return match_ids


def window_snippet(index: Index, doc_id: int, terms: list[str]) -> str:
    path = Path(index.doc_meta[doc_id].path)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8-sig")
    folded = text.casefold()
    at = -1
    hit = ""
    for term in sorted(set(terms), key=lambda t: (index.df(t) or 10**9, t)):
        found = folded.find(term)
        if found >= 0:
            at, hit = found, term
            break
    if at < 0:
        window = text[:160]
    else:
        window = text[max(0, at - 80) : at + len(hit) + 80]
    for term in sorted(set(terms), key=len, reverse=True):
        if not term:
            continue
        window = re.sub(
            rf"(?i)(?<!\w){re.escape(term)}(?!\w)",
            lambda m: f"[{m.group(0)}]",
            window,
        )
    return window.replace("\n", " ")


def score_loop(
    index: Index,
    query: str,
    scorer: Scorer,
    *,
    allow: set[int] | None = None,
) -> dict[int, float]:
    node = parse(query)
    terms = query_terms(node)
    if allow is None:
        allow = set(_id_cache(index)(query))
    scores: dict[int, float] = {}
    for term in terms:
        if term not in index:
            continue
        for posting in index[term]:
            if posting.doc_id not in allow:
                continue
            scores[posting.doc_id] = scores.get(posting.doc_id, 0.0) + scorer(
                term, posting, index
            )
    return scores


def score_numpy(
    index: Index,
    query: str,
    scorer_name: str = "bm25",
    *,
    allow: set[int] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    index.ensure_arrays()
    node = parse(query)
    terms = query_terms(node)
    if allow is None:
        allow = set(_id_cache(index)(query))
    n = int(index.length_vector.shape[0])
    scores = np.zeros(n, dtype=np.float64)
    seen = np.zeros(n, dtype=bool)
    for term in terms:
        if term not in index:
            continue
        if scorer_name == "tfidf":
            add_tfidf_term(scores, index, term, allow=allow, seen=seen)
        else:
            add_bm25_term(scores, index, term, allow=allow, seen=seen)
    return scores, seen


def ranked_loop(
    index: Index, query: str, scorer: Scorer, k: int
) -> list[tuple[int, float]]:
    scores = score_loop(index, query, scorer)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]
    return list(ordered)


def ranked_numpy(
    index: Index, query: str, scorer_name: str, k: int
) -> list[tuple[int, float]]:
    scores, seen = score_numpy(index, query, scorer_name)
    return pick_topk(scores, k, seen=seen)


def semantic_hits(
    index: Index,
    query: str,
    bank: VectorBank,
    *,
    k: int = 10,
    with_snippet: bool = True,
) -> list[SearchResult]:
    q = encode_query(query, bank.model)
    sims = np.asarray(bank.matrix @ q, dtype=np.float64)
    doc_ids = np.asarray(bank.chunk_docs, dtype=np.int32)
    n_docs = int(doc_ids.max()) + 1 if doc_ids.size else 0
    best = np.full(n_docs, -np.inf, dtype=np.float64)
    np.maximum.at(best, doc_ids, sims)
    scored = np.flatnonzero(np.isfinite(best) & (best > -np.inf))
    if scored.size == 0:
        return []
    if scored.size <= k:
        chosen = scored
    else:
        part = np.argpartition(best[scored], -k)[-k:]
        chosen = scored[part]
    order = np.lexsort((chosen, -best[chosen]))
    chosen = chosen[order]
    out: list[SearchResult] = []
    for doc_id in chosen:
        did = int(doc_id)
        if did not in index.doc_meta:
            continue
        snip = window_snippet(index, did, []) if with_snippet else ""
        out.append(SearchResult(float(best[did]), did, index.doc_meta[did].title, snip))
    return out


@timed
def search(
    index: Index,
    query: str,
    scorer: Scorer | None = None,
    k: int = 10,
    *,
    backend: ScoreBackend = "numpy",
    mode: SearchMode = "keyword",
    embeddings: VectorBank | None = None,
    scorer_name: str = "bm25",
    rrf_k: int = 60,
    with_snippet: bool = True,
) -> list[SearchResult]:
    if scorer is None:
        scorer = pick_scorer(scorer_name)

    if mode == "semantic":
        if embeddings is None:
            raise ValueError("semantic mode needs a VectorBank")
        return semantic_hits(index, query, embeddings, k=k, with_snippet=with_snippet)

    if mode == "hybrid":
        if embeddings is None:
            raise ValueError("hybrid mode needs a VectorBank")
        kw = search(
            index,
            query,
            scorer,
            k=max(k, 20),
            backend=backend,
            mode="keyword",
            scorer_name=scorer_name,
            with_snippet=False,
        )
        sem = semantic_hits(index, query, embeddings, k=max(k, 20), with_snippet=False)
        fused = fuse_ranks([[h.doc_id for h in kw], [h.doc_id for h in sem]], k=rrf_k)[:k]
        terms = query_terms(parse(query))
        out: list[SearchResult] = []
        for doc_id, score in fused:
            if doc_id not in index.doc_meta:
                continue
            snip = window_snippet(index, doc_id, terms) if with_snippet else ""
            out.append(SearchResult(score, doc_id, index.doc_meta[doc_id].title, snip))
        return out

    # keyword
    cache = _id_cache(index)
    hits_before = 0
    cache_info = getattr(cache, "cache_info", None)
    if callable(cache_info):
        hits_before = int(cache_info().hits)
    allow = set(cache(query))
    if callable(cache_info) and int(cache_info().hits) > hits_before:
        log.debug("cache hit %s", query)

    if backend == "loop":
        scores = score_loop(index, query, scorer, allow=allow)
        top = heapq.nlargest(k, scores.items(), key=lambda item: item[1])
        pairs = [(doc_id, score) for doc_id, score in top]
    else:
        name = "tfidf" if isinstance(scorer, TfIdf) else "bm25"
        if scorer_name:
            name = scorer_name
        scores_arr, seen = score_numpy(index, query, name, allow=allow)
        pairs = pick_topk(scores_arr, k, seen=seen)

    terms = query_terms(parse(query))
    return [
        SearchResult(
            score,
            doc_id,
            index.doc_meta[doc_id].title,
            window_snippet(index, doc_id, terms) if with_snippet else "",
        )
        for doc_id, score in pairs
        if doc_id in index.doc_meta
    ]