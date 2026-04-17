"""Route :func:`chat` calls to the configured backend adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import FAST_MODEL, LLM_BACKEND


@dataclass(frozen=True)
class ToolCall:
    """One function call requested by the model."""

    id: str
    name: str
    arguments: str  # JSON string, to match OpenAI's shape


@dataclass(frozen=True)
class ChatResponse:
    """Adapter-agnostic model reply."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Raw assistant-message dict to append back to ``messages`` for the next turn.
    # Shape follows the OpenAI ``chat.completions`` message format so the agent
    # loop can stay identical across backends.
    raw_message: dict[str, Any] = field(default_factory=dict)


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    model: str | None = None,
    deep: bool = False,
) -> ChatResponse:
    """Run a single chat turn against the configured backend.

    Args:
        messages: OpenAI-shape message list. System, user, assistant, and tool
            roles are all accepted; adapters translate as needed.
        tools: OpenAI-shape tool schemas (``[{"type":"function","function":...}]``).
        model: Override the default model. When ``None``, FAST_MODEL is used
            unless ``deep=True``, in which case DEEP_MODEL is selected.
        deep: Request the deeper / slower model (e.g. Gemini 2.5 Pro with
            thinking) for heavy synthesis tasks.
    """
    if LLM_BACKEND == "gemini":
        from app.llm import gemini

        return gemini.chat(messages, tools or [], model=model, deep=deep)

    # openai and local both speak the OpenAI wire format
    from app.llm import openai_compat

    return openai_compat.chat(
        messages,
        tools or [],
        model=model or FAST_MODEL,
    )
