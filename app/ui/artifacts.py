"""Inline artifact renderer — emits plots, tables, images, and code inline."""
from __future__ import annotations

import base64
import json
from typing import Any

import streamlit as st


def render_inline_artifacts(artifacts: list[dict[str, Any]]) -> None:
    """Render artifacts inline inside the current Streamlit container.

    Each artifact is emitted in place (no column, no tabs), matching the
    ChatGPT/Claude inline-artifact flow.
    """
    if not artifacts:
        return
    for artifact in artifacts:
        _render_one(artifact)


def _render_one(artifact: dict[str, Any]) -> None:
    kind = artifact.get("kind")
    payload = artifact.get("payload")
    title = artifact.get("title")

    if title:
        st.caption(title)

    if kind == "plot":
        _render_plot(payload, artifact.get("id", "plot"))
    elif kind == "table":
        _render_table(payload, artifact.get("id", "table"))
    elif kind == "image":
        _render_image(payload, artifact.get("mime", "image/png"))
    elif kind == "code":
        _render_code(payload, artifact.get("mime"))
    elif kind == "markdown":
        st.markdown(payload or "")
    elif kind == "text":
        st.code(payload or "", language="text")
    else:
        st.write(payload)


def _render_plot(payload: Any, artifact_id: str) -> None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            st.error("Plot payload is not valid JSON.")
            return
    if not isinstance(payload, dict):
        st.error("Plot payload missing.")
        return
    try:
        st.plotly_chart(
            payload, use_container_width=True, key=f"plot_{artifact_id}"
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not render plot: {exc}")


def _render_image(payload: Any, mime: str) -> None:
    if not payload:
        st.error("Image payload missing.")
        return
    try:
        if isinstance(payload, (bytes, bytearray)):
            raw = bytes(payload)
        else:
            raw = base64.b64decode(str(payload))
        st.image(raw, use_container_width=True)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not render image: {exc}")


def _render_table(payload: Any, artifact_id: str) -> None:
    try:
        import pandas as pd
    except ImportError:
        st.error("pandas is not installed — cannot render table.")
        return

    if isinstance(payload, dict) and "columns" in payload and "rows" in payload:
        df = pd.DataFrame(payload["rows"], columns=payload["columns"])
    elif isinstance(payload, list):
        df = pd.DataFrame(payload)
    else:
        st.write(payload)
        return

    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"{artifact_id}.csv",
        mime="text/csv",
        key=f"csv_{artifact_id}",
    )


def _render_code(payload: Any, mime: str | None = None) -> None:
    code = payload if isinstance(payload, str) else str(payload)
    lang = "python"
    if mime and mime.startswith("text/x-"):
        lang = mime[len("text/x-") :] or "python"
    st.code(code, language=lang)
