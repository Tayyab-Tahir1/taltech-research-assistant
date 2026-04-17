"""Right-hand artifact panel — renders plots, tables, and code blocks."""
from __future__ import annotations

import json
from typing import Any

import streamlit as st


def render_artifact_panel(artifacts: list[dict[str, Any]]) -> None:
    """Render all artifacts collected so far into the current Streamlit column."""
    st.subheader("Artifacts")
    if not artifacts:
        st.caption(
            "Plots, tables, and code from analysis tools will appear here."
        )
        return

    labels = [_label(a, idx) for idx, a in enumerate(artifacts)]
    tabs = st.tabs(labels)
    for tab, artifact in zip(tabs, artifacts):
        with tab:
            _render_one(artifact)


def _label(artifact: dict, idx: int) -> str:
    title = artifact.get("title") or artifact.get("kind", f"artifact {idx + 1}")
    icon = {
        "plot": "📈",
        "table": "📊",
        "code": "📝",
        "text": "🧾",
    }.get(artifact.get("kind", ""), "🗂️")
    return f"{icon} {title}"[:40]


def _render_one(artifact: dict[str, Any]) -> None:
    kind = artifact.get("kind")
    payload = artifact.get("payload")

    if kind == "plot":
        _render_plot(payload)
    elif kind == "table":
        _render_table(payload, artifact.get("id", "table"))
    elif kind == "code":
        _render_code(payload)
    elif kind == "text":
        st.code(payload or "", language="text")
    else:
        st.write(payload)


def _render_plot(payload: Any) -> None:
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
        st.plotly_chart(payload, use_container_width=True)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not render plot: {exc}")


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


def _render_code(payload: Any) -> None:
    code = payload if isinstance(payload, str) else str(payload)
    st.code(code, language="python")
