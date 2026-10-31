from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from findex.corpus import read_text
from findex.models import Index


@dataclass(frozen=True)
class VectorBank:
    matrix: np.ndarray
    chunk_docs: np.ndarray
    model: str
    path: Path

    @property
    def dim(self) -> int:
        return int(self.matrix.shape[1]) if self.matrix.ndim == 2 else 0

    @property
    def n_chunks(self) -> int:
        return int(self.matrix.shape[0])


def split_passages(text: str, *, width: int = 750, overlap: int = 90) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= width:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + width)
        window = text[start:end]
        if end < len(text):
            for sep in ("\n\n", "\n", ". ", " "):
                at = window.rfind(sep)
                if at > width // 3:
                    end = start + at + len(sep)
                    window = text[start:end]
                    break
        piece = window.strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def walk_chunks(index: Index) -> Iterator[tuple[int, str]]:
    for doc_id in sorted(index.doc_meta):
        meta = index.doc_meta[doc_id]
        path = Path(meta.path)
        body = read_text(path) if path.is_file() else ""
        for chunk in split_passages(body):
            yield doc_id, chunk


def build_vector_bank(
    index: Index,
    *,
    model_name: str = "all-MiniLM-L6-v2",
    out: Path,
    batch_size: int = 32,
) -> VectorBank:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    doc_ids: list[int] = []
    texts: list[str] = []
    for doc_id, chunk in walk_chunks(index):
        doc_ids.append(doc_id)
        texts.append(chunk)
    if not texts:
        raise ValueError("no chunks to embed")

    parts: list[np.ndarray] = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("embed", total=len(texts))
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            emb = model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            parts.append(np.asarray(emb, dtype=np.float32))
            progress.advance(task, len(batch))

    matrix = np.vstack(parts).astype(np.float32)
    chunk_docs = np.asarray(doc_ids, dtype=np.int32)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, matrix)
    np.save(out.with_name(out.stem + "_doc_ids.npy"), chunk_docs)
    out.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "model": model_name,
                "n_chunks": int(matrix.shape[0]),
                "dim": int(matrix.shape[1]),
                "vectors": out.name,
                "doc_ids": out.stem + "_doc_ids.npy",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return VectorBank(matrix, chunk_docs, model_name, out)


def load_vector_bank(path: Path) -> VectorBank:
    path = Path(path)
    matrix = np.load(path)
    ids_path = path.with_name(path.stem + "_doc_ids.npy")
    meta_path = path.with_suffix(".meta.json")
    model = "all-MiniLM-L6-v2"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        model = meta.get("model", model)
        ids_name = meta.get("doc_ids")
        if ids_name:
            ids_path = path.with_name(ids_name)
    chunk_docs = np.load(ids_path)
    return VectorBank(matrix.astype(np.float32), chunk_docs.astype(np.int32), model, path)


def encode_query(text: str, model_name: str) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    vec = model.encode([text], normalize_embeddings=True, convert_to_numpy=True)
    return np.asarray(vec[0], dtype=np.float32)