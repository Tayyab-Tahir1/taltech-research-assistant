"""
arXiv paper search via the arXiv Query API (Atom XML).

Free, no auth required. Used as a public fallback when Semantic Scholar
is rate-limited or returns nothing.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import requests

from app.config import ARXIV_API_URL
from app.tools._http import HTTP_TIMEOUT, SourceUnavailableError, get_session

logger = logging.getLogger(__name__)

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def search_arxiv(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search arXiv for papers matching the query.

    Args:
        query: Free-text query.
        limit: Number of results (max 25).

    Returns:
        List of dicts with title, authors, abstract, year, url, pdf_url, source="arxiv".

    Raises:
        SourceUnavailableError: When arXiv is unreachable or returns bad data.
    """
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": min(max(limit, 1), 25),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    session = get_session()
    try:
        resp = session.get(ARXIV_API_URL, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("arXiv request failed: %s", exc)
        raise SourceUnavailableError(
            "arXiv", f"arXiv unreachable: {exc}"
        ) from exc

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        logger.warning("arXiv returned invalid XML: %s", exc)
        raise SourceUnavailableError(
            "arXiv", "arXiv returned an unexpected (non-XML) response."
        ) from exc

    results: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", _NS):
        parsed = _parse_entry(entry)
        if parsed:
            results.append(parsed)
    return results


def _parse_entry(entry: ET.Element) -> dict[str, Any] | None:
    title_el = entry.find("atom:title", _NS)
    title = (title_el.text or "").strip() if title_el is not None else ""
    if not title:
        return None

    summary_el = entry.find("atom:summary", _NS)
    abstract = (summary_el.text or "").strip() if summary_el is not None else ""

    authors = []
    for a in entry.findall("atom:author", _NS):
        name_el = a.find("atom:name", _NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    published_el = entry.find("atom:published", _NS)
    year: int | None = None
    if published_el is not None and published_el.text:
        try:
            year = int(published_el.text[:4])
        except ValueError:
            year = None

    abs_url = ""
    pdf_url = ""
    for link in entry.findall("atom:link", _NS):
        rel = link.get("rel", "")
        link_type = link.get("type", "")
        href = link.get("href", "")
        if link_type == "application/pdf":
            pdf_url = href
        elif rel == "alternate":
            abs_url = href

    return {
        "title": " ".join(title.split()),
        "authors": authors,
        "abstract": " ".join(abstract.split())[:500],
        "year": year,
        "pdf_url": pdf_url,
        "url": abs_url,
        "source": "arxiv",
    }
