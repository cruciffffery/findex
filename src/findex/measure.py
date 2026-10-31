from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from findex.corpus import DocumentWalker
from findex.tokenize import WordStream, tokenize

log = logging.getLogger(__name__)


@dataclass(slots=True)
class CorpusStats:
    document_count: int
    token_count: int
    vocabulary: int
    frequent_terms: list[tuple[str, int]]
    seconds: float


def corpus_stats(folder: Path, top: int = 20) -> CorpusStats:
    walker = DocumentWalker(folder)
    words = WordStream()
    bag: Counter[str] = Counter()
    docs = 0
    tokens = 0
    t0 = perf_counter()
    for body in walker.iter_documents():
        docs += 1
        for piece in words.tokenize(body):
            bag[piece] += 1
            tokens += 1
    elapsed = perf_counter() - t0
    log.info("stats docs=%d tokens=%d vocab=%d", docs, tokens, len(bag))
    return CorpusStats(docs, tokens, len(bag), bag.most_common(top), elapsed)


def token_list(text: str) -> list[str]:
    return list(tokenize(text))
