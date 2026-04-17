"""
Central configuration: LLM backend selection, model names, and environment.

Three backends are supported via ``LLM_BACKEND``:
    - ``gemini`` (default): Google Gemini 2.5 (Flash/Pro) via ``google-genai``.
    - ``openai``: GPT-4o (or any OpenAI-compatible model) via ``openai`` SDK.
    - ``local``:  Self-hosted vLLM behind an OpenAI-compatible endpoint.

Secrets are read from (in order): ``st.secrets`` (Streamlit Cloud), then
``os.environ`` / ``.env``.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Read a secret from st.secrets when available, falling back to os.environ."""
    try:
        import streamlit as st  # noqa: WPS433

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


# ── LLM backend selection ─────────────────────────────────────────────────────
# Priority: explicit LLM_BACKEND env var > LOCAL_MODEL_URL presence > default gemini
_local_url: str = _get_secret("LOCAL_MODEL_URL", "").rstrip("/")
_explicit_backend: str = _get_secret("LLM_BACKEND", "").strip().lower()

if _explicit_backend in {"gemini", "openai", "local"}:
    LLM_BACKEND: str = _explicit_backend
elif _local_url:
    LLM_BACKEND = "local"
elif _get_secret("GOOGLE_API_KEY", ""):
    LLM_BACKEND = "gemini"
elif _get_secret("OPENAI_API_KEY", ""):
    LLM_BACKEND = "openai"
else:
    LLM_BACKEND = "gemini"  # default; will warn on missing key below

# ── Model names (adapter-specific) ────────────────────────────────────────────
# Two logical tiers: FAST (tool-calling, short turns) and DEEP (reasoning, synthesis).
if LLM_BACKEND == "gemini":
    FAST_MODEL: str = _get_secret("GEMINI_FAST_MODEL", "gemini-2.5-flash")
    DEEP_MODEL: str = _get_secret("GEMINI_DEEP_MODEL", "gemini-2.5-pro")
    BACKEND_LABEL: str = f"Gemini ({FAST_MODEL} / {DEEP_MODEL})"
elif LLM_BACKEND == "openai":
    FAST_MODEL = _get_secret("OPENAI_MODEL", "gpt-4o")
    DEEP_MODEL = _get_secret("OPENAI_DEEP_MODEL", FAST_MODEL)
    BACKEND_LABEL = f"OpenAI ({FAST_MODEL})"
else:  # local
    FAST_MODEL = _get_secret("LOCAL_MODEL_NAME", "google/gemma-2-27b-it")
    DEEP_MODEL = _get_secret("LOCAL_DEEP_MODEL", FAST_MODEL)
    BACKEND_LABEL = f"Local vLLM ({FAST_MODEL})"

# Backwards-compat alias used by a few legacy imports.
MODEL: str = FAST_MODEL

# ── Optional API keys ─────────────────────────────────────────────────────────
KAGGLE_USERNAME = _get_secret("KAGGLE_USERNAME", "")
KAGGLE_KEY = _get_secret("KAGGLE_KEY", "")
GITHUB_TOKEN = _get_secret("GITHUB_TOKEN", "")

# ── Paths ─────────────────────────────────────────────────────────────────────
CATALOG_PATH = Path(__file__).parent / "catalog" / "simulation_tools.yaml"

# DATA_DIR resolution order:
#   1. CHATS_DATA_DIR env / secret override
#   2. /gpfs/mariana/home/tayyab/Hackathon/data (HPC default; survives redeploys)
#   3. project-local ./data
# On Streamlit Cloud the gpfs path is unreachable — we fall back to /tmp.
_STREAMLIT_CLOUD: bool = _get_secret("STREAMLIT_CLOUD", "").lower() in {"1", "true", "yes"}
_HPC_DATA_DIR = Path("/gpfs/mariana/home/tayyab/Hackathon/data")
_LOCAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_data_dir_override: str = _get_secret("CHATS_DATA_DIR", "").strip()
if _data_dir_override:
    DATA_DIR = Path(_data_dir_override)
    CHATS_DB_EPHEMERAL = False
elif _STREAMLIT_CLOUD:
    DATA_DIR = Path("/tmp")
    CHATS_DB_EPHEMERAL = True
elif _HPC_DATA_DIR.parent.exists():
    DATA_DIR = _HPC_DATA_DIR
    CHATS_DB_EPHEMERAL = False
else:
    DATA_DIR = _LOCAL_DATA_DIR
    CHATS_DB_EPHEMERAL = False

CHATS_DB_PATH = DATA_DIR / "chats.db"

# ── Semantic Scholar ──────────────────────────────────────────────────────────
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = "title,authors,abstract,year,openAccessPdf,url,externalIds"
SEMANTIC_SCHOLAR_API_KEY = _get_secret("SEMANTIC_SCHOLAR_API_KEY", "")

# ── arXiv ─────────────────────────────────────────────────────────────────────
ARXIV_API_URL = "http://export.arxiv.org/api/query"

# ── TalTech digikogu ──────────────────────────────────────────────────────────
# The live search form uses `?search=<q>`; older `Query[1]=` URLs silently
# return the full unfiltered catalog.
DIGIKOGU_SEARCH_URL = "https://digikogu.taltech.ee/en/Search/Items?search={query}"
DIGIKOGU_SEARCH_URL_ET = "https://digikogu.taltech.ee/et/Search/Items?search={query}"

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_API_URL = "https://api.github.com"
TALTECH_GITHUB_ORGS = ["TalTech-IVAR", "taltech"]


def validate_secrets() -> list[str]:
    """Return a list of human-readable problems with the current secret configuration.

    Empty list means "looks good". Call this from the UI to render a banner
    rather than crashing on first query.
    """
    problems: list[str] = []

    has_openai = bool(_get_secret("OPENAI_API_KEY", ""))
    has_gemini = bool(_get_secret("GOOGLE_API_KEY", ""))
    has_local = bool(_local_url)

    if LLM_BACKEND == "gemini" and not has_gemini:
        problems.append(
            "Gemini backend selected but `GOOGLE_API_KEY` is missing. "
            "Add it to your environment, `.env`, or Streamlit Cloud secrets — "
            "or set `LLM_BACKEND=openai` to use GPT-4o instead."
        )
    elif LLM_BACKEND == "openai" and not has_openai:
        problems.append(
            "OpenAI backend selected but `OPENAI_API_KEY` is missing."
        )
    elif LLM_BACKEND == "local" and not has_local:
        problems.append(
            "Local backend selected but `LOCAL_MODEL_URL` is missing."
        )

    kaggle_user = _get_secret("KAGGLE_USERNAME", "")
    kaggle_key = _get_secret("KAGGLE_KEY", "")
    if bool(kaggle_user) ^ bool(kaggle_key):
        problems.append(
            "Kaggle credentials are half-set: both `KAGGLE_USERNAME` "
            "and `KAGGLE_KEY` are required for dataset search."
        )

    return problems


def get_secret(key: str, default: str = "") -> str:
    """Public accessor for adapter modules that need secrets."""
    return _get_secret(key, default)
