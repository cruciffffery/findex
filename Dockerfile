# syntax=docker/dockerfile:1
# Multi-stage uv build. Index + embeddings baked into /app/deploy for Render.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

# Include torch / sentence-transformers so query-time encode works in the image
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --group semantic

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group semantic

# Build keyword index; reuse pre-baked embeddings from deploy/ or root, else embed now
RUN mkdir -p /app/deploy /app/.cache/huggingface \
    && uv run findex index src/resources --out /app/deploy/index.pkl --format pickle \
    && if [ -f /app/deploy/embeddings.npy ]; then \
         echo "using pre-baked /app/deploy/embeddings.npy"; \
       elif [ -f /app/embeddings.npy ]; then \
         cp /app/embeddings.npy /app/deploy/embeddings.npy; \
         cp /app/embeddings_doc_ids.npy /app/deploy/embeddings_doc_ids.npy 2>/dev/null || true; \
         cp /app/embeddings.meta.json /app/deploy/embeddings.meta.json 2>/dev/null || true; \
       else \
         echo "building embeddings (first build is slow)…"; \
         uv run findex embed --index /app/deploy/index.pkl --out /app/deploy/embeddings.npy --model all-MiniLM-L6-v2; \
       fi \
    && test -f /app/deploy/index.pkl \
    && test -f /app/deploy/embeddings.npy


FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system --gid 1000 appuser \
    && useradd --system --uid 1000 --gid appuser --home /app --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /app/deploy /app/deploy
COPY --from=builder --chown=appuser:appuser /app/pyproject.toml /app/pyproject.toml
COPY --from=builder --chown=appuser:appuser /app/.cache /app/.cache

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    INDEX_PATH="/app/deploy/index.pkl" \
    EMBEDDINGS_PATH="/app/deploy/embeddings.npy" \
    LOG_LEVEL="INFO" \
    PORT="8000" \
    HF_HOME="/app/.cache/huggingface" \
    TRANSFORMERS_CACHE="/app/.cache/huggingface" \
    OMP_NUM_THREADS="1" \
    MKL_NUM_THREADS="1" \
    OPENBLAS_NUM_THREADS="1" \
    TOKENIZERS_PARALLELISM="false"

USER appuser
EXPOSE 8000

CMD ["sh", "-c", "uvicorn findex.web:app --host 0.0.0.0 --port ${PORT:-8000}"]
