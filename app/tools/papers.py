"""
Academic paper search via Semantic Scholar Graph API.

Free tier: ~100 requests/5 min. With SEMANTIC_SCHOLAR_API_KEY: 100 RPS.
Returns papers with title, authors, abstract, year, and open-access PDF link.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.config import (
    SEMANTIC_SCHOLAR_API_KEY,
    SEMANTIC_SCHOLAR_FIELDS,
    SEMANTIC_SCHOLAR_URL,
)
from app.tools._http import (
    HTTP_TIMEOUT,
    RateLimitError,
    SourceUnavailableError,
    get_session,
)

logger = logging.getLogger(__name__)

_LAST_CALL: float = 0.0
_MIN_INTERVAL = 1.1  # respect ~1 RPS rate limit on the free tier

_HEADERS: dict[str, str] = {}
if SEMANTIC_SCHOLAR_API_KEY:
    _HEADERS["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY


def _check_rate_limit(resp: requests.Response) -> None:
    """Raise RateLimitError on rate-limit responses."""
    if resp.status_code == 429:
        raise RateLimitError(
            "SemanticScholar",
            "Semantic Scholar returned 429 Too Many Requests — "
            "set SEMANTIC_SCHOLAR_API_KEY to raise the limit.",
        )
    if resp.status_code == 403:
        body = (resp.text or "").lower()
        if "rate" in body or "limit" in body or "quota" in body:
            raise RateLimitError(
                "SemanticScholar",
                "Semantic Scholar rate-limited this IP "
                "(shared cloud IP likely throttled). "
                "Set SEMANTIC_SCHOLAR_API_KEY or try again in a minute.",
            )


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
        List of dicts with source stamp "semantic_scholar".

    Raises:
        RateLimitError: When Semantic Scholar throttles this request.
        SourceUnavailableError: When the API is unreachable or returns unexpected data.
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
        resp = session.get(
            SEMANTIC_SCHOLAR_URL,
            params=params,
            headers=_HEADERS or None,
            timeout=HTTP_TIMEOUT,
        )
        _check_rate_limit(resp)
        resp.raise_for_status()
        data = resp.json()
    except RateLimitError:
        raise
    except requests.RequestException as exc:
        logger.warning("Semantic Scholar request failed: %s", exc)
        raise SourceUnavailableError(
            "SemanticScholar",
            f"Semantic Scholar unreachable: {exc}",
        ) from exc
    except ValueError as exc:
        logger.warning("Semantic Scholar returned invalid JSON: %s", exc)
        raise SourceUnavailableError(
            "SemanticScholar",
            "Semantic Scholar returned an unexpected response (invalid JSON).",
        ) from exc

    if not isinstance(data, dict) or "data" not in data:
        raise SourceUnavailableError(
            "SemanticScholar",
            "Semantic Scholar returned an unexpected response schema.",
        )

    return [_format_paper(item) for item in data.get("data", [])]


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
        "source": "semantic_scholar",
    }


def _rate_limit() -> None:
    global _LAST_CALL
    elapsed = time.time() - _LAST_CALL
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_CALL = time.time()
