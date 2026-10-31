from __future__ import annotations

import functools
import logging
from time import perf_counter

log = logging.getLogger("findex")


def timed(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        started = perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            ms = (perf_counter() - started) * 1000
            log.debug("%s took %.1f ms", fn.__name__, ms)

    return wrapper
