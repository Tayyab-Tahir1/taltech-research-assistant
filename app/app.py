"""
TalTech Research Assistant — Streamlit UI

ChatGPT-style interface with:
- Google sign-in gate (Streamlit native OAuth)
- Sidebar chat history grouped per user (SQLite)
- Auto-intent routing (no mode radio — the agent reads the prompt)
- `+` popover for uploads and citation generation
- Claude-style artifact side panel for plots, tables, and code
"""
from __future__ import annotations

import hashlib
import os
import sys

# Ensure the project root (Hackathon/) is first in sys.path so that
# 'app' resolves to the app/ package, not this file (app.py) itself.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from datetime import datetime

import streamlit as st

from app.agent import run as agent_run
from app.attachments import classify_attachments
from app.config import BACKEND_LABEL, validate_secrets
from app.features.bibtex_extractor import extract_bibtex_entries
from app.logging_config import setup_logging
from app.storage import chats as chat_store
from app.ui.artifacts import render_artifact_panel
from app.ui.assets import logo_image, logo_pil_image, profile_image
from app.ui.sidebar_history import render_history_sidebar
from app.ui.spinner import rotating_logo_html
from app.ui.styles import inject_css

setup_logging()
chat_store.init_db()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TalTech Research Assistant",
    page_icon=logo_pil_image(),
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

USER_AVATAR = profile_image()
BOT_AVATAR = logo_image()


def _avatar_for(role: str):
    return USER_AVATAR if role == "user" else BOT_AVATAR


def _render_attachments(attachments: list[dict]) -> None:
    if not attachments:
        return
    chips = []
    for att in attachments:
        kind = att.get("kind")
        name = att.get("name", "file")
        if kind == "skipped":
            chips.append(f"⚠️ {att.get('skipped_reason', name)}")
        else:
            chips.append(f"📎 {name}")
    st.caption(" · ".join(chips))


# ── Auth gate ─────────────────────────────────────────────────────────────────
def _auth_enabled() -> bool:
    """Return True if Streamlit native OAuth is configured."""
    try:
        return bool(st.secrets.get("auth"))
    except Exception:
        return False


def _current_user_email() -> str | None:
    """Return the signed-in user's email, or None if not signed in.

    If OAuth is not configured, fall back to a single local user so the app
    stays usable in development without a `[auth]` secrets block.
    """
    if not _auth_enabled():
        return "local@localhost"
    try:
        if getattr(st.user, "is_logged_in", False):
            return st.user.email
    except Exception:
        return None
    return None


def _render_login_screen() -> None:
    if BOT_AVATAR is not None:
        col1, col2 = st.columns([1, 12])
        with col1:
            st.image(BOT_AVATAR, width=56)
        with col2:
            st.title("TalTech Research Assistant")
    else:
        st.title("TalTech Research Assistant")
    st.caption("Sign in with Google to access your chat history.")
    if st.button("Sign in with Google", type="primary"):
        st.login("google")


# ── Secrets validation banner ─────────────────────────────────────────────────
_secret_problems = validate_secrets()
if _secret_problems:
    for _p in _secret_problems:
        st.error(_p)

# ── Auth flow ─────────────────────────────────────────────────────────────────
_user_email = _current_user_email()
if _user_email is None:
    _render_login_screen()
    st.stop()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _build_history() -> list[dict]:
    history = []
    for msg in st.session_state.messages[-20:]:
        history.append({"role": msg["role"], "content": msg["content"]})
    return history


def _extract_and_store_bibtex(response: str) -> None:
    for m in extract_bibtex_entries(response):
        if m not in st.session_state.bibtex_store:
            st.session_state.bibtex_store.append(m)


def _build_chat_export() -> str:
    lines = [f"# TalTech Research Chat — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    for msg in st.session_state.messages:
        role = "**You**" if msg["role"] == "user" else "**TalTech Agent**"
        lines.append(f"\n{role}:\n{msg['content']}\n")
    if st.session_state.bibtex_store:
        lines.append("\n---\n## Collected BibTeX\n```bibtex")
        lines.extend(st.session_state.bibtex_store)
        lines.append("```")
    return "\n".join(lines)


def _file_digest(file_obj) -> str:
    try:
        data = file_obj.getvalue()
    except Exception:
        data = getattr(file_obj, "read", lambda: b"")()
        if hasattr(file_obj, "seek"):
            try:
                file_obj.seek(0)
            except Exception:
                pass
    return hashlib.sha1(data).hexdigest()[:16] if data else file_obj.name


def _drain_pending_attachments() -> list:
    """Pull queued uploads into the agent call and clear the buffer."""
    pending = st.session_state.pending_attachments
    st.session_state.pending_attachments = []
    st.session_state.pending_attachment_keys = set()
    return [entry["file"] for entry in pending]


def _queue_attachment(file_obj) -> None:
    digest = _file_digest(file_obj)
    if digest in st.session_state.pending_attachment_keys:
        return
    st.session_state.pending_attachment_keys.add(digest)
    st.session_state.pending_attachments.append(
        {"digest": digest, "name": file_obj.name, "file": file_obj}
    )


def _remove_pending(digest: str) -> None:
    st.session_state.pending_attachments = [
        e for e in st.session_state.pending_attachments if e["digest"] != digest
    ]
    st.session_state.pending_attachment_keys.discard(digest)


# ── Session state init ────────────────────────────────────────────────────────
_defaults = {
    "messages": [],
    "artifacts": [],
    "bibtex_store": [],
    "is_generating": False,
    "current_chat_id": None,
    "pending_attachments": [],
    "pending_attachment_keys": set(),
    "queued_prompt": None,
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    if BOT_AVATAR is not None:
        side_col1, side_col2 = st.columns([1, 4])
        with side_col1:
            st.image(BOT_AVATAR, width=40)
        with side_col2:
            st.title("TalTech Agent")
    else:
        st.title("TalTech Agent")
    st.caption(f"Backend: {BACKEND_LABEL}")
    st.caption(f"Signed in as **{_user_email}**")
    if _auth_enabled():
        if st.button("Sign out", key="logout_btn"):
            st.logout()
    st.divider()

    render_history_sidebar(_user_email)

    st.divider()
    st.subheader("Export")
    col1, col2 = st.columns(2)

    if col1.button("📥 Chat"):
        chat_md = _build_chat_export()
        st.download_button(
            "Download",
            data=chat_md,
            file_name=f"taltech_chat_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
        )

    if col2.button("📋 BibTeX"):
        if st.session_state.bibtex_store:
            combined = "\n\n".join(st.session_state.bibtex_store)
            st.code(combined, language="bibtex")
        else:
            st.info("No citations collected yet.")

# ── Main area ─────────────────────────────────────────────────────────────────
if BOT_AVATAR is not None:
    head_col1, head_col2 = st.columns([1, 12])
    with head_col1:
        st.image(BOT_AVATAR, width=56)
    with head_col2:
        st.title("TalTech Research Assistant")
else:
    st.title("TalTech Research Assistant")
st.caption(
    "Bilingual (ET/EN) · Thesis · Papers · Datasets · Simulation Tools · GitHub · Plots"
)

chat_col, artifact_col = st.columns([2, 1], gap="medium")

with artifact_col:
    render_artifact_panel(st.session_state.artifacts)

with chat_col:
    # Render chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar=_avatar_for(msg["role"])):
            _render_attachments(msg.get("attachments") or [])
            st.markdown(msg["content"])

    # `+` popover for uploads and citations, plus chat input.
    plus_col, input_col = st.columns([1, 20], gap="small")
    with plus_col:
        with st.popover("➕", use_container_width=True):
            uploaded = st.file_uploader(
                "Upload PDF or image",
                type=["pdf", "png", "jpg", "jpeg"],
                accept_multiple_files=True,
                key="plus_uploader",
            )
            if uploaded:
                for f in uploaded:
                    _queue_attachment(f)

            st.divider()
            with st.form("cite_form", clear_on_submit=True):
                cite_query = st.text_input(
                    "Cite a source (title, URL, or DOI)",
                    key="cite_query_field",
                )
                cite_submit = st.form_submit_button("Generate citation")
                if cite_submit and cite_query.strip():
                    st.session_state.queued_prompt = (
                        f"Generate BibTeX, IEEE, and APA citations for: "
                        f"{cite_query.strip()}"
                    )

    # Render pending-attachment chips so the user can remove before sending.
    if st.session_state.pending_attachments:
        with input_col:
            st.caption("Attached:")
            cols = st.columns(min(4, len(st.session_state.pending_attachments)))
            for idx, entry in enumerate(st.session_state.pending_attachments):
                target = cols[idx % len(cols)]
                with target:
                    if st.button(
                        f"✕ {entry['name'][:18]}",
                        key=f"rm_{entry['digest']}",
                        help="Remove attachment",
                    ):
                        _remove_pending(entry["digest"])
                        st.rerun()

    chat_disabled = st.session_state.is_generating
    with input_col:
        typed = st.chat_input(
            "Ask a research question, paste an abstract, or request a plot…",
            disabled=chat_disabled,
        )

    # Prefer queued prompt (from citation form) over chat_input when both fire.
    prompt_text = (typed or "").strip()
    if not prompt_text and st.session_state.queued_prompt:
        prompt_text = st.session_state.queued_prompt
        st.session_state.queued_prompt = None

    pending_files = _drain_pending_attachments() if prompt_text else []

    if prompt_text or pending_files:
        attachments = classify_attachments(pending_files) if pending_files else []
        for att in attachments:
            if att.get("kind") == "skipped":
                st.warning(att.get("skipped_reason", "File skipped."))

        display_text = prompt_text or "(attachments only)"
        agent_prompt = prompt_text or (
            "The user uploaded attachments without a text prompt. Analyse them and "
            "search for related TalTech and public resources."
        )

        # Persist chat row (create on first turn).
        if st.session_state.current_chat_id is None:
            st.session_state.current_chat_id = chat_store.new_chat(
                _user_email, display_text
            )

        user_msg = {"role": "user", "content": display_text, "attachments": attachments}
        st.session_state.messages.append(user_msg)
        chat_store.save_message(
            st.session_state.current_chat_id,
            _user_email,
            "user",
            display_text,
            attachments=attachments,
        )

        with st.chat_message("user", avatar=USER_AVATAR):
            _render_attachments(attachments)
            st.markdown(display_text)

        st.session_state.is_generating = True
        try:
            with st.chat_message("assistant", avatar=BOT_AVATAR):
                thinking_slot = st.empty()
                thinking_slot.markdown(
                    rotating_logo_html("Searching TalTech resources…"),
                    unsafe_allow_html=True,
                )
                try:
                    history = _build_history()
                    result = agent_run(
                        agent_prompt,
                        history=history,
                        attachments=attachments,
                    )
                finally:
                    thinking_slot.empty()

                response = result.get("content", "") if isinstance(result, dict) else str(result)
                new_artifacts = (
                    result.get("artifacts", []) if isinstance(result, dict) else []
                )
                st.markdown(response)
                _extract_and_store_bibtex(response)

            if new_artifacts:
                st.session_state.artifacts.extend(new_artifacts)

            assistant_msg = {
                "role": "assistant",
                "content": response,
                "artifacts": new_artifacts,
            }
            st.session_state.messages.append(assistant_msg)
            chat_store.save_message(
                st.session_state.current_chat_id,
                _user_email,
                "assistant",
                response,
                artifacts=new_artifacts,
            )
        finally:
            st.session_state.is_generating = False
        st.rerun()
