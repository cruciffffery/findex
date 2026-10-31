from __future__ import annotations

import tracemalloc
from collections import Counter
from time import perf_counter

from findex.corpus import DocumentWalker
from findex.tokenize import WordStream
from findex.types import CorpusMetrics


def _finish(started_at: float, counts: Counter[str], docs: int, tokens: int) -> CorpusMetrics:
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return CorpusMetrics(
        document_count=docs,
        token_count=tokens,
        vocabulary=len(counts),
        frequent_terms=counts.most_common(50),
        seconds=perf_counter() - started_at,
        peak_memory_kib=peak_bytes / 1024.0,
    )


class StreamingPass:

    def __init__(self, walker: DocumentWalker, words: WordStream | None = None) -> None:
        self._walker = walker
        self._words = words or WordStream()

    def run(self) -> CorpusMetrics:
        tracemalloc.start()
        t0 = perf_counter()
        bag: Counter[str] = Counter()
        docs = 0
        tokens = 0

        for body in self._walker.iter_documents():
            docs += 1
            for piece in self._words.tokenize(body):
                bag[piece] += 1
                tokens += 1

        return _finish(t0, bag, docs, tokens)


class EagerPass:

    def __init__(self, walker: DocumentWalker, words: WordStream | None = None) -> None:
        self._walker = walker
        self._words = words or WordStream()

    def run(self) -> CorpusMetrics:
        tracemalloc.start()
        t0 = perf_counter()

        # greedy: keep every document + every token in lists
        bodies = [body for body in self._walker.iter_documents()]
        pieces: list[str] = []
        for body in bodies:
            pieces += list(self._words.tokenize(body))

        bag = Counter(pieces)
        return _finish(t0, bag, len(bodies), len(pieces))
