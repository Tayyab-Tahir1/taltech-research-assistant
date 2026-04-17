"""
Research gap finder: identifies under-researched topics at TalTech.

Runs multiple searches against digikogu and counts results to surface topics
with few existing theses — indicating potential research opportunities.
"""
from __future__ import annotations

from typing import Any

from app.tools.taltech_search import search_taltech_theses

# ── Coverage thresholds (tune here, not in branches) ─────────────────────────
LOW_MAX = 3        # 1..LOW_MAX → "low"
MODERATE_MAX = 7   # LOW_MAX+1..MODERATE_MAX → "moderate"; above → "well-covered"
MAIN_TOP_K = 10
SUBTOPIC_TOP_K = 5


def find_research_gaps(
    topic: str,
    subtopics: list[str] | None = None,
) -> dict[str, Any]:
    """Identify how well a topic is covered in TalTech theses.

    Args:
        topic: Main research area (e.g. "machine learning in robotics").
        subtopics: Optional list of specific sub-themes to probe.
                   Defaults to probing the main topic only.

    Returns:
        Dict with:
            - main_results: list of found theses for the main topic
            - coverage: "low" / "moderate" / "well-covered"
            - gap_message: human-readable assessment
            - subtopic_counts: {subtopic: count} if subtopics provided
    """
    main_results = search_taltech_theses(topic, top_k=MAIN_TOP_K)
    count = len(main_results)

    if count == 0:
        coverage = "none"
        gap_message = (
            f"No TalTech theses found for '{topic}'. "
            "This appears to be a completely unexplored area — excellent research opportunity!"
        )
    elif count <= LOW_MAX:
        coverage = "low"
        gap_message = (
            f"Only {count} TalTech thesis/theses found for '{topic}'. "
            "This is a lightly covered topic — strong potential for original research."
        )
    elif count <= MODERATE_MAX:
        coverage = "moderate"
        gap_message = (
            f"{count} TalTech theses found for '{topic}'. "
            "Moderate coverage — there may be specific sub-angles not yet explored."
        )
    else:
        coverage = "well-covered"
        gap_message = (
            f"{count}+ TalTech theses found for '{topic}'. "
            "Well-researched area. Consider narrowing the scope or finding a novel angle."
        )

    result: dict[str, Any] = {
        "topic": topic,
        "main_results": main_results[:5],
        "total_found": count,
        "coverage": coverage,
        "gap_message": gap_message,
        "subtopic_counts": {},
    }

    if subtopics:
        for sub in subtopics:
            sub_results = search_taltech_theses(sub, top_k=SUBTOPIC_TOP_K)
            result["subtopic_counts"][sub] = len(sub_results)

    return result
