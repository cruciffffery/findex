from __future__ import annotations

import functools
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PostingPlain:
    doc_id: int
    tf: int
    positions: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Posting:
    doc_id: int
    tf: int
    positions: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DocMeta:
    path: str
    title: str


@dataclass(order=True, frozen=True, slots=True)
class SearchResult:
    score: float
    doc_id: int
    title: str = field(compare=False)
    snippet: str = field(compare=False)


@dataclass(frozen=True, slots=True)
class PartialIndex:
    postings: dict[str, list[Posting]]
    doc_lengths: dict[int, int]
    doc_meta: dict[int, DocMeta]


class Index(Mapping[str, list[Posting]]):
    # not frozen: cached_property + numpy caches mutate the instance
    def __init__(
        self,
        postings: dict[str, list[Posting]],
        doc_lengths: dict[int, int],
        doc_meta: dict[int, DocMeta],
    ) -> None:
        self.postings = postings
        self.doc_lengths = doc_lengths
        self.doc_meta = doc_meta
        self._len_vec = None
        self._ids_by_term: dict | None = None
        self._tf_by_term: dict | None = None

    def __getitem__(self, term: str) -> list[Posting]:
        return self.postings[term]

    def __iter__(self) -> Iterator[str]:
        return iter(self.postings)

    def __len__(self) -> int:
        return len(self.postings)

    def __repr__(self) -> str:
        return f"Index(terms={len(self):_}, docs={self.num_docs:_})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Index):
            return NotImplemented
        return (
            self.postings == other.postings
            and self.doc_lengths == other.doc_lengths
            and self.doc_meta == other.doc_meta
        )

    @property
    def num_docs(self) -> int:
        return len(self.doc_lengths)

    @functools.cached_property
    def avg_doc_length(self) -> float:
        if self.num_docs == 0:
            return 0.0
        return sum(self.doc_lengths.values()) / self.num_docs

    def doc_length(self, doc_id: int) -> int:
        return self.doc_lengths[doc_id]

    def df(self, term: str) -> int:
        return len(self[term]) if term in self else 0


    def ensure_arrays(self) -> None:
        # build int32 posting columns once; pickle-safe if attrs missing
        if not hasattr(self, "_len_vec"):
            self._len_vec = None
            self._ids_by_term = None
            self._tf_by_term = None
        if self._len_vec is not None:
            return
        import numpy as np

        top = max(self.doc_lengths) if self.doc_lengths else -1
        lengths = np.zeros(top + 1, dtype=np.int32)
        for doc_id, n in self.doc_lengths.items():
            lengths[doc_id] = n
        ids_map: dict[str, np.ndarray] = {}
        tf_map: dict[str, np.ndarray] = {}
        for term, plist in self.postings.items():
            ids_map[term] = np.fromiter((p.doc_id for p in plist), dtype=np.int32, count=len(plist))
            tf_map[term] = np.fromiter((p.tf for p in plist), dtype=np.int32, count=len(plist))
        self._len_vec = lengths
        self._ids_by_term = ids_map
        self._tf_by_term = tf_map

    @property
    def length_vector(self):
        self.ensure_arrays()
        assert self._len_vec is not None
        return self._len_vec

    def arrays_for(self, term: str):
        import numpy as np

        self.ensure_arrays()
        assert self._ids_by_term is not None and self._tf_by_term is not None
        blank = np.empty(0, dtype=np.int32)
        return self._ids_by_term.get(term, blank), self._tf_by_term.get(term, blank)

    def materialize_numpy(self) -> None:
        self.ensure_arrays()

