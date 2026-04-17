"""
TalTech Research Assistant — Streamlit UI

ChatGPT-style interface with sidebar controls, source cards, BibTeX export,
and support for bilingual (Estonian + English) queries.
"""
from __future__ import annotations

import os
import sys

# Ensure the project root (Hackathon/) is first in sys.path so that
# 'app' resolves to the app/ package, not this file (app.py) itself.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from datetime import datetime

import streamlit as st

from app.config import BACKEND_LABEL, validate_secrets
from app.agent import run as agent_run
from app.features.bibtex_extractor import extract_bibtex_entries
from app.logging_config import setup_logging
from app.ui.assets import logo_pil_image
from app.ui.spinner import rotating_logo_html
from app.ui.styles import inject_css

setup_logging()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TalTech Research Assistant",
    page_icon=logo_pil_image(),
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

# ── Secrets validation banner ─────────────────────────────────────────────────
_secret_problems = validate_secrets()
if _secret_problems:
    for _p in _secret_problems:
        st.error(_p)

# ── Helper functions (defined first so sidebar can call them) ─────────────────

def _augment_prompt(user_prompt: str, mode: str) -> str:
    if mode == "Find Research Gaps":
        return (
            f"[MODE: Research Gap Analysis] {user_prompt}\n\n"
            "Use find_research_gaps to analyse how well this topic is covered in "
            "TalTech theses, then suggest unexplored angles."
        )
    if mode == "Similar Thesis Finder":
        return (
            f"[MODE: Similar Thesis Finder] {user_prompt}\n\n"
            "The user has provided their thesis abstract. Use find_similar_theses "
            "to find related TalTech theses and Semantic Scholar papers."
        )
    if mode == "Cite a Source":
        return (
            f"[MODE: Citation Generator] {user_prompt}\n\n"
            "Generate BibTeX, IEEE, and APA citations for the source described. "
            "Search for it first if needed to get accurate metadata."
        )
    return user_prompt


def _build_history() -> list[dict]:
    """Convert session messages to OpenAI message format (last 20 turns)."""
    history = []
    for msg in st.session_state.messages[-20:]:
        history.append({"role": msg["role"], "content": msg["content"]})
    return history


def _extract_and_store_bibtex(response: str) -> None:
    """Find BibTeX blocks in the response and store them for export."""
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


# ── Session state init ────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []        # list of {role, content}
if "bibtex_store" not in st.session_state:
    st.session_state.bibtex_store = []    # collected BibTeX strings
if "mode" not in st.session_state:
    st.session_state.mode = "Research Assistant"
if "is_generating" not in st.session_state:
    st.session_state.is_generating = False

MODES = [
    "Research Assistant",
    "Find Research Gaps",
    "Similar Thesis Finder",
    "Cite a Source",
]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎓 TalTech Agent")
    st.caption(f"Backend: {BACKEND_LABEL}")
    st.divider()

    mode = st.radio("Mode", MODES, index=MODES.index(st.session_state.mode))
    st.session_state.mode = mode

    st.divider()
    st.subheader("Actions")
    col1, col2 = st.columns(2)

    if col1.button("📥 Export"):
        chat_md = _build_chat_export()
        st.download_button(
            "Download chat",
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

    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.bibtex_store = []
        st.rerun()

    st.divider()
    with st.expander("ℹ️ How to use"):
        st.markdown("""
**Research Assistant** — Ask anything:
- *Find papers on SLAM in robotics*
- *Leia andmestikud vibratsioonanalüüsi jaoks*
- *What simulation tools does TalTech have?*

**Find Research Gaps** — Discover under-researched topics:
- *What robotics topics haven't been studied at TalTech?*

**Similar Thesis Finder** — Paste your abstract:
- The agent finds related TalTech theses and papers

**Cite a Source** — Generate BibTeX / IEEE / APA:
- *Generate BibTeX for the first result*
""")

# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🎓 TalTech Research Assistant")
st.caption(
    "Bilingual (ET/EN) · Thesis · Papers · Datasets · Simulation Tools · GitHub"
)

MODE_PROMPTS = {
    "Research Assistant": "Ask your research question here…",
    "Find Research Gaps": "Describe a topic and I'll check how well it's covered at TalTech…",
    "Similar Thesis Finder": "Paste your thesis abstract and I'll find similar work…",
    "Cite a Source": "Tell me what to cite (paste the title or URL)…",
}

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input — disabled while a response is streaming to avoid races.
placeholder = MODE_PROMPTS.get(mode, "Ask your research question here…")
chat_disabled = st.session_state.is_generating
prompt = st.chat_input(placeholder, disabled=chat_disabled)
if prompt:
    augmented = _augment_prompt(prompt, mode)

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.is_generating = True
    try:
        with st.chat_message("assistant"):
            thinking_slot = st.empty()
            thinking_slot.markdown(
                rotating_logo_html("Searching TalTech resources…"),
                unsafe_allow_html=True,
            )
            try:
                history = _build_history()
                response = agent_run(augmented, history=history)
            finally:
                thinking_slot.empty()

            st.markdown(response)
            _extract_and_store_bibtex(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
    finally:
        st.session_state.is_generating = False
