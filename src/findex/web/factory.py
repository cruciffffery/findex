from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from time import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from findex.models import Index
from findex.store import load_json, load_pickle
from findex.web.config import AppConfig, load_config
from findex.web.routes.http_api import router as api_router
from findex.web.routes.pages import router as page_router

log = logging.getLogger("findex.web")
ASSETS = Path(__file__).resolve().parent / "static"


def open_index_file(path: Path) -> Index:
    if not path.exists():
        raise FileNotFoundError(f"index not found: {path}")
    if path.suffix.lower() == ".json":
        return load_json(path)
    loaded = load_pickle(path)
    if not isinstance(loaded, Index):
        raise TypeError(f"expected Index in {path}")
    return loaded


class TraceHeader(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def make_app(settings: AppConfig | None = None, *, load_on_startup: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = settings if settings is not None else load_config()
        app.state.settings = cfg
        app.state.started_at = time()
        app.state.index = None
        logging.basicConfig(
            level=getattr(logging, cfg.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
        if load_on_startup:
            app.state.index = open_index_file(cfg.index_path)
            log.info("index ready path=%s docs=%s", cfg.index_path, app.state.index.num_docs)
        yield
        app.state.index = None

    app = FastAPI(
        title="findex search",
        version="0.7.0",
        description="HTTP search API and browse UI",
        lifespan=lifespan,
    )
    app.add_middleware(TraceHeader)

    @app.exception_handler(Exception)
    async def boom(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        log.exception("crash request_id=%s", rid)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal server error", "request_id": rid},
        )

    app.include_router(api_router)
    app.include_router(page_router)
    if ASSETS.is_dir():
        app.mount("/static", StaticFiles(directory=str(ASSETS)), name="static")
    return app


app = make_app()