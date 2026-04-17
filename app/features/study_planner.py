"""Build a week-by-week study plan as a table artifact.

Calls the FAST model to produce JSON rows, then emits a table artifact that
the UI renders inline in the assistant message.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from app import llm

logger = logging.getLogger(__name__)

_MIN_WEEKS = 1
_MAX_WEEKS = 26
_MIN_HPW = 1
_MAX_HPW = 60

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def build_study_plan(
    topic: str,
    weeks: int = 6,
    hours_per_week: int = 8,
    milestones: list[str] | None = None,
) -> dict[str, Any]:
    """Return a structured study plan + a table artifact for inline rendering."""
    topic_clean = (topic or "").strip()
    if not topic_clean:
        return {"status": "error", "message": "Empty topic.", "artifacts": []}

    weeks = max(_MIN_WEEKS, min(_MAX_WEEKS, int(weeks) if weeks else 6))
    hours_per_week = max(_MIN_HPW, min(_MAX_HPW, int(hours_per_week) if hours_per_week else 8))

    milestone_block = ""
    if milestones:
        bullets = "\n".join(f"- {m}" for m in milestones if isinstance(m, str) and m.strip())
        if bullets:
            milestone_block = f"\n\nRequired milestones the plan must hit:\n{bullets}"

    system = (
        "You are a study-plan designer for engineering graduate students. "
        "Produce a realistic, progressively deepening plan. "
        "Return ONLY a JSON object with a single key 'rows' whose value is a "
        "list of objects with keys: week (int), focus (str), reading (str), "
        "output (str), hours (int). No prose, no markdown fences."
    )
    user = (
        f"Topic: {topic_clean}\n"
        f"Duration: {weeks} weeks at {hours_per_week} hours/week.\n"
        f"Each week should have a distinct focus, one concrete reading/resource, "
        f"and one deliverable output.{milestone_block}"
    )

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
        logger.exception("study planner call failed")
        return {
            "status": "error",
            "message": f"LLM call failed: {exc}",
            "artifacts": [],
        }

    rows = _extract_rows(response.content or "")
    if not rows:
        return {
            "status": "error",
            "message": "Could not parse a study plan from the model output.",
            "artifacts": [],
        }

    rows = _normalize_rows(rows, weeks=weeks, hours_per_week=hours_per_week)

    artifact = {
        "id": f"plan_{uuid.uuid4().hex[:8]}",
        "kind": "table",
        "mime": "application/json",
        "title": f"Study plan: {topic_clean[:60]} ({weeks} weeks)",
        "payload": rows,
    }
    return {
        "status": "ok",
        "topic": topic_clean,
        "weeks": weeks,
        "hours_per_week": hours_per_week,
        "rows": rows,
        "artifacts": [artifact],
    }


def _extract_rows(text: str) -> list[dict]:
    if not text:
        return []

    candidates: list[str] = []
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text.strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("rows"), list):
            return [r for r in parsed["rows"] if isinstance(r, dict)]
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict)]
    return []


def _normalize_rows(
    rows: list[dict], *, weeks: int, hours_per_week: int
) -> list[dict]:
    cleaned: list[dict] = []
    for idx, row in enumerate(rows[:weeks], start=1):
        cleaned.append(
            {
                "week": int(row.get("week") or idx),
                "focus": str(row.get("focus") or "").strip(),
                "reading": str(row.get("reading") or "").strip(),
                "output": str(row.get("output") or "").strip(),
                "hours": int(row.get("hours") or hours_per_week),
            }
        )
    return cleaned
