"""文献入库：分块并写入向量库。"""

from __future__ import annotations

import hashlib

from app.config import settings
from app.rag.chunk import chunk_text
from app.rag.store import add_document
from app.storage import get_meta, get_text


def make_doc_id(text: str, file_id: str | None = None) -> str:
    if file_id:
        return file_id
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"paste_{digest}"


def index_text(
    text: str,
    *,
    doc_id: str | None = None,
    filename: str | None = None,
) -> dict:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("文本不能为空")

    resolved_id = doc_id or make_doc_id(cleaned)
    resolved_name = filename or "粘贴文本"
    chunks = chunk_text(
        cleaned,
        chunk_size=settings.rag_chunk_size,
        overlap=settings.rag_chunk_overlap,
        file_id=resolved_id,
    )
    return add_document(resolved_id, resolved_name, chunks)


def index_from_file_id(file_id: str) -> dict:
    text = get_text(file_id)
    if not text:
        raise ValueError("上传文件不存在、已过期或未提取到文本")

    meta = get_meta(file_id) or {}
    filename = str(meta.get("filename") or file_id)
    return index_text(text, doc_id=file_id, filename=filename)
