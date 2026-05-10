from __future__ import annotations

import os
import sqlite3
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Deque, Dict, List


def _summary_from_items(items: List[Dict[str, str]]) -> str:
    if not items:
        return "No recent practice history."

    recent_users = [item["user"] for item in items[-2:]]
    recent_guides = [item["assistant"] for item in items[-2:]]
    last_user = recent_users[-1] if recent_users else "None"
    last_guide = recent_guides[-1] if recent_guides else "None"
    return (
        f"Recent practice count: {len(items)}.\n"
        f"Latest user focus: {last_user}\n"
        f"Latest guide move: {last_guide}"
    )


class SlidingWindowMemory:
    """Stores a short interaction history using a fixed-size sliding window."""

    def __init__(self, max_items: int = 5) -> None:
        self.max_items = max_items
        self._items: Deque[Dict[str, str]] = deque(maxlen=max_items)
        self._lock = Lock()

    def add(self, user_input: str, response: str) -> None:
        with self._lock:
            self._items.append({"user": user_input, "assistant": response})

    def history(self) -> List[Dict[str, str]]:
        with self._lock:
            return list(self._items)

    def as_text(self) -> str:
        items = self.history()
        if not items:
            return "No prior interactions."

        formatted = []
        for idx, item in enumerate(items, start=1):
            formatted.append(
                f"Interaction {idx}\n"
                f"User: {item['user']}\n"
                f"Guide: {item['assistant']}"
            )
        return "\n\n".join(formatted)

    def summary_text(self) -> str:
        return _summary_from_items(self.history())


class PersistentSessionMemory:
    """Session-scoped memory view backed by a persistent store."""

    def __init__(self, store: "SessionMemoryStore", key: str, max_items: int) -> None:
        self._store = store
        self._key = key
        self.max_items = max_items

    def add(self, user_input: str, response: str) -> None:
        self._store.add_turn(self._key, user_input, response)

    def history(self) -> List[Dict[str, str]]:
        return self._store.history_for_key(self._key)

    def as_text(self) -> str:
        items = self.history()
        if not items:
            return "No prior interactions."

        formatted = []
        for idx, item in enumerate(items, start=1):
            formatted.append(
                f"Interaction {idx}\n"
                f"User: {item['user']}\n"
                f"Guide: {item['assistant']}"
            )
        return "\n\n".join(formatted)

    def summary_text(self) -> str:
        return _summary_from_items(self.history())


class SessionMemoryStore:
    """Keeps an isolated sliding-window memory per user/session key and persists it to SQLite."""

    def __init__(self, max_items: int = 5, db_path: str | None = None) -> None:
        self.max_items = max_items
        self.db_path = db_path or os.getenv("MEMORY_DB_PATH") or self._default_db_path()
        self._sessions: Dict[str, PersistentSessionMemory] = {}
        self._lock = Lock()
        self._init_db()

    def get_memory(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> PersistentSessionMemory:
        key = self._build_key(user_id=user_id, session_id=session_id)
        with self._lock:
            memory = self._sessions.get(key)
            if memory is None:
                memory = PersistentSessionMemory(store=self, key=key, max_items=self.max_items)
                self._sessions[key] = memory
            return memory

    def clear_memory(self, user_id: str | None = None, session_id: str | None = None) -> None:
        key = self._build_key(user_id=user_id, session_id=session_id)
        with self._lock:
            self._sessions.pop(key, None)
        with self._connect() as conn:
            conn.execute("DELETE FROM interactions WHERE session_key = ?", (key,))
            conn.commit()

    def session_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(DISTINCT session_key) FROM interactions").fetchone()
        return int(row[0] or 0) if row else 0

    def add_turn(self, key: str, user_input: str, response: str) -> None:
        with self._lock:
            with self._connect() as conn:
                next_turn = self._next_turn_index(conn, key)
                conn.execute(
                    """
                    INSERT INTO interactions (session_key, turn_index, user_text, assistant_text)
                    VALUES (?, ?, ?, ?)
                    """,
                    (key, next_turn, user_input, response),
                )
                self._trim_history(conn, key)
                conn.commit()

    def history_for_key(self, key: str) -> List[Dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_text, assistant_text
                FROM interactions
                WHERE session_key = ?
                ORDER BY turn_index ASC
                """,
                (key,),
            ).fetchall()
        return [{"user": row[0], "assistant": row[1]} for row in rows]

    def _init_db(self) -> None:
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interactions_session_key ON interactions(session_key)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    def _next_turn_index(self, conn: sqlite3.Connection, key: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(turn_index), 0) FROM interactions WHERE session_key = ?",
            (key,),
        ).fetchone()
        return int(row[0] or 0) + 1

    def _trim_history(self, conn: sqlite3.Connection, key: str) -> None:
        rows = conn.execute(
            """
            SELECT id
            FROM interactions
            WHERE session_key = ?
            ORDER BY turn_index DESC
            LIMIT -1 OFFSET ?
            """,
            (key, self.max_items),
        ).fetchall()
        if rows:
            conn.executemany("DELETE FROM interactions WHERE id = ?", rows)

    @staticmethod
    def _build_key(user_id: str | None = None, session_id: str | None = None) -> str:
        user_part = (user_id or "anonymous").strip() or "anonymous"
        session_part = (session_id or "default").strip() or "default"
        return f"{user_part}::{session_part}"

    @staticmethod
    def _default_db_path() -> str:
        project_root = Path(__file__).resolve().parents[1]
        return str(project_root / "data" / "session_memory.sqlite3")
