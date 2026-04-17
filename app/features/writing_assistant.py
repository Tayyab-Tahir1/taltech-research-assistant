"""Writing assistant — polish, summarize, expand, or translate a block of text.

Wraps a single FAST-model call with a task-specific prompt. Returns plain
rewritten text so the agent loop can embed it in the final response.
"""
from __future__ import annotations

import logging

from app import llm

logger = logging.getLogger(__name__)

_MAX_INPUT = 6000

_TASKS = {
    "polish": (
        "Rewrite the following text to improve clarity, grammar, and flow. "
        "Preserve meaning and technical terms. Return ONLY the rewritten text."
    ),
    "summarize": (
        "Summarise the following text. Keep all key technical facts. "
        "Return ONLY the summary prose."
    ),
    "expand": (
        "Expand the following text with additional supporting detail and examples, "
        "keeping the author's voice. Return ONLY the expanded text."
    ),
    "translate_et": (
        "Translate the following text into Estonian. Preserve technical "
        "terminology. Return ONLY the Estonian translation."
    ),
    "translate_en": (
        "Translate the following text into English. Preserve technical "
        "terminology. Return ONLY the English translation."
    ),
}

_TONES = {
    "academic": "Use a formal academic tone suitable for a thesis or journal paper.",
    "casual": "Use a clear conversational tone.",
    "concise": "Be terse and direct — minimise filler.",
    "engineering": "Use precise engineering terminology.",
}

_LENGTHS = {
    "same": "Target roughly the same length as the input.",
    "shorter": "Aim for about half the length of the input.",
    "longer": "Aim for about 1.5× the length of the input.",
}


def polish_text(
    text: str,
    task: str = "polish",
    tone: str = "academic",
    target_length: str = "same",
) -> dict:
    """Rewrite ``text`` according to ``task`` / ``tone`` / ``target_length``."""
    clean = (text or "").strip()
    if not clean:
        return {"status": "error", "message": "Empty text."}
    if len(clean) > _MAX_INPUT:
        clean = clean[:_MAX_INPUT]

    task_key = (task or "polish").strip().lower()
    task_instruction = _TASKS.get(task_key)
    if task_instruction is None:
        return {
            "status": "error",
            "message": f"Unknown task {task!r}. Use one of: {sorted(_TASKS)}",
        }

    tone_instruction = _TONES.get((tone or "academic").lower(), _TONES["academic"])
    length_instruction = _LENGTHS.get(
        (target_length or "same").lower(), _LENGTHS["same"]
    )

    system = (
        "You are a careful writing assistant. "
        f"{task_instruction} {tone_instruction} {length_instruction} "
        "Do not add commentary, headings, or quotation marks around the output."
    )

    try:
        response = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": clean},
            ],
            tools=[],
            deep=False,
        )
    except Exception as exc:
        logger.exception("writing assistant call failed")
        return {"status": "error", "message": f"LLM call failed: {exc}"}

    rewritten = (response.content or "").strip()
    if not rewritten:
        return {"status": "error", "message": "Model returned empty output."}

    return {
        "status": "ok",
        "task": task_key,
        "tone": tone,
        "rewritten": rewritten,
    }
