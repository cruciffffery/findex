from __future__ import annotations

import gc
import tracemalloc
from array import array
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

from findex.corpus import DocumentWalker
from findex.deco import timed
from findex.models import DocMeta, Index, Posting, PostingPlain
from findex.store import pickle_size_and_load, timed_save_load
from findex.tokenize import WordStream

CORPUS = Path(__file__).resolve().parents[1] / "resources"
OUT_PKL = Path(__file__).resolve().parents[2] / "index.pkl"
OUT_JSON = Path(__file__).resolve().parents[2] / "index.json"
WITH_POSITIONS = True  # phrase queries need token offsets


@timed
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


def main() -> Index:
    walker, words = DocumentWalker(CORPUS), WordStream()
    tracemalloc.start()
    t0 = perf_counter()
    index = assemble(walker, words, with_positions=WITH_POSITIONS)
    elapsed = perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        f"{index!r} tokens={sum(index.doc_lengths.values())} "
        f"time={elapsed:.4f}s peak={peak / 1024:.1f}KiB"
    )
    timed_save_load(index, OUT_PKL, OUT_JSON)
    return index


if __name__ == "__main__":
    main()
