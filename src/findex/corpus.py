from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


class DocumentWalker:
    def __init__(self, folder: str | Path) -> None:
        self._root = Path(folder)

    def iter_documents(self) -> Iterator[str]:
        for _doc_id, _path, text, _title in self._iter():
            yield text

    def iter_docs(self) -> Iterator[tuple[int, Path, str]]:
        # stable doc_id from sorted paths / jsonl order → postings stay ordered by id
        for doc_id, path, text, _title in self._iter():
            yield doc_id, path, text

    def iter_docs_meta(self) -> Iterator[tuple[int, Path, str, str]]:
        yield from self._iter()

    def _iter(self) -> Iterator[tuple[int, Path, str, str]]:
        if self._root.is_file() and self._root.suffix.lower() == ".jsonl":
            yield from self._iter_jsonl()
            return
        for doc_id, path in enumerate(sorted(self._root.glob("*.txt"))):
            yield doc_id, path, read_text(path), path.stem

    def _iter_jsonl(self) -> Iterator[tuple[int, Path, str, str]]:
        with self._root.open(encoding="utf-8") as fh:
            doc_id = 0
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                url = rec.get("url") or f"doc:{doc_id}"
                title = rec.get("title") or url
                text = rec.get("text") or ""
                yield doc_id, Path(url), text, title
                doc_id += 1