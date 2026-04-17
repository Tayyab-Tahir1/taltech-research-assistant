"""OpenAI + local-vLLM adapter.

Both share the OpenAI wire format, so the only thing that changes between
them is the base URL + API key used to construct the client.
"""
from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.config import LLM_BACKEND, get_secret
from app.llm.router import ChatResponse, ToolCall


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    if LLM_BACKEND == "local":
        base = get_secret("LOCAL_MODEL_URL", "").rstrip("/")
        return OpenAI(
            base_url=base + "/v1",
            api_key=get_secret("LOCAL_MODEL_API_KEY", "none"),
        )
    return OpenAI(api_key=get_secret("OPENAI_API_KEY", "") or "missing")


def chat(
    messages: list[dict],
    tools: list[dict],
    *,
    model: str,
) -> ChatResponse:
    kwargs: dict = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = _client().chat.completions.create(**kwargs)
    msg = response.choices[0].message

    tool_calls: list[ToolCall] = []
    for tc in msg.tool_calls or []:
        tool_calls.append(
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
        )

    return ChatResponse(
        content=msg.content or "",
        tool_calls=tool_calls,
        raw_message=msg.model_dump(exclude_none=True),
    )
