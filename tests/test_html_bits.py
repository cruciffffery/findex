from __future__ import annotations

from findex.crawler.html_bits import scan_html


def test_scan_html_title_text_links() -> None:
    html = (
        "<html><head><title>Hi</title></head>"
        '<body>Hello <a href="/next">n</a><script>x</script></body></html>'
    )
    title, text, links = scan_html(html, "https://ex.com/")
    assert title == "Hi"
    assert "Hello" in text
    assert "x" not in text
    assert links == ["https://ex.com/next"]