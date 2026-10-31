from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

# [^\W_]+ = letters/digits; (?:['’ʼ-][^\W_]+)* keeps apostrophe/hyphen chunks
# don't → don't | good-for-nothing → one token | digits kept | other punct splits
_TOKEN = re.compile(r"[^\W_]+(?:[''\u2019\u02bc\-][^\W_]+)*", re.UNICODE)


def tokenize(text: str) -> Iterator[str]:
    text = unicodedata.normalize("NFKC", text).casefold()
    for match in _TOKEN.finditer(text):
        yield match.group(0)


class WordStream:

    def tokenize(self, text: str) -> Iterator[str]:
        return tokenize(text)
