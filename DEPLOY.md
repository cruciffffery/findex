# Deploy (Render)

## What you need

1. Code on GitHub `main` (this folder as the repo root, or set Root Directory).
2. Service type: **Web Service**, Language: **Docker** (not Rust).
3. Env vars (Render → Environment):

| Key | Value |
|---|---|
| `INDEX_PATH` | `/app/deploy/index.pkl` |
| `EMBEDDINGS_PATH` | `/app/deploy/embeddings.npy` |
| `LOG_LEVEL` | `INFO` |

Do **not** set `PORT` — Render injects it. Health check path: `/health`.

4. Dockerfile already:
   - installs the `semantic` group (torch + sentence-transformers)
   - builds `index.pkl` into `/app/deploy/`
   - uses pre-baked `deploy/embeddings.npy` if present in the repo, otherwise runs `findex embed` during the image build (slow first time)

## Faster builds (recommended)

Before push, bake artifacts once locally:

```bash
cd sasha/lab_8   # or repo root if this is the root
uv sync --group semantic
uv run findex index src/resources --out deploy/index.pkl
uv run findex embed --index deploy/index.pkl --out deploy/embeddings.npy --model all-MiniLM-L6-v2
git add deploy/index.pkl deploy/embeddings.npy deploy/embeddings_doc_ids.npy deploy/embeddings.meta.json
git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -m "Bake deploy index and embeddings"
git push
```

Then Render only copies them — no MiniLM download during build.

## After deploy

1. Copy `https://….onrender.com` → paste into README: `HERE INSERT THE DEPLOY URL`
2. Smoke: `/health`, `/search?q=alice`, `/search?q=alice&mode=hybrid`
3. Optional load: `oha` / `scripts/load_search.py` against the public URL

## Local Docker check

```bash
docker build -t findex .
docker run --rm -e INDEX_PATH=/app/deploy/index.pkl -e EMBEDDINGS_PATH=/app/deploy/embeddings.npy -p 8000:8000 findex
```
