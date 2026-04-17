"""Global CSS injection for TalTech branding.

Call `inject_css()` exactly once from `app.py`, after `st.set_page_config`.
"""
from __future__ import annotations

import streamlit as st

from app.ui.assets import bg_b64

_NAVY = "#003366"
_NAVY_SOFT = "rgba(0, 51, 102, 0.85)"
_SIDEBAR_TEXT = "#FFFFFF"


def _sidebar_background_rule(bg_data: str) -> str:
    """Return the sidebar background-image rule, or an empty string if missing."""
    if not bg_data:
        return ""
    return (
        "[data-testid=\"stSidebar\"] > div:first-child {\n"
        f"  background-image: linear-gradient({_NAVY_SOFT}, {_NAVY_SOFT}),\n"
        f"    url(\"data:image/png;base64,{bg_data}\");\n"
        "  background-size: cover;\n"
        "  background-position: center;\n"
        "  background-repeat: no-repeat;\n"
        "}\n"
    )


def inject_css() -> None:
    bg_data = bg_b64()
    sidebar_bg = _sidebar_background_rule(bg_data)

    css = f"""
<style>
{sidebar_bg}

/* Sidebar text readability over the navy overlay */
[data-testid="stSidebar"], [data-testid="stSidebar"] * {{
    color: {_SIDEBAR_TEXT};
}}
[data-testid="stSidebar"] a {{
    color: #BFD4EC;
    text-decoration: underline;
}}
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] .stButton button,
[data-testid="stSidebar"] .stMarkdown {{
    color: {_SIDEBAR_TEXT};
}}
[data-testid="stSidebar"] .stButton button {{
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.25);
}}
[data-testid="stSidebar"] .stButton button:hover {{
    background-color: rgba(255, 255, 255, 0.18);
    border-color: rgba(255, 255, 255, 0.45);
}}

/* Main-area title in navy */
main h1 {{
    color: {_NAVY};
    letter-spacing: -0.01em;
}}

/* Assistant chat bubble: soft navy-tinted card */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
    background-color: #F4F6FA;
    border-left: 3px solid {_NAVY};
    border-radius: 8px;
    padding: 0.75rem 1rem;
}}

/* User chat bubble: subtle gray */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
    background-color: #FAFAFA;
    border-radius: 8px;
    padding: 0.75rem 1rem;
}}

/* Empty-state hero (ChatGPT-style) */
.empty-state {{
    text-align: center;
    padding: 4rem 1rem 2rem 1rem;
    max-width: 720px;
    margin: 0 auto;
}}
.empty-state h1 {{
    font-size: 2.25rem;
    color: {_NAVY};
    margin-bottom: 0.5rem;
    letter-spacing: -0.01em;
}}
.empty-state p {{
    color: #5B6B82;
    font-size: 1.05rem;
    margin: 0;
}}

/* Composer: wraps the + popover and chat input so the + sits inside */
.composer {{
    position: relative;
}}
.composer [data-testid="stPopover"] {{
    position: absolute;
    left: 10px;
    bottom: 8px;
    z-index: 10;
}}
.composer [data-testid="stPopover"] button {{
    min-height: 32px;
    height: 32px;
    width: 32px;
    padding: 0;
    border-radius: 16px;
}}
.composer [data-testid="stChatInput"] textarea {{
    padding-left: 52px !important;
}}

/* Attachment chips row — compact, single-line, ellipsised */
.attachment-chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 0 0 6px 0;
}}
.attachment-chips .stButton button {{
    max-width: 180px;
    height: 28px;
    min-height: 28px;
    padding: 0 10px;
    font-size: 0.8rem;
    line-height: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    border-radius: 14px;
    background-color: #F1F4F9;
    border: 1px solid #D6DEEA;
    color: #1F2937;
}}
.attachment-chips .stButton button:hover {{
    background-color: #E4EAF5;
    border-color: #A8B9D1;
}}

/* Sidebar history rows — left-aligned with hover-only three-dots */
.sidebar-row-wrapper [data-testid="column"]:first-child .stButton button {{
    text-align: left !important;
    justify-content: flex-start !important;
    background-color: transparent;
    border: none;
    padding-left: 8px;
}}
.sidebar-row-wrapper [data-testid="column"]:first-child .stButton button:hover {{
    background-color: rgba(255, 255, 255, 0.12);
}}
.sidebar-row-wrapper [data-testid="column"]:last-child [data-testid="stPopover"] {{
    opacity: 0;
    transition: opacity 120ms ease-in;
}}
.sidebar-row-wrapper:hover [data-testid="column"]:last-child [data-testid="stPopover"] {{
    opacity: 1;
}}

/* Landing screen — centered provider buttons */
.landing-hero {{
    text-align: center;
    padding: 3rem 1rem 1rem 1rem;
    max-width: 480px;
    margin: 0 auto;
}}
.landing-hero h1 {{
    font-size: 2rem;
    color: {_NAVY};
    margin: 0.75rem 0 0.25rem 0;
}}
.landing-hero p {{
    color: #5B6B82;
    margin: 0 0 1.5rem 0;
}}
.landing-footer {{
    text-align: center;
    color: #8A95A8;
    font-size: 0.8rem;
    margin-top: 1.5rem;
}}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)
