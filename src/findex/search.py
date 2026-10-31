from __future__ import annotations

import functools
import heapq
import logging
import re
from pathlib import Path
from time import perf_counter

from findex.deco import log, timed
from findex.index import OUT_PKL
from findex.models import Index, SearchResult
from findex.query import parse, query_terms
from findex.score import BM25, TfIdf
from findex.store import open_index

QUERY = '(frankenstein OR hatter) AND alice NOT darcy "white rabbit"'
K = 5
# hand labels: titled document that should appear in the top 5
EVAL = (
    ("alice", "alice_in_wonderland"),
    ("hatter", "alice_in_wonderland"),
    ("cheshire", "alice_in_wonderland"),
    ('"white rabbit"', "alice_in_wonderland"),
    ("frankenstein", "frankenstein"),
    ("walton", "frankenstein"),
    ("creature", "frankenstein"),
    ("elizabeth", "pride_and_prejudice"),
    ("darcy", "pride_and_prejudice"),
    ('"pride and prejudice"', "pride_and_prejudice"),
)

ENGINE = "merge"
BENCH_REPEATS = 200_000


def intersect_sorted(left: list[int], right: list[int]) -> list[int]:
    i = j = 0
    out: list[int] = []
    n_l, n_r = len(left), len(right)
    while i < n_l and j < n_r:
        a, b = left[i], right[j]
        if a == b:
            out.append(a)
            i += 1
            j += 1
        elif a < b:
            i += 1
        else:
            j += 1
    return out


def union_sorted(left: list[int], right: list[int]) -> list[int]:
    i = j = 0
    out: list[int] = []
    n_l, n_r = len(left), len(right)
    while i < n_l and j < n_r:
        a, b = left[i], right[j]
        if a == b:
            out.append(a)
            i += 1
            j += 1
        elif a < b:
            out.append(a)
            i += 1
        else:
            out.append(b)
            j += 1
    if i < n_l:
        out.extend(left[i:])
    if j < n_r:
        out.extend(right[j:])
    return out


def difference_sorted(left: list[int], right: list[int]) -> list[int]:
    i = j = 0
    out: list[int] = []
    n_l, n_r = len(left), len(right)
    while i < n_l and j < n_r:
        a, b = left[i], right[j]
        if a == b:
            i += 1
            j += 1
        elif a < b:
            out.append(a)
            i += 1
        else:
            j += 1
    if i < n_l:
        out.extend(left[i:])
    return out


def intersect_set(left: list[int], right: list[int]) -> list[int]:
    return sorted(set(left).intersection(right))


def union_set(left: list[int], right: list[int]) -> list[int]:
    return sorted(set(left).union(right))


def difference_set(left: list[int], right: list[int]) -> list[int]:
    return sorted(set(left).difference(right))


_OPS = {
    "merge": {"AND": intersect_sorted, "OR": union_sorted, "NOT": difference_sorted},
    "set": {"AND": intersect_set, "OR": union_set, "NOT": difference_set},
}


def _doc_ids(index: Index, term: str) -> list[int]:
    hits = index.postings.get(term)
    if not hits:
        return []
    return [hit.doc_id for hit in hits]


def boolean_search(index: Index, query: str, engine: str) -> list[int]:
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


def _term_tf(index: Index, term: str) -> int:
    return sum(hit.tf for hit in index.postings[term])


def bench(index: Index) -> None:
    if len(index.postings) < 2:
        print("bench skipped")
        return
    ranked = sorted(index.postings, key=lambda t: (_term_tf(index, t), t))
    for label, pair in (("rare", ranked[:2]), ("common", ranked[-2:])):
        left, right = pair
        query = f"{left} {right}"
        for engine in ("merge", "set"):
            started = perf_counter()
            for _ in range(BENCH_REPEATS):
                boolean_search(index, query, engine)
            mean = (perf_counter() - started) / BENCH_REPEATS
            print(
                f"{label} {left!r} tf={_term_tf(index, left)} "
                f"{right!r} tf={_term_tf(index, right)} {engine} {mean:.8f}s"
            )


def _id_cache(index: Index):
    cached = getattr(index, "_match_ids", None)
    if cached is not None:
        return cached

    @functools.lru_cache(maxsize=256)
    def match_ids(query: str) -> tuple[int, ...]:
        log.debug("cache miss %s", query)
        return tuple(sorted(parse(query).evaluate(index)))

    index._match_ids = match_ids
    return match_ids


def _window_snippet(index: Index, doc_id: int, terms: list[str]) -> str:
    path = Path(index.doc_meta[doc_id].path)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
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
def search(index: Index, query: str, scorer, k: int = 10) -> list[SearchResult]:
    cache = _id_cache(index)
    hits_before = cache.cache_info().hits
    matched = set(cache(query))
    if cache.cache_info().hits > hits_before:
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
        SearchResult(score, doc_id, index.doc_meta[doc_id].title, _window_snippet(index, doc_id, terms))
        for doc_id, score in top
    ]


def precision_at_5(index: Index) -> None:
    print(f"{'query':<28} {'tfidf':>8} {'bm25':>8}")
    totals = [0.0, 0.0]
    for query, title in EVAL:
        row = []
        for scorer in (TfIdf(), BM25()):
            hits = search(index, query, scorer, K)
            row.append(sum(h.title == title for h in hits) / K)
        totals[0] += row[0]
        totals[1] += row[1]
        print(f"{query:<28} {row[0]:8.2f} {row[1]:8.2f}")
    n = len(EVAL)
    print(f"{'mean':<28} {totals[0] / n:8.2f} {totals[1] / n:8.2f}")


def _show(index: Index, query: str, scorer) -> None:
    print(f"\n{query} ({type(scorer).__name__})")
    for rank, hit in enumerate(search(index, query, scorer, K), 1):
        print(f"{rank} {hit.score:.4f} {hit.title} {hit.snippet}")


def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    with open_index(OUT_PKL) as index:
        _show(index, QUERY, BM25())
        _show(index, QUERY, BM25())
        print("cache", index._match_ids.cache_info())


if __name__ == "__main__":
    main()
