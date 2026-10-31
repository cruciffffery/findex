from __future__ import annotations

import argparse
import gc
import tracemalloc
from array import array
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

from findex.corpus import DocumentWalker
from findex.models import DocMeta, Index, Posting, PostingPlain
from findex.store import pickle_size_and_load, save_json, save_pickle, timed_save_load
from findex.tokenize import WordStream

DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "resources"
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "index.pkl"
KEEP_POSITIONS = False


def assemble(
    walker: DocumentWalker,
    words: WordStream,
    *,
    with_positions: bool = False,
) -> Index:
    buckets: dict[str, list[Posting]] = defaultdict(list)
    lengths: dict[int, int] = {}
    meta: dict[int, DocMeta] = {}

    for doc_id, path, text in walker.iter_docs():
        freq: Counter[str] = Counter()
        offsets: dict[str, list[int]] | None = defaultdict(list) if with_positions else None
        n_tokens = 0
        for offset, term in enumerate(words.tokenize(text)):
            freq[term] += 1
            n_tokens += 1
            if offsets is not None:
                offsets[term].append(offset)

        lengths[doc_id] = n_tokens
        meta[doc_id] = DocMeta(str(path), path.stem)
        for term, tf in freq.items():
            pos = tuple(offsets[term]) if offsets is not None else ()
            buckets[term].append(Posting(doc_id, tf, pos))

    # contract: each posting list sorted by doc_id
    for hits in buckets.values():
        hits.sort(key=lambda p: p.doc_id)

    return Index(dict(buckets), lengths, meta)


def assemble_variant(walker: DocumentWalker, words: WordStream, kind: str):
    if kind == "array":
        # 'I' = unsigned 4-byte ints — no Posting objects
        buckets = defaultdict(lambda: (array("I"), array("I")))
    else:
        buckets = defaultdict(list)

    cls = PostingPlain if kind == "plain" else Posting
    lengths: dict[int, int] = {}
    meta: dict[int, DocMeta] = {}

    for doc_id, path, text in walker.iter_docs():
        freq = Counter(words.tokenize(text))
        lengths[doc_id] = sum(freq.values())
        meta[doc_id] = DocMeta(str(path), path.stem)
        for term, tf in freq.items():
            if kind == "array":
                ids, tfs = buckets[term]
                ids.append(doc_id)
                tfs.append(tf)
            else:
                buckets[term].append(cls(doc_id, tf))

    return {"postings": dict(buckets), "doc_lengths": lengths, "doc_meta": meta}


def _peak_kib(factory):
    gc.collect()
    tracemalloc.start()
    obj = factory()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return obj, peak / 1024


def positions_cost() -> None:
    walker, words = DocumentWalker(DEFAULT_CORPUS), WordStream()
    for flag in (False, True):
        index, peak = _peak_kib(lambda flag=flag: assemble(walker, words, with_positions=flag))
        size, load_s = pickle_size_and_load(index)
        print(f"positions={flag} peak={peak:.1f}KiB pickle={size} load={load_s:.4f}s")
        del index
        gc.collect()


def memory_study() -> None:
    walker, words = DocumentWalker(DEFAULT_CORPUS), WordStream()
    for kind in ("plain", "slots", "array"):
        obj, peak = _peak_kib(lambda kind=kind: assemble_variant(walker, words, kind))
        size, load_s = pickle_size_and_load(obj)
        print(f"{kind} peak={peak:.1f}KiB file={size} load={load_s:.4f}s")
        del obj
        gc.collect()


def build_and_save(
    corpus: Path,
    out: Path,
    *,
    with_positions: bool = False,
    fmt: str = "pickle",
) -> Index:
    walker, words = DocumentWalker(corpus), WordStream()
    tracemalloc.start()
    t0 = perf_counter()
    index = assemble(walker, words, with_positions=with_positions)
    elapsed = perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    if fmt == "json":
        save_json(index, out)
    else:
        save_pickle(index, out)

    print(
        f"docs={len(index.doc_meta)} terms={len(index.postings)} "
        f"tokens={sum(index.doc_lengths.values())} "
        f"time={elapsed:.4f}s peak={peak / 1024:.1f}KiB"
    )
    print(f"saved {out} ({out.stat().st_size} bytes)")
    return index


def main(argv: list[str] | None = None) -> Index:
    parser = argparse.ArgumentParser(prog="python -m findex.index")
    parser.add_argument("corpus", type=Path, nargs="?", default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--positions", action="store_true", default=KEEP_POSITIONS)
    parser.add_argument("--format", choices=("pickle", "json"), default="pickle")
    args = parser.parse_args(argv)

    index = build_and_save(
        args.corpus,
        args.out,
        with_positions=args.positions,
        fmt=args.format,
    )
    sibling = args.out.with_suffix(".json") if args.format == "pickle" else args.out.with_suffix(".pkl")
    if args.format == "pickle":
        timed_save_load(index, args.out, sibling)
    return index


if __name__ == "__main__":
    main()
