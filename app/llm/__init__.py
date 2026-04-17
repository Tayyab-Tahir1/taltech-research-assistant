"""LLM adapter layer.

Exposes a single entry point :func:`chat` that hides the differences between
Gemini, OpenAI, and a local OpenAI-compatible vLLM. Agents should depend only
on this module, never on a concrete SDK client.
"""
from __future__ import annotations

from app.llm.router import ChatResponse, ToolCall, chat

__all__ = ["ChatResponse", "ToolCall", "chat"]
