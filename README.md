# findex — lab 03

Continues lab 02’s inverted index. Ranked search over `src/resources/*.txt` —
**one `.txt` file = one document** (Alice, Frankenstein, Pride & Prejudice).
Adds `Index` as a Mapping, BM25/TF-IDF, query AST, snippets, `@timed` / cache.

```bash
uv sync --group dev
uv run python src/main.py
```

`main.py` builds the index, prints the checks below, then runs the demo query twice
inside `with open_index`.

## Index

`WITH_POSITIONS = True`. One build:

`Index(terms=11_566, docs=3)` — 238869 tokens, 0.9396 s, peak 19273.1 KiB.

## Ranking checks (BM25, k1=1.5, b=0.75)

Same tf and the same document length. Only `df` changes. `cheshire` is in one book,
`elizabeth` in two.

| term | df | weight at tf=1 |
|------|----|----------------|
| cheshire | 1 | 1.5295 |
| elizabeth | 2 | 0.5645 |

The rare term weighs more.

Marginal gain for `cheshire` on the shortest document’s length. The 20th occurrence
adds 0.0053; the first added 1.5295.

| tf | weight | step from tf−1 |
|----|--------|----------------|
| 1 | 1.5295 | 1.5295 |
| 2 | 1.9648 | 0.4353 |
| 20 | 2.6414 | 0.0053 |
| 21 | 2.6463 | 0.0048 |

Same term, tf 1. The short book wins at `b=0.75`. At `b=0` the length term drops out
and the weights match.

| document | tokens | b=0.75 | b=0 |
|----------|--------|--------|-----|
| alice_in_wonderland | 29773 | 1.5295 | 1.0986 |
| pride_and_prejudice | 130791 | 0.8522 | 1.0986 |

## precision@5

Ten hand-labeled queries. A hit counts when the labeled book is in the top 5.
Precision divides by 5. Each query has one labeled book and that book is the only
hit, so every cell is 1/5 = 0.20. Three documents cannot push a retrieved hit past
rank 5, so TF-IDF and BM25 tie.

| query | TF-IDF | BM25 |
|-------|--------|------|
| alice | 0.20 | 0.20 |
| hatter | 0.20 | 0.20 |
| cheshire | 0.20 | 0.20 |
| "white rabbit" | 0.20 | 0.20 |
| frankenstein | 0.20 | 0.20 |
| walton | 0.20 | 0.20 |
| creature | 0.20 | 0.20 |
| elizabeth | 0.20 | 0.20 |
| darcy | 0.20 | 0.20 |
| "pride and prejudice" | 0.20 | 0.20 |
| **mean** | **0.20** | **0.20** |

## @timed and cache

`logging` at DEBUG. `assemble`, `load_pickle`, `_unpickle`, and `search` log milliseconds.
The demo query runs twice on the loaded index. The second call logs `cache hit` and
`CacheInfo(hits=1, misses=1)`.

```text
assemble took 939.3 ms
_unpickle took 36.7 ms
cache miss (frankenstein OR hatter) AND alice NOT darcy "white rabbit"
search took 1.5 ms
cache hit (frankenstein OR hatter) AND alice NOT darcy "white rabbit"
search took 1.4 ms
cache CacheInfo(hits=1, misses=1, maxsize=256, currsize=1)
```

## Demo query

`(frankenstein OR hatter) AND alice NOT darcy "white rabbit"` with BM25.
Frankenstein and Pride drop out; only Alice matches the conjunction + phrase.
Snippets are ±80 characters; matched terms are in `[brackets]`.

| rank | score | title | snippet |
|------|-------|-------|---------|
| 1 | 8.1460 | alice_in_wonderland | …The Project Gutenberg eBook of [Alice]'s Adventures in Wonderland… |
