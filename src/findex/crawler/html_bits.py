from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


class _PageScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.hrefs: list[str] = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        low = tag.lower()
        if low in ("script", "style", "noscript"):
            self._skip += 1
            return
        if self._skip:
            return
        if low == "title":
            self._in_title = True
        if low == "a":
            href = dict(attrs).get("href") or ""
            href = href.strip()
            if href and not href.startswith(("#", "mailto:", "javascript:", "tel:")):
                self.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if low in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
            return
        if low == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            chunk = data.strip()
            if chunk:
                self.text_parts.append(chunk)


def scan_html(html: str | bytes, base_url: str) -> tuple[str, str, list[str]]:
    raw = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    scan = _PageScan()
    scan.feed(raw)
    scan.close()
    title = " ".join(p.strip() for p in scan.title_parts).strip()
    text = " ".join(scan.text_parts)
    links: list[str] = []
    for href in scan.hrefs:
        absolute = urljoin(base_url, href)
        if urlsplit(absolute).scheme.lower() in ("http", "https"):
            links.append(absolute)
    return title, text, links
