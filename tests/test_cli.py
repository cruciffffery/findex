from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from findex.cli import app
from findex.index import build_corpus
from findex.store import save_pickle

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "index" in result.stdout
    assert "search" in result.stdout
    assert "stats" in result.stdout


def test_index_and_search_json(tiny_corpus: Path, tmp_path: Path) -> None:
    out = tmp_path / "idx.pkl"
    built = runner.invoke(
        app,
        ["index", str(tiny_corpus), "--out", str(out), "--no-positions"],
    )
    assert built.exit_code == 0, built.stdout + built.stderr
    assert out.is_file()

    searched = runner.invoke(
        app,
        ["search", str(out), "alice", "--json", "--k", "3"],
    )
    assert searched.exit_code == 0, searched.stdout + searched.stderr
    assert "alice" in searched.stdout.lower() or searched.stdout.strip() == ""


def test_search_missing_index(tmp_path: Path) -> None:
    missing = tmp_path / "nope.pkl"
    result = runner.invoke(app, ["search", str(missing), "alice"])
    assert result.exit_code != 0
    assert "not found" in (result.stdout + result.stderr).lower()


def test_stats(tiny_corpus: Path) -> None:
    result = runner.invoke(app, ["stats", str(tiny_corpus)])
    assert result.exit_code == 0
    assert "documents" in result.stdout.lower() or "documents" in result.stderr.lower()


def test_search_table(tiny_corpus: Path, tmp_path: Path) -> None:
    out = tmp_path / "idx.pkl"
    index = build_corpus(tiny_corpus, with_positions=True)
    save_pickle(index, out)
    result = runner.invoke(app, ["-v", "search", str(out), "rabbit OR darcy", "--k", "5"])
    assert result.exit_code == 0, result.stdout + result.stderr
