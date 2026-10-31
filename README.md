# findex — lab 01

First step of the sasha findex series (01 → 08). Corpus statistics over
`src/resources/` — Alice in Wonderland split into chapter files.  
**Each `*.txt` file is treated as a single document.**

Drop additional texts into that folder as the corpus grows toward the course
target (~1 000 documents / ~50 MB).

## Project layout

| path | role |
|------|------|
| `src/findex/corpus.py` | `DocumentWalker.iter_documents()` — generator, one file per yield |
| `src/findex/tokenize.py` | `tokenize()` / `WordStream` — NFKC + casefold, lazy yields |
| `src/findex/measure.py` | `StreamingPass` (lean) vs `EagerPass` (list-heavy) |
| `src/findex/types.py` | `CorpusMetrics` dataclass |
| `src/main.py` | runs both passes and prints top-50 terms |

## Token rules (documented)

Implemented in `src/findex/tokenize.py`:

1. Text is normalised with **NFKC**, then **casefold**ed.
2. **Apostrophes** (`'`, `’`, `ʼ`) keep word parts together (`don't` → one token).
3. **Hyphens** keep compounds together (`good-for-nothing` → one token).
4. **Digits** are retained (`4`, `1991`).
5. Other punctuation acts as a split boundary (`Hello, world!` → `hello`, `world`).

## Streaming vs eager (measured)

Peak RSS tracked with `tracemalloc`. Eager keeps every document body and every
token occurrence in Python `list`s before building the `Counter`; streaming only
retains the counter.

| mode      | docs | tokens | vocab | time (s) | peak (KiB) |
|-----------|------|--------|-------|----------|------------|
| streaming | 13   | 29773  | 3130  | 0.0776   | 716.7      |
| eager     | 13   | 29773  | 3130  | 0.0533   | 2070.6     |

**Memory story:** eager pays for two large lists (full document texts + every
token string reference). Streaming frees each document after its tokens are
counted, so peak stays near the size of the vocabulary counter (~0.7 MiB here
vs ~2.0 MiB eager on the same 13-file corpus).

## Run

```bash
uv sync --group dev
uv run pytest
uv run python src/main.py
```
