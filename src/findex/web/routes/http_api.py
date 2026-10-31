from __future__ import annotations

from time import time
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status

from findex.web.boundary import DocPayload, HealthPayload, SearchPayload, StatsPayload
from findex.web.engine import fetch_doc, page_search
from findex.web.wiring import ConfigDep, IndexDep

router = APIRouter(tags=["api"])


@router.get("/search", response_model=SearchPayload)
def search_route(
    index: IndexDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    k: Annotated[int, Query(ge=1, le=100)] = 10,
    scorer: Annotated[Literal["bm25", "tfidf"], Query()] = "bm25",
    page: Annotated[int, Query(ge=1)] = 1,
) -> SearchPayload:
    # plain def: scoring is CPU work; FastAPI offloads to a thread pool
    return page_search(index, q, k=k, scorer=scorer, page=page, page_size=k)


@router.get("/docs/{doc_id}", response_model=DocPayload)
def doc_route(doc_id: int, index: IndexDep) -> DocPayload:
    doc = fetch_doc(index, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return doc


@router.get("/stats", response_model=StatsPayload)
def stats_route(request: Request, index: IndexDep, settings: ConfigDep) -> StatsPayload:
    started = getattr(request.app.state, "started_at", time())
    return StatsPayload(
        num_docs=index.num_docs,
        vocab_size=len(index),
        uptime_s=round(time() - started, 3),
        index_path=str(settings.index_path),
    )


@router.get("/health", response_model=HealthPayload)
def health_route(request: Request) -> HealthPayload:
    if getattr(request.app.state, "index", None) is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="index not loaded",
        )
    return HealthPayload(status="ok")