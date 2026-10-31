from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient

from findex.models import DocMeta, Index, Posting
from findex.score import pick_scorer
from findex.search import search as ranked_search

PAUSE = 0.05


def _toy() -> Index:
    return Index(
        {"alice": [Posting(0, 2, (0, 4))], "rabbit": [Posting(0, 1, (1,))]},
        {0: 10},
        {0: DocMeta("mem://0", "chapter")},
    )


def build(mode: Literal["async", "sync"]) -> FastAPI:
    index = _toy()
    app = FastAPI()

    if mode == "async":

        @app.get("/search")
        async def blocked(q: str = Query("alice")):
            time.sleep(PAUSE)
            hits = ranked_search(index, q, pick_scorer("bm25"), k=10)
            return {"n": len(hits)}

    else:

        @app.get("/search")
        def pooled(q: str = Query("alice")):
            time.sleep(PAUSE)
            hits = ranked_search(index, q, pick_scorer("bm25"), k=10)
            return {"n": len(hits)}

    return app


async def burst(app: FastAPI, n: int = 20) -> float:
    transport = ASGITransport(app=app)
    t0 = time.perf_counter()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rows = await asyncio.gather(*(client.get("/search", params={"q": "alice"}) for _ in range(n)))
    for r in rows:
        assert r.status_code == 200, r.text
    return time.perf_counter() - t0


def main() -> None:
    t_async = asyncio.run(burst(build("async"), 20))
    t_sync = asyncio.run(burst(build("sync"), 20))
    a = f"async def + time.sleep({PAUSE}), 20 concurrent: {t_async:.4f}s"
    b = f"def + time.sleep({PAUSE}),          20 concurrent: {t_sync:.4f}s"
    print(a)
    print(b)
    out = Path("data/bench_handlers.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(a + "\n" + b + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()