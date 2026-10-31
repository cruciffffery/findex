from __future__ import annotations

from pathlib import Path

import pytest

from findex.index import assemble, build_parallel, build_partial, merge_partials, split_jobs
from findex.corpus import DocumentWalker
from findex.tokenize import WordStream


def _write(folder: Path, names: list[str]) -> None:
    for name in names:
        (folder / name).write_text(f"{name} alpha alpha\n", encoding="utf-8")


def test_serial_partial_matches_assemble(tmp_path: Path) -> None:
    _write(tmp_path, ["a.txt", "b.txt"])
    paths = sorted(tmp_path.glob("*.txt"))
    got = merge_partials([build_partial((paths, 0, True))])
    expect = assemble(DocumentWalker(tmp_path), WordStream(), with_positions=True)
    assert got == expect


def test_executors_match(tmp_path: Path) -> None:
    _write(tmp_path, ["a.txt", "b.txt", "c.txt"])
    paths = sorted(tmp_path.glob("*.txt"))
    indexes = [build_parallel(paths, 2, ex, True)[0] for ex in ("serial", "threads", "processes")]
    assert indexes[0] == indexes[1] == indexes[2]


def test_doc_ids_follow_path_order(tmp_path: Path) -> None:
    _write(tmp_path, ["b.txt", "a.txt", "c.txt"])
    paths = sorted(tmp_path.glob("*.txt"))
    index = merge_partials([build_partial(job) for job in split_jobs(paths, 2, True)])
    assert sorted(index.doc_lengths) == list(range(len(paths)))
    for hits in index.postings.values():
        ids = [posting.doc_id for posting in hits]
        assert ids == sorted(ids)


def test_worker_error_surfaces(tmp_path: Path) -> None:
    missing = tmp_path / "nope.txt"
    with pytest.raises(FileNotFoundError):
        build_parallel([missing], 1, "processes", False)
