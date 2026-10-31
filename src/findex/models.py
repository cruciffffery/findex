from __future__ import annotations

import functools
from collections.abc import Mapping
from dataclasses import dataclass, field


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


class Index(Mapping):
    # not frozen: cached_property stores avg_doc_length on the instance
    def __init__(self, postings, doc_lengths, doc_meta):
        self.postings = postings
        self.doc_lengths = doc_lengths
        self.doc_meta = doc_meta

    def __getitem__(self, term: str):
        return self.postings[term]

    def __iter__(self):
        return iter(self.postings)

    def __len__(self) -> int:
        return len(self.postings)

    def __repr__(self) -> str:
        return f"Index(terms={len(self):_}, docs={self.num_docs:_})"

    def __eq__(self, other):
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
        return sum(self.doc_lengths.values()) / self.num_docs

    def doc_length(self, doc_id: int) -> int:
        return self.doc_lengths[doc_id]

    def df(self, term: str) -> int:
        return len(self[term]) if term in self else 0
