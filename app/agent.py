"""
GPT-4o tool-use agent loop.

Registers 7 tools as OpenAI function calls, runs the agent loop until the
model stops calling tools, and returns the final text response.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import client, MODEL
from app.tools._http import RateLimitError, ScraperStaleError
from app.tools.taltech_search import search_taltech_theses
from app.tools.papers import search_papers
from app.tools.datasets import search_datasets
from app.tools.sim_tools import get_simulation_tools
from app.tools.github_search import (
    search_github_repos,
    search_taltech_github,
    get_github_readme,
)
from app.features.gap_finder import find_research_gaps
from app.features.similar_thesis import find_similar_theses

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 2000

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are TalTech Research Assistant, an AI agent helping engineering
students at Tallinn University of Technology (TalTech) find resources for their research.

You have access to the following tools:
- search_taltech_theses: Search TalTech's thesis repository (Bachelor's, Master's, PhD)
- search_papers: Search 200M+ academic papers via Semantic Scholar
- search_datasets: Find research datasets on Kaggle and Zenodo
- get_simulation_tools: List simulation software available at TalTech
- search_github_repos: Find open-source code on GitHub
- search_taltech_github: Search TalTech's own GitHub organisations
- get_github_readme: Fetch a GitHub repo's README for details
- find_research_gaps: Check how well a topic is covered in TalTech theses
- find_similar_theses: Find theses and papers similar to a given abstract

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

Never invent: paper titles, author names, dataset URLs, GitHub stars, or tool availability."""

# ── Tool schemas (OpenAI function-call format) ────────────────────────────────
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
                        "default": 5,
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
                        "default": 5,
                    },
                    "year_filter": {
                        "type": "string",
                        "description": "Optional year range, e.g. '2020-2024'",
                        "default": "",
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
                        "default": 5,
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
                        "default": 5,
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
                        "default": 5,
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
                        "default": 5,
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
    "search_datasets": search_datasets,
    "get_simulation_tools": get_simulation_tools,
    "search_github_repos": search_github_repos,
    "search_taltech_github": search_taltech_github,
    "get_github_readme": get_github_readme,
    "find_research_gaps": find_research_gaps,
    "find_similar_theses": find_similar_theses,
}


def run(
    user_message: str,
    history: list[dict] | None = None,
    max_iterations: int = 6,
) -> str:
    """Run the agent loop and return the final assistant message.

    Args:
        user_message: The latest user message.
        history: Prior conversation messages (list of {role, content} dicts).
        max_iterations: Safety cap on tool-call rounds.

    Returns:
        Final assistant response as a string.
    """
    cleaned = _validate_message(user_message)
    if cleaned is None:
        return "Please type a question (1–2000 characters)."

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": cleaned})

    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        # No tool calls — we have the final answer
        if not msg.tool_calls:
            return msg.content or ""

        # Execute all requested tool calls
        for tc in msg.tool_calls:
            result = _call_tool(tc.function.name, tc.function.arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    logger.warning("Agent reached max_iterations without a final answer")
    return "I ran into a processing limit. Please try rephrasing your question."


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
