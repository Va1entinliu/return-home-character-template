from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class RequestConflict(ValueError):
    """A request ID was reused with different content."""


class ConversationStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_text TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (session_id, request_id, kind)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    time_known INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS messages_session_order
                ON messages(session_id, message_order);
                """
            )

    def begin_chat(self, session_id: str, request_id: str, text: str) -> dict:
        now = int(time.time() * 1000)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT request_text, status, response_text
                FROM requests
                WHERE session_id = ? AND request_id = ? AND kind = 'chat'
                """,
                (session_id, request_id),
            ).fetchone()
            if row is not None:
                if row["request_text"] != text:
                    raise RequestConflict(
                        "同一会话中的 request_id 已用于不同文本，请生成新的 request_id"
                    )
                return {
                    "status": row["status"],
                    "response_text": row["response_text"],
                }

            connection.execute(
                """
                INSERT INTO requests (
                    session_id, request_id, kind, request_text,
                    status, response_text, created_at, updated_at
                ) VALUES (?, ?, 'chat', ?, 'pending', NULL, ?, ?)
                """,
                (session_id, request_id, text, now, now),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO messages (
                    message_id, session_id, role, content, created_at, time_known
                ) VALUES (?, ?, 'user', ?, ?, 1)
                """,
                (f"chat:{session_id}:{request_id}:user", session_id, text, now),
            )
            return {"status": "pending", "response_text": None}

    def complete_chat(
        self,
        session_id: str,
        request_id: str,
        request_text: str,
        reply: str,
    ) -> None:
        now = int(time.time() * 1000)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT request_text
                FROM requests
                WHERE session_id = ? AND request_id = ? AND kind = 'chat'
                """,
                (session_id, request_id),
            ).fetchone()
            if row is None or row["request_text"] != request_text:
                raise RequestConflict("请求状态与当前消息不一致")
            connection.execute(
                """
                INSERT OR IGNORE INTO messages (
                    message_id, session_id, role, content, created_at, time_known
                ) VALUES (?, ?, 'assistant', ?, ?, 1)
                """,
                (
                    f"chat:{session_id}:{request_id}:assistant",
                    session_id,
                    reply,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE requests
                SET status = 'completed', response_text = ?, updated_at = ?
                WHERE session_id = ? AND request_id = ? AND kind = 'chat'
                """,
                (reply, now, session_id, request_id),
            )

    def messages(self, session_id: str) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT message_id, role, content, created_at, time_known
                FROM messages
                WHERE session_id = ?
                ORDER BY message_order
                """,
                (session_id,),
            ).fetchall()
        return [
            {
                "id": row["message_id"],
                "role": row["role"],
                "content": row["content"],
                "createdAt": row["created_at"],
                "timeKnown": bool(row["time_known"]),
            }
            for row in rows
        ]
