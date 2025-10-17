import json

def verify_structure(filename):
    """Проверяет структуру на соответствие требованиям"""
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats = {
        'total_categories': 0,
        'root_categories': 0,
        'max_depth': 0,
        'categories_by_depth': {},
        'all_names': [],
        'duplicates': []
    }

    def traverse(items, depth=1):
        """Рекурсивно обходит категории"""
        stats['max_depth'] = max(stats['max_depth'], depth)

        if depth not in stats['categories_by_depth']:
            stats['categories_by_depth'][depth] = 0

        for item in items:
            stats['total_categories'] += 1
            stats['categories_by_depth'][depth] += 1

            if depth == 1:
                stats['root_categories'] += 1

            name = item.get('name', '')
            stats['all_names'].append(name)

            if 'children' in item and item['children']:
                traverse(item['children'], depth + 1)

    traverse(data)

    # Проверка дубликатов
    name_counts = {}
    for name in stats['all_names']:
        name_counts[name] = name_counts.get(name, 0) + 1

    stats['duplicates'] = [name for name, count in name_counts.items() if count > 1]

    return stats, data

# Проверяем структуру
stats, data = verify_structure('unified_category_structure.json')

print("=" * 80)
print("PROVIRKA UNIFIKOVANOYI STRUKTURI")
print("=" * 80)
print(f"\n[OK] Vsogo kategoriy: {stats['total_categories']}")
print(f"[OK] Korenevikh kategoriy: {stats['root_categories']}")
print(f"[OK] Maksimalna glibina: {stats['max_depth']}")

print(f"\nРаспределение по уровням:")
for depth in sorted(stats['categories_by_depth'].keys()):
    print(f"  Уровень {depth}: {stats['categories_by_depth'][depth]} категорий")

print(f"\n{'=' * 80}")
print("ТРЕБОВАНИЯ:")
print(f"{'=' * 80}")

# Проверка требований
req1 = stats['max_depth'] <= 4
req2 = 8 <= stats['root_categories'] <= 11
req3 = len(stats['duplicates']) == 0

print(f"[{'OK' if req1 else 'FAIL'}] Maksimalna glibina <= 4: {stats['max_depth']}")
print(f"[{'OK' if req2 else 'FAIL'}] Kilkist' korenevikh 8-11: {stats['root_categories']}")
print(f"[{'OK' if req3 else 'FAIL'}] Nemae dublikativ: {len(stats['duplicates'])} dublikativ")

if stats['duplicates']:
    print(f"\nНайденные дубликаты:")
    for dup in stats['duplicates']:
        print(f"  - {dup}")

# Проверка языка (простая проверка на наличие украинских символов)
has_ukrainian = any(any(c in name for c in 'іїєґ') for name in stats['all_names'])
has_non_ukrainian = any(any(c in name for c in 'ыэъё') for name in stats['all_names'])

print(f"\n[{'OK' if has_ukrainian else 'FAIL'}] Ukrainska mova: {'Tak' if has_ukrainian else 'Ni'}")
print(f"[{'OK' if not has_non_ukrainian else 'FAIL'}] Nemae rosiyskikh simvoliv: {'Tak' if not has_non_ukrainian else 'Ni'}")

# Проверка на "Інше"
has_inshe = any('інше' in name.lower() or 'прочее' in name.lower() for name in stats['all_names'])
print(f"[{'OK' if not has_inshe else 'FAIL'}] Nemae 'Inshe': {'Tak' if not has_inshe else 'Ni'}")

print(f"\n{'=' * 80}")
print("KORENEVІ KATEGORII:")
print(f"{'=' * 80}")
for i, cat in enumerate(data, 1):
    child_count = len(cat.get('children', []))
    print(f"{i}. {cat['name']} ({child_count} pidkategoriy)")

all_passed = req1 and req2 and req3 and has_ukrainian and not has_non_ukrainian and not has_inshe

print(f"\n{'=' * 80}")
if all_passed:
    print(">>> VSI VIMOGI VIKONANI! <<<")
else:
    print("!!! DEYAKI VIMOGI NE VIKONANI !!!")
print(f"{'=' * 80}")
