from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findex.models import DocMeta, Index, Posting
from findex.web.config import AppConfig
from findex.web.factory import make_app
from findex.web.wiring import require_index


def _fixture_index(tmp_path: Path) -> Index:
    doc = tmp_path / "chapter.txt"
    doc.write_text("alice followed the white rabbit into the garden", encoding="utf-8")
    postings = {
        "alice": [Posting(0, 1, (0,))],
        "white": [Posting(0, 1, (3,))],
        "rabbit": [Posting(0, 1, (4,))],
        "garden": [Posting(0, 1, (7,))],
    }
    return Index(postings, {0: 8}, {0: DocMeta(str(doc), "chapter")})


@pytest.fixture
def client(tmp_path: Path):
    index = _fixture_index(tmp_path)
    app = make_app(AppConfig(index_path=tmp_path / "missing.pkl"), load_on_startup=False)
    app.dependency_overrides[require_index] = lambda: index
    with TestClient(app) as c:
        app.state.index = index
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_index():
    app = make_app(AppConfig(index_path=Path("missing.pkl")), load_on_startup=False)
    with TestClient(app) as c:
        yield c


def test_search_ok(client: TestClient) -> None:
    r = client.get("/search", params={"q": "alice", "k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "alice"
    assert body["total"] >= 1
    assert body["results"][0]["doc_id"] == 0
    assert "title" in body["results"][0]


def test_search_validation_422(client: TestClient) -> None:
    r = client.get("/search", params={"q": "alice", "k": "abc"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_document_404(client: TestClient) -> None:
    r = client.get("/docs/999")
    assert r.status_code == 404


def test_document_ok(client: TestClient) -> None:
    r = client.get("/docs/0")
    assert r.status_code == 200
    assert r.json()["title"] == "chapter"
    assert "alice" in r.json()["text"]


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_503_when_unloaded(client_no_index: TestClient) -> None:
    r = client_no_index.get("/health")
    assert r.status_code == 503


def test_stats(client: TestClient) -> None:
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["num_docs"] == 1
    assert body["vocab_size"] == 4


def test_ui_home(client: TestClient) -> None:
    r = client.get("/", params={"q": "alice"})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert b"findex" in r.content
    assert b"chapter" in r.content