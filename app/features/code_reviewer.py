"""Lightweight code reviewer — returns findings + the original snippet as artifacts."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app import llm

logger = logging.getLogger(__name__)

_MAX_CODE = 8000

_FOCI = {
    "bugs+style": "Highlight bugs, logic errors, readability issues, and style violations.",
    "bugs": "Focus on correctness and likely bugs only.",
    "style": "Focus on readability, naming, and idiomatic style only.",
    "security": "Focus on security issues: input validation, injection, unsafe calls.",
    "performance": "Focus on performance: algorithmic complexity, allocations, I/O.",
}


def review_code(
    code: str,
    language: str = "python",
    focus: str = "bugs+style",
) -> dict[str, Any]:
    """Review ``code`` and return findings markdown + the code itself as artifacts."""
    snippet = (code or "").strip()
    if not snippet:
        return {"status": "error", "message": "Empty code.", "artifacts": []}
    if len(snippet) > _MAX_CODE:
        snippet = snippet[:_MAX_CODE]

    focus_key = (focus or "bugs+style").strip().lower()
    focus_instruction = _FOCI.get(focus_key, _FOCI["bugs+style"])
    lang = (language or "python").strip().lower()

    system = (
        "You are an experienced code reviewer. "
        f"{focus_instruction} "
        "Return markdown with exactly these sections: "
        "'## Summary' (2-3 sentences), "
        "'## Findings' (numbered list; for each item include **Severity**: "
        "CRITICAL/HIGH/MEDIUM/LOW, the line or pattern, and a suggested fix), "
        "and '## Suggested refactor' (short code block or 'None needed'). "
        "Be concrete. Quote exact identifiers when referring to the code."
    )
    user = f"Language: {lang}\n\n```{lang}\n{snippet}\n```"

    try:
        response = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            tools=[],
            deep=False,
        )
    except Exception as exc:
        logger.exception("code reviewer call failed")
        return {
            "status": "error",
            "message": f"LLM call failed: {exc}",
            "artifacts": [],
        }

    findings = (response.content or "").strip()
    if not findings:
        return {
            "status": "error",
            "message": "Model returned empty review.",
            "artifacts": [],
        }

    artifacts = [
        {
            "id": f"review_{uuid.uuid4().hex[:8]}",
            "kind": "markdown",
            "mime": "text/markdown",
            "title": f"Code review ({lang}, focus: {focus_key})",
            "payload": findings,
        },
        {
            "id": f"code_{uuid.uuid4().hex[:8]}",
            "kind": "code",
            "mime": f"text/x-{lang}",
            "title": f"Reviewed snippet ({lang})",
            "payload": snippet,
        },
    ]
    return {
        "status": "ok",
        "language": lang,
        "focus": focus_key,
        "findings": findings,
        "artifacts": artifacts,
    }
