"""RAG Agent 共享工具（LangGraph 节点复用）。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

from app.config import settings
from app.llm import chat_completion
from app.memory.store import MemoryStore, get_memory_store
from app.prompts import RAG_AGENT_GRADE_SYSTEM, RAG_AGENT_PLAN_SYSTEM
from app.rag.ask import RetrievedSource, retrieve_sources


@dataclass
class AgentStep:
    phase: str
    message: str
    detail: dict | None = None
    agent: str = "researcher"

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "message": self.message,
            "detail": self.detail,
            "agent": self.agent,
        }


def strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_json_object(raw: str, fallback: dict) -> dict:
    try:
        data = json.loads(strip_json_fence(raw))
        return data if isinstance(data, dict) else fallback
    except Exception:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return fallback


def as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def source_key(source: RetrievedSource) -> tuple[str, int, int]:
    return (source.doc_id, source.char_start, source.char_end)


def merge_sources(*groups: list[RetrievedSource]) -> list[RetrievedSource]:
    seen: set[tuple[str, int, int]] = set()
    merged: list[RetrievedSource] = []
    for group in groups:
        for source in group:
            key = source_key(source)
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
    merged.sort(key=lambda s: s.score or 0.0, reverse=True)
    return [replace(source, index=i) for i, source in enumerate(merged, start=1)]


def summarize_sources(sources: list[RetrievedSource], limit: int = 8) -> str:
    if not sources:
        return "（暂无检索片段）"
    lines: list[str] = []
    for source in sources[:limit]:
        preview = source.text.replace("\n", " ").strip()
        if len(preview) > 160:
            preview = preview[:160] + "…"
        loc = f"第{source.page}页" if source.page else f"字符{source.char_start}-{source.char_end}"
        lines.append(f"[{source.index}] {source.filename} · {loc}：{preview}")
    if len(sources) > limit:
        lines.append(f"… 另有 {len(sources) - limit} 个片段")
    return "\n".join(lines)


def with_memory_context(base: str, memory_context: str) -> str:
    if not memory_context.strip():
        return base
    return f"{memory_context.strip()}\n\n---\n\n{base}"


async def plan_retrieval(question: str, memory_context: str = "") -> tuple[str, list[str]]:
    user_content = with_memory_context(f"用户问题：{question}", memory_context)
    raw = await chat_completion(RAG_AGENT_PLAN_SYSTEM, user_content)
    data = parse_json_object(
        raw,
        {"analysis": "直接检索用户问题", "search_queries": [question], "complexity": "simple"},
    )
    analysis = str(data.get("analysis") or "分析用户问题").strip()
    queries = as_str_list(data.get("search_queries"))
    if not queries:
        queries = [question]
    max_queries = settings.rag_agent_max_sub_queries
    return analysis, queries[:max_queries]


async def grade_context(
    question: str,
    sources: list[RetrievedSource],
    memory_context: str = "",
) -> tuple[bool, list[str], list[str]]:
    if not sources:
        return False, ["未检索到任何文献片段"], [question]

    base = (
        f"用户问题：{question}\n\n"
        f"已检索片段摘要（共 {len(sources)} 条）：\n{summarize_sources(sources)}"
    )
    raw = await chat_completion(RAG_AGENT_GRADE_SYSTEM, with_memory_context(base, memory_context))
    data = parse_json_object(
        raw,
        {"sufficient": True, "gaps": [], "follow_up_queries": []},
    )
    sufficient = bool(data.get("sufficient"))
    gaps = as_str_list(data.get("gaps"))
    follow_up = as_str_list(data.get("follow_up_queries"))[:2]
    return sufficient, gaps, follow_up


def retrieve_multi(
    queries: list[str],
    *,
    doc_ids: list[str] | None,
    top_k: int,
) -> list[RetrievedSource]:
    groups: list[list[RetrievedSource]] = []
    for query in queries:
        groups.append(retrieve_sources(query, doc_ids=doc_ids, top_k=top_k))
    return merge_sources(*groups)


def sources_to_dicts(sources: list[RetrievedSource]) -> list[dict]:
    return [s.to_dict() for s in sources]


def sources_from_dicts(items: list[dict]) -> list[RetrievedSource]:
    return [RetrievedSource.from_dict(item) for item in items]


async def persist_step(
    memory: MemoryStore | None,
    session_id: str | None,
    step: AgentStep,
) -> None:
    if not memory or not session_id:
        return
    memory.record_agent_step(session_id, step.to_dict())
    memory.save_checkpoint(
        session_id,
        phase=step.phase,
        message=step.message,
        payload={"step": step.to_dict()},
    )


def make_step(
    phase: str,
    message: str,
    detail: dict | None = None,
    agent: str = "researcher",
) -> dict:
    return AgentStep(phase=phase, message=message, detail=detail, agent=agent).to_dict()


async def persist_and_return_step(
    memory: MemoryStore,
    session_id: str | None,
    phase: str,
    message: str,
    detail: dict | None = None,
    agent: str = "researcher",
) -> dict:
    step = AgentStep(phase=phase, message=message, detail=detail, agent=agent)
    await persist_step(memory, session_id, step)
    return step.to_dict()
