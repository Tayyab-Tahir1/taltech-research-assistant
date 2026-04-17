"""
Live scraper for TalTech's thesis repository: digikogu.taltech.ee

Hits the search page directly — no authentication, no local PDFs.
Returns metadata extracted from search result HTML.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.config import DIGIKOGU_SEARCH_URL
from app.tools._http import HTTP_TIMEOUT, ScraperStaleError, get_session

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TalTechResearchAgent/1.0; "
        "+https://taltech-research-assistant.streamlit.app)"
    )
}


def search_taltech_theses(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Search TalTech digikogu and return thesis metadata.

    Raises:
        ScraperStaleError: when HTTP 200 but no selectors match (structure changed).
    """
    url = DIGIKOGU_SEARCH_URL.format(query=urllib.parse.quote(query))
    session = get_session()
    try:
        response = session.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("digikogu request failed: %s", exc)
        return []

    return _parse_results(response.text, top_k, url)


def _parse_results(html: str, top_k: int, url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []

    items = (
        soup.select("li.list-group-item")
        or soup.select(".search-result-item")
        or soup.select(".result-item")
        or soup.select("li.item")
    )

    for item in items[:top_k]:
        result = _extract_item(item)
        if result:
            results.append(result)

    if not results:
        results = _fallback_extract(soup, top_k)

    if not results:
        logger.warning(
            "digikogu: all selectors missed for %s (html len=%d)", url, len(html)
        )
        raise ScraperStaleError("digikogu.taltech.ee", url)

    return results


def _extract_item(item) -> dict[str, Any] | None:
    """Extract metadata from a digikogu search result <li> element."""
    # Title + URL — anchor wraps the whole display block
    link_tag = item.select_one("a[href]")
    if not link_tag:
        return None

    href = link_tag.get("href", "")
    if href and not href.startswith("http"):
        href = "https://digikogu.taltech.ee" + href

    # Title is in a <span class="title"> inside the link
    title_tag = link_tag.select_one(".title") or link_tag
    title = title_tag.get_text(strip=True)

    # Author
    author_tag = item.select_one(".author")
    author = author_tag.get_text(strip=True) if author_tag else "Unknown"

    # Year (stored as a date string like "14.05.2026")
    year_tag = item.select_one(".year")
    year = _extract_year(year_tag.get_text(strip=True) if year_tag else "")

    # Degree type (badge next to the link, e.g. "pre-dissertations", "master")
    badge_tag = item.select_one(".badge")
    degree = badge_tag.get_text(strip=True) if badge_tag else ""

    return {
        "title": title,
        "author": author,
        "year": year,
        "degree": degree,
        "url": href,
        "snippet": "",
        "source": "taltech_digikogu",
    }


def _fallback_extract(soup: BeautifulSoup, top_k: int) -> list[dict[str, Any]]:
    """Last-resort extraction: grab any anchor with a digikogu item URL."""
    results = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if "/Item/" not in href and "/en/Item/" not in href:
            continue
        if not href.startswith("http"):
            href = "https://digikogu.taltech.ee" + href
        if href in seen:
            continue
        seen.add(href)
        results.append(
            {
                "title": a.get_text(strip=True) or "Untitled",
                "author": "Unknown",
                "year": "",
                "degree": "",
                "url": href,
                "snippet": "",
                "source": "taltech_digikogu",
            }
        )
        if len(results) >= top_k:
            break
    return results


def _extract_year(text: str) -> str:
    import re
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return match.group(0) if match else text[:10]
