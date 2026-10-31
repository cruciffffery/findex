from __future__ import annotations

from pathlib import Path
from time import perf_counter

from findex.corpus import read_text
from findex.models import Index, SearchResult
from findex.score import pick_scorer
from findex.search import search as ranked_search
from findex.web.boundary import DocPayload, HitOut, SearchPayload, ScorerName

HIT_CAP = 100


def page_search(
    index: Index,
    query: str,
    *,
    k: int = 10,
    scorer: ScorerName = "bm25",
    page: int = 1,
    page_size: int = 10,
) -> SearchPayload:
    size = min(max(k, 1), page_size)
    t0 = perf_counter()
    hits = ranked_search(index, query, pick_scorer(scorer), k=HIT_CAP)
    took_ms = (perf_counter() - t0) * 1000.0
    total = len(hits)
    start = (page - 1) * size
    window = hits[start : start + size]
    return SearchPayload(
        query=query,
        total=total,
        page=page,
        page_size=size,
        took_ms=round(took_ms, 3),
        results=[_as_hit(h) for h in window],
    )


def _as_hit(hit: SearchResult) -> HitOut:
    return HitOut(doc_id=hit.doc_id, title=hit.title, score=hit.score, snippet=hit.snippet)


def fetch_doc(index: Index, doc_id: int) -> DocPayload | None:
    meta = index.doc_meta.get(doc_id)
    if meta is None:
        return None
    return DocPayload(
        doc_id=doc_id,
        title=meta.title,
        path=meta.path,
        text=_body(meta.path),
    )


def _body(path_str: str) -> str:
    path = Path(path_str)
    if path.is_file():
        return read_text(path)
    return ""


def mark_terms(snippet: str) -> str:
    # Lab-3 "[term]" markers → <mark> for the HTML page
    parts: list[str] = []
    i = 0
    while i < len(snippet):
        if snippet[i] == "[":
            end = snippet.find("]", i + 1)
            if end > i:
                parts.append("<mark>")
                parts.append(_esc(snippet[i + 1 : end]))
                parts.append("</mark>")
                i = end + 1
                continue
        parts.append(_esc(snippet[i]))
        i += 1
    return "".join(parts)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )