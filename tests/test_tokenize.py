from __future__ import annotations

import pytest

from findex.tokenize import WordStream, tokenize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CAFÉ", ["café"]),
        ("Ａｌｉｃｅ", ["alice"]),
        ("don't", ["don't"]),
        ("it's", ["it's"]),
        ("good-for-nothing", ["good-for-nothing"]),
        ("number 4 and 1991", ["number", "4", "and", "1991"]),
        ("Hello, world!", ["hello", "world"]),
        ("", []),
        ("... --- !!!", []),
    ],
)
def test_tokenize_cases(text: str, expected: list[str]) -> None:
    assert list(tokenize(text)) == expected


def test_wordstream_matches_tokenize() -> None:
    sample = "Alice's Adventures"
    assert list(WordStream().tokenize(sample)) == list(tokenize(sample))


def test_lazy_yield() -> None:
    it = tokenize("a b c")
    assert next(it) == "a"
    assert list(it) == ["b", "c"]
