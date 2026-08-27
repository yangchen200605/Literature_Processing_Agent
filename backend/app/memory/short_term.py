"""短期记忆：基于 checkpoint 的会话快照（文件存储 + TTL）。"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from app.config import settings
from app.memory.models import Checkpoint, SessionState, TurnRecord

SESSIONS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "sessions"


def _ensure_root() -> None:
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)


def _session_dir(session_id: str) -> Path:
    return SESSIONS_ROOT / session_id


def _meta_path(session_id: str) -> Path:
    return _session_dir(session_id) / "session.json"


def _checkpoints_dir(session_id: str) -> Path:
    return _session_dir(session_id) / "checkpoints"


def _latest_path(session_id: str) -> Path:
    return _session_dir(session_id) / "latest_checkpoint.json"


def cleanup_expired_sessions() -> None:
    """清理超过 TTL 的会话目录。"""
    _ensure_root()
    ttl = settings.memory_session_ttl_seconds
    now = time.time()
    for path in SESSIONS_ROOT.iterdir():
        if not path.is_dir():
            continue
        meta = path / "session.json"
        try:
            if meta.is_file():
                updated = json.loads(meta.read_text(encoding="utf-8")).get("updated_at", 0)
            else:
                updated = path.stat().st_mtime
            if now - float(updated) > ttl:
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            continue


class ShortTermStore:
    """短期记忆 store：session 状态 + 有序 checkpoint 链。"""

    def create_session(
        self,
        *,
        doc_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> SessionState:
        cleanup_expired_sessions()
        _ensure_root()
        session_id = uuid.uuid4().hex
        now = time.time()
        state = SessionState(
            session_id=session_id,
            doc_ids=list(doc_ids or []),
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        folder = _session_dir(session_id)
        folder.mkdir(parents=True, exist_ok=False)
        _checkpoints_dir(session_id).mkdir(parents=True, exist_ok=True)
        self._save_session(state)
        return state

    def get_session(self, session_id: str) -> SessionState | None:
        path = _meta_path(session_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionState.from_dict(data)
        except Exception:
            return None

    def save_session(self, state: SessionState) -> SessionState:
        state.updated_at = time.time()
        self._save_session(state)
        return state

    def _save_session(self, state: SessionState) -> None:
        _session_dir(state.session_id).mkdir(parents=True, exist_ok=True)
        _meta_path(state.session_id).write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_checkpoint(
        self,
        session_id: str,
        *,
        phase: str,
        message: str,
        payload: dict | None = None,
    ) -> Checkpoint | None:
        state = self.get_session(session_id)
        if not state:
            return None

        sequence = state.checkpoint_count + 1
        if sequence > settings.memory_max_checkpoints_per_session:
            self._prune_old_checkpoints(session_id, keep=settings.memory_max_checkpoints_per_session - 1)
            state = self.get_session(session_id)
            if not state:
                return None
            sequence = state.checkpoint_count + 1

        checkpoint_id = f"ckpt_{sequence}_{uuid.uuid4().hex[:8]}"
        now = time.time()
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            phase=phase,
            message=message,
            payload=dict(payload or {}),
            sequence=sequence,
            created_at=now,
        )

        ckpt_dir = _checkpoints_dir(session_id)
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        ckpt_path = ckpt_dir / f"{checkpoint_id}.json"
        ckpt_path.write_text(
            json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        state.checkpoint_count = sequence
        state.latest_checkpoint_id = checkpoint_id
        state.updated_at = now
        self._save_session(state)

        _latest_path(session_id).write_text(
            json.dumps({"checkpoint_id": checkpoint_id, "sequence": sequence}, ensure_ascii=False),
            encoding="utf-8",
        )
        return checkpoint

    def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        ckpt_dir = _checkpoints_dir(session_id)
        if not ckpt_dir.is_dir():
            return []
        items: list[Checkpoint] = []
        for path in ckpt_dir.glob("ckpt_*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append(Checkpoint.from_dict(data))
            except Exception:
                continue
        items.sort(key=lambda c: c.sequence)
        return items

    def get_checkpoint(self, session_id: str, checkpoint_id: str) -> Checkpoint | None:
        path = _checkpoints_dir(session_id) / f"{checkpoint_id}.json"
        if not path.is_file():
            return None
        try:
            return Checkpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def restore_checkpoint(self, session_id: str, checkpoint_id: str) -> SessionState | None:
        checkpoint = self.get_checkpoint(session_id, checkpoint_id)
        state = self.get_session(session_id)
        if not checkpoint or not state:
            return None

        checkpoints = self.list_checkpoints(session_id)
        for ckpt in checkpoints:
            if ckpt.sequence > checkpoint.sequence:
                try:
                    (_checkpoints_dir(session_id) / f"{ckpt.checkpoint_id}.json").unlink(missing_ok=True)
                except Exception:
                    pass

        trace = state.agent_trace
        if checkpoint.payload.get("agent_trace"):
            trace = list(checkpoint.payload["agent_trace"])

        turns = state.turns
        if checkpoint.payload.get("turns"):
            raw_turns = checkpoint.payload["turns"]
            turns = [
                TurnRecord(**t) if isinstance(t, dict) else TurnRecord(question=str(t))
                for t in raw_turns
            ]

        state.agent_trace = trace
        state.turns = turns
        state.doc_ids = list(checkpoint.payload.get("doc_ids") or state.doc_ids)
        state.latest_checkpoint_id = checkpoint_id
        state.checkpoint_count = checkpoint.sequence
        state.updated_at = time.time()
        self._save_session(state)

        _latest_path(session_id).write_text(
            json.dumps({"checkpoint_id": checkpoint_id, "sequence": checkpoint.sequence}, ensure_ascii=False),
            encoding="utf-8",
        )
        return state

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
        state = self.get_session(session_id)
        if not state:
            return None
        now = time.time()
        state.turns.append(
            TurnRecord(
                question=question,
                answer=answer,
                doc_ids=list(doc_ids or state.doc_ids),
                source_count=source_count,
                created_at=now,
            )
        )
        if doc_ids:
            state.doc_ids = list(doc_ids)
        if agent_trace is not None:
            state.agent_trace = agent_trace
        state.updated_at = now
        return self.save_session(state)

    def build_conversation_context(self, session_id: str, *, max_turns: int | None = None) -> str:
        state = self.get_session(session_id)
        if not state or not state.turns:
            return ""
        limit = max_turns or settings.memory_short_term_turn_limit
        recent = state.turns[-limit:]
        lines = ["以下是同一会话中的近期问答，供理解指代与上下文："]
        for i, turn in enumerate(recent, start=1):
            lines.append(f"【第{i}轮】")
            lines.append(f"问：{turn.question}")
            if turn.answer:
                ans = turn.answer.strip()
                if len(ans) > 600:
                    ans = ans[:600] + "…"
                lines.append(f"答：{ans}")
        return "\n".join(lines)

    def _prune_old_checkpoints(self, session_id: str, *, keep: int) -> None:
        checkpoints = self.list_checkpoints(session_id)
        if len(checkpoints) <= keep:
            return
        for ckpt in checkpoints[: len(checkpoints) - keep]:
            try:
                (_checkpoints_dir(session_id) / f"{ckpt.checkpoint_id}.json").unlink(missing_ok=True)
            except Exception:
                pass
        state = self.get_session(session_id)
        if state:
            remaining = self.list_checkpoints(session_id)
            state.checkpoint_count = len(remaining)
            if remaining:
                state.latest_checkpoint_id = remaining[-1].checkpoint_id
            self._save_session(state)
