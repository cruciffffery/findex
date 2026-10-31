from __future__ import annotations

import time
from pathlib import Path

from findex.index import build_corpus
from findex.models import DocMeta, Index, Posting
from findex.score import BM25
from findex.search import ranked_loop, ranked_numpy


def median_ms(fn, repeats: int = 21) -> float:
    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    return samples[len(samples) // 2]


def synth(n: int = 40_000) -> Index:
    postings = {"common": [Posting(i, 1 + (i % 5)) for i in range(n)]}
    lengths = {i: 50 + (i % 20) for i in range(n)}
    meta = {i: DocMeta(f"{i}.txt", f"d{i}") for i in range(n)}
    index = Index(postings, lengths, meta)
    index.ensure_arrays()
    return index


def main() -> None:
    corpus = Path("src/resources")
    index = build_corpus(corpus, with_positions=False, executor="serial", workers=1)
    rare = min((t for t in index.postings if index.df(t) > 0), key=lambda t: index.df(t))
    queries = [
        ("common", "the"),
        ("rare", rare),
        ("3-term", "alice white rabbit"),
    ]
    rows = []
    for label, q in queries:
        loop_ms = median_ms(lambda q=q: ranked_loop(index, q, BM25(), 10))
        np_ms = median_ms(lambda q=q: ranked_numpy(index, q, "bm25", 10))
        matched = len(ranked_loop(index, q, BM25(), 10_000))
        speed = (loop_ms / np_ms) if np_ms > 0 else float("inf")
        rows.append((label, q, matched, loop_ms, np_ms, speed))

    big = synth()
    loop_ms = median_ms(lambda: ranked_loop(big, "common", BM25(), 10), repeats=5)
    np_ms = median_ms(lambda: ranked_numpy(big, "common", "bm25", 10), repeats=5)
    rows.append(("synthetic-40k", "common", 40_000, loop_ms, np_ms, loop_ms / np_ms))

    print("| Query | Docs matched | Lab 3 loop (ms) | NumPy (ms) | Speedup |")
    print("|---|---:|---:|---:|---:|")
    for label, q, matched, loop_ms, np_ms, speed in rows:
        print(f"| {label} ({q}) | {matched} | {loop_ms:.3f} | {np_ms:.3f} | {speed:.1f}x |")

    lines = [
        "# NumPy scorer speedup",
        "",
        "Scorer + top-k only (no snippet I/O). Median of repeats.",
        "",
        "| Query | Docs matched | Lab 3 loop (ms) | NumPy (ms) | Speedup |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, q, matched, loop_ms, np_ms, speed in rows:
        lines.append(
            f"| {label} ({q}) | {matched} | {loop_ms:.3f} | {np_ms:.3f} | {speed:.1f}x |"
        )
    best = max(r[5] for r in rows)
    lines += [
        "",
        f"Largest speedup in this table: **{best:.1f}x**.",
        "",
        "## Notes",
        "",
        "- Tiny posting lists: NumPy call overhead can lose to a short Python loop.",
        "- Long lists (synthetic 40k): ufuncs + argpartition win clearly.",
        "",
    ]
    Path("docs/numpy_speedup.md").write_text("\\n".join(lines), encoding="utf-8")
    print("wrote docs/numpy_speedup.md")


if __name__ == "__main__":
    main()
