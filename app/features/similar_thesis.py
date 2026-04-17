"""
Similar thesis finder.

Given a thesis abstract or description, this module:
1. Extracts keywords via the LLM (handled by the agent)
2. Searches TalTech digikogu with those keywords
3. Searches Semantic Scholar with the abstract as query
4. Returns combined, deduplicated results
"""
from __future__ import annotations

import re
from typing import Any

from app.tools.taltech_search import search_taltech_theses
from app.tools.papers import search_papers


def find_similar_theses(
    abstract: str,
    keywords: list[str] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Find theses and papers similar to a given abstract.

    Args:
        abstract: The user's thesis abstract or description (up to ~1000 chars).
        keywords: Pre-extracted keywords (agent should extract these first).
                  If None, a simple extraction is done locally.
        top_k: Number of results per source.

    Returns:
        Dict with:
            - taltech_matches: list of matching TalTech theses
            - paper_matches: list of matching Semantic Scholar papers
            - keywords_used: list of keywords that were queried
    """
    if not keywords:
        keywords = _extract_keywords(abstract)

    # Use first 3 keywords combined for TalTech search (improves recall)
    taltech_query = " ".join(keywords[:3]) if keywords else abstract[:100]
    taltech_results = search_taltech_theses(taltech_query, top_k=top_k)

    # Use truncated abstract for Semantic Scholar
    paper_query = abstract[:250]
    paper_results = search_papers(paper_query, max_results=top_k)

    return {
        "taltech_matches": taltech_results,
        "paper_matches": paper_results,
        "keywords_used": keywords,
    }


def _extract_keywords(text: str, max_keywords: int = 6) -> list[str]:
    """Simple keyword extraction: longest meaningful noun phrases.

    This is a fallback. The agent should call GPT-4o to extract proper
    keywords before invoking find_similar_theses.
    """
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
        "this", "that", "these", "those", "it", "its", "we", "i", "our",
        "using", "used", "based", "approach", "method", "methods", "paper",
        "study", "research", "work", "results", "propose", "proposed",
    }
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    seen: set[str] = set()
    keywords = []
    for w in words:
        if w not in stopwords and w not in seen:
            seen.add(w)
            keywords.append(w)
        if len(keywords) >= max_keywords:
            break
    return keywords
