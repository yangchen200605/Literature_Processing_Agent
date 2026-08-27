"""长期记忆：SQLite 持久化 store。"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

from app.config import settings
from app.memory.models import LongTermMemory

MEMORY_DB = Path(__file__).resolve().parent.parent.parent / "data" / "memory" / "memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS long_term_memories (
    memory_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    doc_ids TEXT NOT NULL DEFAULT '[]',
    session_id TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ltm_kind ON long_term_memories(kind);
CREATE INDEX IF NOT EXISTS idx_ltm_created ON long_term_memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ltm_session ON long_term_memories(session_id);
"""


class LongTermStore:
    """长期记忆 store：跨会话持久化 QA 摘要、文献笔记等。"""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or MEMORY_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def save(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        doc_ids: list[str] | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
        memory_id: str | None = None,
    ) -> LongTermMemory:
        now = time.time()
        mid = memory_id or uuid.uuid4().hex
        record = LongTermMemory(
            memory_id=mid,
            kind=kind,
            title=title.strip(),
            content=content.strip(),
            doc_ids=list(doc_ids or []),
            session_id=session_id,
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO long_term_memories
                (memory_id, kind, title, content, doc_ids, session_id, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    kind=excluded.kind,
                    title=excluded.title,
                    content=excluded.content,
                    doc_ids=excluded.doc_ids,
                    session_id=excluded.session_id,
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at
                """,
                (
                    record.memory_id,
                    record.kind,
                    record.title,
                    record.content,
                    json.dumps(record.doc_ids, ensure_ascii=False),
                    record.session_id,
                    json.dumps(record.metadata, ensure_ascii=False),
                    record.created_at,
                    record.updated_at,
                ),
            )
        self._enforce_limit()
        return record

    def get(self, memory_id: str) -> LongTermMemory | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM long_term_memories WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        if not row:
            return None
        return LongTermMemory.from_row(dict(row))

    def delete(self, memory_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM long_term_memories WHERE memory_id = ?",
                (memory_id,),
            )
            return cur.rowcount > 0

    def list_memories(
        self,
        *,
        kind: str | None = None,
        doc_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[LongTermMemory]:
        clauses: list[str] = []
        params: list[object] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if doc_id:
            clauses.append("doc_ids LIKE ?")
            params.append(f'%"{doc_id}"%')

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        sql = f"""
            SELECT * FROM long_term_memories
            {where}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [LongTermMemory.from_row(dict(row)) for row in rows]

    def search(
        self,
        query: str,
        *,
        doc_ids: list[str] | None = None,
        kind: str | None = None,
        limit: int = 5,
    ) -> list[LongTermMemory]:
        q = (query or "").strip()
        if not q:
            return self.list_memories(kind=kind, limit=limit)

        tokens = [t for t in q.replace("，", " ").replace(",", " ").split() if t.strip()]
        if not tokens:
            return self.list_memories(kind=kind, limit=limit)

        clauses = ["(" + " OR ".join(["title LIKE ? OR content LIKE ?"] * len(tokens)) + ")"]
        params: list[object] = []
        for token in tokens:
            pattern = f"%{token}%"
            params.extend([pattern, pattern])
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if doc_ids:
            doc_clause = " OR ".join(["doc_ids LIKE ?"] * len(doc_ids))
            clauses.append(f"({doc_clause})")
            for doc_id in doc_ids:
                params.append(f'%"{doc_id}"%')

        params.append(limit)
        sql = f"""
            SELECT * FROM long_term_memories
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [LongTermMemory.from_row(dict(row)) for row in rows]

    def build_context_snippet(
        self,
        *,
        query: str,
        doc_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> str:
        k = limit or settings.memory_long_term_context_limit
        hits = self.search(query, doc_ids=doc_ids, kind="qa_summary", limit=k)
        note_limit = max(1, k - len(hits))
        hits.extend(self.search(query, doc_ids=doc_ids, kind="doc_note", limit=note_limit))
        if not hits:
            return ""
        lines = ["以下是与当前问题相关的历史长期记忆："]
        for i, mem in enumerate(hits[:k], start=1):
            title = mem.title or mem.kind
            body = mem.content.strip()
            if len(body) > 400:
                body = body[:400] + "…"
            lines.append(f"[L{i}] {title}\n{body}")
        return "\n\n".join(lines)

    def _enforce_limit(self) -> None:
        max_items = settings.memory_long_term_max_items
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM long_term_memories").fetchone()[0]
            if count <= max_items:
                return
            overflow = count - max_items
            conn.execute(
                """
                DELETE FROM long_term_memories
                WHERE memory_id IN (
                    SELECT memory_id FROM long_term_memories
                    ORDER BY updated_at ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )
