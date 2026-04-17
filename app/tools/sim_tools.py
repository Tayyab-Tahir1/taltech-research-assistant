"""
Simulation tools catalog loader from YAML file.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import yaml

from app.config import CATALOG_PATH

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_catalog() -> list[dict[str, Any]]:
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("tools", [])
    except (OSError, yaml.YAMLError) as exc:
        logger.error("Failed to load simulation tools catalog: %s", exc)
        return []


def get_simulation_tools(domain: str | None = None) -> list[dict[str, Any]]:
    """Return simulation tools, optionally filtered by engineering domain.

    Args:
        domain: Optional domain string, e.g. "mechanical", "robotics", "CFD".
                Case-insensitive substring match against tool's domain list.

    Returns:
        List of tool dicts: name, domain, description, license, access, url, docs_url.
    """
    tools = _load_catalog()
    if not domain:
        return tools

    domain_lower = domain.lower()
    filtered = []
    for tool in tools:
        domains = tool.get("domain", [])
        if isinstance(domains, str):
            domains = [domains]
        if any(domain_lower in d.lower() for d in domains):
            filtered.append(tool)
    return filtered
