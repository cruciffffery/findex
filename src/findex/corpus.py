from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


class DocumentWalker:

    def __init__(self, folder: str | Path) -> None:
        self._folder = Path(folder)

    def iter_documents(self) -> Iterator[str]:
        for path in sorted(self._folder.glob("*.txt")):
            yield path.read_text(encoding="utf-8")
