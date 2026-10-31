from findex.vectors import split_passages


def test_split_passages_respects_width() -> None:
    text = ("word " * 400).strip()
    parts = split_passages(text, width=200, overlap=20)
    assert len(parts) > 1
    assert all(len(p) <= 220 for p in parts)
