"""
Builds path strings for every category based on parent_id hierarchy.
Returns enriched category dicts with 'path' and 'is_leaf' fields.
"""

import json
from typing import Any


def build_paths(categories: list[dict]) -> dict[str, str]:
    """
    Returns {id: full_path} for every category.
    E.g. {"24323": "Ножі та інструменти > Мультитули"}
    """
    id_map: dict[str, dict] = {str(c["id"]): c for c in categories}
    cache: dict[str, str] = {}

    def _get_path(cat_id: str) -> str:
        if cat_id in cache:
            return cache[cat_id]
        cat = id_map.get(cat_id)
        if not cat:
            return ""
        parent_id = cat.get("parent_id")
        if parent_id:
            parent_path = _get_path(str(parent_id))
            path = f"{parent_path} > {cat['name']}" if parent_path else cat["name"]
        else:
            path = cat["name"]
        cache[cat_id] = path
        return path

    for c in categories:
        _get_path(str(c["id"]))

    return cache


def get_leaf_categories(categories: list[dict], paths: dict[str, str]) -> list[dict[str, Any]]:
    """
    Returns only leaf categories enriched with path.
    Primary: categories with final == '1'.
    Fallback: categories that have no children (no other category references them as parent_id).
    """
    result = [
        {
            "id": str(c["id"]),
            "name": c["name"],
            "path": paths.get(str(c["id"]), c["name"]),
        }
        for c in categories
        if str(c.get("final", "0")) == "1"
    ]
    if result:
        return result

    # Fallback: categories with no children
    parent_ids = {str(c["parent_id"]) for c in categories if c.get("parent_id") is not None}
    return [
        {
            "id": str(c["id"]),
            "name": c["name"],
            "path": paths.get(str(c["id"]), c["name"]),
        }
        for c in categories
        if str(c["id"]) not in parent_ids
    ]


def load_and_build(filepath: str) -> tuple[list[dict], dict[str, str]]:
    """Load JSON file and return (categories, paths_by_id)."""
    with open(filepath, encoding="utf-8") as f:
        categories = json.load(f)
    paths = build_paths(categories)
    return categories, paths


def filter_unmatched(categories: list[dict]) -> tuple[list[dict], int]:
    """
    Filters out source categories that already have assignment_category_id set.
    Those are already matched and don't need processing.
    Returns (unmatched_categories, skipped_count).
    """
    result = []
    skipped = 0
    for c in categories:
        if c.get("assignment_category_id") is not None:
            skipped += 1
        else:
            result.append(c)
    return result, skipped


def print_tree_stats(categories: list[dict], label: str) -> None:
    total = len(categories)
    leaves = sum(1 for c in categories if str(c.get("final", "0")) == "1")
    roots = sum(1 for c in categories if c.get("parent_id") is None)
    print(f"[{label}] total={total}, leaves={leaves}, roots={roots}, non-leaves={total - leaves}")
