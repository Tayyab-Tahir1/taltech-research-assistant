"""Per-user chat-history sidebar widget.

Groups chats by Today / Yesterday / Earlier based on ``updated_at`` and lets
the user switch, rename, or delete a chat. Keeps Streamlit state in sync:

- ``st.session_state.current_chat_id``  — int | None
- ``st.session_state.messages``          — list of message dicts
- ``st.session_state.artifacts``         — list of artifact dicts
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import streamlit as st

from app.storage import chats as chat_store


def render_history_sidebar(user_email: str) -> None:
    """Render the chat-history block in the active sidebar container."""
    if st.button("➕ New chat", use_container_width=True, key="new_chat_btn"):
        _reset_chat_state()
        st.rerun()

    try:
        history = chat_store.list_chats(user_email)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load chat history: {exc}")
        return

    if not history:
        st.caption("No previous chats yet.")
        return

    for group_label, group_chats in _group_by_day(history):
        st.caption(group_label)
        for chat in group_chats:
            _render_chat_row(chat, user_email)


def _render_chat_row(chat: Any, user_email: str) -> None:
    is_active = st.session_state.get("current_chat_id") == chat.id
    col_main, col_menu = st.columns([5, 1], gap="small")

    with col_main:
        label = ("● " if is_active else "") + (chat.title or "Untitled")
        if st.button(
            label,
            key=f"chat_open_{chat.id}",
            use_container_width=True,
        ):
            _load_chat_into_state(chat.id, user_email)
            st.rerun()

    with col_menu:
        with st.popover("⋮", use_container_width=True):
            new_title = st.text_input(
                "Rename",
                value=chat.title,
                key=f"rename_field_{chat.id}",
            )
            col_r, col_d = st.columns(2)
            if col_r.button("Save", key=f"rename_btn_{chat.id}"):
                chat_store.rename_chat(chat.id, user_email, new_title)
                st.rerun()
            if col_d.button("Delete", key=f"delete_btn_{chat.id}"):
                chat_store.delete_chat(chat.id, user_email)
                if st.session_state.get("current_chat_id") == chat.id:
                    _reset_chat_state()
                st.rerun()


def _load_chat_into_state(chat_id: int, user_email: str) -> None:
    messages = chat_store.load_chat(chat_id, user_email)
    st.session_state.current_chat_id = chat_id
    st.session_state.messages = [
        {
            "role": m.role,
            "content": m.content,
            "attachments": m.attachments,
            "artifacts": m.artifacts,
        }
        for m in messages
    ]
    st.session_state.artifacts = [
        art for m in messages for art in (m.artifacts or [])
    ]
    st.session_state.bibtex_store = []


def _reset_chat_state() -> None:
    st.session_state.current_chat_id = None
    st.session_state.messages = []
    st.session_state.artifacts = []
    st.session_state.bibtex_store = []
    st.session_state.pending_attachments = []


def _group_by_day(chats: list) -> list[tuple[str, list]]:
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    buckets: dict[str, list] = {"Today": [], "Yesterday": [], "Earlier": []}
    for chat in chats:
        dt = _parse_dt(chat.updated_at)
        when = dt.date() if dt else None
        if when == today:
            buckets["Today"].append(chat)
        elif when == yesterday:
            buckets["Yesterday"].append(chat)
        else:
            buckets["Earlier"].append(chat)
    return [(label, rows) for label, rows in buckets.items() if rows]


def _parse_dt(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
