from __future__ import annotations

import json
import os
import pickle
import tempfile
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

from findex.deco import timed
from findex.models import DocMeta, Index, Posting


def save_pickle(obj, path: Path) -> None:
    path.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


@timed
def load_pickle(path: Path):
    # pickle can run arbitrary code on load — only open files this build wrote
    return pickle.loads(path.read_bytes())


@timed
def _unpickle(raw: bytes):
    return pickle.loads(raw)


@contextmanager
def open_index(path: Path):
    handle = path.open("rb")
    try:
        yield _unpickle(handle.read())
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
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_json(path: Path) -> Index:
    payload = json.loads(path.read_text(encoding="utf-8"))
    postings = {
        term: [Posting(row[0], row[1], tuple(row[2])) for row in rows]
        for term, rows in payload["inv"].items()
    }
    lengths = {int(k): v for k, v in payload["lengths"].items()}
    meta = {int(k): DocMeta(v["path"], v["title"]) for k, v in payload["meta"].items()}
    return Index(postings, lengths, meta)


def _median(fn, repeats: int = 5) -> float:
    times = [0.0] * repeats
    for i in range(repeats):
        t0 = perf_counter()
        fn()
        times[i] = perf_counter() - t0
    times.sort()
    return times[repeats // 2]


def pickle_size_and_load(obj) -> tuple[int, float]:
    fd, name = tempfile.mkstemp(suffix=".pkl")
    os.close(fd)
    path = Path(name)
    try:
        save_pickle(obj, path)
        return path.stat().st_size, _median(lambda: load_pickle(path))
    finally:
        path.unlink(missing_ok=True)


def timed_save_load(index: Index, pkl: Path, js: Path) -> None:
    save_p = _median(lambda: save_pickle(index, pkl))
    load_p = _median(lambda: load_pickle(pkl))
    save_j = _median(lambda: save_json(index, js))
    load_j = _median(lambda: load_json(js))
    print(
        f"pickle size={pkl.stat().st_size} save={save_p:.4f}s load={load_p:.4f}s\n"
        f"json size={js.stat().st_size} save={save_j:.4f}s load={load_j:.4f}s"
    )
