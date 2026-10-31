from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    bits = urlsplit(url.strip())
    host = (bits.hostname or "").lower()
    netloc = f"{host}:{bits.port}" if bits.port else host
    path = bits.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(bits.query, keep_blank_values=True)))
    return urlunsplit((bits.scheme.lower(), netloc, path, query, ""))
