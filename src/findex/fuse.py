from __future__ import annotations

from collections import defaultdict


def fuse_ranks(rankings: list[list[int]], *, k: int = 60) -> list[tuple[int, float]]:
    # Reciprocal Rank Fusion: sum 1/(k + rank); lower doc_id wins ties
    bag: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            bag[doc_id] += 1.0 / (k + rank)
    return sorted(bag.items(), key=lambda item: (-item[1], item[0]))