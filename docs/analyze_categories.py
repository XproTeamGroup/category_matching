import json
from collections import defaultdict

def analyze_json_file(filename):
    """Анализирует структуру JSON файла с категориями"""
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats = {
        'filename': filename,
        'total_categories': 0,
        'root_categories': [],
        'max_depth': 0,
        'all_categories': []
    }

    def traverse(items, depth=1, parent_name=''):
        """Рекурсивно обходит категории и собирает статистику"""
        nonlocal stats

        stats['max_depth'] = max(stats['max_depth'], depth)

        for item in items:
            stats['total_categories'] += 1

            category_info = {
                'id': item.get('id'),
                'name': item.get('name'),
                'parent_name': parent_name,
                'depth': depth,
                'has_children': len(item.get('children', [])) > 0
            }

            stats['all_categories'].append(category_info)

            if depth == 1:
                stats['root_categories'].append({
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'children_count': len(item.get('children', []))
                })

            if 'children' in item and item['children']:
                traverse(item['children'], depth + 1, item.get('name'))

    traverse(data)
    return stats

# Анализируем все три файла
files = ['2_1.json', '3_1.json', '4_1.json']
all_stats = []

print("=" * 80)
print("АНАЛИЗ СТРУКТУРЫ КАТЕГОРИЙ")
print("=" * 80)

for filename in files:
    try:
        stats = analyze_json_file(filename)
        all_stats.append(stats)

        print(f"\n{'=' * 80}")
        print(f"Файл: {filename}")
        print(f"{'=' * 80}")
        print(f"Всего категорий: {stats['total_categories']}")
        print(f"Корневых категорий: {len(stats['root_categories'])}")
        print(f"Максимальная глубина: {stats['max_depth']}")
        print(f"\nКорневые категории:")
        for i, cat in enumerate(stats['root_categories'], 1):
            print(f"  {i}. {cat['name']} (подкатегорий: {cat['children_count']})")

    except Exception as e:
        print(f"Ошибка при обработке {filename}: {e}")

# Сохраняем детальную информацию в файл для дальнейшего анализа
print(f"\n{'=' * 80}")
print("Сохранение детальной информации...")
print(f"{'=' * 80}")

with open('category_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(all_stats, f, ensure_ascii=False, indent=2)

print("\nДетальная информация сохранена в category_analysis.json")

# Собираем все уникальные категории
all_categories = []
for stats in all_stats:
    all_categories.extend(stats['all_categories'])

print(f"\nВсего категорий во всех файлах: {len(all_categories)}")

# Группируем по названиям для поиска дубликатов
categories_by_name = defaultdict(list)
for cat in all_categories:
    categories_by_name[cat['name']].append(cat)

print(f"\nУникальных названий категорий: {len(categories_by_name)}")

# Выводим самые популярные категории (встречающиеся в нескольких файлах)
print(f"\n{'=' * 80}")
print("КАТЕГОРИИ, ВСТРЕЧАЮЩИЕСЯ В НЕСКОЛЬКИХ ФАЙЛАХ:")
print(f"{'=' * 80}")
common_categories = {name: cats for name, cats in categories_by_name.items() if len(cats) > 1}
for name, cats in sorted(common_categories.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"\n{name} (встречается {len(cats)} раз)")
    for cat in cats:
        depth_str = "  " * (cat['depth'] - 1)
        print(f"  {depth_str}└─ Уровень {cat['depth']}, родитель: {cat['parent_name'] or 'корень'}")
