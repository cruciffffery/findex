# findex — lab 02

Continues lab 01’s `DocumentWalker` / `tokenize` pipeline. Builds an inverted
index over `src/resources/*.txt` (Alice, Frankenstein, Pride & Prejudice) —
**one `.txt` file = one document**.

```bash
# from repo root (after uv sync)
uv run python -m findex.index src/resources --out index.pkl
uv run python -m findex.search index.pkl "elizabeth darcy" --engine merge
uv run python src/main.py   # rebuild + memory / bench / save-load tables
```


## Layout

- `src/findex/corpus.py` — `DocumentWalker.iter_docs()` (lazy, one file at a time)
- `src/findex/models.py` — `Posting`, `DocMeta` (`frozen=True`, `slots=True`)
- `src/findex/index.py` — single pass with `defaultdict` + `Counter`
- `src/findex/search.py` — AND / OR / NOT, `--engine {merge,set}`
- `src/findex/store.py` — pickle + json
- `src/main.py` — measurement entry point

## Memory (tracemalloc)

Same corpus: 3 docs, 238869 tokens, 11566 terms. File size and load time are pickle. Load time is the median of 5.

| representation | peak (KiB) | file (bytes) | load (s) |
|----------------|------------|--------------|----------|
| plain dataclass | 15706.7 | 538067 | 0.0128 |
| `slots=True` | 15370.7 | 430756 | 0.0382 |
| `array('I')` pairs | 16123.4 | 659565 | 0.0112 |

**Where the bytes went:** slotted `Posting` objects drop the per-instance `__dict__`, so peak falls from 15706.7 KiB (plain) to 15370.7 KiB. Plain pickle is larger for the same reason. The `array('I')` row stores raw ints, but every term still owns two array headers; with many short posting lists that header tax dominates, so peak (16123.4 KiB) and pickle size (659565) sit above the slotted object layout on this corpus.

## merge vs set

Mean of 200000 `search()` calls. `term term` is AND.

| pair | query | tf | engine | mean (s) |
|------|-------|----|--------|----------|
| rare | `0 108` | 1, 1 | merge | 0.00000085 |
| rare | `0 108` | 1, 1 | set | 0.00000100 |
| common | `and the` | 7807, 11072 | merge | 0.00000060 |
| common | `and the` | 7807, 11072 | set | 0.00000059 |

On rare one-doc terms, merge wins: `set` still allocates two hash sets for a tiny AND. On the common pair the times are essentially tied (set slightly ahead here).

## Save / load

Slots index, positions off. Times are the median of 5.

| format | size (bytes) | save (s) | load (s) |
|--------|--------------|----------|----------|
| pickle | 430736 | 0.0272 | 0.0278 |
| json | 310175 | 0.0166 | 0.0221 |

`pickle.load` executes whatever the blob asks for. Only load an index this program wrote.

## Positions

`--positions` on `python -m findex.index` (off by default).

| positions | peak (KiB) | pickle (bytes) |
|-----------|------------|----------------|
| off | 15075.0 | 430736 |
| on | 19276.7 | 1326575 |

Peak jumps from 15075.0 KiB to 19276.7 KiB: every token offset becomes a Python `int` hanging off each posting.
