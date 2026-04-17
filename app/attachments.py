"""
Helpers for handling uploaded PDF and image attachments from Streamlit's
chat_input. PDFs are extracted to plain text; images are converted to base64
data URLs for GPT-4o vision.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB per file
MAX_PDF_PAGES = 20
MAX_PDF_CHARS = 20_000

IMAGE_MIME_MAP = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


def _ext(name: str) -> str:
    return (name.rsplit(".", 1)[-1] if "." in name else "").lower()


def _read_bytes(uploaded_file) -> bytes:
    """Read the uploaded file's bytes without consuming the stream permanently."""
    data = uploaded_file.read()
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    return data


def is_oversize(uploaded_file) -> bool:
    size = getattr(uploaded_file, "size", None)
    if size is None:
        size = len(_read_bytes(uploaded_file))
    return size > MAX_FILE_BYTES


def pdf_to_text(uploaded_file, max_pages: int = MAX_PDF_PAGES,
                max_chars: int = MAX_PDF_CHARS) -> str:
    """Extract text from an uploaded PDF. Returns empty string on failure."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed; cannot extract PDF text")
        return ""

    data = _read_bytes(uploaded_file)
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        logger.warning("Failed to open PDF %s: %s", getattr(uploaded_file, "name", "?"), exc)
        return ""

    parts: list[str] = []
    total = 0
    for page in reader.pages[:max_pages]:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        parts.append(txt)
        total += len(txt)
        if total >= max_chars:
            break

    return "\n\n".join(parts)[:max_chars].strip()


def image_to_data_url(uploaded_file) -> str:
    """Return a base64 data URL for an image upload."""
    data = _read_bytes(uploaded_file)
    ext = _ext(getattr(uploaded_file, "name", ""))
    mime = IMAGE_MIME_MAP.get(ext)
    if not mime:
        guessed, _ = mimetypes.guess_type(getattr(uploaded_file, "name", ""))
        mime = guessed or "image/png"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def classify_attachments(files: list) -> list[dict[str, Any]]:
    """Convert Streamlit UploadedFile objects into normalized dicts.

    Returns list of {"kind": "pdf"|"image", "name", "text" or "data_url", "skipped_reason"}.
    Oversize / unsupported files get a skipped_reason and empty payload.
    """
    out: list[dict[str, Any]] = []
    for f in files or []:
        name = getattr(f, "name", "upload")
        ext = _ext(name)

        if is_oversize(f):
            out.append({"kind": "skipped", "name": name,
                        "skipped_reason": f"{name} exceeds 5 MB limit"})
            continue

        if ext == "pdf":
            text = pdf_to_text(f)
            out.append({"kind": "pdf", "name": name, "text": text})
        elif ext in IMAGE_MIME_MAP:
            data_url = image_to_data_url(f)
            out.append({"kind": "image", "name": name, "data_url": data_url})
        else:
            out.append({"kind": "skipped", "name": name,
                        "skipped_reason": f"{name}: unsupported file type"})
    return out
