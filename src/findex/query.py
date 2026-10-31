from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from findex.models import Index
from findex.tokenize import tokenize


class QueryNode(Protocol):
    def evaluate(self, index: Index) -> set[int]: ...


class _Ops:
    def __and__(self, other: QueryNode) -> And:
        return And(self, other)  # type: ignore[arg-type]  # self is Term|Phrase|And|Or|Not at runtime

    def __or__(self, other: QueryNode) -> Or:
        return Or(self, other)  # type: ignore[arg-type]

    def __invert__(self) -> Not:
        return Not(self)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Term(_Ops):
    value: str

    def evaluate(self, index: Index) -> set[int]:
        if self.value not in index:
            return set()
        return {hit.doc_id for hit in index[self.value]}


@dataclass(frozen=True)
class Phrase(_Ops):
    words: tuple[str, ...]

    def evaluate(self, index: Index) -> set[int]:
        # next word must sit at position p + 1
        if any(word not in index for word in self.words):
            return set()
        by_doc: list[dict[int, tuple[int, ...]]] = [
            {hit.doc_id: hit.positions for hit in index[word]} for word in self.words
        ]
        shared: set[int] = set(by_doc[0]).intersection(*(set(col) for col in by_doc[1:]))
        return {doc_id for doc_id in shared if _phrase_holds(by_doc, doc_id)}


@dataclass(frozen=True)
class And(_Ops):
    left: QueryNode
    right: QueryNode

    def evaluate(self, index: Index) -> set[int]:
        return self.left.evaluate(index) & self.right.evaluate(index)


@dataclass(frozen=True)
class Or(_Ops):
    left: QueryNode
    right: QueryNode

    def evaluate(self, index: Index) -> set[int]:
        return self.left.evaluate(index) | self.right.evaluate(index)


@dataclass(frozen=True)
class Not(_Ops):
    child: QueryNode

    def evaluate(self, index: Index) -> set[int]:
        return set(index.doc_meta) - self.child.evaluate(index)


def _adjacent(prev: tuple[int, ...], nxt: tuple[int, ...]) -> tuple[int, ...]:
    i = j = 0
    found: list[int] = []
    while i < len(prev) and j < len(nxt):
        want = prev[i] + 1
        if nxt[j] == want:
            found.append(nxt[j])
            i += 1
            j += 1
        elif nxt[j] < want:
            j += 1
        else:
            i += 1
    return tuple(found)


def _phrase_holds(by_doc: list[dict[int, tuple[int, ...]]], doc_id: int) -> bool:
    chain = by_doc[0][doc_id]
    for col in by_doc[1:]:
        chain = _adjacent(chain, col[doc_id])
        if not chain:
            return False
    return True


def _lex(query: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i = 0
    n = len(query)
    while i < n:
        ch = query[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()":
            tokens.append(("op", ch))
            i += 1
            continue
        if ch == '"':
            j = query.find('"', i + 1)
            if j < 0:
                j = n
            tokens.append(("phrase", query[i + 1 : j]))
            i = j + 1
            continue
        j = i
        while j < n and not query[j].isspace() and query[j] not in '()"':
            j += 1
        tokens.append(("word", query[i:j]))
        i = j
    return tokens


def _is_kw(tok: tuple[str, str] | None, *names: str) -> bool:
    return bool(tok) and tok[0] == "word" and tok[1].upper() in names


def _leaf(tok: tuple[str, str]) -> Term | Phrase:
    if tok[0] == "phrase":
        words = tuple(tokenize(tok[1]))
        if len(words) > 1:
            return Phrase(words)
        return Term(words[0] if words else "")
    return Term(tok[1].casefold())


Node = Term | Phrase | And | Or | Not


def parse(query: str) -> Node:
    tokens = _lex(query)
    if not tokens:
        raise ValueError("empty query")
    cursor = 0

    def peek() -> tuple[str, str] | None:
        return tokens[cursor] if cursor < len(tokens) else None

    def take() -> tuple[str, str]:
        nonlocal cursor
        tok = tokens[cursor]
        cursor += 1
        return tok

    def atom() -> Node:
        tok = take()
        if tok == ("op", "("):
            node = parse_or()
            if peek() == ("op", ")"):
                take()
            return node
        return _leaf(tok)

    def parse_not() -> Node:
        if _is_kw(peek(), "NOT"):
            take()
            return Not(atom())
        return atom()

    def parse_and() -> Node:
        node: Node = parse_not()
        while True:
            tok = peek()
            if tok is None or tok == ("op", ")") or _is_kw(tok, "OR"):
                return node
            if _is_kw(tok, "AND"):
                take()
            node = node & parse_not()
        return node

    def parse_or() -> Node:
        node: Node = parse_and()
        while _is_kw(peek(), "OR"):
            take()
            node = node | parse_and()
        return node

    return parse_or()


def query_terms(node: object) -> list[str]:
    if isinstance(node, Term):
        return [node.value]
    if isinstance(node, Phrase):
        return list(node.words)
    if isinstance(node, Not):
        return []
    if isinstance(node, (And, Or)):
        return query_terms(node.left) + query_terms(node.right)
    return []
