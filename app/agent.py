"""
Function-calling agent loop.

Backend-agnostic: talks to Gemini 2.5, GPT-4o, or a local vLLM through
:mod:`app.llm`. Registers ~10 research tools, dispatches calls, and returns
the model's final text response to the Streamlit UI.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app import llm
from app.tools._http import RateLimitError, ScraperStaleError, SourceUnavailableError
from app.tools.taltech_search import search_taltech_theses
from app.tools.papers import search_papers
from app.tools.arxiv_search import search_arxiv
from app.tools.datasets import search_datasets
from app.tools.sim_tools import get_simulation_tools
from app.tools.github_search import (
    search_github_repos,
    search_taltech_github,
    get_github_readme,
)
from app.tools.analysis import generate_plot, run_analysis
from app.features.gap_finder import find_research_gaps
from app.features.similar_thesis import find_similar_theses

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 2000

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are TalTech Research Assistant, an AI agent helping engineering
students at Tallinn University of Technology (TalTech) find resources for their research.

You have access to the following tools:
- search_taltech_theses: Search TalTech's thesis repository (Bachelor's, Master's, PhD)
- search_papers: Search 200M+ academic papers via Semantic Scholar
- search_arxiv: Search arXiv.org preprints (free public fallback, no rate limit)
- search_datasets: Find research datasets on Kaggle and Zenodo
- get_simulation_tools: List simulation software available at TalTech
- search_github_repos: Find open-source code on GitHub
- search_taltech_github: Search TalTech's own GitHub organisations
- get_github_readme: Fetch a GitHub repo's README for details
- find_research_gaps: Check how well a topic is covered in TalTech theses
- find_similar_theses: Find theses and papers similar to a given abstract
- generate_plot: Build a Plotly chart (bar/line/scatter/hist/pie) from data you already have
- run_analysis: Run a short Python snippet for analysis; returns plots, tables, and code as artifacts

HOW TO INTERPRET INTENT (infer from the prompt — there are no explicit modes):
  • If the user pastes a long block resembling a thesis abstract (≥ ~400 chars
    describing their own research), call ``find_similar_theses`` on it.
  • If the user asks about coverage, under-researched areas, research gaps,
    or "what hasn't been studied" at TalTech, call ``find_research_gaps``.
  • If the user explicitly says "cite", "citation", "BibTeX", "IEEE", or "APA"
    for a specific source, search for the source first (if needed) and then
    produce BibTeX + IEEE + APA blocks side by side.
  • Otherwise, run the general research flow: TalTech theses first, then
    Semantic Scholar, then arXiv.

Guidelines:
1. ALWAYS use your search tools BEFORE answering — never fabricate paper titles,
   thesis names, author names, dataset URLs, or GitHub star counts.
2. Respond in the SAME LANGUAGE the student uses (Estonian or English).
3. Always include clickable links to your sources.
4. After finding a source, offer to generate a BibTeX citation.
5. When few results are found for a topic, mention this may be a research gap.
6. Be concise — students are busy; give clear, direct answers with source cards.
7. For simulation tools, always mention whether TalTech has a license or if it's free.
8. If a GitHub rate limit is hit, inform the user and suggest adding GITHUB_TOKEN.
9. If a tool returns {"status": "error", ...}, tell the user that source is
   temporarily unavailable and relay the message — NEVER invent results to fill
   the gap. Prefer results from other working tools and be explicit about what
   failed.
10. CITE THE SOURCE OF EVERY RESULT. Group results under explicit section headings
    that name the origin, e.g. "**From TalTech digikogu:**", "**From Semantic
    Scholar (public):**", "**From arXiv (public):**", "**From GitHub (public):**".
    Never merge sources into an unlabelled list — the student must always be able
    to see whether a result came from TalTech's own catalogue or a public source.
12. When the user asks for analysis, trends, comparison, counts by year, or a
    visualisation, call ``generate_plot`` (preferred for simple charts from data
    you already have) or ``run_analysis`` (for deeper computations). Describe
    each artifact briefly in text — the UI will render the actual chart/table
    on the right; do NOT paste the raw data back in chat.
11. FALLBACK CHAIN for paper/literature queries: ALWAYS try tools in this order,
    and include results from every tool that returns data — don't stop at the
    first one:
       a. search_taltech_theses (TalTech first)
       b. search_papers (Semantic Scholar)
       c. search_arxiv (public fallback)
    If TalTech returns nothing, explicitly say "No TalTech theses matched — here
    are public results:" and then show Semantic Scholar + arXiv findings. If
    Semantic Scholar returns an error sentinel (rate-limited), acknowledge it
    and still show arXiv results so the student is never left empty-handed.

Never invent: paper titles, author names, dataset URLs, GitHub stars, or tool availability."""

# ── Tool schemas (OpenAI function-call format; the adapter translates for Gemini) ──
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_taltech_theses",
            "description": (
                "Search TalTech's thesis repository (digikogu.taltech.ee) for "
                "Bachelor's, Master's, and PhD theses. Use for any query about "
                "TalTech student research, theses, or manuscripts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_papers",
            "description": (
                "Search for academic papers and journal articles via Semantic Scholar "
                "(200M+ papers). Returns title, authors, abstract, year, and PDF links."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Max papers to return (default 5)",
                    },
                    "year_filter": {
                        "type": "string",
                        "description": "Optional year range, e.g. '2020-2024'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_arxiv",
            "description": (
                "Search arXiv.org preprints (free, public, no rate limit). "
                "Use as a fallback when Semantic Scholar is unavailable, or alongside "
                "it for broader coverage. Returns title, authors, abstract, year, and PDF link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 25)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_datasets",
            "description": (
                "Search for research datasets on Kaggle and Zenodo. "
                "Use when the student needs data for experiments or ML training."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Dataset search query"},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["kaggle", "zenodo"]},
                        "description": "Which sources to search (default: both)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Results per source (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_simulation_tools",
            "description": (
                "Return a list of simulation tools and software available at TalTech. "
                "Filter by engineering domain (e.g. 'robotics', 'CFD', 'electronics')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional engineering domain filter, e.g. 'mechanical', "
                            "'robotics', 'CFD', 'electronics', 'structural'. "
                            "Leave empty to return all tools."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_github_repos",
            "description": (
                "Search GitHub for open-source repositories. Useful for finding "
                "code examples, libraries, and project templates related to a topic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "language": {
                        "type": "string",
                        "description": "Optional language filter, e.g. 'python', 'matlab', 'cpp'",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_taltech_github",
            "description": (
                "Search repositories within TalTech's own GitHub organisations "
                "(TalTech-IVAR, taltech). Good for course materials, lab repos, "
                "and student project templates from TalTech."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_github_readme",
            "description": (
                "Fetch and return the README of a specific GitHub repository "
                "to understand its contents and usage. Use after finding a repo "
                "that looks relevant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_full_name": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format, e.g. 'openai/whisper'",
                    }
                },
                "required": ["repo_full_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_research_gaps",
            "description": (
                "Analyse how well a topic is covered by existing TalTech theses "
                "to identify research gaps and opportunities. Use when the student "
                "asks what hasn't been studied at TalTech or wants research ideas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Main research topic to analyse",
                    },
                    "subtopics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of sub-themes to probe separately",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_plot",
            "description": (
                "Create a Plotly chart as an artifact for the right-hand panel. "
                "Use for simple visualisations built from data you already have: "
                "year histograms, per-topic bar charts, comparison scatter plots."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["bar", "line", "scatter", "hist", "pie"],
                        "description": "Plot type.",
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Plot data. Either a single series with x/y (or values/labels) "
                            "or {series: [{name, x, y}, ...]} for multi-series charts."
                        ),
                    },
                    "options": {
                        "type": "object",
                        "description": "Optional title, x_label, y_label, color.",
                    },
                },
                "required": ["kind", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_analysis",
            "description": (
                "Run a short Python snippet in a restricted subprocess (timeout 15s). "
                "Helpers `emit_table(df)` and `emit_figure(fig)` are pre-injected so "
                "the snippet can return DataFrames and Plotly figures as artifacts. "
                "`data` (if provided) is exposed to the snippet as a module-level dict."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute.",
                    },
                    "data": {
                        "type": "object",
                        "description": "Optional JSON-serialisable dict available to the snippet as `data`.",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_theses",
            "description": (
                "Given a thesis abstract or description, find similar TalTech theses "
                "and Semantic Scholar papers. Use when the student pastes their abstract "
                "and wants to find related work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "abstract": {
                        "type": "string",
                        "description": "Thesis abstract or description",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pre-extracted keywords (optional)",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Results per source (default 5)",
                    },
                },
                "required": ["abstract"],
            },
        },
    },
]

# ── Tool dispatch ─────────────────────────────────────────────────────────────
_TOOL_MAP: dict[str, Any] = {
    "search_taltech_theses": search_taltech_theses,
    "search_papers": search_papers,
    "search_arxiv": search_arxiv,
    "search_datasets": search_datasets,
    "get_simulation_tools": get_simulation_tools,
    "search_github_repos": search_github_repos,
    "search_taltech_github": search_taltech_github,
    "get_github_readme": get_github_readme,
    "find_research_gaps": find_research_gaps,
    "find_similar_theses": find_similar_theses,
    "generate_plot": generate_plot,
    "run_analysis": run_analysis,
}

# Tools that emit artifact descriptors consumable by the right-hand UI panel.
_ARTIFACT_TOOLS = {"generate_plot", "run_analysis"}

# Tools that warrant the deep-reasoning model tier (Gemini 2.5 Pro with thinking).
_DEEP_TOOLS = {"find_research_gaps", "find_similar_theses"}


def run(
    user_message: str,
    history: list[dict] | None = None,
    attachments: list[dict] | None = None,
    max_iterations: int = 6,
) -> dict[str, Any]:
    """Run the agent loop.

    Returns a dict ``{"content": str, "artifacts": list[dict]}`` so the UI can
    render chat text and the artifact panel from the same call.
    """
    cleaned = _validate_message(user_message)
    if cleaned is None and not attachments:
        return {"content": "Please type a question (1–2000 characters).", "artifacts": []}
    if cleaned is None:
        cleaned = "(attachments only)"

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append(_build_user_message(cleaned, attachments))

    collected_artifacts: list[dict] = []
    use_deep = False
    for _ in range(max_iterations):
        response = llm.chat(messages, tools=TOOLS, deep=use_deep)
        messages.append(response.raw_message)

        if not response.tool_calls:
            return {
                "content": response.content or "",
                "artifacts": collected_artifacts,
            }

        for tc in response.tool_calls:
            if tc.name in _DEEP_TOOLS:
                use_deep = True
            result = _call_tool(tc.name, tc.arguments)
            if tc.name in _ARTIFACT_TOOLS and isinstance(result, dict):
                for art in result.get("artifacts") or []:
                    if isinstance(art, dict):
                        collected_artifacts.append(art)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,  # required by the Gemini adapter
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    logger.warning("Agent reached max_iterations without a final answer")
    return {
        "content": "I ran into a processing limit. Please try rephrasing your question.",
        "artifacts": collected_artifacts,
    }


def _build_user_message(text: str, attachments: list[dict] | None) -> dict:
    """Build the user message, inlining PDF text and attaching images as vision parts."""
    usable = [a for a in (attachments or []) if a.get("kind") in {"pdf", "image"}]
    if not usable:
        return {"role": "user", "content": text}

    pdf_blocks: list[str] = []
    for att in usable:
        if att.get("kind") == "pdf" and att.get("text"):
            pdf_blocks.append(
                f"\n\n--- Attached PDF: {att.get('name', 'document.pdf')} ---\n"
                f"{att['text']}\n--- end PDF ---"
            )

    combined_text = text + ("".join(pdf_blocks) if pdf_blocks else "")
    content: list[dict] = [{"type": "text", "text": combined_text}]
    for att in usable:
        if att.get("kind") == "image" and att.get("data_url"):
            content.append({"type": "image_url", "image_url": {"url": att["data_url"]}})
    return {"role": "user", "content": content}


def _validate_message(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_MESSAGE_LEN:
        cleaned = cleaned[:MAX_MESSAGE_LEN]
    return cleaned


def _error_sentinel(name: str, message: str, hint: str = "") -> dict:
    return {
        "status": "error",
        "tool": name,
        "message": message,
        "hint": hint,
        "results": [],
    }


def _call_tool(name: str, arguments_json: str) -> Any:
    fn = _TOOL_MAP.get(name)
    if fn is None:
        logger.error("Unknown tool requested: %s", name)
        return _error_sentinel(name, f"Unknown tool: {name}")
    try:
        kwargs = json.loads(arguments_json) if arguments_json else {}
        logger.info("tool.call name=%s args=%s", name, kwargs)
        result = fn(**kwargs)
        return result
    except RateLimitError as exc:
        logger.warning("Tool %s hit rate limit: %s", name, exc)
        return _error_sentinel(
            name,
            f"{exc.service} rate limit reached.",
            hint="Set GITHUB_TOKEN in your environment to raise the limit from 60 to 5000 req/hr.",
        )
    except SourceUnavailableError as exc:
        logger.warning("Tool %s source unavailable: %s", name, exc)
        return _error_sentinel(
            name,
            f"{exc.service} is temporarily unavailable: {exc}",
            hint="Try again in a minute, or set SEMANTIC_SCHOLAR_API_KEY for higher limits.",
        )
    except ScraperStaleError as exc:
        logger.warning("Tool %s scraper stale: %s", name, exc)
        return _error_sentinel(
            name,
            f"The {exc.source} page structure may have changed; results are temporarily unavailable.",
            hint=f"Affected URL: {exc.url}",
        )
    except json.JSONDecodeError as exc:
        logger.error("Tool %s got invalid JSON args: %s", name, exc)
        return _error_sentinel(name, f"Invalid tool arguments: {exc}")
    except Exception as exc:
        logger.exception("Tool %s raised an error", name)
        return _error_sentinel(name, str(exc))
