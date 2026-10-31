# findex — lab 06

![CI](https://img.shields.io/badge/CI-GitHub%20Actions-0A7A0A)

Continues lab 05. Indexing was CPU-bound; crawling waits on the network, so one
event-loop thread can keep many HTTP requests in flight.

```bash
uv sync --all-groups
findex crawl https://books.toscrape.com/ --max-pages 200 --concurrency 20 --per-host 2 --out data/crawl.jsonl --log crawl.log
findex index data/crawl.jsonl --out index.pkl --executor serial
findex search index.pkl "fiction" --k 5
uv run python -m findex.bench_crawl
uv run pytest
```

Version **0.6.0**. Tag **`lab-06`** when you push.

## Continuity

| lab | adds |
|-----|------|
| 01–03 | corpus → inverted index → ranking |
| 04 | types, pytest, typer/rich CLI |
| 05 | parallel index build, GIL benchmarks |
| 06 | asyncio crawl (`TaskGroup`, semaphores, robots, retries) → JSONL → index |

## Permission / ethics

Crawl target: **https://books.toscrape.com/** — a public practice bookstore built
for scraping tutorials.

- `robots.txt` returns **404** on this host; empty rules → allow-all under
  `urllib.robotparser` (still polite: allowlist, caps, delays).
- User-Agent: `findex-crawler/0.6 (+mailto:crawl-lab@example.org; books.toscrape practice crawl)`
- Allowlist: `books.toscrape.com` only
- Cap: `--max-pages` (benchmarks use **200**)
- Global concurrency + `--per-host` / `--host-delay` so one origin is not hammered

## Benchmark (same seed, max_pages=200)

Seed: `https://books.toscrape.com/`. Host delay **0.25** s, `--per-host 2`.
Measured with `uv run python -m findex.bench_crawl`.

| Concurrency | Pages | Wall (s) | Pages/s | Errors | Peak RSS |
|---|---|---|---|---|---|
| 1 | 200 | 109.56 | 1.83 | 0 | 41.6 MiB |
| 5 | 200 | 55.82 | 3.58 | 0 | 42.6 MiB |
| 20 | 200 | 56.27 | 3.55 | 0 | 43.6 MiB |

## Why concurrency 20 in one thread beats Lab 5 here

Lab 5 was **CPU-bound** tokenization under the GIL: extra threads did not overlap
useful work. This crawl is **I/O-bound**: most wall time is waiting for sockets.
One event-loop thread parks a coroutine at `await client.get(...)` and schedules
another. Overlapping waits cut wall time roughly in half from concurrency 1 → 5
(1.83 → 3.58 pages/s) without twenty OS threads. RSS stays near **42–44 MiB**.

## Cost of the per-host limit (and why it stays)

`--per-host 2` and `--host-delay 0.25` cap load on a single origin. Concurrency 5
and 20 land at almost the same pages/s (**3.58** vs **3.55**) because the frontier is
one host: the global semaphore can admit 20 tasks, but only two fetches overlap and
each is followed by a 0.25 s pause. That leaves throughput on the table and is
intentional — fewer 429s, and a crawl that looks like a client rather than a flood.
The limit remains even when the allowlist already has a single hostname.

## Where the loop would block if we indexed inline

Tokenizing and building postings is CPU work. Doing it inside a crawl worker
(between `await`s) would hold the event loop for hundreds of milliseconds per page —
every other in-flight request would stall. With `--debug`, asyncio would warn about
a slow callback. That is why `findex crawl` only streams JSONL, and `findex index`
runs afterward in ordinary synchronous code.

## Handled failure (429 + Retry-After, and a live 404)

`pull` retries **429 / 5xx / timeouts** (max 3) with exponential backoff + jitter and
honors `Retry-After`. Other 4xx are logged once and not retried.

Live 404 (no retry — a single log line):

```text
https://books.toscrape.com/catalogue/this-page-does-not-exist-xyz/index.html	404	153	0.450	HTTP 404
```

Transient 429 path (MockTransport, same retry code as production) in
[`data/failure_demo.log.txt`](data/failure_demo.log.txt):

```text
https://books.toscrape.com/flaky	429	4	0.012	HTTP 429 (attempt 1, retry after Retry-After)
https://books.toscrape.com/flaky	429	4	0.008	HTTP 429 (attempt 2, retry)
https://books.toscrape.com/flaky	200	52	0.015	
```

## Reflection (defence prompts)

1. Why does overlapping waits beat Lab 5’s thread pool for this workload?
2. What would `asyncio` debug report if `build_corpus` ran inside a crawl worker?
3. Why did concurrency 20 not beat concurrency 5 on this single-host crawl?