from __future__ import annotations

from pathlib import Path

from findex.corpus import DocumentWalker
from findex.measure import EagerPass, StreamingPass
from findex.tokenize import WordStream
from findex.types import CorpusMetrics

CORPUS_DIR = Path(__file__).resolve().parent / "resources"


def report(title: str, metrics: CorpusMetrics) -> None:
    print(
        f"\n[{title}] "
        f"docs={metrics.document_count} "
        f"tokens={metrics.token_count} "
        f"vocab={metrics.vocabulary} "
        f"time={metrics.seconds:.4f}s "
        f"peak={metrics.peak_memory_kib:.1f}KiB"
    )
    for term, freq in metrics.frequent_terms:
        print(f"  {term}\t{freq}")


def main() -> None:
    walker = DocumentWalker(CORPUS_DIR)
    stream = WordStream()
    report("streaming", StreamingPass(walker, stream).run())
    report("eager", EagerPass(walker, stream).run())


if __name__ == "__main__":
    main()
