from __future__ import annotations

import asyncio

import httpx

from findex.crawler.robots_store import RobotsStore


def test_robots_cache_per_host() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            hits["n"] += 1
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, content=b"ok")

    async def main() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            store = RobotsStore(client, user_agent="bot")
            assert await store.may_fetch("https://ex.com/ok")
            assert not await store.may_fetch("https://ex.com/private")
            assert await store.may_fetch("https://ex.com/ok2")
        assert hits["n"] == 1

    asyncio.run(main())