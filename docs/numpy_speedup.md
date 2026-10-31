# NumPy scorer speedup

Scorer + top-k only (no snippet I/O). Median of repeats.

| Query | Docs matched | Lab 3 loop (ms) | NumPy (ms) | Speedup |
|---|---:|---:|---:|---:|
| common (	he) | 15 | 0.014 | 0.038 | 0.4x |
| rare (carroll) | 1 | 0.004 | 0.031 | 0.1x |
| 3-term (lice white rabbit) | 7 | 0.022 | 0.086 | 0.3x |
| synthetic-40k (common) | 40000 | 35.486 | 3.583 | 9.9x |

Largest speedup in this table: **9.9x**.

## Notes

- Tiny posting lists: NumPy call overhead can lose to a short Python loop.
- Long lists (synthetic 40k): ufuncs + argpartition win clearly.
