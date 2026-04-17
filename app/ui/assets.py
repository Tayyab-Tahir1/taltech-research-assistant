"""
Base64-encoded asset loader for branding images.

Images are read from the project `images/` directory once per Streamlit process
and cached via `st.cache_resource` so the bytes are not re-read on every rerun.
"""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
_IMAGES_DIR = _ROOT / "images"

LOGO_PATH = _IMAGES_DIR / "logo-taltech-1.png"
BG_PATH = _IMAGES_DIR / "taltech bg1.png"
PROFILE_PATH = _IMAGES_DIR / "profile.png"


@st.cache_resource(show_spinner=False)
def _b64(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def logo_b64() -> str:
    """Return the TalTech logo as a base64-encoded PNG string."""
    return _b64(str(LOGO_PATH))


def bg_b64() -> str:
    """Return the TalTech sidebar background as a base64-encoded PNG string."""
    return _b64(str(BG_PATH))


@st.cache_resource(show_spinner=False)
def _pil_image(path_str: str):
    """Return a PIL Image for the given asset path, or None if unavailable."""
    try:
        from PIL import Image
    except ImportError:
        return None
    path = Path(path_str)
    if not path.exists():
        return None
    with path.open("rb") as fh:
        return Image.open(BytesIO(fh.read())).copy()


def logo_image():
    """Return the TalTech logo as a PIL Image (or None)."""
    return _pil_image(str(LOGO_PATH))


def profile_image():
    """Return the user profile image as a PIL Image (or None)."""
    return _pil_image(str(PROFILE_PATH))


@st.cache_resource(show_spinner=False)
def logo_pil_image():
    """Return the logo as a PIL Image for use as the Streamlit favicon.

    Falls back to the graduation-cap emoji string if Pillow or the file is
    missing so the app stays importable in minimal environments.
    """
    try:
        from PIL import Image  # local import — keeps cold-start cheap
    except ImportError:
        return "🎓"
    if not LOGO_PATH.exists():
        return "🎓"
    with LOGO_PATH.open("rb") as fh:
        return Image.open(BytesIO(fh.read())).copy()
