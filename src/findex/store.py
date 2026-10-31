from __future__ import annotations

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from findex.deco import timed
from findex.models import DocMeta, Index, Posting

log = logging.getLogger(__name__)


def save_pickle(obj: object, path: Path) -> None:
    import pickle

    path.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


@timed
def load_pickle(path: Path) -> object:
    import pickle

    # pickle can run arbitrary code on load — only open files this build wrote
    return pickle.loads(path.read_bytes())


@timed
def _unpickle(raw: bytes) -> object:
    import pickle

    return pickle.loads(raw)


@contextmanager
def open_index(path: Path) -> Generator[Index]:
    handle = path.open("rb")
    try:
        loaded = _unpickle(handle.read())
        if not isinstance(loaded, Index):
            raise TypeError("index file did not contain an Index")
        yield loaded
    finally:
        handle.close()


def save_json(index: Index, path: Path) -> None:
    payload = {
        "lengths": {str(did): n for did, n in index.doc_lengths.items()},
        "meta": {
            str(did): {"path": meta.path, "title": meta.title}
            for did, meta in index.doc_meta.items()
        },
        "inv": {
            term: [[hit.doc_id, hit.tf, list(hit.positions)] for hit in hits]
            for term, hits in index.postings.items()
        },
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def load_json(path: Path) -> Index:
    payload = json.loads(path.read_text(encoding="utf-8"))
    postings = {
        term: [Posting(row[0], row[1], tuple(row[2])) for row in rows]
        for term, rows in payload["inv"].items()
    }
    lengths = {int(k): int(v) for k, v in payload["lengths"].items()}
    meta = {int(k): DocMeta(str(v["path"]), str(v["title"])) for k, v in payload["meta"].items()}
    return Index(postings, lengths, meta)
