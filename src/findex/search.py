from __future__ import annotations

import argparse
import tracemalloc
from pathlib import Path
from time import perf_counter

from findex.models import Index
from findex.store import load_json, load_pickle

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


_ENGINES = {
    "merge": {"AND": intersect_sorted, "OR": union_sorted, "NOT": difference_sorted},
    "set": {"AND": intersect_set, "OR": union_set, "NOT": difference_set},
}


def _doc_ids(index: Index, term: str) -> list[int]:
    hits = index.postings.get(term)
    if not hits:
        return []
    return [hit.doc_id for hit in hits]


def search(index: Index, query: str, engine: str) -> list[int]:
    # "term term" → AND; OR / NOT take the next term; evaluate left → right
    universe = sorted(index.doc_meta)
    ops = _ENGINES[engine]
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
                search(index, query, engine)
            mean = (perf_counter() - started) / BENCH_REPEATS
            print(
                f"{label} {left!r} tf={_term_tf(index, left)} "
                f"{right!r} tf={_term_tf(index, right)} {engine} {mean:.8f}s"
            )


def _load_index(path: Path) -> Index:
    if path.suffix.lower() == ".json":
        return load_json(path)
    return load_pickle(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m findex.search")
    parser.add_argument("index", type=Path, nargs="?", default=Path("index.pkl"))
    parser.add_argument("query", nargs="?", default="elizabeth darcy")
    parser.add_argument("--engine", choices=("merge", "set"), default="merge")
    args = parser.parse_args(argv)

    tracemalloc.start()
    t0 = perf_counter()
    index = _load_index(args.index)
    hits = search(index, args.query, args.engine)
    elapsed = perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"\n{args.query!r} ({args.engine})")
    for doc_id in hits:
        print(f"  {doc_id}\t{index.doc_meta[doc_id].title}")
    print(f"search time={elapsed:.4f}s peak={peak / 1024:.1f}KiB")


if __name__ == "__main__":
    main()
