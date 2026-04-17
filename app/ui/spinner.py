"""Rotating TalTech logo used as the agent-thinking indicator.

Usage:
    from app.ui.spinner import rotating_logo_html
    placeholder = st.empty()
    placeholder.markdown(rotating_logo_html("Searching TalTech theses…"),
                         unsafe_allow_html=True)
    # … run the work …
    placeholder.empty()
"""
from __future__ import annotations

from html import escape

from app.ui.assets import logo_b64

_TEMPLATE = """
<div class="taltech-thinking" role="status" aria-live="polite">
  <img src="{src}" alt="TalTech logo" class="taltech-spin" />
  <span class="taltech-thinking-label">{label}</span>
</div>
<style>
.taltech-thinking {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.5rem 0;
    color: #003366;
    font-weight: 500;
}}
.taltech-spin {{
    width: 32px;
    height: 32px;
    animation: taltechRotate 2s linear infinite;
    transform-origin: 50% 50%;
}}
@keyframes taltechRotate {{
    from {{ transform: rotate(0deg); }}
    to   {{ transform: rotate(360deg); }}
}}
@media (prefers-reduced-motion: reduce) {{
    .taltech-spin {{ animation: none; }}
}}
</style>
"""

_FALLBACK_SRC = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<circle cx='12' cy='12' r='10' fill='%23003366'/></svg>"
)


def rotating_logo_html(label: str = "Thinking…") -> str:
    """Return an HTML snippet rendering the rotating TalTech logo + label."""
    b64 = logo_b64()
    src = f"data:image/png;base64,{b64}" if b64 else _FALLBACK_SRC
    return _TEMPLATE.format(src=src, label=escape(label))
