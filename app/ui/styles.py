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
</style>
"""
    st.markdown(css, unsafe_allow_html=True)
