from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from time import perf_counter
from typing import cast

log = logging.getLogger("findex")


def timed[F: Callable[..., object]](fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        started = perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            ms = (perf_counter() - started) * 1000
            log.debug("%s took %.1f ms", fn.__name__, ms)

    return cast(F, wrapper)
