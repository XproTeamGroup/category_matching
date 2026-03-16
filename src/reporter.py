"""
Generates output files:
  output/mapping.json   — full mapping with source_id → reference_id
  output/mapping.csv    — same as spreadsheet-friendly CSV
  output/unmatched.json — source categories with no match (for manual review)
  output/stats.json     — statistics summary
"""

import csv
import json
import os
from typing import Any


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def _ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _path(filename: str) -> str:
    return os.path.join(OUTPUT_DIR, filename)


def build_stats(
    total_source: int,
    matched: list[dict],
    unmatched: list[dict],
    out_of_scope: list[dict] | None = None,
    rejected_by_verify: list[dict] | None = None,
) -> dict[str, Any]:
    by_method: dict[str, int] = {}
    for m in matched:
        method = m.get("method", "unknown")
        by_method[method] = by_method.get(method, 0) + 1

    match_count = len(matched)
    oos_count = len(out_of_scope) if out_of_scope else 0
    # match rate excludes out_of_scope (they can't be matched by design)
    matchable = total_source - oos_count
    rate = round(match_count / matchable * 100, 1) if matchable else 0
    rate_total = round(match_count / total_source * 100, 1) if total_source else 0

    stats: dict[str, Any] = {
        "total_source": total_source,
        "matched": match_count,
        "unmatched": len(unmatched),
        "match_rate_percent": rate_total,
        "by_method": by_method,
    }
    if out_of_scope is not None:
        stats["out_of_scope"] = oos_count
        stats["matchable_total"] = matchable
        stats["match_rate_of_matchable_percent"] = rate

    if rejected_by_verify is not None:
        stats["rejected_by_verify"] = len(rejected_by_verify)

    return stats


def save_all(
    matched: list[dict],
    unmatched: list[dict],
    total_source: int,
    out_of_scope: list[dict] | None = None,
    rejected_by_verify: list[dict] | None = None,
) -> dict[str, Any]:
    _ensure_output_dir()

    stats = build_stats(total_source, matched, unmatched, out_of_scope, rejected_by_verify)

    fieldnames = ["source_id", "source_name", "reference_id", "reference_name",
                  "reference_path", "method", "confidence"]

    # mapping.json
    with open(_path("mapping.json"), "w", encoding="utf-8") as f:
        json.dump(matched, f, ensure_ascii=False, indent=2)

    # mapping.csv — written immediately after JSON so they are always in sync
    try:
        with open(_path("mapping.csv"), "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames,
                                    extrasaction="ignore", restval="")
            writer.writeheader()
            writer.writerows(matched)
        # Verify row count matches
        with open(_path("mapping.csv"), encoding="utf-8-sig", newline="") as f:
            written = sum(1 for _ in csv.reader(f)) - 1  # minus header
        if written != len(matched):
            print(f"  ПОПЕРЕДЖЕННЯ: mapping.csv має {written} рядків, очікувалось {len(matched)}")
    except PermissionError:
        print("  ПОМИЛКА: mapping.csv відкритий в іншій програмі (Excel?). "
              "Закрийте файл і запустіть ще раз.")

    # unmatched.json
    with open(_path("unmatched.json"), "w", encoding="utf-8") as f:
        json.dump(unmatched, f, ensure_ascii=False, indent=2)

    # out_of_scope.json (only in --force-match mode)
    if out_of_scope is not None:
        with open(_path("out_of_scope.json"), "w", encoding="utf-8") as f:
            json.dump(out_of_scope, f, ensure_ascii=False, indent=2)

    # verify_rejected.json (only when --verify is used)
    if rejected_by_verify is not None:
        with open(_path("verify_rejected.json"), "w", encoding="utf-8") as f:
            json.dump(rejected_by_verify, f, ensure_ascii=False, indent=2)

    # stats.json
    with open(_path("stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def print_stats(stats: dict[str, Any]) -> None:
    print()
    print("=" * 55)
    print("РЕЗУЛЬТАТИ МАТЧИНГУ")
    print("=" * 55)
    print(f"  Всього source категорій      : {stats['total_source']}")
    if "out_of_scope" in stats:
        print(f"  Поза доменом (out_of_scope)  : {stats['out_of_scope']}")
        print(f"  Потенційно сматчуваних       : {stats['matchable_total']}")
    print(f"  Сматчено                     : {stats['matched']}")
    print(f"  Не сматчено                  : {stats['unmatched']}")
    print(f"  Відсоток (від усіх)          : {stats['match_rate_percent']}%")
    if "match_rate_of_matchable_percent" in stats:
        print(f"  Відсоток (від сматчуваних)   : {stats['match_rate_of_matchable_percent']}%")
    if "rejected_by_verify" in stats:
        print(f"  Відхилено верифікацією       : {stats['rejected_by_verify']}")
    print()
    print("  По методах:")
    for method, count in stats.get("by_method", {}).items():
        print(f"    {method:20s}: {count}")
    print("=" * 55)
    print("  Файли збережено в: output/")
    print("    mapping.json      — маппінг для імпорту в БД")
    print("    mapping.csv       — Excel-friendly")
    print("    unmatched.json    — потребують ручної перевірки")
    if "out_of_scope" in stats:
        print("    out_of_scope.json    — поза доменом reference")
    if "rejected_by_verify" in stats:
        print("    verify_rejected.json — відхилені верифікацією (для ручного перегляду)")
    print("    stats.json        — статистика")
    print("=" * 55)
