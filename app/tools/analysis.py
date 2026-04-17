"""Analysis and visualisation tools that emit artifact descriptors.

Two agent-callable entry points:

- :func:`generate_plot` — deterministic Plotly JSON builder (no code execution).
- :func:`run_analysis` — runs short Python snippets in a restricted subprocess,
  returning any stdout, stderr, tables, and figures as artifacts.

Artifact descriptors follow this shape so :mod:`app.ui.artifacts` can render
any backend-produced item uniformly::

    {
        "id":      "art_<n>",        # stable per-run id
        "kind":    "plot"|"table"|"code"|"text",
        "mime":    "application/vnd.plotly.v1+json"|"application/vnd.dataframe+json"
                   |"text/x-python"|"text/plain",
        "title":   "Optional label for the panel tab",
        "payload": {...}             # JSON-serialisable plot spec, dataframe,
                                     # or code string (depends on kind)
    }

The tool return value itself is::

    {"status": "ok"|"error", "message": "...", "artifacts": [descriptor, ...]}
"""
from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_PLOTLY_MIME = "application/vnd.plotly.v1+json"
_DF_MIME = "application/vnd.dataframe+json"
_SUPPORTED_KINDS = {"bar", "line", "scatter", "hist", "pie"}
_SANDBOX_TIMEOUT_S = 15
_MAX_STDOUT_CHARS = 20_000


def _artifact_id() -> str:
    return "art_" + uuid.uuid4().hex[:10]


# ── generate_plot ─────────────────────────────────────────────────────────────

def generate_plot(
    kind: str,
    data: dict,
    options: dict | None = None,
) -> dict[str, Any]:
    """Build a Plotly figure spec from a small JSON payload.

    Args:
        kind: One of ``bar``, ``line``, ``scatter``, ``hist``, ``pie``.
        data: Shape depends on ``kind``. Common keys: ``x``, ``y``, ``values``,
            ``labels``, ``series`` (list of {name, x, y}).
        options: Optional ``title``, ``x_label``, ``y_label``, ``color``.

    Returns an artifact descriptor dict.
    """
    options = options or {}
    if kind not in _SUPPORTED_KINDS:
        return _error(
            f"Unsupported plot kind '{kind}'. "
            f"Supported: {sorted(_SUPPORTED_KINDS)}."
        )

    try:
        spec = _build_plot_spec(kind, data, options)
    except Exception as exc:
        logger.exception("generate_plot failed")
        return _error(f"Failed to build plot: {exc}")

    artifact = {
        "id": _artifact_id(),
        "kind": "plot",
        "mime": _PLOTLY_MIME,
        "title": options.get("title") or kind.capitalize(),
        "payload": spec,
    }
    return {"status": "ok", "artifacts": [artifact]}


def _build_plot_spec(kind: str, data: dict, options: dict) -> dict:
    title = options.get("title")
    x_label = options.get("x_label")
    y_label = options.get("y_label")
    color = options.get("color")

    traces: list[dict] = []

    if "series" in data and isinstance(data["series"], list):
        for s in data["series"]:
            traces.append(_trace_from_series(kind, s, color))
    else:
        traces.append(_trace_from_series(kind, data, color))

    layout: dict[str, Any] = {
        "margin": {"l": 48, "r": 16, "t": 48, "b": 48},
        "template": "plotly_white",
    }
    if title:
        layout["title"] = {"text": title}
    if x_label:
        layout["xaxis"] = {"title": {"text": x_label}}
    if y_label:
        layout["yaxis"] = {"title": {"text": y_label}}

    return {"data": traces, "layout": layout}


def _trace_from_series(kind: str, s: dict, color: str | None) -> dict:
    trace: dict[str, Any] = {"name": s.get("name", "")}
    marker: dict[str, Any] = {}
    if color:
        marker["color"] = color

    if kind == "bar":
        trace.update({"type": "bar", "x": s.get("x") or [], "y": s.get("y") or []})
    elif kind == "line":
        trace.update(
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": s.get("x") or [],
                "y": s.get("y") or [],
            }
        )
    elif kind == "scatter":
        trace.update(
            {
                "type": "scatter",
                "mode": "markers",
                "x": s.get("x") or [],
                "y": s.get("y") or [],
            }
        )
    elif kind == "hist":
        trace.update(
            {
                "type": "histogram",
                "x": s.get("x") or s.get("values") or [],
                "nbinsx": s.get("nbinsx"),
            }
        )
    elif kind == "pie":
        trace.update(
            {
                "type": "pie",
                "labels": s.get("labels") or [],
                "values": s.get("values") or [],
            }
        )
    if marker:
        trace["marker"] = marker
    return trace


# ── run_analysis ──────────────────────────────────────────────────────────────

_SANDBOX_PREAMBLE = textwrap.dedent(
    """
    import json as __json, sys as __sys, os as __os
    __artifacts = []

    def emit_table(df, title=None):
        import pandas as __pd
        if not isinstance(df, __pd.DataFrame):
            df = __pd.DataFrame(df)
        payload = {
            "columns": list(df.columns),
            "rows": df.astype(object).where(df.notna(), None).values.tolist(),
        }
        __artifacts.append({
            "kind": "table",
            "mime": "application/vnd.dataframe+json",
            "title": title or "Table",
            "payload": payload,
        })

    def emit_figure(fig, title=None):
        import plotly.io as __pio
        spec = __json.loads(__pio.to_json(fig))
        __artifacts.append({
            "kind": "plot",
            "mime": "application/vnd.plotly.v1+json",
            "title": title or "Figure",
            "payload": spec,
        })
    """
).strip()

_SANDBOX_EPILOGUE = textwrap.dedent(
    """
    __sys.stdout.flush()
    __sys.stderr.write("\\n__ARTIFACTS_JSON__=" + __json.dumps(__artifacts))
    """
).strip()


def run_analysis(code: str, data: dict | None = None) -> dict[str, Any]:
    """Run a short Python analysis snippet in a restricted subprocess.

    The snippet may use :func:`emit_table` and :func:`emit_figure` helpers
    (auto-injected) to return artifacts. ``data`` is exposed as a module-level
    ``data`` dict.

    Resource guards: 15s wall timeout, ``PYTHONNOUSERSITE=1``, a scrubbed
    environment, and the subprocess runs in a fresh temp CWD. This is NOT a
    hardened sandbox; it is safe because the operator controls the code, and
    no secrets are accessible from the temp directory.
    """
    if not isinstance(code, str) or not code.strip():
        return _error("No code provided.")

    injected_data = f"data = {json.dumps(data or {}, default=str)}\n"
    full_code = (
        _SANDBOX_PREAMBLE
        + "\n"
        + injected_data
        + "\n"
        + textwrap.dedent(code)
        + "\n"
        + _SANDBOX_EPILOGUE
    )

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
    }

    with tempfile.TemporaryDirectory(prefix="analysis_") as tmpdir:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", full_code],
                capture_output=True,
                timeout=_SANDBOX_TIMEOUT_S,
                env=env,
                cwd=tmpdir,
                text=True,
            )
        except subprocess.TimeoutExpired:
            return _error(
                f"Analysis exceeded the {_SANDBOX_TIMEOUT_S}s time limit."
            )
        except Exception as exc:
            logger.exception("run_analysis subprocess failed")
            return _error(f"Subprocess failed to start: {exc}")

    stdout = (proc.stdout or "")[:_MAX_STDOUT_CHARS]
    stderr_full = proc.stderr or ""
    stderr, artifacts = _extract_artifacts(stderr_full)

    descriptors: list[dict] = [
        {"id": _artifact_id(), **a} for a in artifacts
    ]

    if stdout:
        descriptors.append(
            {
                "id": _artifact_id(),
                "kind": "text",
                "mime": "text/plain",
                "title": "stdout",
                "payload": stdout,
            }
        )

    descriptors.append(
        {
            "id": _artifact_id(),
            "kind": "code",
            "mime": "text/x-python",
            "title": "Analysis code",
            "payload": textwrap.dedent(code).strip(),
        }
    )

    if proc.returncode != 0:
        return {
            "status": "error",
            "message": (stderr[-2000:] or "Analysis failed.").strip(),
            "artifacts": descriptors,
        }

    return {
        "status": "ok",
        "message": stderr[-500:].strip() or "Analysis complete.",
        "artifacts": descriptors,
    }


def _extract_artifacts(stderr: str) -> tuple[str, list[dict]]:
    marker = "__ARTIFACTS_JSON__="
    idx = stderr.rfind(marker)
    if idx < 0:
        return stderr, []
    head = stderr[:idx].rstrip()
    tail = stderr[idx + len(marker):].strip()
    try:
        artifacts = json.loads(tail)
        if not isinstance(artifacts, list):
            artifacts = []
    except json.JSONDecodeError:
        artifacts = []
    return head, artifacts


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "message": message, "artifacts": []}
