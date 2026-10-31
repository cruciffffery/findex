from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


class DocumentWalker:

    def __init__(self, folder: str | Path) -> None:
        self._folder = Path(folder)

    def iter_documents(self) -> Iterator[str]:
        for path in sorted(self._folder.glob("*.txt")):
            yield path.read_text(encoding="utf-8")

    def iter_docs(self) -> Iterator[tuple[int, Path, str]]:
        # stable doc_id from sorted paths → postings stay ordered by id
        for doc_id, path in enumerate(sorted(self._folder.glob("*.txt"))):
            yield doc_id, path, path.read_text(encoding="utf-8")
