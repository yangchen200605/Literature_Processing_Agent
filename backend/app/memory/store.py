"""统一 Memory Store：短期 checkpoint + 长期持久化。"""

from __future__ import annotations

from app.memory.long_term import LongTermStore
from app.memory.models import Checkpoint, LongTermMemory, SessionState
from app.memory.short_term import ShortTermStore

_store: MemoryStore | None = None


class MemoryStore:
    """
    记忆管理门面。

    - 短期：Session + Checkpoint（会话内 Agent 状态、可回滚）
    - 长期：SQLite 持久化（QA 摘要、文献笔记，跨会话检索）
    """

    def __init__(self) -> None:
        self.short = ShortTermStore()
        self.long = LongTermStore()

    # --- Session / Checkpoint ---

    def create_session(
        self,
        *,
        doc_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> SessionState:
        return self.short.create_session(doc_ids=doc_ids, metadata=metadata)

    def get_session(self, session_id: str) -> SessionState | None:
        return self.short.get_session(session_id)

    def save_checkpoint(
        self,
        session_id: str,
        *,
        phase: str,
        message: str,
        payload: dict | None = None,
    ) -> Checkpoint | None:
        state = self.short.get_session(session_id)
        if state and payload is not None:
            payload = {
                **payload,
                "doc_ids": state.doc_ids,
                "turns": [t.to_dict() for t in state.turns],
                "agent_trace": state.agent_trace,
            }
        return self.short.save_checkpoint(
            session_id,
            phase=phase,
            message=message,
            payload=payload,
        )

    def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        return self.short.list_checkpoints(session_id)

    def restore_checkpoint(self, session_id: str, checkpoint_id: str) -> SessionState | None:
        return self.short.restore_checkpoint(session_id, checkpoint_id)

    def append_turn(
        self,
        session_id: str,
        *,
        question: str,
        answer: str,
        doc_ids: list[str] | None = None,
        source_count: int = 0,
        agent_trace: list[dict] | None = None,
    ) -> SessionState | None:
        return self.short.append_turn(
            session_id,
            question=question,
            answer=answer,
            doc_ids=doc_ids,
            source_count=source_count,
            agent_trace=agent_trace,
        )

    def record_agent_step(
        self,
        session_id: str,
        step: dict,
    ) -> SessionState | None:
        state = self.short.get_session(session_id)
        if not state:
            return None
        state.agent_trace.append(step)
        return self.short.save_session(state)

    # --- 长期记忆 ---

    def save_qa_summary(
        self,
        *,
        question: str,
        answer: str,
        doc_ids: list[str] | None = None,
        session_id: str | None = None,
        source_count: int = 0,
    ) -> LongTermMemory:
        title = question.strip()[:80] or "问答摘要"
        content = f"问：{question.strip()}\n\n答：{answer.strip()}"
        return self.long.save(
            kind="qa_summary",
            title=title,
            content=content,
            doc_ids=doc_ids,
            session_id=session_id,
            metadata={"source_count": source_count},
        )

    def save_doc_note(
        self,
        *,
        title: str,
        content: str,
        doc_ids: list[str] | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> LongTermMemory:
        return self.long.save(
            kind="doc_note",
            title=title,
            content=content,
            doc_ids=doc_ids,
            session_id=session_id,
            metadata=metadata,
        )

    def list_long_term(
        self,
        *,
        kind: str | None = None,
        doc_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[LongTermMemory]:
        return self.long.list_memories(
            kind=kind,
            doc_id=doc_id,
            session_id=session_id,
            limit=limit,
            offset=offset,
        )

    def search_long_term(
        self,
        query: str,
        *,
        doc_ids: list[str] | None = None,
        kind: str | None = None,
        limit: int = 5,
    ) -> list[LongTermMemory]:
        return self.long.search(query, doc_ids=doc_ids, kind=kind, limit=limit)

    def delete_long_term(self, memory_id: str) -> bool:
        return self.long.delete(memory_id)

    # --- Agent 上下文组装 ---

    def build_agent_context(
        self,
        session_id: str | None,
        question: str,
        *,
        doc_ids: list[str] | None = None,
    ) -> str:
        """合并短期会话历史 + 长期相关记忆，供 Agent prompt 使用。"""
        parts: list[str] = []
        if session_id:
            short_ctx = self.short.build_conversation_context(session_id)
            if short_ctx:
                parts.append(short_ctx)
        long_ctx = self.long.build_context_snippet(query=question, doc_ids=doc_ids)
        if long_ctx:
            parts.append(long_ctx)
        return "\n\n---\n\n".join(parts)


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
