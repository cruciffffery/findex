from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CorpusMetrics:
    document_count: int
    token_count: int
    vocabulary: int
    frequent_terms: list[tuple[str, int]]
    seconds: float
    peak_memory_kib: float
