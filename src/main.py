from __future__ import annotations

from findex.index import DEFAULT_CORPUS, DEFAULT_OUT, build_and_save, memory_study, positions_cost
from findex.search import bench
from findex.search import main as run_search
from findex.store import timed_save_load


def main() -> None:
    index = build_and_save(DEFAULT_CORPUS, DEFAULT_OUT)
    timed_save_load(index, DEFAULT_OUT, DEFAULT_OUT.with_suffix(".json"))
    positions_cost()
    memory_study()
    bench(index)
    run_search([str(DEFAULT_OUT), "elizabeth darcy", "--engine", "merge"])


if __name__ == "__main__":
    main()
