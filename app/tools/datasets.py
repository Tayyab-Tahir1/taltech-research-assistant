"""
Dataset search via Kaggle API and Zenodo REST API.

Kaggle requires KAGGLE_USERNAME + KAGGLE_KEY env vars.
Zenodo is free and requires no authentication.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from app.config import KAGGLE_USERNAME, KAGGLE_KEY
from app.tools._http import HTTP_TIMEOUT, get_session

logger = logging.getLogger(__name__)

ZENODO_SEARCH_URL = "https://zenodo.org/api/records"
KAGGLE_API_URL = "https://www.kaggle.com/api/v1/datasets/list"


def search_datasets(
    query: str,
    sources: list[str] | None = None,
    max_results: int = 5,
) -> dict[str, Any]:
    """Search for research datasets across Kaggle and Zenodo.

    Returns:
        Dict with keys `results` (list of dataset dicts) and `warnings`
        (list of strings describing partial/skipped sources). The agent surfaces
        these to the user so they know when a source was unavailable.
    """
    if sources is None:
        sources = ["zenodo", "kaggle"]

    results: list[dict[str, Any]] = []
    warnings: list[str] = []

    if "zenodo" in sources:
        zenodo_results, zenodo_warning = _search_zenodo(query, max_results)
        results.extend(zenodo_results)
        if zenodo_warning:
            warnings.append(zenodo_warning)

    if "kaggle" in sources:
        if KAGGLE_USERNAME and KAGGLE_KEY:
            kaggle_results, kaggle_warning = _search_kaggle(query, max_results)
            results.extend(kaggle_results)
            if kaggle_warning:
                warnings.append(kaggle_warning)
        else:
            warnings.append(
                "Kaggle credentials not configured (KAGGLE_USERNAME + KAGGLE_KEY) "
                "— Kaggle was skipped. Zenodo results only."
            )
            logger.info("Kaggle credentials not configured — skipping Kaggle search")

    return {"results": results, "warnings": warnings}


def _search_zenodo(query: str, limit: int) -> tuple[list[dict[str, Any]], str]:
    params = {
        "q": query,
        "size": limit,
        "sort": "mostrecent",
        "type": "dataset",
    }
    session = get_session()
    try:
        resp = session.get(ZENODO_SEARCH_URL, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("Zenodo request failed: %s", exc)
        return [], "Zenodo temporarily unavailable — please retry later."
    except ValueError:
        return [], "Zenodo returned an invalid response."

    results = []
    for hit in data.get("hits", {}).get("hits", []):
        meta = hit.get("metadata", {})
        files = hit.get("files", [])
        size = sum(f.get("size", 0) for f in files)
        formats = list({f.get("type", "") for f in files if f.get("type")})
        results.append(
            {
                "name": meta.get("title", "Untitled"),
                "description": (meta.get("description") or "")[:300],
                "url": f"https://zenodo.org/record/{hit.get('id', '')}",
                "size": _format_size(size),
                "format": ", ".join(formats) or "N/A",
                "source": "Zenodo",
                "license": meta.get("license", {}).get("id", ""),
            }
        )
    return results, ""


def _search_kaggle(query: str, limit: int) -> tuple[list[dict[str, Any]], str]:
    params = {"search": query, "page": 1, "pageSize": limit}
    session = get_session()
    try:
        resp = session.get(
            KAGGLE_API_URL,
            params=params,
            auth=(KAGGLE_USERNAME, KAGGLE_KEY),
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("Kaggle request failed: %s", exc)
        return [], "Kaggle temporarily unavailable — please retry later."
    except ValueError:
        return [], "Kaggle returned an invalid response."

    results = []
    for ds in data[:limit]:
        results.append(
            {
                "name": ds.get("title", "Untitled"),
                "description": (ds.get("subtitle") or "")[:300],
                "url": f"https://www.kaggle.com/datasets/{ds.get('ref', '')}",
                "size": _format_size(ds.get("totalBytes", 0)),
                "format": ds.get("fileType", "N/A"),
                "source": "Kaggle",
                "license": ds.get("licenseName", ""),
            }
        )
    return results, ""


def _format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} PB"
