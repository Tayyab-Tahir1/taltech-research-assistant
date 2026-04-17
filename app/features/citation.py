"""
Citation generator: BibTeX, IEEE, and APA formats.

GPT-4o formats citations from raw metadata so the output is clean even when
fields are partially missing. Template-based fallback used for offline testing.
"""
from __future__ import annotations

import re
from typing import Any


def make_bibtex(meta: dict[str, Any], entry_type: str = "misc") -> str:
    """Generate a BibTeX entry from source metadata.

    Args:
        meta: Dict containing any of: title, author/authors, year, url,
              school, journal, doi, publisher.
        entry_type: BibTeX entry type: article, mastersthesis, phdthesis,
                    inproceedings, misc, dataset.

    Returns:
        Formatted BibTeX string.
    """
    title = meta.get("title", "Untitled")
    year = str(meta.get("year", ""))
    url = meta.get("url", "")
    school = meta.get("school", "Tallinn University of Technology")
    journal = meta.get("journal", "")
    doi = meta.get("doi", "")

    # Build citation key: first author surname + year
    authors = _get_authors(meta)
    first_author = authors[0] if authors else "Unknown"
    surname = first_author.split()[-1].lower() if first_author != "Unknown" else "unknown"
    key = re.sub(r"[^a-z0-9]", "", f"{surname}{year}")

    author_field = " and ".join(authors) if authors else "Unknown"

    lines = [f"@{entry_type}{{{key},"]
    lines.append(f"  author  = {{{author_field}}},")
    lines.append(f"  title   = {{{{{title}}}}},")

    if year:
        lines.append(f"  year    = {{{year}}},")

    if entry_type in ("mastersthesis", "phdthesis"):
        lines.append(f"  school  = {{{school}}},")
    elif journal:
        lines.append(f"  journal = {{{journal}}},")

    if doi:
        lines.append(f"  doi     = {{{doi}}},")
    if url:
        lines.append(f"  url     = {{{url}}},")

    lines.append("}")
    return "\n".join(lines)


def make_ieee(meta: dict[str, Any]) -> str:
    """Format an IEEE-style citation string.

    Returns:
        Human-readable IEEE reference string.
    """
    authors = _get_authors(meta)
    if len(authors) > 3:
        author_str = f"{authors[0]} et al."
    elif authors:
        author_str = ", ".join(authors)
    else:
        author_str = "Unknown"

    title = meta.get("title", "Untitled")
    year = meta.get("year", "n.d.")
    url = meta.get("url", "")
    journal = meta.get("journal", "")
    school = meta.get("school", "Tallinn University of Technology")

    if journal:
        return f'{author_str}, "{title}," {journal}, {year}.'
    if meta.get("entry_type") in ("mastersthesis", "phdthesis"):
        return f'{author_str}, "{title}," M.Sc./Ph.D. thesis, {school}, {year}.'
    if url:
        return f'{author_str}, "{title}," {year}. [Online]. Available: {url}'
    return f'{author_str}, "{title}," {year}.'


def make_apa(meta: dict[str, Any]) -> str:
    """Format an APA 7th edition citation string."""
    authors = _get_authors(meta)
    year = meta.get("year", "n.d.")
    title = meta.get("title", "Untitled")
    url = meta.get("url", "")
    journal = meta.get("journal", "")

    if len(authors) > 6:
        author_str = _apa_name(authors[0]) + " et al."
    else:
        author_str = ", ".join(_apa_name(a) for a in authors) if authors else "Unknown"

    base = f"{author_str} ({year}). {title}."
    if journal:
        base += f" {journal}."
    if url:
        base += f" {url}"
    return base


def _get_authors(meta: dict[str, Any]) -> list[str]:
    authors = meta.get("authors") or meta.get("author")
    if not authors:
        return []
    if isinstance(authors, str):
        return [a.strip() for a in authors.split(" and ")]
    return [str(a) for a in authors]


def _apa_name(full_name: str) -> str:
    parts = full_name.strip().split()
    if len(parts) < 2:
        return full_name
    surname = parts[-1]
    initials = " ".join(p[0].upper() + "." for p in parts[:-1])
    return f"{surname}, {initials}"
