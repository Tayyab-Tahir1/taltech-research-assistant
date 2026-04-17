"""
Academic paper search via Semantic Scholar Graph API.

Free tier: ~100 requests/5 min. No API key needed for basic use.
Returns papers with title, authors, abstract, year, and open-access PDF link.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.config import SEMANTIC_SCHOLAR_URL, SEMANTIC_SCHOLAR_FIELDS
from app.tools._http import HTTP_TIMEOUT, get_session

logger = logging.getLogger(__name__)

_LAST_CALL: float = 0.0
_MIN_INTERVAL = 1.1  # respect ~1 RPS rate limit


def search_papers(
    query: str,
    max_results: int = 5,
    year_filter: str = "",
) -> list[dict[str, Any]]:
    """Search Semantic Scholar for academic papers.

    Args:
        query: Search query (title words, topic, etc.).
        max_results: Number of papers to return (max 10 per call).
        year_filter: Optional year range like "2020-2024" or "2022-".

    Returns:
        List of dicts: title, authors, abstract, year, pdf_url, url.
    """
    _rate_limit()
    params: dict[str, Any] = {
        "query": query,
        "limit": min(max_results, 10),
        "fields": SEMANTIC_SCHOLAR_FIELDS,
    }
    if year_filter:
        params["year"] = year_filter

    session = get_session()
    try:
        resp = session.get(SEMANTIC_SCHOLAR_URL, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("Semantic Scholar request failed: %s", exc)
        return []
    except ValueError:
        logger.warning("Semantic Scholar returned invalid JSON")
        return []

    papers = []
    for item in data.get("data", []):
        papers.append(_format_paper(item))
    return papers


def _format_paper(item: dict) -> dict[str, Any]:
    authors = [a.get("name", "") for a in item.get("authors", [])]
    pdf_url = ""
    oap = item.get("openAccessPdf")
    if oap:
        pdf_url = oap.get("url", "")

    external_ids = item.get("externalIds") or {}
    url = item.get("url") or ""
    if not url:
        doi = external_ids.get("DOI")
        if doi:
            url = f"https://doi.org/{doi}"
        arxiv_id = external_ids.get("ArXiv")
        if arxiv_id and not url:
            url = f"https://arxiv.org/abs/{arxiv_id}"

    return {
        "title": item.get("title", "Untitled"),
        "authors": authors,
        "abstract": (item.get("abstract") or "")[:500],
        "year": item.get("year"),
        "pdf_url": pdf_url,
        "url": url,
    }


def _rate_limit() -> None:
    global _LAST_CALL
    elapsed = time.time() - _LAST_CALL
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_CALL = time.time()
