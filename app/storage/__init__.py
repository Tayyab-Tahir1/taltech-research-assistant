"""Persistent storage for per-user chat history (SQLite)."""
from __future__ import annotations

from app.storage.chats import (
    Chat,
    Message,
    connect,
    delete_chat,
    init_db,
    list_chats,
    load_chat,
    new_chat,
    rename_chat,
    save_message,
    touch_chat,
)

__all__ = [
    "Chat",
    "Message",
    "connect",
    "delete_chat",
    "init_db",
    "list_chats",
    "load_chat",
    "new_chat",
    "rename_chat",
    "save_message",
    "touch_chat",
]
