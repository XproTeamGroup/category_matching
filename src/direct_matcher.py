"""
Direct matching without AI: exact → case-insensitive → normalized.
Normalized = strip Latin brand words + series markers, lowercase.

Fully domain-agnostic. Returns matched results and unmatched source categories.
"""

import re
from typing import Any


_SERIES_RE = re.compile(
    r"\b\d+[а-яіієї]?\b"       # "6а", "7", "8"
    r"|\bсері[яї]\b"            # "серія", "серії"
    r"|\bserie[s]?\b"           # "series"
    r"|\bмодел[ьі]\b",          # "модель", "моделі"
    re.IGNORECASE,
)

# Words that are too generic to uniquely identify a category.
# A normalized result consisting ONLY of these words is unreliable for matching
# and should be sent to AI instead.
_STOP_WORDS = frozenset({
    "аксесуари", "аксесуар",
    "набори", "набір", "набор",
    "комплектуючі", "комплектуючий", "комплект", "комплекти",
    "інше", "інший", "інші",
    "продукт", "продукти",
    "товар", "товари",
    "і", "та", "або", "для", "до",
})


def normalize(text: str) -> str:
    """
    Strips Latin words (likely brand names), numbers with series markers,
    punctuation, and lowercases. Keeps Cyrillic words only.
    """
    text = re.sub(r"[A-Za-z]+", " ", text)
    text = _SERIES_RE.sub(" ", text)
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_meaningful(norm: str) -> bool:
    """Returns True only if the normalized text has at least one non-stop word."""
    tokens = set(norm.split())
    return bool(tokens - _STOP_WORDS)


def _build_ref_index(ref_leaves: list[dict]) -> tuple[dict, dict]:
    exact_index: dict[str, dict] = {}
    normalized_index: dict[str, dict] = {}

    for leaf in ref_leaves:
        exact_index[leaf["name"].lower().strip()] = leaf
        norm = normalize(leaf["name"])
        if norm and norm not in normalized_index:
            normalized_index[norm] = leaf
        # Also index by last path segment (e.g. "Мультитули" from "Ножі > Мультитули")
        last_segment = leaf["path"].split(" > ")[-1]
        exact_index[last_segment.lower().strip()] = leaf
        norm_last = normalize(last_segment)
        if norm_last and norm_last not in normalized_index:
            normalized_index[norm_last] = leaf

    return exact_index, normalized_index


def match_direct(
    source_categories: list[dict],
    ref_leaves: list[dict],
) -> tuple[list[dict[str, Any]], list[dict]]:
    """
    Tries to match each source category to a reference leaf directly.
    Returns (matched_results, unmatched_source_categories).
    """
    exact_index, normalized_index = _build_ref_index(ref_leaves)

    matched: list[dict[str, Any]] = []
    unmatched: list[dict] = []

    for src in source_categories:
        src_name = src["name"]
        ref_leaf = None
        method = None

        # 1. Exact case-insensitive
        ref_leaf = exact_index.get(src_name.lower().strip())
        if ref_leaf:
            method = "exact"

        # 2. Normalized (strip brands, series markers)
        # Skip if result is only generic stop words — send to AI instead
        if not ref_leaf:
            norm = normalize(src_name)
            if norm and _is_meaningful(norm):
                ref_leaf = normalized_index.get(norm)
                if ref_leaf:
                    method = "normalized"

        if ref_leaf:
            matched.append({
                "source_id": str(src["id"]),
                "source_name": src_name,
                "reference_id": ref_leaf["id"],
                "reference_name": ref_leaf["name"],
                "reference_path": ref_leaf["path"],
                "method": method,
                "confidence": "high",
            })
        else:
            unmatched.append(src)

    return matched, unmatched
