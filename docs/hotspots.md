# Top-3 hotspots (before NumPy / semantic)

Measured on the Alice + Frankenstein + Pride corpus (15 docs). Query: `alice white rabbit`.

Artifacts: `docs/cprofile_search.txt`, `docs/search.svg` (cProfile → flame via flameprof).
py-spy on this Windows host failed with `Failed to find python version` — SVG is from cProfile.

## Cold CLI search

1. **Pickle restore of Posting objects** — many small Python objects. Mix of native pickle + Python dataclasses.
2. **Import tax** (typer/rich/httpx/crawler) — Python; irrelevant once the API has the index in RAM.
3. **Filesystem during import** — native/system I/O.

## Hot-path search (API-shaped)

1. **Snippet disk reads** (`window_snippet` → `Path.read_text`) — I/O native + Python strings. NumPy will not fix this; benches measure scorer alone.
2. **Python posting loops in Lab-3 BM25** — pure Python over Posting objects. Hypothesis: vectorize with int32 columns + ufuncs.
3. **Heap / sort of scores** — Python; replace with `np.argpartition`.

## After

NumPy BM25/TF-IDF + argpartition landed; identical ranking tests pass. Semantic path is optional `E @ q` + RRF hybrid.
