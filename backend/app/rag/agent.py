"""Agentic RAG：规划 → 多路检索 → 评估 → 补充检索 → 合成回答。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable, Awaitable
from dataclasses import dataclass, replace

from app.config import settings
from app.llm import chat_completion, chat_completion_stream
from app.prompts import RAG_AGENT_GRADE_SYSTEM, RAG_AGENT_PLAN_SYSTEM, RAG_QA_SYSTEM
from app.rag.ask import RetrievedSource, build_rag_prompt, retrieve_sources


@dataclass
class AgentStep:
    phase: str
    message: str
    detail: dict | None = None

    def to_dict(self) -> dict:
        return {"phase": self.phase, "message": self.message, "detail": self.detail}


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_json_object(raw: str, fallback: dict) -> dict:
    try:
        data = json.loads(_strip_json_fence(raw))
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


def _as_str_list(value) -> list[str]:
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


def _source_key(source: RetrievedSource) -> tuple[str, int, int]:
    return (source.doc_id, source.char_start, source.char_end)


def _merge_sources(*groups: list[RetrievedSource]) -> list[RetrievedSource]:
    seen: set[tuple[str, int, int]] = set()
    merged: list[RetrievedSource] = []
    for group in groups:
        for source in group:
            key = _source_key(source)
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
    merged.sort(key=lambda s: s.score or 0.0, reverse=True)
    return [replace(source, index=i) for i, source in enumerate(merged, start=1)]


def _summarize_sources(sources: list[RetrievedSource], limit: int = 8) -> str:
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


async def _plan_retrieval(question: str) -> tuple[str, list[str]]:
    raw = await chat_completion(
        RAG_AGENT_PLAN_SYSTEM,
        f"用户问题：{question}",
    )
    data = _parse_json_object(
        raw,
        {"analysis": "直接检索用户问题", "search_queries": [question], "complexity": "simple"},
    )
    analysis = str(data.get("analysis") or "分析用户问题").strip()
    queries = _as_str_list(data.get("search_queries"))
    if not queries:
        queries = [question]
    max_queries = settings.rag_agent_max_sub_queries
    return analysis, queries[:max_queries]


async def _grade_context(question: str, sources: list[RetrievedSource]) -> tuple[bool, list[str], list[str]]:
    if not sources:
        return False, ["未检索到任何文献片段"], [question]

    raw = await chat_completion(
        RAG_AGENT_GRADE_SYSTEM,
        (
            f"用户问题：{question}\n\n"
            f"已检索片段摘要（共 {len(sources)} 条）：\n{_summarize_sources(sources)}"
        ),
    )
    data = _parse_json_object(
        raw,
        {"sufficient": True, "gaps": [], "follow_up_queries": []},
    )
    sufficient = bool(data.get("sufficient"))
    gaps = _as_str_list(data.get("gaps"))
    follow_up = _as_str_list(data.get("follow_up_queries"))[:2]
    return sufficient, gaps, follow_up


def _retrieve_multi(
    queries: list[str],
    *,
    doc_ids: list[str] | None,
    top_k: int,
) -> list[RetrievedSource]:
    groups: list[list[RetrievedSource]] = []
    for query in queries:
        groups.append(
            retrieve_sources(query, doc_ids=doc_ids, top_k=top_k)
        )
    return _merge_sources(*groups)


async def run_agentic_rag(
    question: str,
    *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
    on_step: Callable[[AgentStep], Awaitable[None]] | None = None,
) -> tuple[list[AgentStep], list[RetrievedSource], str]:
    """执行 Agentic RAG，返回步骤、最终片段与回答 prompt。"""
    cleaned = (question or "").strip()
    if not cleaned:
        raise ValueError("问题不能为空")

    k = top_k or settings.rag_top_k
    steps: list[AgentStep] = []
    used_queries: set[str] = set()

    async def emit(phase: str, message: str, detail: dict | None = None) -> None:
        step = AgentStep(phase=phase, message=message, detail=detail)
        steps.append(step)
        if on_step:
            await on_step(step)

    analysis, plan_queries = await _plan_retrieval(cleaned)
    for q in plan_queries:
        used_queries.add(q.strip().lower())
    await emit(
        "plan",
        f"已规划 {len(plan_queries)} 条检索路径",
        {"analysis": analysis, "search_queries": plan_queries},
    )

    sources = _retrieve_multi(plan_queries, doc_ids=doc_ids, top_k=k)
    await emit(
        "retrieve",
        f"首轮检索完成，合并 {len(sources)} 个片段",
        {"queries": plan_queries, "source_count": len(sources)},
    )

    for round_idx in range(settings.rag_agent_max_iterations):
        sufficient, gaps, follow_up = await _grade_context(cleaned, sources)
        if sufficient:
            await emit(
                "grade",
                "上下文评估：信息充足，开始生成回答",
                {"sufficient": True, "round": round_idx + 1},
            )
            break

        fresh_queries = [q for q in follow_up if q.strip().lower() not in used_queries]
        if not fresh_queries:
            await emit(
                "grade",
                "上下文评估：仍不完整，但无新的检索方向",
                {"sufficient": False, "gaps": gaps, "round": round_idx + 1},
            )
            break

        for q in fresh_queries:
            used_queries.add(q.strip().lower())

        await emit(
            "grade",
            f"上下文评估：信息不足，发起第 {round_idx + 2} 轮补充检索",
            {"sufficient": False, "gaps": gaps, "follow_up_queries": fresh_queries},
        )

        extra = _retrieve_multi(fresh_queries, doc_ids=doc_ids, top_k=k)
        before = len(sources)
        sources = _merge_sources(sources, extra)
        await emit(
            "retrieve",
            f"补充检索新增 {len(sources) - before} 个片段（共 {len(sources)} 个）",
            {"queries": fresh_queries, "source_count": len(sources)},
        )
    else:
        await emit("grade", "已达最大检索轮次，基于现有片段作答", {"sufficient": False})

    await emit("answer", "正在合成最终回答", {"source_count": len(sources)})
    return steps, sources, build_rag_prompt(cleaned, sources)


async def stream_agentic_answer(
    question: str,
    *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
) -> AsyncIterator[dict]:
    """产出 Agent 事件 dict，最后以 type=answer_delta 流式输出回答。"""
    step_queue: list[AgentStep] = []

    async def collect(step: AgentStep) -> None:
        step_queue.append(step)

    steps, sources, user_prompt = await run_agentic_rag(
        question,
        doc_ids=doc_ids,
        top_k=top_k,
        on_step=collect,
    )

    for step in step_queue:
        yield {"type": "agent_step", "step": step.to_dict()}

    yield {
        "type": "sources",
        "sources": [source.to_dict() for source in sources],
        "steps": [step.to_dict() for step in steps],
    }

    yield {"type": "start", "task": "ask"}
    async for delta in chat_completion_stream(RAG_QA_SYSTEM, user_prompt):
        yield {"type": "delta", "text": delta}
    yield {"type": "done", "task": "ask"}
