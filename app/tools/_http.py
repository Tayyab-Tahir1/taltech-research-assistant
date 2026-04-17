"""Shared HTTP session and timeout constants for all tools."""
from __future__ import annotations

import requests

HTTP_TIMEOUT: tuple[int, int] = (5, 25)

_session: requests.Session | None = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": "TalTech-Research-Assistant/1.0"})
        _session = s
    return _session


class RateLimitError(Exception):
    """Raised when an external API rate limit has been exhausted."""

    def __init__(self, service: str, message: str = "") -> None:
        super().__init__(message or f"{service} rate limit exceeded")
        self.service = service


class ScraperStaleError(Exception):
    """Raised when a scraper's selectors no longer match the live page."""

    def __init__(self, source: str, url: str, message: str = "") -> None:
        super().__init__(message or f"{source} page structure changed at {url}")
        self.source = source
        self.url = url


class SourceUnavailableError(Exception):
    """Raised when an external source is temporarily unreachable or returns unexpected data."""

    def __init__(self, service: str, message: str = "") -> None:
        super().__init__(message or f"{service} temporarily unavailable")
        self.service = service
