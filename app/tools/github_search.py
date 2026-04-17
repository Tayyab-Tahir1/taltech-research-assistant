"""
GitHub search tools: general repo search, README fetcher, and TalTech org search.

Unauthenticated: 60 req/hr.  With GITHUB_TOKEN: 5 000 req/hr.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

import requests

from app.config import GITHUB_API_URL, GITHUB_TOKEN, TALTECH_GITHUB_ORGS
from app.tools._http import HTTP_TIMEOUT, RateLimitError, get_session

logger = logging.getLogger(__name__)

_HEADERS: dict[str, str] = {"Accept": "application/vnd.github+json"}
_RAW_HEADERS: dict[str, str] = {"Accept": "application/vnd.github.raw"}
if GITHUB_TOKEN:
    _HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    _RAW_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def _check_rate_limit(resp: requests.Response) -> None:
    """Raise RateLimitError on rate-limit responses."""
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining")
        body = (resp.text or "").lower()
        if remaining == "0" or "rate limit" in body or "api rate limit" in body:
            raise RateLimitError(
                "GitHub",
                "GitHub API rate limit exceeded (X-RateLimit-Remaining=0).",
            )
    if resp.status_code == 429:
        raise RateLimitError("GitHub", "GitHub returned 429 Too Many Requests.")


def search_github_repos(
    query: str,
    language: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    q = query
    if language:
        q += f" language:{language}"

    params = {"q": q, "sort": "stars", "order": "desc", "per_page": min(top_k, 10)}
    return _repo_search(params, top_k)


def search_taltech_github(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    org_filter = " ".join(f"org:{org}" for org in TALTECH_GITHUB_ORGS)
    q = f"{query} {org_filter}"
    params = {"q": q, "sort": "stars", "order": "desc", "per_page": min(top_k, 10)}
    return _repo_search(params, top_k)


def get_github_readme(repo_full_name: str, max_chars: int = 2000) -> dict[str, Any]:
    """Fetch and decode the README for a GitHub repository."""
    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/readme"
    session = get_session()
    try:
        resp = session.get(url, headers=_HEADERS, timeout=HTTP_TIMEOUT)
        _check_rate_limit(resp)
        if resp.status_code == 404:
            return {"repo": repo_full_name, "readme_text": "", "url": "", "not_found": True}
        resp.raise_for_status()
        data = resp.json()
    except RateLimitError:
        raise
    except requests.RequestException as exc:
        logger.warning("GitHub README request failed for %s: %s", repo_full_name, exc)
        return {"repo": repo_full_name, "readme_text": "", "url": ""}
    except ValueError:
        return {"repo": repo_full_name, "readme_text": "", "url": ""}

    encoded = data.get("content", "")
    try:
        text = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        text = ""

    return {
        "repo": repo_full_name,
        "readme_text": text[:max_chars],
        "url": data.get("html_url", f"https://github.com/{repo_full_name}"),
    }


def _repo_search(params: dict, top_k: int) -> list[dict[str, Any]]:
    url = f"{GITHUB_API_URL}/search/repositories"
    session = get_session()
    try:
        resp = session.get(url, headers=_HEADERS, params=params, timeout=HTTP_TIMEOUT)
        _check_rate_limit(resp)
        resp.raise_for_status()
        data = resp.json()
    except RateLimitError:
        raise
    except requests.RequestException as exc:
        logger.warning("GitHub search request failed: %s", exc)
        return []
    except ValueError:
        return []

    results = []
    for item in data.get("items", [])[:top_k]:
        results.append(
            {
                "name": item.get("name", ""),
                "full_name": item.get("full_name", ""),
                "description": (item.get("description") or "")[:200],
                "url": item.get("html_url", ""),
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language", ""),
                "topics": item.get("topics", []),
                "updated_at": (item.get("updated_at") or "")[:10],
            }
        )
    return results
