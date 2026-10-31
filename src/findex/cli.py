from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated, Literal, NoReturn

import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from findex.index import DEFAULT_CORPUS, DEFAULT_EXECUTOR, DEFAULT_WORKERS, build_corpus
from findex.measure import corpus_stats
from findex.models import Index, SearchResult
from findex.score import pick_scorer
from findex.search import search
from findex.store import open_index, save_json, save_pickle

app = typer.Typer(add_completion=False, no_args_is_help=True, pretty_exceptions_enable=False)
err = Console(stderr=True)
out = Console()
log = logging.getLogger("findex")


def _setup_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _fail(message: str, code: int = 1) -> NoReturn:
    err.print(f"[red]{message}[/red]")
    raise typer.Exit(code)


@app.callback()
def _root(
    verbose: Annotated[
        int,
        typer.Option("-v", count=True, help="Raise log level (-v INFO, -vv DEBUG)"),
    ] = 0,
) -> None:
    _setup_logging(verbose)


@app.command("index")
def index_cmd(
    corpus: Annotated[Path, typer.Argument(exists=True, file_okay=False)] = DEFAULT_CORPUS,
    out_path: Annotated[Path, typer.Option("--out", help="Output index path")] = Path(
        "index.pkl"
    ),
    positions: Annotated[bool, typer.Option("--positions/--no-positions")] = True,
    limit: Annotated[int | None, typer.Option("--limit", help="Max documents")] = None,
    fmt: Annotated[Literal["pickle", "json"], typer.Option("--format")] = "pickle",
    workers: Annotated[
        int,
        typer.Option("--workers", min=1, help="Worker count (ignored for serial)"),
    ] = DEFAULT_WORKERS,
    executor: Annotated[
        Literal["serial", "threads", "processes"],
        typer.Option("--executor"),
    ] = DEFAULT_EXECUTOR,
) -> None:
    files = sorted(corpus.glob("*.txt"))
    if limit is not None:
        files = files[:limit]
    if not files:
        _fail(f"no .txt files under {corpus}")

    built: Index
    with Progress(console=err) as progress:
        task = progress.add_task("indexing", total=len(files))

        def tick() -> None:
            progress.advance(task)

        try:
            built = build_corpus(
                corpus,
                with_positions=positions,
                limit=limit,
                on_doc=tick if executor == "serial" else None,
                workers=workers,
                executor=executor,
            )
            if executor != "serial":
                for _ in files:
                    tick()
        except OSError as exc:
            _fail(str(exc))
        except Exception as exc:  # noqa: BLE001 — surface worker traceback text
            _fail(str(exc))

    try:
        if fmt == "json":
            save_json(built, out_path)
        else:
            save_pickle(built, out_path)
    except OSError as exc:
        _fail(str(exc))

    err.print(
        f"saved {out_path} ({out_path.stat().st_size} bytes) {built!r} "
        f"executor={executor} workers={workers if executor != 'serial' else 1} "
        f"cores={os.cpu_count()}"
    )


@app.command("search")
def search_cmd(
    index_path: Annotated[Path, typer.Argument(help="Index file")],
    query: Annotated[str, typer.Argument(help="Query string")],
    k: Annotated[int, typer.Option("--k", min=1)] = 10,
    scorer_name: Annotated[
        Literal["bm25", "tfidf"],
        typer.Option("--scorer"),
    ] = "bm25",
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON lines on stdout")] = False,
) -> None:
    if not index_path.is_file():
        _fail(f"index not found: {index_path}")

    hits: list[SearchResult]
    try:
        scorer = pick_scorer(scorer_name)
        with open_index(index_path) as index:
            hits = search(index, query, scorer, k)
    except ValueError as exc:
        _fail(str(exc))
    except (OSError, TypeError, KeyError) as exc:
        _fail(str(exc))
    except Exception as exc:  # noqa: BLE001
        _fail(str(exc))

    if as_json:
        for hit in hits:
            line = json.dumps(
                {
                    "doc_id": hit.doc_id,
                    "score": hit.score,
                    "title": hit.title,
                    "snippet": hit.snippet,
                },
                ensure_ascii=True,
            )
            sys.stdout.write(line + "\n")
        return

    table = Table(title=f"search: {query}")
    table.add_column("#", justify="right")
    table.add_column("score", justify="right")
    table.add_column("title")
    table.add_column("snippet")
    for rank, hit in enumerate(hits, 1):
        table.add_row(str(rank), f"{hit.score:.4f}", hit.title, hit.snippet[:120])
    out.print(table)


@app.command("stats")
def stats_cmd(
    corpus: Annotated[Path, typer.Argument(exists=True, file_okay=False)] = DEFAULT_CORPUS,
) -> None:
    try:
        stats = corpus_stats(corpus)
    except OSError as exc:
        _fail(str(exc))
        return

    table = Table(title="corpus stats")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("documents", str(stats.document_count))
    table.add_row("tokens", str(stats.token_count))
    table.add_row("vocabulary", str(stats.vocabulary))
    table.add_row("seconds", f"{stats.seconds:.4f}")
    out.print(table)

    top = Table(title="top terms")
    top.add_column("term")
    top.add_column("tf", justify="right")
    for term, tf in stats.frequent_terms:
        top.add_row(term, str(tf))
    out.print(top)


@app.command("bench")
def bench_cmd() -> None:
    from findex.bench import main as run_bench

    run_bench()


if __name__ == "__main__":
    app()
