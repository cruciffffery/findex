from __future__ import annotations

from findex.crawler.urls import normalize_url


def test_normalize_lowercases_and_drops_fragment() -> None:
    assert normalize_url("HTTPS://Books.Example.com/Path/#frag") == "https://books.example.com/Path"


def test_normalize_sorts_query() -> None:
    a = normalize_url("https://ex.com/x?b=2&a=1")
    b = normalize_url("https://ex.com/x?a=1&b=2")
    assert a == b == "https://ex.com/x?a=1&b=2"


def test_normalize_trailing_slash() -> None:
    assert normalize_url("https://ex.com/a/") == "https://ex.com/a"
    assert normalize_url("https://ex.com/") == "https://ex.com/"