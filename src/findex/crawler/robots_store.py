from __future__ import annotations

import asyncio
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from findex.crawler.http_pull import DEFAULT_USER_AGENT


class RobotsStore:
    def __init__(self, client: httpx.AsyncClient, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._client = client
        self._ua = user_agent
        self._by_host: dict[str, RobotFileParser] = {}
        self._gates: dict[str, asyncio.Lock] = {}

    async def _fetch_rules(self, host: str, scheme: str) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            resp = await self._client.get(f"{scheme}://{host}/robots.txt", timeout=10.0)
            # missing robots (404) → empty rules → allow by default
            rows = resp.text.splitlines() if resp.status_code < 400 else []
        except httpx.HTTPError:
            rows = []
        parser.parse(rows)
        return parser

    async def may_fetch(self, url: str) -> bool:
        bits = urlsplit(url)
        host = (bits.hostname or "").lower()
        if not host:
            return False
        if host not in self._by_host:
            gate = self._gates.setdefault(host, asyncio.Lock())
            async with gate:
                if host not in self._by_host:
                    scheme = (bits.scheme or "https").lower()
                    self._by_host[host] = await self._fetch_rules(host, scheme)
        return self._by_host[host].can_fetch(self._ua, url)
