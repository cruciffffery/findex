# findex - lab 07

**Live deploy URL:** HERE INSERT THE DEPLOY URL

HTTP search API + browse UI. Version **0.7.0**. Tag **`lab-07`** when you push.

Continues lab 06: the crawler filled a corpus; this lab puts BM25 behind FastAPI
so anyone can query it from a browser or `curl`.

```bash
uv sync --all-groups
findex index src/resources --out index.pkl
findex serve --index index.pkl --port 8000
# open http://127.0.0.1:8000/
uv run pytest
uv run python scripts/bench_handlers.py
```

## Continuity

| lab | adds |
|-----|------|
| 01-03 | corpus → inverted index → ranking |
| 04 | types, pytest, typer/rich CLI |
| 05 | parallel index build, GIL benchmarks |
| 06 | asyncio crawl → JSONL |
| 07 | FastAPI / Pydantic / Jinja+htmx UI, Docker, load numbers |

## API

- `GET /search?q=&k=&scorer=&page=` - validated params, paginated hits
- `GET /docs/{doc_id}` - document body (404 if unknown)
- `GET /stats` - docs / vocab / uptime
- `GET /health` - `ok`, or **503** while the index is missing
- OpenAPI: `/docs`

Index loads once in **lifespan** from `INDEX_PATH` (`pydantic-settings`).
Pydantic models sit only on the wire; scoring still uses Lab 2-3 dataclasses.
Unexpected errors log a request id and return a bare 500 (no stack).

`findex serve [--port 8000] [--workers N]` wraps uvicorn.

## UI

Dark sidebar layout. `GET /` - search box, highlighted snippets, scores,
pagination, document page at `GET /doc/{doc_id}`. Optional **htmx** fragment at
`/fragment/results` updates the result panel without a full reload.

## Tests

`TestClient` + `dependency_overrides` (no real index file on disk for the suite):

- search 200
- bad `k` → 422
- missing doc → 404
- unloaded index → `/health` 503

## def vs async def

`/search` does CPU scoring. Kept as plain **`def`** so FastAPI runs it in a thread
pool instead of blocking the event loop.

20 concurrent requests (`scripts/bench_handlers.py`, `time.sleep(0.05)` as a
blocking stand-in):

| mode | wall |
|---|---|
| `async def` (blocks the loop) | **1.22 s** |
| `def` (thread pool) | **0.76 s** |

## Docker

Multi-stage image from `uv.lock`, non-root user, index baked at
`/app/deploy/index.pkl`.

```bash
docker build -t findex .
docker run --rm -e INDEX_PATH=/app/deploy/index.pkl -p 8000:8000 findex
```

## Deploy

1. HERE INSERT THE DEPLOY URL on the first line of this README.
2. Env: `INDEX_PATH`, optional `PORT`, `LOG_LEVEL`.
3. Platform health check: `/health`.
4. Deployed load numbers: HERE INSERT DEPLOYED OHA / LOAD NUMBERS

## Load test

Client: `scripts/load_search.py` (same columns as `oha`: RPS, p50 / p95 / p99).
Query `q=alice`, concurrency 20, 200 requests (local).

| Target | RPS | p50 (ms) | p95 | p99 |
|---|---|---|---|---|
| local, 1 worker, `async def` (blocking stand-in; see handler bench) | ~8.6 | ~2200 | ~3100 | ~3400 |
| local, 1 worker, `def` | **13.8** | **1388** | **2045** | **2217** |
| local, 4 workers | **13.7** | **1417** | **1680** | **1780** |
| deployed (HERE INSERT THE DEPLOY URL) | - | - | - | - |

**Reading the table (labs 5-6):** a blocking `async def` parks the event loop
(lab 6). Plain `def` offloads to a thread pool; the GIL (lab 5) still serializes
bytecode in one process - which is why 4 workers barely moved RPS on this small
index while p99 tightened a bit.

## Reflection

1. Trace curl → Uvicorn → ASGI → FastAPI → Pydantic → your route.
2. Why is `/search` a `def`, and what breaks if it is a blocking `async def`?
3. What should `/health` return before lifespan finishes loading the index?