from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HitOut(BaseModel):
    doc_id: int
    title: str
    score: float
    snippet: str


class SearchPayload(BaseModel):
    query: str
    total: int
    page: int
    page_size: int
    took_ms: float
    mode: Literal["keyword", "semantic", "hybrid"] = "keyword"
    results: list[HitOut]


class DocPayload(BaseModel):
    doc_id: int
    title: str
    path: str
    text: str


class StatsPayload(BaseModel):
    num_docs: int
    vocab_size: int
    uptime_s: float
    index_path: str
    embeddings: bool = False


class HealthPayload(BaseModel):
    status: Literal["ok", "unavailable"] = "ok"
    detail: str | None = None


class ErrPayload(BaseModel):
    detail: str
    request_id: str | None = None


ScorerName = Literal["bm25", "tfidf"]
ModeName = Literal["keyword", "semantic", "hybrid"]
