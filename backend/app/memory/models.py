"""记忆数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TurnRecord:
    """单轮问答记录（写入 session 与长期记忆）。"""

    question: str
    answer: str = ""
    doc_ids: list[str] = field(default_factory=list)
    source_count: int = 0
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Checkpoint:
    """短期记忆 checkpoint：Agent 每个关键阶段的快照。"""

    checkpoint_id: str
    session_id: str
    phase: str
    message: str
    payload: dict[str, Any]
    sequence: int
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        return cls(
            checkpoint_id=str(data["checkpoint_id"]),
            session_id=str(data["session_id"]),
            phase=str(data["phase"]),
            message=str(data.get("message") or ""),
            payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
            sequence=int(data.get("sequence") or 0),
            created_at=float(data.get("created_at") or 0),
        )


@dataclass
class SessionState:
    """会话短期状态：多轮对话 + 最新 checkpoint 指针。"""

    session_id: str
    doc_ids: list[str] = field(default_factory=list)
    turns: list[TurnRecord] = field(default_factory=list)
    agent_trace: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    latest_checkpoint_id: str | None = None
    checkpoint_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "doc_ids": self.doc_ids,
            "turns": [t.to_dict() for t in self.turns],
            "agent_trace": self.agent_trace,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "latest_checkpoint_id": self.latest_checkpoint_id,
            "checkpoint_count": self.checkpoint_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        turns_raw = data.get("turns") or []
        turns = [
            TurnRecord(**item) if isinstance(item, dict) else TurnRecord(question=str(item))
            for item in turns_raw
        ]
        return cls(
            session_id=str(data["session_id"]),
            doc_ids=list(data.get("doc_ids") or []),
            turns=turns,
            agent_trace=list(data.get("agent_trace") or []),
            metadata=dict(data.get("metadata") or {}),
            created_at=float(data.get("created_at") or 0),
            updated_at=float(data.get("updated_at") or 0),
            latest_checkpoint_id=data.get("latest_checkpoint_id"),
            checkpoint_count=int(data.get("checkpoint_count") or 0),
        )


@dataclass
class LongTermMemory:
    """长期记忆条目：跨会话持久化的摘要/笔记。"""

    memory_id: str
    kind: str
    title: str
    content: str
    doc_ids: list[str] = field(default_factory=list)
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> LongTermMemory:
        import json

        meta = row.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        doc_ids = row.get("doc_ids")
        if isinstance(doc_ids, str):
            try:
                doc_ids = json.loads(doc_ids)
            except Exception:
                doc_ids = []
        return cls(
            memory_id=str(row["memory_id"]),
            kind=str(row.get("kind") or "note"),
            title=str(row.get("title") or ""),
            content=str(row.get("content") or ""),
            doc_ids=list(doc_ids or []),
            session_id=row.get("session_id"),
            metadata=dict(meta or {}),
            created_at=float(row.get("created_at") or 0),
            updated_at=float(row.get("updated_at") or 0),
        )
