from __future__ import annotations

import functools
import heapq
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from findex.deco import timed
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
from findex.score import Scorer

log = logging.getLogger(__name__)

EngineName = Literal["merge", "set"]

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
    # "term term" → AND; OR / NOT take the next term; evaluate left → right
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
        return cached  # type: ignore[no-any-return]  # runtime cache attribute on Index

    @functools.lru_cache(maxsize=256)
    def match_ids(query: str) -> tuple[int, ...]:
        log.debug("cache miss %s", query)
        return tuple(sorted(parse(query).evaluate(index)))

    index._match_ids = match_ids  # type: ignore[attr-defined]  # attach lru cache to instance
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


@timed
def search(
    index: Index,
    query: str,
    scorer: Scorer,
    k: int = 10,
) -> list[SearchResult]:
    cache = _id_cache(index)
    hits_before = 0
    cache_info = getattr(cache, "cache_info", None)
    if callable(cache_info):
        hits_before = int(cache_info().hits)  # type: ignore[union-attr]  # lru_cache.cache_info
    matched = set(cache(query))
    if callable(cache_info) and int(cache_info().hits) > hits_before:  # type: ignore[union-attr]
        log.debug("cache hit %s", query)
    node = parse(query)
    terms = query_terms(node)
    scores: dict[int, float] = {}
    for term in terms:
        if term not in index:
            continue
        for posting in index[term]:
            if posting.doc_id not in matched:
                continue
            scores[posting.doc_id] = scores.get(posting.doc_id, 0.0) + scorer(term, posting, index)
    top = heapq.nlargest(k, scores.items(), key=lambda item: item[1])
    return [
        SearchResult(
            score,
            doc_id,
            index.doc_meta[doc_id].title,
            window_snippet(index, doc_id, terms),
        )
        for doc_id, score in top
    ]
