"""
Centralised logging setup for the TalTech Research Assistant.

Call `setup_logging()` once from the app entry point. Tool modules can then
`logger = logging.getLogger(__name__)` and emit INFO for calls and WARN for
fallbacks; the UI does not need to know about this.
"""
from __future__ import annotations

import logging
import os

_CONFIGURED = False

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Third-party loggers that flood at INFO level.
_NOISY_LOGGERS = ("urllib3", "httpx", "httpcore", "openai")


def setup_logging(level: str | int | None = None) -> None:
    """Install a single root handler; safe to call more than once.

    Args:
        level: override level (e.g. "DEBUG"). Defaults to `LOG_LEVEL` env var
               or INFO.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved = level or os.getenv("LOG_LEVEL", "INFO")
    if isinstance(resolved, str):
        resolved = resolved.upper()

    logging.basicConfig(
        level=resolved,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
    )

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _CONFIGURED = True
