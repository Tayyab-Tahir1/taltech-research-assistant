"""Google Gemini 2.5 adapter.

Translates OpenAI-shape messages + tool schemas to the ``google-genai`` SDK
and converts the Gemini reply back into our :class:`ChatResponse`.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from functools import lru_cache
from typing import Any

from app.config import DEEP_MODEL, FAST_MODEL, get_secret
from app.llm.router import ChatResponse, ToolCall

logger = logging.getLogger(__name__)

_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


@lru_cache(maxsize=1)
def _client():
    from google import genai  # noqa: WPS433

    api_key = get_secret("GOOGLE_API_KEY", "")
    return genai.Client(api_key=api_key or "missing")


def chat(
    messages: list[dict],
    tools: list[dict],
    *,
    model: str | None,
    deep: bool,
) -> ChatResponse:
    from google.genai import types  # noqa: WPS433

    target_model = model or (DEEP_MODEL if deep else FAST_MODEL)
    system_instruction, contents = _to_gemini_contents(messages, types)
    gemini_tools = _to_gemini_tools(tools, types) if tools else None

    config_kwargs: dict[str, Any] = {}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if gemini_tools:
        config_kwargs["tools"] = gemini_tools
    if deep:
        # Pro thinking budget: let the model reason for up to ~8k tokens
        # before producing output. ``-1`` would be unlimited; keep a cap so
        # free-tier TPM budgets aren't exhausted by a single turn.
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=8192)

    response = _client().models.generate_content(
        model=target_model,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    return _from_gemini_response(response)


# ── Message translation ───────────────────────────────────────────────────────

def _to_gemini_contents(messages: list[dict], types) -> tuple[str, list]:
    """Split messages into (system_instruction, gemini_contents)."""
    system_parts: list[str] = []
    contents: list = []

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            if isinstance(msg.get("content"), str):
                system_parts.append(msg["content"])
            continue

        if role == "user":
            contents.append(_user_message_to_content(msg, types))
        elif role == "assistant":
            content = _assistant_message_to_content(msg, types)
            if content is not None:
                contents.append(content)
        elif role == "tool":
            contents.append(_tool_message_to_content(msg, types))

    return ("\n\n".join(system_parts).strip(), contents)


def _user_message_to_content(msg: dict, types):
    parts: list = []
    content = msg.get("content")
    if isinstance(content, str):
        parts.append(types.Part.from_text(text=content))
    elif isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                parts.append(types.Part.from_text(text=part.get("text", "")))
            elif ptype == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                m = _DATA_URL_RE.match(url)
                if m:
                    try:
                        data = base64.b64decode(m.group("data"))
                        parts.append(
                            types.Part.from_bytes(
                                data=data, mime_type=m.group("mime")
                            )
                        )
                    except Exception as exc:
                        logger.warning("Failed to decode image for Gemini: %s", exc)
    if not parts:
        parts.append(types.Part.from_text(text=""))
    return types.Content(role="user", parts=parts)


def _assistant_message_to_content(msg: dict, types):
    parts: list = []
    content = msg.get("content")
    if isinstance(content, str) and content:
        parts.append(types.Part.from_text(text=content))

    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        name = fn.get("name", "")
        args_json = fn.get("arguments", "{}")
        try:
            args = json.loads(args_json) if isinstance(args_json, str) else (args_json or {})
        except json.JSONDecodeError:
            args = {}
        parts.append(types.Part.from_function_call(name=name, args=args))

    if not parts:
        return None
    return types.Content(role="model", parts=parts)


def _tool_message_to_content(msg: dict, types):
    """A tool-result message becomes a user Content with a FunctionResponse part."""
    raw = msg.get("content", "")
    try:
        response_dict = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except json.JSONDecodeError:
        response_dict = {"result": raw}
    if not isinstance(response_dict, dict):
        response_dict = {"result": response_dict}

    # Gemini doesn't track tool_call_id the way OpenAI does; it matches by name.
    # We stash the name in the message during the dispatch loop.
    name = msg.get("name") or msg.get("tool_name") or "tool"
    return types.Content(
        role="user",
        parts=[types.Part.from_function_response(name=name, response=response_dict)],
    )


# ── Tool-schema translation ───────────────────────────────────────────────────

def _to_gemini_tools(openai_tools: list[dict], types) -> list:
    declarations = []
    for tool in openai_tools:
        fn = tool.get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        declarations.append(
            types.FunctionDeclaration(
                name=name,
                description=fn.get("description", ""),
                parameters=_json_schema_to_gemini(fn.get("parameters") or {}, types),
            )
        )
    if not declarations:
        return []
    return [types.Tool(function_declarations=declarations)]


_TYPE_MAP = {
    "object": "OBJECT",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
}


def _json_schema_to_gemini(schema: dict, types):
    """Convert a JSON-schema dict (OpenAI tool parameters) to a Gemini Schema."""
    if not isinstance(schema, dict) or not schema:
        return types.Schema(type="OBJECT", properties={})

    kwargs: dict[str, Any] = {}
    raw_type = schema.get("type", "object")
    kwargs["type"] = _TYPE_MAP.get(raw_type, "STRING")

    if "description" in schema:
        kwargs["description"] = schema["description"]
    if "enum" in schema:
        kwargs["enum"] = [str(v) for v in schema["enum"]]
    if raw_type == "object":
        props = schema.get("properties") or {}
        kwargs["properties"] = {
            k: _json_schema_to_gemini(v, types) for k, v in props.items()
        }
        required = schema.get("required")
        if required:
            kwargs["required"] = list(required)
    if raw_type == "array":
        items = schema.get("items") or {"type": "string"}
        kwargs["items"] = _json_schema_to_gemini(items, types)

    return types.Schema(**kwargs)


# ── Response translation ──────────────────────────────────────────────────────

def _from_gemini_response(response) -> ChatResponse:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    raw_tool_calls: list[dict] = []

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        for part in (getattr(content, "parts", None) or []):
            fc = getattr(part, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                call_id = f"call_{len(tool_calls) + 1}"
                args_obj = dict(getattr(fc, "args", {}) or {})
                args_json = json.dumps(args_obj, ensure_ascii=False)
                tool_calls.append(
                    ToolCall(id=call_id, name=fc.name, arguments=args_json)
                )
                raw_tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": fc.name, "arguments": args_json},
                    }
                )
                continue
            text = getattr(part, "text", None)
            if text:
                text_parts.append(text)

    content_text = "".join(text_parts).strip()
    raw_message: dict[str, Any] = {"role": "assistant", "content": content_text}
    if raw_tool_calls:
        raw_message["tool_calls"] = raw_tool_calls

    return ChatResponse(
        content=content_text,
        tool_calls=tool_calls,
        raw_message=raw_message,
    )
