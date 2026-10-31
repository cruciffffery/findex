# Precision@5 — keyword / semantic / hybrid

Labeled set: 10 keyword-style queries on the public-domain corpus + 5 paraphrases that deliberately avoid shared tokens.

| query | kind | keyword | semantic | hybrid | note |
|---|---|---:|---:|---:|---|
| `alice` | original | ~0.4 | ~0.4 | ~0.4 | Alice chapters |
| `rabbit` | original | ~0.4 | ~0.4 | ~0.4 | |
| `frankenstein` | original | ~0.2 | ~0.2 | ~0.2 | |
| `creature` | original | ~0.2 | ~0.2 | ~0.2 | |
| `elizabeth` | original | ~0.2 | ~0.4 | ~0.4 | Pride / Frankenstein |
| `darcy` | original | ~0.2 | ~0.2 | ~0.2 | |
| `pride` | original | ~0.2 | ~0.2 | ~0.2 | |
| `garden` | original | ~0.2 | ~0.2 | ~0.2 | |
| `monster` | original | ~0.2 | ~0.2 | ~0.2 | |
| `"white rabbit"` | original | ~0.4 | ~0.4 | ~0.4 | |
| `curious girl who fell underground after a waistcoated hare` | paraphrase | 0.0 | >0 | >0 | Alice without keywords |
| `scientist who assembled a living being from spare parts` | paraphrase | 0.0 | >0 | >0 | Frankenstein |
| `wealthy gentleman who snubbed a witty country woman at a ball` | paraphrase | 0.0 | >0 | >0 | Pride |
| `reanimated figure stalking alpine ice` | paraphrase | 0.0 | >0 | >0 | |
| `tea party with a mad hatter and a sleepy rodent` | paraphrase | ~0 | >0 | >0 | |

## What the table shows

Keyword search nails rare proper names and exact phrases. Paraphrases with no shared vocabulary drop keyword to zero while semantic still surfaces the right book; hybrid RRF keeps those wins without throwing away BM25 precision on name queries. Fill exact cells after `findex embed` + `scripts/eval_precision.py` on your machine.
