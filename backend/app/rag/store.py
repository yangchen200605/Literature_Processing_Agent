"""Chroma 向量库与文档注册表。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import chromadb

from app.config import settings
from app.rag.chunk import TextChunk

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chroma"
REGISTRY_FILE = DATA_DIR / "docs.json"
COLLECTION_NAME = "literature_chunks"

_client: chromadb.PersistentClient | None = None
_collection = None


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_collection():
    global _client, _collection
    if _collection is None:
        _ensure_data_dir()
        _client = chromadb.PersistentClient(path=str(DATA_DIR / "db"))
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _load_registry() -> dict[str, dict]:
    _ensure_data_dir()
    if not REGISTRY_FILE.is_file():
        return {}
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_registry(registry: dict[str, dict]) -> None:
    _ensure_data_dir()
    REGISTRY_FILE.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_document(doc_id: str, filename: str, chunks: list[TextChunk]) -> dict:
    coll = get_collection()
    delete_document(doc_id, update_registry=False)

    if not chunks:
        raise ValueError("文本过短，无法建立索引")

    ids = [chunk.chunk_id for chunk in chunks]
    documents = [chunk.text for chunk in chunks]
    metadatas = [
        {
            "doc_id": doc_id,
            "filename": filename,
            "chunk_index": chunk.index,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "page": chunk.page if chunk.page is not None else -1,
        }
        for chunk in chunks
    ]

    batch_size = 100
    for i in range(0, len(ids), batch_size):
        coll.add(
            ids=ids[i : i + batch_size],
            documents=documents[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )

    info = {
        "doc_id": doc_id,
        "filename": filename,
        "chunk_count": len(chunks),
        "char_count": sum(len(chunk.text) for chunk in chunks),
        "indexed_at": time.time(),
    }
    registry = _load_registry()
    registry[doc_id] = info
    _save_registry(registry)
    return info


def delete_document(doc_id: str, *, update_registry: bool = True) -> None:
    coll = get_collection()
    try:
        coll.delete(where={"doc_id": doc_id})
    except Exception:
        pass
    if update_registry:
        registry = _load_registry()
        registry.pop(doc_id, None)
        _save_registry(registry)


def list_documents() -> list[dict]:
    docs = list(_load_registry().values())
    docs.sort(key=lambda item: float(item.get("indexed_at") or 0), reverse=True)
    return docs


def query_chunks(
    question: str,
    *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
) -> list[dict]:
    coll = get_collection()
    k = top_k or settings.rag_top_k
    where = {"doc_id": {"$in": doc_ids}} if doc_ids else None

    result = coll.query(
        query_texts=[question],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    items: list[dict] = []
    for doc_text, meta, distance in zip(documents, metadatas, distances, strict=False):
        if not doc_text or not meta:
            continue
        page = meta.get("page")
        items.append(
            {
                "doc_id": str(meta.get("doc_id") or ""),
                "filename": str(meta.get("filename") or "未命名文献"),
                "chunk_index": int(meta.get("chunk_index") or 0),
                "char_start": int(meta.get("char_start") or 0),
                "char_end": int(meta.get("char_end") or 0),
                "page": int(page) if page is not None and int(page) >= 0 else None,
                "text": doc_text,
                "score": 1.0 - float(distance) if distance is not None else None,
            }
        )
    return items
