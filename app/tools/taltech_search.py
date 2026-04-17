"""
Live scraper for TalTech's thesis repository: digikogu.taltech.ee

Hits the public search page directly — no authentication, no local PDFs.
Returns metadata extracted from search result HTML.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

from app.config import DIGIKOGU_SEARCH_URL, DIGIKOGU_SEARCH_URL_ET
from app.tools._http import get_session

logger = logging.getLogger(__name__)

# digikogu can be slow on a cold cache — give it more headroom.
_DIGIKOGU_TIMEOUT: tuple[int, int] = (10, 40)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TalTechResearchAgent/1.0; "
        "+https://taltech-research-assistant.streamlit.app)"
    ),
    "Accept-Language": "en-US,en;q=0.9,et;q=0.7",
}


def search_taltech_theses(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Search TalTech digikogu and return thesis metadata.

    Zero results is a normal outcome — returns ``[]`` rather than raising.
    Retries once against the Estonian endpoint if the English endpoint is empty,
    since a few bilingual works are only indexed there.
    """
    results = _search_one(DIGIKOGU_SEARCH_URL, query, top_k)
    if not results:
        results = _search_one(DIGIKOGU_SEARCH_URL_ET, query, top_k)
    if not results:
        logger.warning("taltech: 0 results for %r", query)
    return results


def _search_one(
    url_template: str, query: str, top_k: int
) -> list[dict[str, Any]]:
    url = url_template.format(query=urllib.parse.quote(query))
    session = get_session()
    try:
        response = session.get(url, headers=HEADERS, timeout=_DIGIKOGU_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("digikogu request failed (%s): %s", url, exc)
        return []
    return _parse_results(response.text, top_k)


def _parse_results(html: str, top_k: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    # digikogu renders each hit as:
    #   <a title="master's theses" href="/en/Item/<id>">
    #     <span class="display-view-3">
    #       <span class="title">…</span>
    #       <span class="author">…</span>
    #       <span class="year">14.05.2026</span>
    #     </span>
    #   </a>
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if "/Item/" not in href:
            continue

        abs_url = href if href.startswith("http") else "https://digikogu.taltech.ee" + href
        if abs_url in seen:
            continue

        title = _first_text(a, [".title"]) or a.get_text(" ", strip=True)
        if not title:
            continue

        author = _first_text(a, [".author", ".creator"])
        year = _extract_year(_first_text(a, [".year", ".date"]))
        degree = (a.get("title") or "").strip() or _first_text(a, [".badge", ".type"])

        # Fall back to walking up to the enclosing <li> to recover missing fields.
        if not author or not year:
            container = _nearest_container(a)
            author = author or _first_text(container, [".author", ".creator"])
            year = year or _extract_year(_first_text(container, [".year", ".date"]))

        seen.add(abs_url)
        results.append(
            {
                "title": title,
                "author": author or "Unknown",
                "year": year,
                "degree": degree,
                "url": abs_url,
                "snippet": "",
                "source": "taltech_digikogu",
            }
        )
        if len(results) >= top_k:
            break

    return results


def _first_text(node: Tag | None, selectors: list[str]) -> str:
    if node is None:
        return ""
    for sel in selectors:
        tag = node.select_one(sel)
        if tag:
            text = tag.get_text(" ", strip=True)
            if text:
                return text
    return ""


def _nearest_container(node: Tag) -> Tag | None:
    current = node
    for _ in range(6):
        current = current.parent
        if current is None:
            return None
        if getattr(current, "name", None) == "li":
            return current
    return None


def _extract_year(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return match.group(0) if match else text[:10]
