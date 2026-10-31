from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated, Literal, NoReturn, Optional
from urllib.parse import urlsplit

import typer
from rich.console import Console
from rich.live import Live
from rich.progress import Progress
from rich.table import Table

from findex.crawler.http_pull import DEFAULT_USER_AGENT
from findex.crawler.spider import CrawlMeter, run_crawl
from findex.crawler.urls import normalize_url
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
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


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


def _domain_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _meter_table(meter: CrawlMeter) -> Table:
    table = Table(title="findex crawl")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("pages", str(meter.pages))
    table.add_row("pages/s", f"{meter.pages_per_sec:.2f}")
    table.add_row("in-flight", str(meter.in_flight))
    table.add_row("errors", str(meter.errors))
    table.add_row("queue", str(meter.queue_depth))
    return table


def _drain_log(log_fh, meter: CrawlMeter, visited: list[str]) -> None:
    while meter.log_lines:
        line = meter.log_lines.pop(0)
        log_fh.write(line + "\n")
        visited.append(line.split("\t", 1)[0])
    log_fh.flush()


async def _crawl_async(
    seeds: list[str],
    *,
    max_pages: int,
    concurrency: int,
    per_host: int,
    host_delay: float,
    timeout: float,
    out_path: Path,
    log_path: Path,
    allowed_domains: list[str] | None,
    user_agent: str,
    debug: bool,
) -> CrawlMeter:
    seeds = [normalize_url(u) for u in seeds]
    allowed = allowed_domains or [_domain_of(s) for s in seeds]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    meter = CrawlMeter()
    visited: list[str] = []
    saved: list[str] = []

    with out_path.open("w", encoding="utf-8") as fh, log_path.open("w", encoding="utf-8") as log_fh:
        log_fh.write("url\tstatus\tbytes\telapsed\terror\n")
        live_cm = nullcontext(None) if debug else Live(_meter_table(meter), refresh_per_second=4)
        with live_cm as live:
            async for page in run_crawl(
                seeds,
                max_pages=max_pages,
                concurrency=concurrency,
                per_host=per_host,
                allowed_domains=allowed,
                host_delay=host_delay,
                timeout=timeout,
                user_agent=user_agent,
                meter=meter,
            ):
                saved.append(page.url)
                line = json.dumps(
                    {
                        "url": page.url,
                        "title": page.title,
                        "text": page.text,
                        "fetched_at": page.fetched_at,
                    },
                    ensure_ascii=False,
                )

                def _write(line: str = line) -> None:
                    fh.write(line + "\n")
                    fh.flush()
                    _drain_log(log_fh, meter, visited)

                await asyncio.to_thread(_write)
                if live is not None:
                    live.update(_meter_table(meter))
            if live is not None:
                live.update(_meter_table(meter))
        _drain_log(log_fh, meter, visited)

    err.print(
        f"wrote {meter.pages} pages to {out_path} "
        f"({meter.pages_per_sec:.2f} pages/s, errors={meter.errors})"
    )
    saved_set = set(saved)
    err.print("visited:")
    for url in dict.fromkeys(visited):
        mark = "saved" if url in saved_set else "fetch"
        err.print(f"  [{mark}] {url}")
    return meter


@app.command("crawl")
def crawl_cmd(
    seeds: Annotated[list[str], typer.Argument(help="Seed URL(s)")],
    max_pages: Annotated[int, typer.Option("--max-pages")] = 500,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 10,
    per_host: Annotated[int, typer.Option("--per-host", min=1)] = 2,
    host_delay: Annotated[float, typer.Option("--host-delay")] = 0.25,
    timeout: Annotated[float, typer.Option("--timeout")] = 10.0,
    out_path: Annotated[Path, typer.Option("--out")] = Path("data/crawl.jsonl"),
    log_path: Annotated[Path, typer.Option("--log")] = Path("crawl.log"),
    allowed_domain: Annotated[
        Optional[list[str]],
        typer.Option("--allowed-domain", help="Repeatable allowlist host"),
    ] = None,
    user_agent: Annotated[str, typer.Option("--user-agent")] = DEFAULT_USER_AGENT,
    debug: Annotated[bool, typer.Option("--debug", help="asyncio debug mode")] = False,
) -> None:
    kwargs = dict(
        seeds=seeds,
        max_pages=max_pages,
        concurrency=concurrency,
        per_host=per_host,
        host_delay=host_delay,
        timeout=timeout,
        out_path=out_path,
        log_path=log_path,
        allowed_domains=allowed_domain,
        user_agent=user_agent,
        debug=debug,
    )
    if not debug:
        asyncio.run(_crawl_async(**kwargs), debug=False)
        return
    loop = asyncio.new_event_loop()
    loop.slow_callback_duration = 0.25
    asyncio.set_event_loop(loop)
    try:
        loop.set_debug(True)
        loop.run_until_complete(_crawl_async(**kwargs))
    finally:
        loop.close()


@app.command("index")
def index_cmd(
    corpus: Annotated[Path, typer.Argument(exists=True)] = DEFAULT_CORPUS,
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
    if corpus.is_file() and corpus.suffix.lower() == ".jsonl":
        total = sum(1 for line in corpus.open(encoding="utf-8") if line.strip())
        if limit is not None:
            total = min(total, limit)
        if total == 0:
            _fail(f"no records in {corpus}")
        built: Index
        with Progress(console=err) as progress:
            task = progress.add_task("indexing", total=total)

            def tick() -> None:
                progress.advance(task)

            try:
                built = build_corpus(
                    corpus,
                    with_positions=positions,
                    limit=limit,
                    on_doc=tick,
                    workers=1,
                    executor="serial",
                )
            except OSError as exc:
                _fail(str(exc))
            except Exception as exc:  # noqa: BLE001
                _fail(str(exc))
    else:
        if not corpus.is_dir():
            _fail(f"corpus must be a directory or .jsonl file: {corpus}")
        files = sorted(corpus.glob("*.txt"))
        if limit is not None:
            files = files[:limit]
        if not files:
            _fail(f"no .txt files under {corpus}")

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
            except Exception as exc:  # noqa: BLE001
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
        f"executor={executor if corpus.is_dir() else 'serial'} "
        f"workers={workers if corpus.is_dir() and executor != 'serial' else 1} "
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
    backend: Annotated[Literal["numpy", "loop"], typer.Option("--backend")] = "numpy",
    mode: Annotated[
        Literal["keyword", "semantic", "hybrid"],
        typer.Option("--mode"),
    ] = "keyword",
    embeddings: Annotated[
        Path | None,
        typer.Option("--embeddings", help="embeddings .npy"),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON lines on stdout")] = False,
) -> None:
    if not index_path.is_file():
        _fail(f"index not found: {index_path}")

    hits: list[SearchResult]
    try:
        scorer = pick_scorer(scorer_name)
        bank = None
        if mode in ("semantic", "hybrid"):
            emb = embeddings or Path("embeddings.npy")
            if not emb.is_file():
                _fail(f"embeddings not found: {emb}")
            from findex.vectors import load_vector_bank

            bank = load_vector_bank(emb)
        with open_index(index_path) as index:
            index.ensure_arrays()
            hits = search(
                index,
                query,
                scorer,
                k,
                backend=backend,
                mode=mode,
                embeddings=bank,
                scorer_name=scorer_name,
            )
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


@app.command("bench-crawl")
def bench_crawl_cmd() -> None:
    from findex.bench_crawl import main as run_bench_crawl

    run_bench_crawl()





@app.command("embed")
def embed_cmd(
    index_path: Annotated[Path, typer.Option("--index")] = Path("index.pkl"),
    out: Annotated[Path, typer.Option("--out")] = Path("embeddings.npy"),
    model: Annotated[str, typer.Option("--model")] = "all-MiniLM-L6-v2",
) -> None:
    if not index_path.is_file():
        _fail(f"index not found: {index_path}")
    from findex.vectors import build_vector_bank

    with open_index(index_path) as index:
        store = build_vector_bank(index, model_name=model, out=out)
    err.print(f"embeddings n_chunks={store.n_chunks} dim={store.dim} -> {out}")


@app.command("serve")
def serve_cmd(
    index: Annotated[Path, typer.Option("--index", help="Index pickle/json path")] = Path("index.pkl"),
    embeddings: Annotated[
        Path | None,
        typer.Option("--embeddings", help="Optional embeddings .npy"),
    ] = None,
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8000,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    workers: Annotated[int, typer.Option("--workers", min=1)] = 1,
    reload: Annotated[bool, typer.Option("--reload")] = False,
) -> None:
    import os

    import uvicorn

    os.environ["INDEX_PATH"] = str(index.resolve())
    if embeddings is not None:
        os.environ["EMBEDDINGS_PATH"] = str(embeddings.resolve())
    # clear cached settings so INDEX_PATH is re-read
    from findex.web.config import load_config

    load_config.cache_clear()
    uvicorn.run(
        "findex.web:app",
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
    )


if __name__ == "__main__":
    app()