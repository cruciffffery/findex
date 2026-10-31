from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from findex.crawler.html_bits import scan_html
from findex.crawler.http_pull import DEFAULT_USER_AGENT, FetchOutcome, pull
from findex.crawler.robots_store import RobotsStore
from findex.crawler.urls import normalize_url


@dataclass(frozen=True, slots=True)
class PageRecord:
    url: str
    title: str
    text: str
    fetched_at: str


@dataclass
class CrawlMeter:
    pages: int = 0
    errors: int = 0
    in_flight: int = 0
    queue_depth: int = 0
    started_at: float = field(default_factory=time.perf_counter)
    log_lines: list[str] = field(default_factory=list)

    @property
    def pages_per_sec(self) -> float:
        return self.pages / max(1e-9, time.perf_counter() - self.started_at)


def _hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


class Spider:
    def __init__(
        self,
        seeds: Iterable[str],
        *,
        max_pages: int = 500,
        concurrency: int = 10,
        per_host: int = 2,
        allowed_domains: Iterable[str] | None = None,
        host_delay: float = 0.25,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        meter: CrawlMeter | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.max_pages = max_pages
        self.concurrency = max(1, concurrency)
        self.per_host = max(1, per_host)
        self.host_delay = host_delay
        self.timeout = timeout
        self.user_agent = user_agent
        self.meter = meter or CrawlMeter()
        self.allowed = {d.lower().lstrip(".") for d in (allowed_domains or [])}
        self.client = client
        self._owns_client = client is None
        self.seeds = list(seeds)

        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.outbox: asyncio.Queue[PageRecord | None] = asyncio.Queue()
        self.seen: set[str] = set()
        self.halt = asyncio.Event()
        self.saved = 0
        self.open_jobs = 0
        self.global_sem = asyncio.Semaphore(self.concurrency)
        self.host_sems: dict[str, asyncio.Semaphore] = {}
        self.host_ready: dict[str, float] = {}
        self.robots: RobotsStore | None = None

    def _domain_ok(self, url: str) -> bool:
        host = _hostname(url)
        if not host:
            return False
        if not self.allowed:
            return True
        return host in self.allowed or any(host.endswith("." + d) for d in self.allowed)

    def push(self, url: str) -> None:
        if self.halt.is_set() or self.saved >= self.max_pages:
            return
        url = normalize_url(url)
        if url in self.seen or not self._domain_ok(url):
            return
        self.seen.add(url)
        self.open_jobs += 1
        self.queue.put_nowait(url)
        self.meter.queue_depth = self.queue.qsize()

    def _note(self, fr: FetchOutcome) -> None:
        status = fr.status if fr.status is not None else "-"
        self.meter.log_lines.append(
            f"{fr.url}\t{status}\t{fr.nbytes}\t{fr.elapsed:.3f}\t{fr.error or ''}"
        )

    async def _gated_pull(self, url: str) -> FetchOutcome:
        assert self.client is not None
        host = _hostname(url)
        sem = self.host_sems.setdefault(host, asyncio.Semaphore(self.per_host))
        async with self.global_sem, sem:
            pause = self.host_ready.get(host, 0.0) - time.perf_counter()
            if pause > 0:
                await asyncio.sleep(pause)
            self.meter.in_flight += 1
            try:
                return await pull(self.client, url, timeout=self.timeout)
            finally:
                self.meter.in_flight -= 1
                self.host_ready[host] = time.perf_counter() + self.host_delay

    async def _visit(self, url: str) -> None:
        assert self.robots is not None
        if self.halt.is_set() or self.saved >= self.max_pages:
            return

        if not await self.robots.may_fetch(url):
            self.meter.errors += 1
            self._note(
                FetchOutcome(url=url, status=None, nbytes=0, elapsed=0.0, error="robots disallowed")
            )
            return

        fr = await self._gated_pull(url)
        self._note(fr)
        if fr.status is None or fr.status >= 400 or not fr.body:
            if fr.status is None or fr.status >= 400:
                self.meter.errors += 1
            return

        base = fr.final_url or url
        title, text, links = await asyncio.to_thread(scan_html, fr.body, base)
        page = PageRecord(
            url=normalize_url(base),
            title=title or normalize_url(base),
            text=text,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

        if self.saved >= self.max_pages or self.halt.is_set():
            return
        self.saved += 1
        self.meter.pages = self.saved
        await self.outbox.put(page)

        if self.saved >= self.max_pages:
            self.halt.set()
            return
        for link in links:
            self.push(link)

    async def _worker(self) -> None:
        while not self.halt.is_set():
            try:
                url = await asyncio.wait_for(self.queue.get(), timeout=0.15)
            except TimeoutError:
                if self.open_jobs <= 0:
                    self.halt.set()
                    return
                continue
            try:
                self.meter.queue_depth = self.queue.qsize()
                await self._visit(url)
            finally:
                self.open_jobs -= 1
                self.queue.task_done()

    async def stream(self) -> AsyncIterator[PageRecord]:
        if self.client is None:
            self.client = httpx.AsyncClient(
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
                timeout=self.timeout,
            )
        self.robots = RobotsStore(self.client, user_agent=self.user_agent)

        for seed in self.seeds:
            self.push(seed)

        async def run_pool() -> None:
            try:
                async with asyncio.TaskGroup() as tg:
                    for _ in range(self.concurrency):
                        tg.create_task(self._worker())
            finally:
                self.halt.set()
                await self.outbox.put(None)

        producer = asyncio.create_task(run_pool())
        yielded = 0
        try:
            while True:
                item = await self.outbox.get()
                if item is None:
                    break
                yield item
                yielded += 1
                if yielded >= self.max_pages:
                    self.halt.set()
                    break
        finally:
            self.halt.set()
            if not producer.done():
                producer.cancel()
                try:
                    await producer
                except (asyncio.CancelledError, ExceptionGroup, Exception):
                    pass
            if self._owns_client and self.client is not None:
                await self.client.aclose()


async def run_crawl(
    seeds: Iterable[str],
    *,
    max_pages: int = 500,
    concurrency: int = 10,
    per_host: int = 2,
    allowed_domains: Iterable[str] | None = None,
    host_delay: float = 0.25,
    timeout: float = 10.0,
    user_agent: str = DEFAULT_USER_AGENT,
    meter: CrawlMeter | None = None,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[PageRecord]:
    spider = Spider(
        seeds,
        max_pages=max_pages,
        concurrency=concurrency,
        per_host=per_host,
        allowed_domains=allowed_domains,
        host_delay=host_delay,
        timeout=timeout,
        user_agent=user_agent,
        meter=meter,
        client=client,
    )
    async for page in spider.stream():
        yield page
