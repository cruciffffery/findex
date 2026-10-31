from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

from findex.corpus import DocumentWalker
from findex.deco import timed
from findex.models import DocMeta, Index, Posting
from findex.tokenize import WordStream

log = logging.getLogger(__name__)

DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "resources"
WITH_POSITIONS_DEFAULT = True


@timed
def assemble(
    walker: DocumentWalker,
    words: WordStream,
    *,
    with_positions: bool = False,
    limit: int | None = None,
    on_doc: Callable[[], None] | None = None,
) -> Index:
    buckets: dict[str, list[Posting]] = defaultdict(list)
    lengths: dict[int, int] = {}
    meta: dict[int, DocMeta] = {}

    for doc_id, path, text in walker.iter_docs():
        if limit is not None and doc_id >= limit:
            break
        freq: Counter[str] = Counter()
        offsets: dict[str, list[int]] | None = defaultdict(list) if with_positions else None
        n_tokens = 0
        for offset, term in enumerate(words.tokenize(text)):
            freq[term] += 1
            n_tokens += 1
            if offsets is not None:
                offsets[term].append(offset)

        lengths[doc_id] = n_tokens
        meta[doc_id] = DocMeta(str(path), path.stem)
        for term, tf in freq.items():
            pos = tuple(offsets[term]) if offsets is not None else ()
            buckets[term].append(Posting(doc_id, tf, pos))
        if on_doc is not None:
            on_doc()

    # contract: each posting list sorted by doc_id
    for hits in buckets.values():
        hits.sort(key=lambda p: p.doc_id)

    index = Index(dict(buckets), lengths, meta)
    log.info("built %r tokens=%d", index, sum(lengths.values()))
    return index


def build_corpus(
    corpus: Path,
    *,
    with_positions: bool = WITH_POSITIONS_DEFAULT,
    limit: int | None = None,
    on_doc: Callable[[], None] | None = None,
) -> Index:
    return assemble(
        DocumentWalker(corpus),
        WordStream(),
        with_positions=with_positions,
        limit=limit,
        on_doc=on_doc,
    )
