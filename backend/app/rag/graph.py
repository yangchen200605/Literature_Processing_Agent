"""LangGraph Agentic RAG：规划 → 检索 → 评估 → HITL → 作答。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.config import settings
from app.llm import chat_completion_stream
from app.memory.store import MemoryStore, get_memory_store
from app.prompts import RAG_QA_SYSTEM
from app.rag.ask import RetrievedSource, build_rag_prompt
from app.rag.common import (
    grade_context,
    merge_sources,
    persist_and_return_step,
    plan_retrieval,
    retrieve_multi,
    sources_from_dicts,
    sources_to_dicts,
    with_memory_context,
)

CHECKPOINT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "langgraph"
CHECKPOINT_DB = CHECKPOINT_DIR / "checkpoints.db"

_checkpointer: MemorySaver | None = None
_compiled_graph = None


def _merge_steps(existing: list[dict], new: list[dict]) -> list[dict]:
    return existing + new


class RagGraphState(TypedDict, total=False):
    question: str
    doc_ids: list[str]
    top_k: int
    session_id: str | None
    memory_context: str
    save_to_long_term: bool
    human_in_the_loop: bool
    analysis: str
    plan_queries: list[str]
    used_queries: list[str]
    sources: list[dict]
    steps: Annotated[list[dict], _merge_steps]
    grade_round: int
    sufficient: bool
    gaps: list[str]
    pending_queries: list[str]
    user_prompt: str
    feedback: str | None
    cancelled: bool
    cancel_message: str
    _plan_edited: bool
    _plan_edit_feedback: str | None


# --- 节点 ---


async def plan_node(state: RagGraphState) -> dict:
    memory = get_memory_store()
    session_id = state.get("session_id")
    question = state["question"]
    memory_context = state.get("memory_context") or ""

    analysis, plan_queries = await plan_retrieval(question, memory_context)
    used = list(state.get("used_queries") or [])
    for q in plan_queries:
        key = q.strip().lower()
        if key not in used:
            used.append(key)

    hitl = bool(state.get("human_in_the_loop"))
    step = await persist_and_return_step(
        memory,
        session_id,
        "plan",
        f"已规划 {len(plan_queries)} 条检索路径{'，等待人工确认' if hitl else ''}",
        {"analysis": analysis, "search_queries": plan_queries},
    )
    return {
        "analysis": analysis,
        "plan_queries": plan_queries,
        "used_queries": used,
        "steps": [step],
    }


def plan_review_node(state: RagGraphState) -> dict:
    if not state.get("human_in_the_loop"):
        return {}

    response = interrupt(
        {
            "stage": "plan_review",
            "message": "请确认或修改检索计划后再继续",
            "analysis": state.get("analysis"),
            "search_queries": state.get("plan_queries") or [],
            "session_id": state.get("session_id"),
        }
    )
    action = str(response.get("action") or "approve").strip().lower()
    feedback = response.get("feedback")

    if action == "reject":
        return {
            "cancelled": True,
            "cancel_message": str(feedback or "用户已取消"),
        }

    updates: dict = {}
    if feedback:
        updates["feedback"] = str(feedback)

    if action in {"edit", "edit_queries"}:
        edited = [q.strip() for q in (response.get("edited_queries") or []) if q.strip()]
        if not edited:
            raise ValueError("检索查询不能为空")
        updates["plan_queries"] = edited
        updates["_plan_edited"] = True
        updates["_plan_edit_feedback"] = feedback
    elif action != "approve":
        raise ValueError("plan_review 阶段仅支持 approve、edit_queries 或 reject")

    return updates


async def plan_edit_emit_node(state: RagGraphState) -> dict:
    if not state.get("_plan_edited"):
        return {}
    memory = get_memory_store()
    session_id = state.get("session_id")
    queries = state.get("plan_queries") or []
    step = await persist_and_return_step(
        memory,
        session_id,
        "plan",
        f"人工修改检索计划为 {len(queries)} 条查询",
        {
            "search_queries": queries,
            "human_edited": True,
            "feedback": state.get("_plan_edit_feedback"),
        },
    )
    return {"steps": [step]}


async def retrieve_initial_node(state: RagGraphState) -> dict:
    memory = get_memory_store()
    session_id = state.get("session_id")
    queries = state.get("plan_queries") or []
    top_k = int(state.get("top_k") or settings.rag_top_k)
    doc_ids = state.get("doc_ids") or None

    sources = retrieve_multi(queries, doc_ids=doc_ids, top_k=top_k)
    step = await persist_and_return_step(
        memory,
        session_id,
        "retrieve",
        f"首轮检索完成，合并 {len(sources)} 个片段",
        {"queries": queries, "source_count": len(sources)},
    )
    return {
        "sources": sources_to_dicts(sources),
        "steps": [step],
        "grade_round": 0,
    }


async def grade_node(state: RagGraphState) -> dict:
    memory = get_memory_store()
    session_id = state.get("session_id")
    question = state["question"]
    memory_context = state.get("memory_context") or ""
    sources = sources_from_dicts(state.get("sources") or [])
    grade_round = int(state.get("grade_round") or 0) + 1
    used = list(state.get("used_queries") or [])
    hitl = bool(state.get("human_in_the_loop"))

    sufficient, gaps, follow_up = await grade_context(question, sources, memory_context)
    fresh = [q for q in follow_up if q.strip().lower() not in {u.lower() for u in used}]

    if sufficient:
        msg = "上下文评估：信息充足，等待人工确认后作答" if hitl else "上下文评估：信息充足，开始生成回答"
        detail = {"sufficient": True, "round": grade_round}
        pending: list[str] = []
    elif not fresh:
        msg = "上下文评估：仍不完整，但无新的检索方向"
        detail = {"sufficient": False, "gaps": gaps, "round": grade_round}
        pending = []
    elif grade_round >= settings.rag_agent_max_iterations:
        msg = "已达最大检索轮次，等待人工确认" if hitl else "已达最大检索轮次，基于现有片段作答"
        detail = {"sufficient": False, "round": grade_round}
        pending = []
    else:
        for q in fresh:
            used.append(q.strip().lower())
        msg = f"上下文评估：信息不足，发起第 {grade_round + 1} 轮补充检索"
        detail = {"sufficient": False, "gaps": gaps, "follow_up_queries": fresh, "round": grade_round}
        pending = fresh

    step = await persist_and_return_step(
        memory, session_id, "grade", msg, detail,
    )
    return {
        "sufficient": sufficient,
        "gaps": gaps,
        "pending_queries": pending,
        "used_queries": used,
        "grade_round": grade_round,
        "steps": [step],
    }


async def retrieve_more_node(state: RagGraphState) -> dict:
    memory = get_memory_store()
    session_id = state.get("session_id")
    queries = state.get("pending_queries") or []
    top_k = int(state.get("top_k") or settings.rag_top_k)
    doc_ids = state.get("doc_ids") or None
    existing = sources_from_dicts(state.get("sources") or [])

    extra = retrieve_multi(queries, doc_ids=doc_ids, top_k=top_k)
    before = len(existing)
    merged = merge_sources(existing, extra)
    step = await persist_and_return_step(
        memory,
        session_id,
        "retrieve",
        f"补充检索新增 {len(merged) - before} 个片段（共 {len(merged)} 个）",
        {"queries": queries, "source_count": len(merged)},
    )
    return {
        "sources": sources_to_dicts(merged),
        "pending_queries": [],
        "steps": [step],
    }


async def answer_review_node(state: RagGraphState) -> dict:
    if not state.get("human_in_the_loop"):
        return {}

    memory = get_memory_store()
    session_id = state.get("session_id")
    top_k = int(state.get("top_k") or settings.rag_top_k)
    doc_ids = state.get("doc_ids") or None
    sources = sources_from_dicts(state.get("sources") or [])
    all_steps: list[dict] = []

    while True:
        response = interrupt(
            {
                "stage": "answer_review",
                "message": "请确认引用片段是否充分，确认后将生成回答",
                "source_count": len(sources),
                "session_id": state.get("session_id"),
            }
        )
        action = str(response.get("action") or "approve").strip().lower()
        feedback = response.get("feedback")

        if action == "reject":
            return {
                "cancelled": True,
                "cancel_message": str(feedback or "用户已取消"),
                "sources": sources_to_dicts(sources),
                "steps": all_steps,
            }

        if action == "refine":
            queries = [q.strip() for q in (response.get("extra_queries") or []) if q.strip()]
            if not queries:
                raise ValueError("补充检索查询不能为空")
            step = await persist_and_return_step(
                memory,
                session_id,
                "retrieve",
                f"人工要求补充检索 {len(queries)} 条查询",
                {"queries": queries, "human_refine": True, "feedback": feedback},
            )
            all_steps.append(step)

            extra = retrieve_multi(queries, doc_ids=doc_ids, top_k=top_k)
            sources = merge_sources(sources, extra)
            step2 = await persist_and_return_step(
                memory,
                session_id,
                "retrieve",
                f"补充检索后共 {len(sources)} 个片段，请再次确认",
                {"queries": queries, "source_count": len(sources)},
            )
            all_steps.append(step2)
            continue

        if action != "approve":
            raise ValueError("answer_review 阶段支持 approve、refine 或 reject")

        updates: dict = {
            "sources": sources_to_dicts(sources),
            "steps": all_steps,
        }
        if feedback:
            updates["feedback"] = str(feedback)
        return updates


async def prepare_answer_node(state: RagGraphState) -> dict:
    if state.get("cancelled"):
        return {}

    memory = get_memory_store()
    session_id = state.get("session_id")
    question = state["question"]
    memory_context = state.get("memory_context") or ""
    feedback = state.get("feedback")
    sources = sources_from_dicts(state.get("sources") or [])
    hitl = bool(state.get("human_in_the_loop"))

    user_prompt = build_rag_prompt(question, sources)
    if memory_context.strip():
        user_prompt = with_memory_context(user_prompt, memory_context)
    if feedback and str(feedback).strip():
        user_prompt = with_memory_context(user_prompt, f"用户补充说明：{feedback.strip()}")

    msg = "人工已确认证据，Analyst 开始作答" if hitl else "Researcher 已完成证据搜集，交由 Analyst 作答"
    step = await persist_and_return_step(
        memory,
        session_id,
        "answer",
        msg,
        {"source_count": len(sources)},
        agent="analyst",
    )
    return {"user_prompt": user_prompt, "steps": [step]}


# --- 路由 ---


def route_after_plan_review(state: RagGraphState) -> Literal["plan_edit_emit", "__end__"]:
    if state.get("cancelled"):
        return "__end__"
    return "plan_edit_emit"


def route_after_grade(state: RagGraphState) -> Literal["retrieve_more", "answer_review"]:
    if state.get("sufficient"):
        return "answer_review"
    pending = state.get("pending_queries") or []
    if not pending:
        return "answer_review"
    if int(state.get("grade_round") or 0) >= settings.rag_agent_max_iterations:
        return "answer_review"
    return "retrieve_more"


def route_after_answer_review(state: RagGraphState) -> Literal["prepare_answer", "__end__"]:
    if state.get("cancelled"):
        return "__end__"
    return "prepare_answer"


# --- 构图 ---


def _get_checkpointer() -> MemorySaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
    return _checkpointer


def build_rag_graph(checkpointer: MemorySaver | None = None):
    graph = StateGraph(RagGraphState)

    graph.add_node("plan", plan_node)
    graph.add_node("plan_review", plan_review_node)
    graph.add_node("plan_edit_emit", plan_edit_emit_node)
    graph.add_node("retrieve_initial", retrieve_initial_node)
    graph.add_node("grade", grade_node)
    graph.add_node("retrieve_more", retrieve_more_node)
    graph.add_node("answer_review", answer_review_node)
    graph.add_node("prepare_answer", prepare_answer_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "plan_review")
    graph.add_conditional_edges("plan_review", route_after_plan_review)
    graph.add_edge("plan_edit_emit", "retrieve_initial")
    graph.add_edge("retrieve_initial", "grade")
    graph.add_conditional_edges("grade", route_after_grade)
    graph.add_edge("retrieve_more", "grade")
    graph.add_conditional_edges("answer_review", route_after_answer_review)
    graph.add_edge("prepare_answer", END)

    cp = checkpointer or _get_checkpointer()
    return graph.compile(checkpointer=cp)


def get_rag_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_rag_graph()
    return _compiled_graph


# --- 流式适配（保持原有 SSE 事件格式）---


def _build_initial_state(
    question: str,
    *,
    doc_ids: list[str] | None,
    top_k: int,
    session_id: str | None,
    memory_context: str,
    save_to_long_term: bool,
    human_in_the_loop: bool,
    memory: MemoryStore,
) -> dict:
    return {
        "question": question.strip(),
        "doc_ids": list(doc_ids or []),
        "top_k": top_k,
        "session_id": session_id,
        "memory_context": memory_context,
        "save_to_long_term": save_to_long_term,
        "human_in_the_loop": human_in_the_loop,
        "steps": [],
        "used_queries": [],
        "sources": [],
        "grade_round": 0,
        "cancelled": False,
    }


def _resolve_session(
    memory: MemoryStore,
    question: str,
    session_id: str | None,
    doc_ids: list[str] | None,
) -> tuple[str | None, list[str] | None]:
    if not session_id:
        return doc_ids, session_id
    sess = memory.get_session(session_id)
    if not sess:
        raise ValueError("session_id 无效或已过期")
    if doc_ids:
        sess.doc_ids = list(doc_ids)
        memory.short.save_session(sess)
    elif sess.doc_ids:
        doc_ids = sess.doc_ids
    return doc_ids, session_id


async def _stream_graph(
    graph_input,
    thread_id: str,
) -> AsyncIterator[dict]:
    graph = get_rag_graph()
    config = {"configurable": {"thread_id": thread_id}}

    async for chunk in graph.astream(graph_input, config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            for item in chunk["__interrupt__"]:
                yield {"type": "interrupt", "value": item.value, "run_id": thread_id}
            continue

        for _node, update in chunk.items():
            if not isinstance(update, dict):
                continue
            for step in update.get("steps") or []:
                yield {"type": "agent_step", "step": step}


async def _finalize_turn(
    memory: MemoryStore,
    state: dict,
    *,
    question: str,
    full_answer: str,
    session_id: str | None,
    doc_ids: list[str] | None,
    save_to_long_term: bool,
) -> None:
    sources = sources_from_dicts(state.get("sources") or [])
    steps = state.get("steps") or []
    if not session_id:
        return
    sess = memory.append_turn(
        session_id,
        question=question,
        answer=full_answer,
        doc_ids=doc_ids,
        source_count=len(sources),
        agent_trace=steps,
    )
    memory.save_checkpoint(
        session_id,
        phase="turn_complete",
        message="本轮问答已完成",
        payload={
            "question": question,
            "answer_preview": full_answer[:500],
            "source_count": len(sources),
        },
    )
    if sess and save_to_long_term and full_answer.strip():
        memory.save_qa_summary(
            question=question,
            answer=full_answer,
            doc_ids=doc_ids or sess.doc_ids,
            session_id=session_id,
            source_count=len(sources),
        )


def cleanup_expired_graph_threads() -> None:
    """清理过期的 LangGraph checkpoint（替代原 HITL JSON TTL）。"""
    if not CHECKPOINT_DB.is_file():
        return
    # SqliteSaver 无按 thread 列出 API；依赖 LangGraph 内部表结构较脆弱，暂保留文件累积。
    # 完成时可 delete_thread；此处仅确保目录存在。
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


async def stream_agentic_answer(
    question: str,
    *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
    session_id: str | None = None,
    save_to_long_term: bool = True,
    memory: MemoryStore | None = None,
) -> AsyncIterator[dict]:
    mem = memory or get_memory_store()
    cleaned = (question or "").strip()
    if not cleaned:
        raise ValueError("问题不能为空")

    doc_ids, session_id = _resolve_session(mem, cleaned, session_id, doc_ids)
    memory_context = mem.build_agent_context(session_id, cleaned, doc_ids=doc_ids)
    thread_id = uuid.uuid4().hex

    initial = _build_initial_state(
        cleaned,
        doc_ids=doc_ids,
        top_k=top_k or settings.rag_top_k,
        session_id=session_id,
        memory_context=memory_context,
        save_to_long_term=save_to_long_term,
        human_in_the_loop=False,
        memory=mem,
    )

    async for event in _stream_graph(initial, thread_id):
        yield event

    graph = get_rag_graph()
    config = {"configurable": {"thread_id": thread_id}}
    final = graph.get_state(config).values

    if final.get("cancelled"):
        yield {"type": "cancelled", "run_id": thread_id, "message": final.get("cancel_message") or "已取消"}
        return

    sources = final.get("sources") or []
    steps = final.get("steps") or []
    user_prompt = final.get("user_prompt") or ""

    yield {
        "type": "sources",
        "sources": sources,
        "steps": steps,
        "session_id": session_id,
    }

    yield {"type": "start", "task": "ask"}
    answer_parts: list[str] = []
    async for delta in chat_completion_stream(RAG_QA_SYSTEM, user_prompt):
        answer_parts.append(delta)
        yield {"type": "delta", "text": delta}
    yield {"type": "done", "task": "ask"}

    full_answer = "".join(answer_parts)
    await _finalize_turn(
        mem,
        final,
        question=cleaned,
        full_answer=full_answer,
        session_id=session_id,
        doc_ids=doc_ids,
        save_to_long_term=save_to_long_term,
    )

    try:
        graph.checkpointer.delete_thread(thread_id)
    except Exception:
        pass


async def stream_hitl_start(
    question: str,
    *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
    session_id: str | None = None,
    save_to_long_term: bool = True,
    memory: MemoryStore | None = None,
) -> AsyncIterator[dict]:
    mem = memory or get_memory_store()
    cleaned = (question or "").strip()
    if not cleaned:
        raise ValueError("问题不能为空")

    doc_ids, session_id = _resolve_session(mem, cleaned, session_id, doc_ids)
    memory_context = mem.build_agent_context(session_id, cleaned, doc_ids=doc_ids)
    run_id = uuid.uuid4().hex

    initial = _build_initial_state(
        cleaned,
        doc_ids=doc_ids,
        top_k=top_k or settings.rag_top_k,
        session_id=session_id,
        memory_context=memory_context,
        save_to_long_term=save_to_long_term,
        human_in_the_loop=True,
        memory=mem,
    )

    async for event in _stream_graph(initial, run_id):
        if event["type"] == "interrupt":
            value = event["value"]
            yield {
                "type": "human_review",
                "run_id": run_id,
                "stage": value.get("stage"),
                "message": value.get("message"),
                "analysis": value.get("analysis"),
                "search_queries": value.get("search_queries"),
                "source_count": value.get("source_count"),
                "session_id": value.get("session_id") or session_id,
            }
            yield {"type": "paused", "run_id": run_id, "stage": value.get("stage")}
        else:
            yield event


async def stream_hitl_continue(
    run_id: str,
    *,
    action: str,
    edited_queries: list[str] | None = None,
    extra_queries: list[str] | None = None,
    feedback: str | None = None,
    memory: MemoryStore | None = None,
) -> AsyncIterator[dict]:
    mem = memory or get_memory_store()
    graph = get_rag_graph()
    config = {"configurable": {"thread_id": run_id}}

    snap = graph.get_state(config)
    if not snap.values:
        raise ValueError("run_id 无效或已过期，请重新提问")

    resume_payload = {
        "action": (action or "approve").strip().lower(),
        "edited_queries": edited_queries,
        "extra_queries": extra_queries,
        "feedback": feedback,
    }

    saw_interrupt = False
    async for event in _stream_graph(Command(resume=resume_payload), run_id):
        if event["type"] == "interrupt":
            saw_interrupt = True
            value = event["value"]
            final_snap = graph.get_state(config).values
            sources = final_snap.get("sources") or []
            steps = final_snap.get("steps") or []
            if sources:
                yield {
                    "type": "sources",
                    "sources": sources,
                    "steps": steps,
                    "session_id": final_snap.get("session_id"),
                }
            yield {
                "type": "human_review",
                "run_id": run_id,
                "stage": value.get("stage"),
                "message": value.get("message"),
                "source_count": value.get("source_count"),
                "session_id": value.get("session_id"),
            }
            yield {"type": "paused", "run_id": run_id, "stage": value.get("stage")}
        else:
            yield event

    final = graph.get_state(config).values

    if final.get("cancelled"):
        yield {"type": "cancelled", "run_id": run_id, "message": final.get("cancel_message") or "用户已取消"}
        try:
            graph.checkpointer.delete_thread(run_id)
        except Exception:
            pass
        return

    if saw_interrupt:
        return

    sources = final.get("sources") or []
    steps = final.get("steps") or []
    user_prompt = final.get("user_prompt") or ""
    session_id = final.get("session_id")
    question = final.get("question") or ""
    doc_ids = final.get("doc_ids") or []
    save_lt = bool(final.get("save_to_long_term", True))

    yield {
        "type": "sources",
        "sources": sources,
        "steps": steps,
        "session_id": session_id,
    }

    yield {"type": "start", "task": "ask"}
    answer_parts: list[str] = []
    async for delta in chat_completion_stream(RAG_QA_SYSTEM, user_prompt):
        answer_parts.append(delta)
        yield {"type": "delta", "text": delta}
    yield {"type": "done", "task": "ask"}

    full_answer = "".join(answer_parts)
    await _finalize_turn(
        mem,
        final,
        question=question,
        full_answer=full_answer,
        session_id=session_id,
        doc_ids=doc_ids,
        save_to_long_term=save_lt,
    )

    try:
        graph.checkpointer.delete_thread(run_id)
    except Exception:
        pass


async def run_agentic_rag(
    question: str,
    *,
    doc_ids: list[str] | None = None,
    top_k: int | None = None,
    memory_context: str = "",
    session_id: str | None = None,
    memory: MemoryStore | None = None,
    on_step=None,
) -> tuple[list[dict], list[RetrievedSource], str]:
    """非流式运行（内部/测试用）。"""
    from app.rag.common import AgentStep

    all_steps: list[dict] = []
    sources_out: list[RetrievedSource] = []
    user_prompt = ""

    async for event in stream_agentic_answer(
        question,
        doc_ids=doc_ids,
        top_k=top_k,
        session_id=session_id,
        memory=memory,
    ):
        t = event.get("type")
        if t == "agent_step":
            step = event["step"]
            all_steps.append(step)
            if on_step:
                await on_step(
                    AgentStep(
                        phase=step["phase"],
                        message=step["message"],
                        detail=step.get("detail"),
                        agent=step.get("agent") or "researcher",
                    )
                )
        elif t == "sources":
            sources_out = sources_from_dicts(event.get("sources") or [])

    user_prompt = build_rag_prompt(question.strip(), sources_out)
    if memory_context.strip():
        user_prompt = with_memory_context(user_prompt, memory_context)

    return all_steps, sources_out, user_prompt
