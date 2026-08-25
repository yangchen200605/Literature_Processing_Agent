"""检索增强问答。"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.rag.store import query_chunks


@dataclass
class RetrievedSource:
    index: int
    doc_id: str
    filename: str
    text: str
    page: int | None = None
    char_start: int = 0
    char_end: int = 0
    score: float | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "doc_id": self.doc_id,
            "filename": self.filename,
            "text": self.text,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "score": self.score,
        }


def retrieve_sources(
    question: str,
    *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
) -> list[RetrievedSource]:
    hits = query_chunks(question, doc_ids=doc_ids or None, top_k=top_k)
    sources: list[RetrievedSource] = []
    for idx, hit in enumerate(hits, start=1):
        sources.append(
            RetrievedSource(
                index=idx,
                doc_id=hit["doc_id"],
                filename=hit["filename"],
                text=hit["text"],
                page=hit.get("page"),
                char_start=hit.get("char_start") or 0,
                char_end=hit.get("char_end") or 0,
                score=hit.get("score"),
            )
        )
    return sources


def build_rag_prompt(question: str, sources: list[RetrievedSource]) -> str:
    if not sources:
        return (
            f"用户问题：{question}\n\n"
            "注意：未检索到任何文献片段。请说明需要先上传并索引文献，且当前知识库中可能没有相关内容。"
        )

    context_parts: list[str] = []
    for source in sources:
        if source.page:
            location = f"第{source.page}页"
        else:
            location = f"字符 {source.char_start}-{source.char_end}"
        context_parts.append(
            f"[{source.index}] （{source.filename} · {location}）\n{source.text}"
        )

    context = "\n\n".join(context_parts)
    return (
        "以下是从文献中检索到的相关片段：\n\n"
        f"{context}\n\n"
        "---\n\n"
        f"用户问题：{question}\n\n"
        "请基于以上片段作答；引用片段时用 [1]、[2] 标注编号。"
    )


def ask_question(
    question: str,
    *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
) -> tuple[list[RetrievedSource], str]:
    """返回检索片段与组装好的用户 prompt。"""
    cleaned = (question or "").strip()
    if not cleaned:
        raise ValueError("问题不能为空")

    k = top_k or settings.rag_top_k
    sources = retrieve_sources(cleaned, doc_ids=doc_ids or None, top_k=k)
    return sources, build_rag_prompt(cleaned, sources)
