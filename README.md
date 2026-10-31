# findex — lab 04

![CI](https://img.shields.io/badge/CI-GitHub%20Actions-0A7A0A)

Installable CLI on top of the ranked index from labs 01–03. Same Gutenberg corpus
(`alice_in_wonderland`, `frankenstein`, `pride_and_prejudice`).

```bash
uv sync --all-groups
uv tool install .
findex --help
findex index src/resources --out index.pkl
findex search index.pkl "elizabeth darcy" --scorer bm25
findex search index.pkl "alice OR creature" --json
findex stats src/resources
uv run pytest --cov=findex
uv build   # → dist/findex-0.4.0-*.whl
```

Version **0.4.0**. Tag for the course deliverable: `lab-04` / release `v0.4.0`.

## Continuity (labs 01 → 04)

| lab | adds |
|-----|------|
| 01 | streaming `tokenize` + corpus stats |
| 02 | inverted index, boolean merge, pickle/json |
| 03 | `Index` object model, BM25/TF-IDF, query AST, snippets |
| 04 | types (pyright strict), pytest+Hypothesis, typer/rich CLI, CI |

## What this lab adds

| piece | where |
|-------|--------|
| `Scorer` as `typing.Protocol` | `src/findex/score.py` |
| pyright **strict**, 0 errors | `[tool.pyright]` |
| typer + rich CLI | `src/findex/cli.py` → `[project.scripts] findex` |
| ≥30 pytest + Hypothesis | `tests/` (50 collected) |
| logging to stderr (`-v` / `-vv`) | CLI callback |
| GitHub Actions | `.github/workflows/ci.yml` (ruff, pyright, pytest) |

## Coverage

`uv run pytest --cov=findex --cov-report=term-missing`:

| metric | value |
|--------|-------|
| tests | **50 passed** |
| line+branch coverage | **92%** |

Intentionally thin / out of coverage:

- some CLI error branches (missing corpus, OS failures)
- full-corpus precision@5 demo from lab 03 (use `findex search` instead)
- release upload of the wheel (manual `v0.4.0` GitHub Release step)

## CLI behaviour

- Diagnostics → **stderr**; table / `--json` → **stdout**
- Missing index / bad query → one clear line, nonzero exit, no traceback
- `findex index` — rich progress while walking documents
- `findex search` — rich table; `--json` emits one JSON object per line
- `findex stats` — document / token / vocab table + top terms

## Tooling check (local)

```text
ruff check          → All checks passed
pyright (strict)    → 0 errors
pytest              → 50 passed, 92% coverage
uv build            → dist/findex-0.4.0-py3-none-any.whl
```
