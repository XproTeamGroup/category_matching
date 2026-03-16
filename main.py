"""
Category matching pipeline.

Usage:
    python main.py                                        # direct + AI
    python main.py --force-match                          # + force AI pass
    python main.py --examples examples.json               # with few-shot examples
    python main.py --verify                               # + post-match verification
    python main.py --force-match --examples ex.json --verify   # all options

    python main.py --reference reference.json --source source.json
    python main.py --skip-ai       # direct matching only
    python main.py --dry-run       # stats only, no files saved
"""

import argparse
import json
import sys

from src.tree_builder import load_and_build, get_leaf_categories, filter_unmatched, print_tree_stats
from src.direct_matcher import match_direct
from src.ai_matcher import match_with_ai, match_with_ai_force, verify_matches
from src.reporter import save_all, build_stats, print_stats


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Universal category matching tool")
    p.add_argument("--reference", default="reference.json")
    p.add_argument("--source", default="source.json")
    p.add_argument(
        "--examples",
        metavar="FILE",
        help='JSON file with known correct matches: [{"source_name": "...", "reference_path": "..."}]',
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="After matching, ask AI to verify each AI match pair. "
             "Rejected pairs go to verify_rejected.json for manual review.",
    )
    p.add_argument(
        "--force-match",
        action="store_true",
        help="Re-run AI on unmatched with assertive prompt + scope classification.",
    )
    p.add_argument("--skip-ai", action="store_true", help="Direct matching only, skip AI")
    p.add_argument("--dry-run", action="store_true", help="Print stats only, don't save files")
    return p.parse_args()


def load_examples(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            print(f"Помилка: {path} повинен бути JSON-масивом")
            sys.exit(1)
        required = {"source_name", "reference_path"}
        for item in data:
            if not required.issubset(item):
                print(f"Помилка: кожен елемент examples повинен мати поля: {required}")
                sys.exit(1)
        print(f"  Завантажено {len(data)} прикладів з {path}")
        return data
    except FileNotFoundError:
        print(f"Помилка: файл прикладів не знайдено — {path}")
        sys.exit(1)


def main() -> None:
    args = parse_args()

    # ── 1. Load files ────────────────────────────────────────────────────────
    print("Завантажую файли...")
    try:
        ref_categories, ref_paths = load_and_build(args.reference)
        src_categories, _ = load_and_build(args.source)
    except FileNotFoundError as e:
        print(f"Помилка: {e}")
        sys.exit(1)

    print_tree_stats(ref_categories, "REFERENCE")
    print_tree_stats(src_categories, "SOURCE")

    ref_leaves = get_leaf_categories(ref_categories, ref_paths)

    src_categories, already_matched = filter_unmatched(src_categories)
    print(f"\nЦілі (листові reference): {len(ref_leaves)}")
    print(f"Source для матчингу: {len(src_categories)}"
          + (f" (пропущено вже сматчених: {already_matched})" if already_matched else ""))

    # ── 2. Load examples (optional) ──────────────────────────────────────────
    examples: list[dict] | None = None
    if args.examples:
        print()
        examples = load_examples(args.examples)

    # ── 3. Direct matching ───────────────────────────────────────────────────
    print("\nКрок 1: Прямий матчинг (exact / normalized)...")
    matched, unmatched = match_direct(src_categories, ref_leaves)
    print(f"  Результат: {len(matched)} сматчено, {len(unmatched)} залишилось")

    # ── 4. Standard AI matching ──────────────────────────────────────────────
    out_of_scope: list[dict] | None = None

    if not args.skip_ai and unmatched:
        print(f"\nКрок 2: AI матчинг ({len(unmatched)} категорій)...")
        ai_matched, unmatched = match_with_ai(unmatched, ref_leaves, examples)
        matched.extend(ai_matched)
        print(f"  Результат: {len(ai_matched)} сматчено, {len(unmatched)} залишилось")
    elif args.skip_ai:
        print("\nКрок 2: пропущено (--skip-ai)")

    # ── 5. Force-match pass (optional) ──────────────────────────────────────
    if args.force_match and unmatched and not args.skip_ai:
        print(f"\nКрок 3 (--force-match): {len(unmatched)} категорій...")
        force_matched, out_of_scope, unmatched = match_with_ai_force(
            unmatched, ref_leaves, examples
        )
        matched.extend(force_matched)
        print(f"  Результат: {len(force_matched)} сматчено, "
              f"{len(out_of_scope)} out_of_scope, {len(unmatched)} не сматчено")

    # ── 6. Verify AI matches (optional) ──────────────────────────────────────
    rejected_by_verify: list[dict] | None = None

    if args.verify and not args.skip_ai:
        ai_count = sum(1 for m in matched if m.get("method") in {"ai", "ai_force"})
        print(f"\nКрок verify (--verify): перевіряю {ai_count} AI матчів...")
        matched, rejected_by_verify = verify_matches(matched, examples)
        confirmed_count = ai_count - len(rejected_by_verify)
        # Rejected pairs go to unmatched for manual review
        unmatched = list(unmatched) + [
            {k: v for k, v in r.items() if k != "method"}
            for r in rejected_by_verify
        ]
        print(f"  Підтверджено: {confirmed_count}, відхилено: {len(rejected_by_verify)}")

    # ── 7. Save results ──────────────────────────────────────────────────────
    total_source = len(src_categories)

    if args.dry_run:
        stats = build_stats(total_source, matched, unmatched, out_of_scope, rejected_by_verify)
    else:
        stats = save_all(matched, unmatched, total_source, out_of_scope, rejected_by_verify)

    print_stats(stats)


if __name__ == "__main__":
    main()
