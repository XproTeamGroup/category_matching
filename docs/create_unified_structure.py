import json
from collections import defaultdict

def load_categories(filename):
    """Загружает категории из JSON файла"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def flatten_categories(items, parent_path=''):
    """Преобразует иерархию в плоский список с путями"""
    flat = []
    for item in items:
        path = f"{parent_path} > {item['name']}" if parent_path else item['name']
        flat.append({
            'id': item['id'],
            'name': item['name'],
            'path': path,
            'depth': len(path.split(' > ')),
            'has_children': len(item.get('children', [])) > 0
        })
        if 'children' in item and item['children']:
            flat.extend(flatten_categories(item['children'], path))
    return flat

# Загружаем все файлы
print("Загрузка файлов...")
cat_2 = load_categories('../2_1.json')
cat_3 = load_categories('../3_1.json')
cat_4 = load_categories('../4_1.json')

# Преобразуем в плоские списки
flat_2 = flatten_categories(cat_2)
flat_3 = flatten_categories(cat_3)
flat_4 = flatten_categories(cat_4)

all_flat = flat_2 + flat_3 + flat_4

print(f"Всего категорий: {len(all_flat)}")

# Группируем по названиям
by_name = defaultdict(list)
for cat in all_flat:
    by_name[cat['name']].append(cat)

print(f"Уникальных названий: {len(by_name)}")

# Определяем основные группы
# Анализируем корневые категории из всех файлов
root_categories_2 = [item['name'] for item in cat_2]
root_categories_3 = [item['name'] for item in cat_3]
root_categories_4 = [item['name'] for item in cat_4]

print("\n" + "=" * 80)
print("КОРНЕВЫЕ КАТЕГОРИИ ИЗ ФАЙЛОВ:")
print("=" * 80)
print(f"\n2_1.json ({len(root_categories_2)} категорий):")
for i, name in enumerate(root_categories_2, 1):
    print(f"  {i}. {name}")

print(f"\n3_1.json ({len(root_categories_3)} категорий):")
for i, name in enumerate(root_categories_3, 1):
    print(f"  {i}. {name}")

print(f"\n4_1.json ({len(root_categories_4)} категорий):")
for i, name in enumerate(root_categories_4, 1):
    print(f"  {i}. {name}")

# Теперь создадим унифицированную структуру
print("\n" + "=" * 80)
print("СОЗДАНИЕ УНИФИЦИРОВАННОЙ СТРУКТУРЫ")
print("=" * 80)

# Основные категории (8-11 штук)
unified_structure = []

# ID счетчик для новой структуры
current_id = 1

def create_category(name, children=None):
    """Создает категорию с автоинкрементным ID"""
    global current_id
    cat = {
        "id": current_id,
        "name": name
    }
    current_id += 1

    if children:
        cat["children"] = children
    else:
        cat["children"] = []

    return cat

# Собираем все категории для анализа паттернов
print("\nАнализ паттернов категорий...")

# Категории, связанные с запчастями для конкретных брендов/моделей
brand_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['simson', 'jawa', 'romet', 'komar', 'wsk', 'wfm', 'shl', 'mz etz', 'atv', 'baxter', 'mopar'])]

# Категории, связанные с двигателем
engine_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['двигун', 'мотор', 'циліндр', 'поршн', 'головк', 'кільц', 'карбюратор', 'газник'])]

# Категории, связанные с электрикой
electric_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['електр', 'електри', 'освітл', 'світл', 'лампа', 'акумулятор', 'батаре', 'зарядн', 'led', 'діод'])]

# Категории кузова и рамы
body_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['кузов', 'надбудов', 'надвож', 'рама', 'підвіс', 'завіш', 'амортизатор'])]

# Категории колес и шин
wheel_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['колес', 'шин', 'огумі', 'опон', 'камер', 'диск', 'обід', 'підшипник'])]

# Тормозная система
brake_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['гальм', 'тормоз', 'колод', 'щелеп', 'блокад'])]

# Трансмиссия и привод
transmission_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['передач', 'зчеплен', 'привід', 'напед', 'варіатор', 'ланцюг', 'зубчаст', 'ремен', 'пас'])]

# Выхлопная система
exhaust_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['випуск', 'видих', 'видех', 'глушник', 'тлумік'])]

# Одежда и защита
clothing_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['одяг', 'шолом', 'каск', 'рукавиц', 'захист', 'ослон', 'баклав', 'комінарк'])]

# Аксессуары
accessory_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['аксесуар', 'багаж', 'валіз', 'куфр', 'дзеркал', 'люстерк', 'брелок', 'наклейк', 'накрет'])]

# Химия и масла
chemistry_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['олій', 'олей', 'масл', 'хімі', 'мастил', 'антифриз', 'охолод'])]

# Инструменты
tools_categories = [c for c in all_flat if any(word in c['name'].lower() for word in
    ['інструмент', 'ключ', 'набір', 'нарзедз'])]

print(f"  Категории брендов: {len(set(c['name'] for c in brand_categories))}")
print(f"  Категории двигателя: {len(set(c['name'] for c in engine_categories))}")
print(f"  Категории электрики: {len(set(c['name'] for c in electric_categories))}")
print(f"  Категории кузова: {len(set(c['name'] for c in body_categories))}")
print(f"  Категории колес: {len(set(c['name'] for c in wheel_categories))}")
print(f"  Категории тормозов: {len(set(c['name'] for c in brake_categories))}")
print(f"  Категории трансмиссии: {len(set(c['name'] for c in transmission_categories))}")
print(f"  Категории выхлопа: {len(set(c['name'] for c in exhaust_categories))}")
print(f"  Категории одежды: {len(set(c['name'] for c in clothing_categories))}")
print(f"  Категории аксессуаров: {len(set(c['name'] for c in accessory_categories))}")
print(f"  Категории химии: {len(set(c['name'] for c in chemistry_categories))}")
print(f"  Категории инструментов: {len(set(c['name'] for c in tools_categories))}")

# Сохраним сводку в файл
with open('category_patterns.json', 'w', encoding='utf-8') as f:
    json.dump({
        'brand_categories': sorted(list(set(c['name'] for c in brand_categories))),
        'engine_categories': sorted(list(set(c['name'] for c in engine_categories))),
        'electric_categories': sorted(list(set(c['name'] for c in electric_categories))),
        'body_categories': sorted(list(set(c['name'] for c in body_categories))),
        'wheel_categories': sorted(list(set(c['name'] for c in wheel_categories))),
        'brake_categories': sorted(list(set(c['name'] for c in brake_categories))),
        'transmission_categories': sorted(list(set(c['name'] for c in transmission_categories))),
        'exhaust_categories': sorted(list(set(c['name'] for c in exhaust_categories))),
        'clothing_categories': sorted(list(set(c['name'] for c in clothing_categories))),
        'accessory_categories': sorted(list(set(c['name'] for c in accessory_categories))),
        'chemistry_categories': sorted(list(set(c['name'] for c in chemistry_categories))),
        'tools_categories': sorted(list(set(c['name'] for c in tools_categories)))
    }, f, ensure_ascii=False, indent=2)

print("\nПаттерны категорий сохранены в category_patterns.json")
print("\nГотово! Теперь можно создавать унифицированную структуру вручную.")
