from __future__ import annotations

import logging
import multiprocessing as mp
import os
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from time import perf_counter, process_time
from typing import Literal

from findex.corpus import DocumentWalker, read_text
from findex.deco import timed
from findex.models import DocMeta, Index, PartialIndex, Posting
from findex.tokenize import WordStream

log = logging.getLogger(__name__)

DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "resources"
WITH_POSITIONS_DEFAULT = True
DEFAULT_WORKERS = os.cpu_count() or 1
# processes win only when tokenize work dwarfs spawn/pickle; here serial is fastest
DEFAULT_EXECUTOR: Literal["serial", "threads", "processes"] = "serial"

# (paths, start_doc_id, with_positions) — paths only; worker reads the files itself
ChunkJob = tuple[list[Path], int, bool]
ExecutorName = Literal["serial", "threads", "processes"]


def build_partial(job: ChunkJob) -> PartialIndex:
    # module-level so spawn can pickle it; nested defs / lambdas cannot cross processes
    paths, start_id, with_positions = job
    words = WordStream()
    buckets: dict[str, list[Posting]] = defaultdict(list)
    lengths: dict[int, int] = {}
    meta: dict[int, DocMeta] = {}

    for offset, path in enumerate(paths):
        doc_id = start_id + offset
        text = read_text(path)
        freq: Counter[str] = Counter()
        offsets: dict[str, list[int]] | None = defaultdict(list) if with_positions else None
        n_tokens = 0
        for pos, term in enumerate(words.tokenize(text)):
            freq[term] += 1
            n_tokens += 1
            if offsets is not None:
                offsets[term].append(pos)
        lengths[doc_id] = n_tokens
        meta[doc_id] = DocMeta(str(path), path.stem)
        for term, tf in freq.items():
            positions = tuple(offsets[term]) if offsets is not None else ()
            buckets[term].append(Posting(doc_id, tf, positions))

    return PartialIndex(dict(buckets), lengths, meta)


def split_jobs(paths: list[Path], workers: int, with_positions: bool) -> list[ChunkJob]:
    n = max(1, workers)
    size = len(paths)
    out: list[ChunkJob] = []
    for i in range(n):
        a = i * size // n
        b = (i + 1) * size // n
        # a is the first global doc_id for this slice (index in the sorted path list)
        out.append((paths[a:b], a, with_positions))
    return out


def merge_partials(parts: Iterable[PartialIndex]) -> Index:
    buckets: dict[str, list[Posting]] = defaultdict(list)
    lengths: dict[int, int] = {}
    meta: dict[int, DocMeta] = {}
    for part in parts:
        for term, hits in part.postings.items():
            buckets[term].extend(hits)
        lengths.update(part.doc_lengths)
        meta.update(part.doc_meta)
    # sort so chunk finish order does not change the index
    for hits in buckets.values():
        hits.sort(key=lambda p: p.doc_id)
    return Index(dict(buckets), lengths, meta)


def _timed_partial(job: ChunkJob) -> tuple[PartialIndex, float]:
    c0 = process_time()
    return build_partial(job), process_time() - c0


def build_parallel(
    paths: list[Path],
    workers: int,
    executor: ExecutorName,
    with_positions: bool,
) -> tuple[Index, float, float]:
    n = 1 if executor == "serial" else max(1, workers)
    work = split_jobs(paths, n, with_positions)

    if executor == "serial":
        timed_parts = [_timed_partial(job) for job in work]
    elif executor == "threads":
        with ThreadPoolExecutor(n) as pool:
            timed_parts = list(pool.map(_timed_partial, work))
    else:
        # spawn: child re-imports this module; pool.map re-raises the worker traceback
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(n, mp_context=ctx) as pool:
            timed_parts = list(pool.map(_timed_partial, work))

    parts = [part for part, _ in timed_parts]
    worker_cpu = sum(cpu for _, cpu in timed_parts)
    t0 = perf_counter()
    index = merge_partials(parts)
    return index, perf_counter() - t0, worker_cpu


@timed
def assemble(
    walker: DocumentWalker,
    words: WordStream,
    *,
    with_positions: bool = False,
    limit: int | None = None,
    on_doc: Callable[[], None] | None = None,
) -> Index:
    # lab-04 style serial path kept for identity tests / search fixtures
    buckets: dict[str, list[Posting]] = defaultdict(list)
    lengths: dict[int, int] = {}
    meta: dict[int, DocMeta] = {}

    for doc_id, path, text in walker.iter_docs():
        if limit is not None and doc_id >= limit:
            break
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
        if on_doc is not None:
            on_doc()

    for hits in buckets.values():
        hits.sort(key=lambda p: p.doc_id)

    index = Index(dict(buckets), lengths, meta)
    log.info("built %r tokens=%d", index, sum(lengths.values()))
    return index


def build_corpus(
    corpus: Path,
    *,
    with_positions: bool = WITH_POSITIONS_DEFAULT,
    limit: int | None = None,
    on_doc: Callable[[], None] | None = None,
    workers: int = 1,
    executor: ExecutorName = "serial",
) -> Index:
    paths = sorted(corpus.glob("*.txt"))
    if limit is not None:
        paths = paths[:limit]
    if executor == "serial" and workers <= 1 and on_doc is not None:
        return assemble(
            DocumentWalker(corpus),
            WordStream(),
            with_positions=with_positions,
            limit=limit,
            on_doc=on_doc,
        )
    index, _merge_s, _cpu = build_parallel(paths, workers, executor, with_positions)
    if on_doc is not None:
        for _ in paths:
            on_doc()
    log.info("built %r tokens=%d via %s/%d", index, sum(index.doc_lengths.values()), executor, workers)
    return index
