from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from findex.web.engine import fetch_doc, mark_terms, page_search
from findex.web.wiring import IndexDep

TPL = Path(__file__).resolve().parent.parent / "templates"
jinja = Jinja2Templates(directory=str(TPL))
jinja.env.filters["mark"] = mark_terms

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def home_page(
    request: Request,
    index: IndexDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    k: Annotated[int, Query(ge=1, le=100)] = 10,
    scorer: Annotated[Literal["bm25", "tfidf"], Query()] = "bm25",
    page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    ctx: dict = {
        "request": request,
        "q": q or "",
        "k": k,
        "scorer": scorer,
        "page": page,
        "payload": None,
        "pages": 0,
    }
    if q:
        payload = page_search(index, q, k=k, scorer=scorer, page=page, page_size=k)
        ctx["payload"] = payload
        ctx["pages"] = max(1, ceil(payload.total / payload.page_size)) if payload.total else 0
    return jinja.TemplateResponse(request, "home.html", ctx)


@router.get("/doc/{doc_id}", response_class=HTMLResponse)
def browse_doc(request: Request, doc_id: int, index: IndexDep) -> HTMLResponse:
    doc = fetch_doc(index, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return jinja.TemplateResponse(request, "browse.html", {"request": request, "doc": doc})


@router.get("/fragment/results", response_class=HTMLResponse)
def results_fragment(
    request: Request,
    index: IndexDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    k: Annotated[int, Query(ge=1, le=100)] = 10,
    scorer: Annotated[Literal["bm25", "tfidf"], Query()] = "bm25",
    page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    if not q:
        return HTMLResponse("")
    payload = page_search(index, q, k=k, scorer=scorer, page=page, page_size=k)
    pages = max(1, ceil(payload.total / payload.page_size)) if payload.total else 0
    return jinja.TemplateResponse(
        request,
        "results_fragment.html",
        {
            "request": request,
            "q": q,
            "k": k,
            "scorer": scorer,
            "page": page,
            "payload": payload,
            "pages": pages,
        },
    )

