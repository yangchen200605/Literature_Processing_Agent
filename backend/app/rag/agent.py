"""Agentic RAG 入口（LangGraph 实现，见 graph.py）。"""

from __future__ import annotations

from app.rag.common import AgentStep
from app.rag.graph import run_agentic_rag, stream_agentic_answer

# 向后兼容：旧代码从此模块导入的工具函数
from app.rag.common import (  # noqa: F401
    merge_sources as _merge_sources,
    grade_context as _grade_context,
    persist_step as _persist_step,
    plan_retrieval as _plan_retrieval,
    retrieve_multi as _retrieve_multi,
    with_memory_context as _with_memory_context,
)

__all__ = [
    "AgentStep",
    "run_agentic_rag",
    "stream_agentic_answer",
    "_grade_context",
    "_merge_sources",
    "_persist_step",
    "_plan_retrieval",
    "_retrieve_multi",
    "_with_memory_context",
]
