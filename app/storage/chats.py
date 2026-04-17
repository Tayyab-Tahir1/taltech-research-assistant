"""SQLite-backed per-user chat history.

All queries are parameterised and always include ``user_email`` in the WHERE
clause so one user can never read another user's chats.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from app.config import CHATS_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    title      TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id          INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    attachments_json TEXT,
    artifacts_json   TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chats_user
    ON chats(user_email, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_chat
    ON messages(chat_id, id);
"""


@dataclass(frozen=True)
class Chat:
    id: int
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Message:
    id: int
    role: str
    content: str
    attachments: list[dict]
    artifacts: list[dict]
    created_at: str


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with foreign keys and row factory enabled."""
    path = Path(db_path or CHATS_DB_PATH)
    _ensure_dir(path)
    conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def list_chats(user_email: str, limit: int = 100) -> list[Chat]:
    if not user_email:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at "
            "FROM chats WHERE user_email = ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_email, limit),
        ).fetchall()
    return [
        Chat(
            id=r["id"],
            title=r["title"],
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
        )
        for r in rows
    ]


def load_chat(chat_id: int, user_email: str) -> list[Message]:
    """Return messages for the given chat, but only if the user owns it."""
    if not user_email or chat_id is None:
        return []
    with connect() as conn:
        owner = conn.execute(
            "SELECT 1 FROM chats WHERE id = ? AND user_email = ?",
            (chat_id, user_email),
        ).fetchone()
        if not owner:
            return []
        rows = conn.execute(
            "SELECT id, role, content, attachments_json, artifacts_json, created_at "
            "FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
    return [
        Message(
            id=r["id"],
            role=r["role"],
            content=r["content"],
            attachments=_loads_list(r["attachments_json"]),
            artifacts=_loads_list(r["artifacts_json"]),
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


def new_chat(user_email: str, first_prompt: str) -> int:
    title = _derive_title(first_prompt)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO chats (user_email, title) VALUES (?, ?)",
            (user_email, title),
        )
        return int(cur.lastrowid)


def save_message(
    chat_id: int,
    user_email: str,
    role: str,
    content: str,
    attachments: list[dict] | None = None,
    artifacts: list[dict] | None = None,
) -> int:
    """Append a message to a chat the user owns; returns the new row id."""
    with connect() as conn:
        owner = conn.execute(
            "SELECT 1 FROM chats WHERE id = ? AND user_email = ?",
            (chat_id, user_email),
        ).fetchone()
        if not owner:
            raise PermissionError("Chat not owned by user")
        cur = conn.execute(
            "INSERT INTO messages "
            "(chat_id, role, content, attachments_json, artifacts_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                chat_id,
                role,
                content,
                json.dumps(attachments) if attachments else None,
                json.dumps(artifacts) if artifacts else None,
            ),
        )
        conn.execute(
            "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (chat_id,),
        )
        return int(cur.lastrowid)


def touch_chat(chat_id: int, user_email: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE chats SET updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND user_email = ?",
            (chat_id, user_email),
        )


def rename_chat(chat_id: int, user_email: str, title: str) -> None:
    title = (title or "").strip()[:120] or "Untitled chat"
    with connect() as conn:
        conn.execute(
            "UPDATE chats SET title = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND user_email = ?",
            (title, chat_id, user_email),
        )


def delete_chat(chat_id: int, user_email: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM chats WHERE id = ? AND user_email = ?",
            (chat_id, user_email),
        )


def _derive_title(prompt: str) -> str:
    cleaned = " ".join((prompt or "").split())
    if not cleaned:
        return "New chat"
    return cleaned[:60] + ("…" if len(cleaned) > 60 else "")


def _loads_list(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []
