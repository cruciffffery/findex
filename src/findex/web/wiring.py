from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from findex.models import Index
from findex.vectors import VectorBank
from findex.web.config import AppConfig, load_config


def require_config(request: Request) -> AppConfig:
    return getattr(request.app.state, "settings", None) or load_config()


def require_index(request: Request) -> Index:
    index = getattr(request.app.state, "index", None)
    if index is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="index not loaded",
        )
    return index


def optional_embeddings(request: Request) -> VectorBank | None:
    return getattr(request.app.state, "embeddings", None)


ConfigDep = Annotated[AppConfig, Depends(require_config)]
IndexDep = Annotated[Index, Depends(require_index)]
EmbedDep = Annotated[VectorBank | None, Depends(optional_embeddings)]
