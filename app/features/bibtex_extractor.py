"""Balanced-brace BibTeX entry extractor.

Replaces the fragile regex that failed on entries with nested braces
spanning multiple fields (common for TeX markup in thesis titles).
"""
from __future__ import annotations


def extract_bibtex_entries(text: str) -> list[str]:
    """Return all complete @-prefixed BibTeX entries found in text.

    Scans for `@`, consumes until the opening `{`, then tracks brace depth
    until it returns to zero. Ignores braces inside quoted fields.
    """
    if not text:
        return []

    entries: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        if text[i] != "@":
            i += 1
            continue

        start = i
        # Find the first '{' after the entry type
        brace_open = text.find("{", i)
        if brace_open == -1:
            break

        depth = 1
        j = brace_open + 1
        in_quote = False

        while j < n and depth > 0:
            ch = text[j]
            if ch == '"' and text[j - 1] != "\\":
                in_quote = not in_quote
            elif not in_quote:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            j += 1

        if depth == 0:
            entries.append(text[start:j])
            i = j
        else:
            # Unbalanced — bail out to avoid partial capture
            break

    return entries
