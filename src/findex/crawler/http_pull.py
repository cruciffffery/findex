from __future__ import annotations

import asyncio
import email.utils
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

DEFAULT_USER_AGENT = (
    "findex-crawler/0.6 (+mailto:crawl-lab@example.org; books.toscrape practice crawl)"
)

ATTEMPT_CAP = 3
BASE_WAIT = 0.4
WAIT_CEILING = 10.0


@dataclass(frozen=True, slots=True)
class FetchOutcome:
    url: str
    status: int | None
    nbytes: int
    elapsed: float
    body: bytes = b""
    error: str | None = None
    final_url: str | None = None
    content_type: str | None = None


def _retry_after_secs(raw: str | None) -> float | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _delay(attempt: int, retry_after: str | None = None) -> float:
    hinted = _retry_after_secs(retry_after)
    if hinted is not None:
        return hinted + random.uniform(0.0, 0.3)
    return min(WAIT_CEILING, BASE_WAIT * (2 ** attempt)) + random.uniform(0.0, 0.8)


def _should_retry(status: int | None, exc: BaseException | None) -> bool:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    return status == 429 or (status is not None and 500 <= status <= 599)


async def pull(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = 10.0,
    max_attempts: int = ATTEMPT_CAP,
) -> FetchOutcome:
    last = FetchOutcome(url=url, status=None, nbytes=0, elapsed=0.0, error="fetch failed")

    for attempt in range(max_attempts):
        started = time.perf_counter()
        try:
            async with asyncio.timeout(timeout):
                resp = await client.get(url)
            elapsed = time.perf_counter() - started
            payload = resp.content
            code = resp.status_code
            last = FetchOutcome(
                url=url,
                status=code,
                nbytes=len(payload),
                elapsed=elapsed,
                body=payload,
                error=None if code < 400 else f"HTTP {code}",
                final_url=str(resp.url),
                content_type=resp.headers.get("content-type"),
            )
            if _should_retry(code, None) and attempt + 1 < max_attempts:
                await asyncio.sleep(_delay(attempt, resp.headers.get("Retry-After")))
                continue
            return last
        except (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException) as exc:
            last = FetchOutcome(
                url=url,
                status=None,
                nbytes=0,
                elapsed=time.perf_counter() - started,
                error=f"timeout: {exc}",
            )
            if attempt + 1 < max_attempts:
                await asyncio.sleep(_delay(attempt))
        except httpx.HTTPError as exc:
            last = FetchOutcome(
                url=url,
                status=None,
                nbytes=0,
                elapsed=time.perf_counter() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
            if _should_retry(None, exc) and attempt + 1 < max_attempts:
                await asyncio.sleep(_delay(attempt))
            else:
                break

    return last
