__all__ = [
    "DEFAULT_USER_AGENT",
    "FetchOutcome",
    "PageRecord",
    "run_crawl",
    "pull",
]


def __getattr__(name: str):
    if name in ("DEFAULT_USER_AGENT", "FetchOutcome", "pull"):
        from findex.crawler import http_pull as mod

        return getattr(mod, name)
    if name in ("PageRecord", "run_crawl"):
        from findex.crawler import spider as mod

        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
