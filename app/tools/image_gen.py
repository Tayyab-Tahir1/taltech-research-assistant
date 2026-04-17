"""Native image generation via Gemini 2.0 Flash.

Returns an artifact descriptor so the UI can render the PNG inline in the
chat bubble, matching the flow for ``generate_plot`` / ``run_analysis``.
"""
from __future__ import annotations

import base64
import logging
import uuid
from typing import Any

from app.config import get_secret

logger = logging.getLogger(__name__)

_IMAGE_MODEL = "gemini-2.0-flash-exp"
_MAX_PROMPT_LEN = 1200


def generate_image(prompt: str, aspect_ratio: str = "1:1") -> dict[str, Any]:
    """Generate an image from a text prompt via Gemini native image output.

    ``aspect_ratio`` is accepted for forward-compatibility but is encoded into
    the prompt rather than passed as a config field — the 2.0 Flash image
    preview doesn't expose a structured aspect-ratio control yet.
    """
    clean = (prompt or "").strip()
    if not clean:
        return {"status": "error", "message": "Empty image prompt.", "artifacts": []}
    if len(clean) > _MAX_PROMPT_LEN:
        clean = clean[:_MAX_PROMPT_LEN]

    api_key = get_secret("GOOGLE_API_KEY", "")
    if not api_key:
        return {
            "status": "error",
            "message": "GOOGLE_API_KEY is not set — cannot generate images.",
            "artifacts": [],
        }

    try:
        from google import genai  # noqa: WPS433
        from google.genai import types  # noqa: WPS433
    except ImportError as exc:
        logger.error("google-genai import failed: %s", exc)
        return {
            "status": "error",
            "message": "google-genai SDK not installed.",
            "artifacts": [],
        }

    full_prompt = (
        f"{clean}\n\nRender as a {aspect_ratio} aspect-ratio image."
        if aspect_ratio and aspect_ratio != "1:1"
        else clean
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_IMAGE_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )
    except Exception as exc:
        logger.exception("Gemini image generation failed")
        return {
            "status": "error",
            "message": f"Image generation failed: {exc}",
            "artifacts": [],
        }

    artifacts: list[dict[str, Any]] = []
    caption_parts: list[str] = []

    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                raw = inline.data
                if isinstance(raw, (bytes, bytearray)):
                    payload_b64 = base64.b64encode(bytes(raw)).decode("ascii")
                else:
                    payload_b64 = str(raw)
                artifacts.append(
                    {
                        "id": f"img_{uuid.uuid4().hex[:8]}",
                        "kind": "image",
                        "mime": getattr(inline, "mime_type", None) or "image/png",
                        "title": clean[:80],
                        "payload": payload_b64,
                    }
                )
                continue
            text = getattr(part, "text", None)
            if text:
                caption_parts.append(text)

    if not artifacts:
        return {
            "status": "error",
            "message": "Model did not return an image — try a more concrete prompt.",
            "artifacts": [],
        }

    return {
        "status": "ok",
        "caption": "".join(caption_parts).strip(),
        "artifacts": artifacts,
    }
