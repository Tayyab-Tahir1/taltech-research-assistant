"""
Central configuration: LLM client, model selection, and environment variables.
Supports both OpenAI API (default) and local vLLM via SLURM (if LOCAL_MODEL_URL is set).

Secrets are read from (in order): st.secrets (Streamlit Cloud), os.environ / .env.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

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


# ── LLM backend ──────────────────────────────────────────────────────────────
_local_url = _get_secret("LOCAL_MODEL_URL", "").rstrip("/")

if _local_url:
    client = OpenAI(
        base_url=_local_url + "/v1",
        api_key=_get_secret("LOCAL_MODEL_API_KEY", "none"),
    )
    MODEL = _get_secret("LOCAL_MODEL_NAME", "google/gemma-2-27b-it")
    BACKEND_LABEL = f"Local vLLM ({MODEL})"
else:
    api_key = _get_secret("OPENAI_API_KEY", "")
    if not api_key:
        import warnings
        warnings.warn(
            "OPENAI_API_KEY is not set — agent calls will fail. "
            "Set it in your environment, .env file, or Streamlit Cloud secrets.",
            stacklevel=2,
        )
    client = OpenAI(api_key=api_key or "missing")
    MODEL = _get_secret("OPENAI_MODEL", "gpt-4o")
    BACKEND_LABEL = f"OpenAI ({MODEL})"

# ── Optional API keys ─────────────────────────────────────────────────────────
KAGGLE_USERNAME = _get_secret("KAGGLE_USERNAME", "")
KAGGLE_KEY = _get_secret("KAGGLE_KEY", "")
GITHUB_TOKEN = _get_secret("GITHUB_TOKEN", "")

# ── Paths ─────────────────────────────────────────────────────────────────────
CATALOG_PATH = Path(__file__).parent / "catalog" / "simulation_tools.yaml"

# ── Semantic Scholar ──────────────────────────────────────────────────────────
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = "title,authors,abstract,year,openAccessPdf,url,externalIds"

# ── TalTech digikogu ──────────────────────────────────────────────────────────
DIGIKOGU_SEARCH_URL = (
    "https://digikogu.taltech.ee/en/Search/Items"
    "?Query%5B1%5D={query}&SortType=-47"
)

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
    has_local = bool(_local_url)
    if not (has_openai or has_local):
        problems.append(
            "No LLM backend configured: set `OPENAI_API_KEY` "
            "(or `LOCAL_MODEL_URL` for a self-hosted vLLM) "
            "in your environment or Streamlit Cloud secrets."
        )

    kaggle_user = _get_secret("KAGGLE_USERNAME", "")
    kaggle_key = _get_secret("KAGGLE_KEY", "")
    if bool(kaggle_user) ^ bool(kaggle_key):
        problems.append(
            "Kaggle credentials are half-set: both `KAGGLE_USERNAME` "
            "and `KAGGLE_KEY` are required for dataset search."
        )

    return problems
