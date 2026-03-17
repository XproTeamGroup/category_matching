"""
AI-based semantic matching via OpenAI-compatible API.
Uses only stdlib urllib — no third-party AI libraries.

Domain-agnostic: the model infers the domain from the reference tree itself.

Public API:
  match_with_ai(source, ref_leaves, examples)         — standard matching
  match_with_ai_force(source, ref_leaves, examples)   — assertive + scope classification
  verify_matches(matched, examples)                   — post-match quality check
"""

import json
import time
import urllib.request
import urllib.error
from typing import Any

from . import config


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _call_api(prompt: str) -> str:
    url = config.AI_BASE_URL.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": config.AI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config.AI_API_KEY}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_reference_context(ref_leaves: list[dict]) -> str:
    lines = [f'{{"id": "{leaf["id"]}", "path": "{leaf["path"]}"}}' for leaf in ref_leaves]
    return "[\n  " + ",\n  ".join(lines) + "\n]"


def _format_examples(examples: list[dict]) -> str:
    """Formats few-shot examples for prompt injection."""
    lines = [
        f'  "{ex["source_name"]}" → "{ex["reference_path"]}"'
        for ex in examples
    ]
    return "\n".join(lines)


# ── Prompts ───────────────────────────────────────────────────────────────────

def _build_prompt_standard(
    ref_context: str,
    batch: list[dict],
    examples: list[dict] | None = None,
) -> str:
    source_lines = [
        f'{{"id": "{s["id"]}", "path": "{s.get("path", s["name"])}"}}'
        for s in batch
    ]
    source_json = "[\n  " + ",\n  ".join(source_lines) + "\n]"

    examples_block = ""
    if examples:
        examples_block = f"""
EXAMPLES (known correct matches — use as reference for style and precision):
{_format_examples(examples)}
"""

    return f"""You are an expert at product category classification.

TASK: For each category in SOURCE, find the most suitable category from REFERENCE.
Source paths show the full hierarchy (e.g. "Brand > Electronics > Phones").

REFERENCE (all available leaf categories — full paths from root):
{ref_context}
{examples_block}
SOURCE (categories to match):
{source_json}

RULES:
- Choose ONLY from the provided REFERENCE categories (use the exact "id")
- One match per SOURCE category
- If no suitable match exists — set mapped_to_id to null
- Reply with ONLY a valid JSON array, no explanations

RESPONSE (JSON array, exactly {len(batch)} items):
[
  {{"source_id": "...", "source_name": "...", "mapped_to_id": "...", "mapped_to_path": "..."}},
  ...
]"""


def _build_prompt_force(
    ref_context: str,
    batch: list[dict],
    examples: list[dict] | None = None,
) -> str:
    source_lines = [
        f'{{"id": "{s["id"]}", "path": "{s.get("path", s["name"])}"}}'
        for s in batch
    ]
    source_json = "[\n  " + ",\n  ".join(source_lines) + "\n]"

    examples_block = ""
    if examples:
        examples_block = f"""
EXAMPLES (known correct matches — use as reference for style and precision):
{_format_examples(examples)}
"""

    return f"""You are an expert at product category classification.

TASK: For each category in SOURCE, find the best matching category from REFERENCE.
Analyze the reference tree to understand the domain it covers.
Source paths show the full hierarchy (e.g. "Brand > Electronics > Phones").

REFERENCE (all available leaf categories — full paths from root):
{ref_context}
{examples_block}
SOURCE (categories to match):
{source_json}

RULES:
- A valid match requires REAL semantic similarity — the source item genuinely belongs in that reference category
- Do NOT match based on a shared generic word alone (e.g. both containing "accessories" or "sets" is not sufficient)
- If a reasonable match exists — use it, even if the name is not identical
- Set mapped_to_id to null when the source category has no meaningful place in this reference tree
- When mapped_to_id is null, set out_of_scope:
    true  — category belongs to a completely different domain
    false — domain-adjacent but no specific reference category exists
- Use the exact "id" from REFERENCE
- Reply with ONLY a valid JSON array, no explanations

RESPONSE (JSON array, exactly {len(batch)} items):
[
  {{"source_id": "...", "source_name": "...", "mapped_to_id": "...", "mapped_to_path": "...", "out_of_scope": false}},
  ...
]"""


def _build_prompt_verify(
    batch: list[dict],
    examples: list[dict] | None = None,
) -> str:
    """
    batch items: {"id": str, "source_path": str, "reference_path": str}
    """
    pairs = json.dumps(batch, ensure_ascii=False, indent=2)

    examples_block = ""
    if examples:
        examples_block = f"""
KNOWN CORRECT matches (for calibration):
{_format_examples(examples)}
"""

    return f"""You are a quality checker for category matching results.

TASK: For each pair below decide if the source category CORRECTLY belongs in the reference category.
Answer true only when there is genuine semantic fit.
Answer false if the match is wrong, forced, or based only on a shared generic word.
{examples_block}
PAIRS TO VERIFY:
{pairs}

RULES:
- Be strict: a superficial word overlap is NOT a valid match
- Reply with ONLY a valid JSON array, no explanations

RESPONSE (JSON array, exactly {len(batch)} items):
[
  {{"id": "...", "correct": true}},
  ...
]"""


# ── Validation helpers ────────────────────────────────────────────────────────

def _validate_and_parse(
    response_text: str,
    batch: list[dict],
    valid_ids: set[str],
    expect_out_of_scope: bool = False,
) -> list[dict[str, Any]] | None:
    text = response_text.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        items = json.loads(text[start: end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list) or not items:
        return None

    batch_ids = {str(s["id"]) for s in batch}
    returned_ids = {str(item.get("source_id", "")) for item in items}
    if not batch_ids.issubset(returned_ids):
        return None

    for item in items:
        mapped_id = item.get("mapped_to_id")
        if mapped_id and str(mapped_id) not in valid_ids:
            item["mapped_to_id"] = None
            item["mapped_to_path"] = None
        if expect_out_of_scope and "out_of_scope" not in item:
            item["out_of_scope"] = False
    return items


def _validate_verify_response(
    response_text: str,
    batch_ids: set[str],
) -> list[dict[str, Any]] | None:
    text = response_text.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        items = json.loads(text[start: end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list) or not items:
        return None

    returned_ids = {str(item.get("id", "")) for item in items}
    if not batch_ids.issubset(returned_ids):
        return None
    # Ensure "correct" field is boolean
    for item in items:
        if "correct" not in item:
            return None
        item["correct"] = bool(item["correct"])
    return items


# ── Deep single-item prompt ───────────────────────────────────────────────────

def _build_prompt_deep(
    ref_context: str,
    source: dict,
    examples: list[dict] | None = None,
) -> str:
    examples_block = ""
    if examples:
        examples_block = f"""
EXAMPLES (known correct matches — use as calibration):
{_format_examples(examples)}
"""

    return f"""You are an expert at product category classification for a weapons, tactical, and outdoor equipment store.

REFERENCE (all available leaf categories — full paths from root):
{ref_context}
{examples_block}
SOURCE CATEGORY TO CLASSIFY:
  leaf (the actual category): "{source["name"]}"
  full path (parent context only): "{source.get("path", source["name"])}"

IMPORTANT: Focus on the LEAF category name — that is what you are classifying.
The path shows where it lives in the source tree, but do not let parent names
mislead you about what the leaf category actually contains.

INSTRUCTIONS:
Step 1 — UNDERSTAND: What is the LEAF category "{source["name"]}"? What products does it contain?
         - Consider synonyms, related terms, and how it might be named differently.
         - If the term is Ukrainian or Russian and unfamiliar, try to decompose it morphologically
           (e.g. "пулелійки" = "пуля"+"лійка" = bullet casting molds; "набоєприймач" = magazine).
           Use the parent path as a strong hint for the domain.
         - The parent path is only additional context — do not confuse it with the category itself.
Step 2 — EXPLORE: Look through the reference tree. Which categories could potentially match?
         Think broadly — consider parent categories, related domains, partial overlaps.
         If you are uncertain about the exact meaning of a term, prefer a broader domain match
         over declaring no match.
Step 3 — DECIDE: Choose the single best match, or declare no match.
         A valid match requires genuine semantic fit — the products from the source category
         would actually belong in that reference category.
         If no reasonable match exists, set mapped_to_id to null and classify out_of_scope:
           true  — completely different domain (e.g. furniture, toys)
           false — related domain but no specific reference category covers it

RULES:
- Use the exact "id" from REFERENCE
- PRIORITY ORDER for matching:
    1. Exact or near-exact name match (including synonym/translation equivalents, e.g. "патрон"="набій", "набої"="патрони", "рушниця"="гвинтівка")
       Also match when source name is a compound of reference name (e.g. "Намети, тенти" → "Намети")
    2. Specific product terminology match (caliber, weapon type, brand)
    3. Semantic/functional match
  Never jump to step 3 if a step 1 or 2 match exists in the reference tree.
- Do NOT match on shared generic words alone ("аксесуари", "інше", "набори")
- Prefer a specific match over a generic one
- Reply with ONLY valid JSON, no text outside the JSON object

RESPONSE (single JSON object):
{{
  "source_path": "{source.get("path", source["name"])}",
  "reasoning": "...",
  "mapped_to_id": "...",
  "mapped_to_path": "...",
  "out_of_scope": false
}}"""


def _validate_deep_response(
    response_text: str,
    valid_ids: set[str],
    path_to_id: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    text = response_text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        item = json.loads(text[start: end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(item, dict):
        return None
    mapped_id = item.get("mapped_to_id")
    if mapped_id and str(mapped_id) not in valid_ids:
        # Fallback: try to recover correct ID by matching the provided path
        recovered_id = None
        if path_to_id and item.get("mapped_to_path"):
            candidate = str(item["mapped_to_path"]).strip()
            # exact match first
            recovered_id = path_to_id.get(candidate)
            # normalized match: lowercase + collapse spaces
            if not recovered_id:
                norm_candidate = " ".join(candidate.lower().split())
                norm_map = {" ".join(k.lower().split()): v for k, v in path_to_id.items()}
                recovered_id = norm_map.get(norm_candidate)
        if recovered_id:
            item["mapped_to_id"] = recovered_id
        else:
            item["mapped_to_id"] = None
            item["mapped_to_path"] = None
    if "out_of_scope" not in item:
        item["out_of_scope"] = False
    return item


# ── Core batch runner ─────────────────────────────────────────────────────────

def _run_batches(
    source_categories: list[dict],
    ref_leaves: list[dict],
    prompt_fn,             # callable(ref_context, batch) -> str
    expect_out_of_scope: bool = False,
) -> list[dict[str, Any]]:
    valid_ids = {leaf["id"] for leaf in ref_leaves}
    ref_context = _build_reference_context(ref_leaves)
    total = len(source_categories)
    total_batches = (total + config.BATCH_SIZE - 1) // config.BATCH_SIZE
    all_items: list[dict[str, Any]] = []

    for batch_start in range(0, total, config.BATCH_SIZE):
        batch = source_categories[batch_start: batch_start + config.BATCH_SIZE]
        batch_num = batch_start // config.BATCH_SIZE + 1
        print(f"    Батч {batch_num}/{total_batches} ({len(batch)} категорій)...")

        prompt = prompt_fn(ref_context, batch)
        result_items = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                response_text = _call_api(prompt)
                result_items = _validate_and_parse(
                    response_text, batch, valid_ids, expect_out_of_scope
                )
                if result_items is not None:
                    break
                print(f"      Спроба {attempt}: невалідна відповідь, повторюю...")
            except urllib.error.HTTPError as e:
                print(f"      Спроба {attempt}: HTTP {e.code} — {e.reason}")
                if attempt < config.MAX_RETRIES:
                    time.sleep(2)
            except Exception as e:
                print(f"      Спроба {attempt}: помилка — {e}")
                if attempt < config.MAX_RETRIES:
                    time.sleep(2)

        if result_items is None:
            print(f"      Батч {batch_num}: всі спроби вичерпано")
            for src in batch:
                all_items.append({
                    "source_id": str(src["id"]),
                    "source_name": src["name"],
                    "mapped_to_id": None,
                    "mapped_to_path": None,
                    "out_of_scope": False,
                })
        else:
            all_items.extend(result_items)

    return all_items


# ── Public API ────────────────────────────────────────────────────────────────

def match_with_ai(
    source_categories: list[dict],
    ref_leaves: list[dict],
    examples: list[dict] | None = None,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Standard matching. Returns (matched, unmatched)."""
    if not source_categories:
        return [], []

    ref_lookup = {leaf["id"]: leaf for leaf in ref_leaves}
    valid_ids = {leaf["id"] for leaf in ref_leaves}
    src_lookup = {str(s["id"]): s for s in source_categories}

    prompt_fn = lambda ctx, batch: _build_prompt_standard(ctx, batch, examples)
    raw_items = _run_batches(source_categories, ref_leaves, prompt_fn)

    matched, unmatched = [], []
    for item in raw_items:
        src_id = str(item.get("source_id", ""))
        src = src_lookup.get(src_id)
        if not src:
            continue
        mapped_id = str(item.get("mapped_to_id") or "")
        if mapped_id and mapped_id in valid_ids:
            ref_leaf = ref_lookup[mapped_id]
            matched.append({
                "source_id": src_id,
                "source_name": src["name"],
                "source_path": src.get("path", src["name"]),
                "reference_id": mapped_id,
                "reference_name": ref_leaf["name"],
                "reference_path": ref_leaf["path"],
                "method": "ai",
                "confidence": "medium",
            })
        else:
            unmatched.append(src)

    return matched, unmatched


def match_with_ai_force(
    source_categories: list[dict],
    ref_leaves: list[dict],
    examples: list[dict] | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    """Force matching + scope classification. Returns (matched, out_of_scope, unmatched)."""
    if not source_categories:
        return [], [], []

    ref_lookup = {leaf["id"]: leaf for leaf in ref_leaves}
    valid_ids = {leaf["id"] for leaf in ref_leaves}
    src_lookup = {str(s["id"]): s for s in source_categories}

    prompt_fn = lambda ctx, batch: _build_prompt_force(ctx, batch, examples)
    raw_items = _run_batches(
        source_categories, ref_leaves, prompt_fn, expect_out_of_scope=True
    )

    matched, out_of_scope, still_unmatched = [], [], []
    for item in raw_items:
        src_id = str(item.get("source_id", ""))
        src = src_lookup.get(src_id)
        if not src:
            continue
        mapped_id = str(item.get("mapped_to_id") or "")
        if mapped_id and mapped_id in valid_ids:
            ref_leaf = ref_lookup[mapped_id]
            matched.append({
                "source_id": src_id,
                "source_name": src["name"],
                "source_path": src.get("path", src["name"]),
                "reference_id": mapped_id,
                "reference_name": ref_leaf["name"],
                "reference_path": ref_leaf["path"],
                "method": "ai_force",
                "confidence": "medium",
            })
        elif item.get("out_of_scope"):
            out_of_scope.append(src)
        else:
            still_unmatched.append(src)

    return matched, out_of_scope, still_unmatched


def match_with_ai_deep(
    source_categories: list[dict],
    ref_leaves: list[dict],
    examples: list[dict] | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[dict]]:
    """
    Deep single-item matching with chain-of-thought reasoning.
    Processes one category at a time, asks AI to reason before deciding.
    Returns (matched, out_of_scope, unmatched).
    """
    if not source_categories:
        return [], [], []

    valid_ids = {leaf["id"] for leaf in ref_leaves}
    ref_lookup = {leaf["id"]: leaf for leaf in ref_leaves}
    path_to_id = {leaf["path"]: leaf["id"] for leaf in ref_leaves}
    ref_context = _build_reference_context(ref_leaves)
    total = len(source_categories)

    matched, out_of_scope, unmatched = [], [], []

    for i, src in enumerate(source_categories, 1):
        src_id = str(src["id"])
        print(f"    [{i}/{total}] {src.get('path', src['name'])[:60]}...")

        prompt = _build_prompt_deep(ref_context, src, examples)
        result = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                response_text = _call_api(prompt)
                result = _validate_deep_response(response_text, valid_ids, path_to_id)
                if result is not None:
                    break
                print(f"      Спроба {attempt}: невалідна відповідь, повторюю...")
            except urllib.error.HTTPError as e:
                print(f"      Спроба {attempt}: HTTP {e.code} — {e.reason}")
                if attempt < config.MAX_RETRIES:
                    time.sleep(2)
            except Exception as e:
                print(f"      Спроба {attempt}: помилка — {e}")
                if attempt < config.MAX_RETRIES:
                    time.sleep(2)

        if result is None:
            unmatched.append(src)
            continue

        mapped_id = str(result.get("mapped_to_id") or "")
        reasoning = result.get("reasoning", "")
        if reasoning:
            print(f"      → {reasoning[:80]}...")

        if mapped_id and mapped_id in valid_ids:
            ref_leaf = ref_lookup[mapped_id]
            matched.append({
                "source_id": src_id,
                "source_name": src["name"],
                "source_path": src.get("path", src["name"]),
                "reference_id": mapped_id,
                "reference_name": ref_leaf["name"],
                "reference_path": ref_leaf["path"],
                "method": "ai_deep",
                "confidence": "high",
                "reasoning": reasoning,
            })
        elif result.get("out_of_scope"):
            out_of_scope.append({**src, "reasoning": reasoning})
        else:
            unmatched.append({**src, "reasoning": reasoning})

    return matched, out_of_scope, unmatched


def verify_matches(
    matched: list[dict],
    examples: list[dict] | None = None,
    methods_to_verify: frozenset[str] = frozenset({"ai", "ai_force", "ai_deep"}),
) -> tuple[list[dict], list[dict]]:
    """
    Verifies AI matches by asking the model: "Is this match correct?"
    Only verifies matches whose method is in methods_to_verify.
    High-confidence direct matches (exact/normalized) are passed through unchanged.

    Returns (confirmed_matched, rejected_matched).
    rejected_matched items have method="verify_rejected" and can be moved to unmatched.
    """
    to_verify = [m for m in matched if m.get("method") in methods_to_verify]
    skip = [m for m in matched if m.get("method") not in methods_to_verify]

    if not to_verify:
        return matched, []

    print(f"    Верифікую {len(to_verify)} AI матчів...")

    # Build verification batches
    batch_size = config.BATCH_SIZE
    total_batches = (len(to_verify) + batch_size - 1) // batch_size
    confirmed: list[dict] = []
    rejected: list[dict] = []

    for batch_start in range(0, len(to_verify), batch_size):
        batch = to_verify[batch_start: batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        print(f"    Верифікація батч {batch_num}/{total_batches} ({len(batch)} пар)...")

        verify_items = [
            {k: v for k, v in {
                "id": m["source_id"],
                "source_path": m.get("source_path", m["source_name"]),
                "reference_path": m["reference_path"],
                "reasoning": m.get("reasoning"),
            }.items() if v is not None}
            for m in batch
        ]
        batch_ids = {item["id"] for item in verify_items}
        prompt = _build_prompt_verify(verify_items, examples)
        result = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                response_text = _call_api(prompt)
                result = _validate_verify_response(response_text, batch_ids)
                if result is not None:
                    break
                print(f"      Спроба {attempt}: невалідна відповідь, повторюю...")
            except urllib.error.HTTPError as e:
                print(f"      Спроба {attempt}: HTTP {e.code} — {e.reason}")
                if attempt < config.MAX_RETRIES:
                    time.sleep(2)
            except Exception as e:
                print(f"      Спроба {attempt}: помилка — {e}")
                if attempt < config.MAX_RETRIES:
                    time.sleep(2)

        if result is None:
            # Can't verify this batch — keep all matches as-is
            print(f"      Батч {batch_num}: верифікація невдала, залишаю матчі без змін")
            confirmed.extend(batch)
            continue

        verdict_by_id = {str(item["id"]): item["correct"] for item in result}
        for m in batch:
            if verdict_by_id.get(m["source_id"], True):
                confirmed.append(m)
            else:
                rejected.append({**m, "method": "verify_rejected"})

    return skip + confirmed, rejected
