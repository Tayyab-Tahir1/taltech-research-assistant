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
from app.ui.artifacts import render_inline_artifacts
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


def _current_user_provider() -> str | None:
    """Return a human label for which OAuth provider signed the user in."""
    if not _auth_enabled():
        return None
    try:
        if not getattr(st.user, "is_logged_in", False):
            return None
        iss = getattr(st.user, "iss", "") or ""
        if "microsoft" in iss or "microsoftonline" in iss:
            return "Microsoft"
        if "google" in iss or "accounts.google.com" in iss:
            return "Google"
    except Exception:
        return None
    return None


def _provider_configured(name: str) -> bool:
    try:
        auth = st.secrets.get("auth")
        if not auth:
            return False
        return bool(auth.get(name))
    except Exception:
        return False


def _render_login_screen() -> None:
    st.markdown('<div class="landing-hero">', unsafe_allow_html=True)
    if BOT_AVATAR is not None:
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            st.image(BOT_AVATAR, width=110)
    st.markdown(
        "<h1>TalTech Research Assistant</h1>"
        "<p>Sign in to access your chat history and research workspace.</p>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    has_google = _provider_configured("google")
    has_microsoft = _provider_configured("microsoft")

    if has_google and has_microsoft:
        col_g, col_m = st.columns(2)
        with col_g:
            if st.button(
                "Continue with Google",
                type="primary",
                use_container_width=True,
                key="login_google",
            ):
                st.login("google")
        with col_m:
            if st.button(
                "Continue with Microsoft",
                use_container_width=True,
                key="login_microsoft",
            ):
                st.login("microsoft")
    elif has_microsoft:
        if st.button(
            "Continue with Microsoft",
            type="primary",
            use_container_width=True,
            key="login_microsoft",
        ):
            st.login("microsoft")
    else:
        if st.button(
            "Continue with Google",
            type="primary",
            use_container_width=True,
            key="login_google",
        ):
            st.login("google")

    st.markdown(
        "<div class='landing-footer'>"
        "By continuing, you agree to the TalTech terms."
        "</div>",
        unsafe_allow_html=True,
    )


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
        logo_l, logo_c, logo_r = st.columns([1, 2, 1])
        with logo_c:
            st.image(BOT_AVATAR, width=140)
    st.markdown(
        "<h2 style='text-align:center;margin:0.25rem 0 0.5rem 0'>TalTech Agent</h2>",
        unsafe_allow_html=True,
    )
    st.caption(f"Backend: {BACKEND_LABEL}")
    _provider_label = _current_user_provider()
    if _provider_label:
        st.caption(f"Signed in with {_provider_label} · **{_user_email}**")
    else:
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
# Empty-state hero appears only on a fresh chat.
if not st.session_state.messages:
    st.markdown(
        "<div class='empty-state'>"
        "<h1>What are you researching today?</h1>"
        "<p>Ask about TalTech theses, papers, datasets, simulation tools, or paste "
        "an abstract. Generate citations, plots, study plans, or code reviews.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

# Render chat history inline — artifacts persist across reruns.
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar=_avatar_for(msg["role"])):
        _render_attachments(msg.get("attachments") or [])
        st.markdown(msg["content"])
        render_inline_artifacts(msg.get("artifacts") or [])

# Render pending-attachment chips as a compact flex row above the composer.
if st.session_state.pending_attachments:
    st.markdown('<div class="attachment-chips">', unsafe_allow_html=True)
    chip_cols = st.columns(len(st.session_state.pending_attachments))
    for idx, entry in enumerate(st.session_state.pending_attachments):
        with chip_cols[idx]:
            label = entry["name"]
            if len(label) > 22:
                label = label[:20] + "…"
            if st.button(
                f"✕ {label}",
                key=f"rm_{entry['digest']}",
                help=f"Remove {entry['name']}",
            ):
                _remove_pending(entry["digest"])
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# Composer: + popover overlaid on the chat input via CSS.
st.markdown('<div class="composer">', unsafe_allow_html=True)
with st.popover("➕", use_container_width=False):
    uploaded = st.file_uploader(
        "Upload PDF or image",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="plus_uploader",
    )
    if uploaded:
        for f in uploaded:
            _queue_attachment(f)

    with st.form("cite_form", clear_on_submit=True):
        cite_query = st.text_input(
            "Cite a source",
            label_visibility="collapsed",
            placeholder="Cite a source (DOI, title, URL)",
            key="cite_query_field",
        )
        cite_submit = st.form_submit_button(
            "Generate citation", use_container_width=True
        )
        if cite_submit and cite_query.strip():
            st.session_state.queued_prompt = (
                f"Generate BibTeX, IEEE, and APA citations for: "
                f"{cite_query.strip()}"
            )

chat_disabled = st.session_state.is_generating
typed = st.chat_input(
    "Ask a research question, paste an abstract, or request a plot…",
    disabled=chat_disabled,
)
st.markdown("</div>", unsafe_allow_html=True)

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
            render_inline_artifacts(new_artifacts)
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
