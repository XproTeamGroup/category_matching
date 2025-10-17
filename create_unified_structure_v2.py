import json

# Загрузка файлов
with open('2_1.json', 'r', encoding='utf-8') as f:
    data_2 = json.load(f)
with open('3_1.json', 'r', encoding='utf-8') as f:
    data_3 = json.load(f)
with open('4_1.json', 'r', encoding='utf-8') as f:
    data_4 = json.load(f)

current_id = 1
unified_structure = []

# Множество для отслеживания уже добавленных категорий (по имени)
seen_categories = set()

# Функция для копирования структуры категории с новыми ID и исключением "Інше"
def copy_category_structure(cat, parent_id=None, max_depth=3, current_depth=1, parent_path=""):
    global current_id, seen_categories

    # Пропускаем категории "Інше"
    if 'Інше' in cat['name'] or 'Inne' in cat['name']:
        return None

    # Создаем уникальный путь для категории
    current_path = f"{parent_path}/{cat['name']}" if parent_path else cat['name']

    # Проверяем, не добавлена ли уже эта категория в этом пути
    if current_path in seen_categories:
        return None

    seen_categories.add(current_path)

    new_cat = {
        "id": current_id,
        "name": cat['name'],
        "children": []
    }
    current_id += 1

    # Рекурсивно добавляем детей, если не достигли максимальной глубины
    if cat.get('children') and current_depth < max_depth:
        for child in cat['children']:
            new_child = copy_category_structure(child, new_cat['id'], max_depth, current_depth + 1, current_path)
            if new_child:
                new_cat['children'].append(new_child)

    return new_cat

# ============================================================
# 1. ВЕЛОСИПЕДНІ АКСЕСУАРИ ТА ЧАСТИНИ
# ============================================================
bike_cat = {
    "id": current_id,
    "name": "Велосипедні аксесуари та частини",
    "children": []
}
current_id += 1
seen_categories.add(bike_cat['name'])

for cat in data_2:
    new_cat = copy_category_structure(cat, bike_cat['id'], parent_path=bike_cat['name'])
    if new_cat:
        bike_cat['children'].append(new_cat)

unified_structure.append(bike_cat)
print(f"1. {bike_cat['name']}: {len(bike_cat['children'])} підкатегорій")

# ============================================================
# 2. МОТОЦИКЛЕТНІ ТА МОПЕДНІ ЧАСТИНИ
# ============================================================
moto_cat = {
    "id": current_id,
    "name": "Мотоциклетні та мопедні частини",
    "children": []
}
current_id += 1
seen_categories.add(moto_cat['name'])

model_keywords = ['JAWA', 'MZ', 'ROMET', 'KOMAR', 'SIMSON', 'WSK', 'WFM', 'SHL', 'ATV']

for cat in data_3:
    if not any(keyword in cat['name'] for keyword in model_keywords):
        new_cat = copy_category_structure(cat, moto_cat['id'], parent_path=moto_cat['name'])
        if new_cat:
            moto_cat['children'].append(new_cat)

unified_structure.append(moto_cat)
print(f"2. {moto_cat['name']}: {len(moto_cat['children'])} підкатегорій")

# ============================================================
# 3. ЧАСТИНИ ДЛЯ КОНКРЕТНИХ МОТОЦИКЛЕТНИХ МОДЕЛЕЙ
# ============================================================
specific_models_cat = {
    "id": current_id,
    "name": "Частини для конкретних мотоциклетних моделей",
    "children": []
}
current_id += 1
seen_categories.add(specific_models_cat['name'])

for cat in data_3:
    if any(keyword in cat['name'] for keyword in model_keywords):
        new_cat = copy_category_structure(cat, specific_models_cat['id'], parent_path=specific_models_cat['name'])
        if new_cat:
            specific_models_cat['children'].append(new_cat)

unified_structure.append(specific_models_cat)
print(f"3. {specific_models_cat['name']}: {len(specific_models_cat['children'])} підкатегорій")

# ============================================================
# 4. OFF-ROAD ТА 4X4 АКСЕСУАРИ
# ============================================================
offroad_cat = {
    "id": current_id,
    "name": "Off-road та 4x4 аксесуари",
    "children": []
}
current_id += 1
seen_categories.add(offroad_cat['name'])

# Основные категории для off-road
offroad_keywords = ['надвож', 'підвіс', 'кузов', 'бампер', 'багажник', 'захист', 'дах',
                    'двер', 'маск', 'порог', 'пак', 'bull', 'намет']

for cat in data_4:
    cat_name_lower = cat['name'].lower()
    if any(keyword in cat_name_lower for keyword in offroad_keywords):
        new_cat = copy_category_structure(cat, offroad_cat['id'], parent_path=offroad_cat['name'])
        if new_cat:
            offroad_cat['children'].append(new_cat)

unified_structure.append(offroad_cat)
print(f"4. {offroad_cat['name']}: {len(offroad_cat['children'])} підкатегорій")

# ============================================================
# 5. ШИНИ, ДИСКИ ТА КОЛЕСА
# ============================================================
wheels_cat = {
    "id": current_id,
    "name": "Шини, диски та колеса",
    "children": []
}
current_id += 1
seen_categories.add(wheels_cat['name'])

wheels_keywords = ['шин', 'огум', 'опон', 'диск', 'фельг', 'felg', 'кол', 'камер',
                  'дет', 'відстан', 'dystans']

# Из всех файлов, избегая дублирования
for cat in data_2 + data_3 + data_4:
    if any(keyword in cat['name'].lower() for keyword in wheels_keywords):
        new_cat = copy_category_structure(cat, wheels_cat['id'], parent_path=wheels_cat['name'])
        if new_cat:
            wheels_cat['children'].append(new_cat)

unified_structure.append(wheels_cat)
print(f"5. {wheels_cat['name']}: {len(wheels_cat['children'])} підкатегорій")

# ============================================================
# 6. ОСВІТЛЕННЯ ТА ЕЛЕКТРИКА
# ============================================================
lighting_cat = {
    "id": current_id,
    "name": "Освітлення та електрика",
    "children": []
}
current_id += 1
seen_categories.add(lighting_cat['name'])

lighting_keywords = ['освітл', 'світл', 'електр', 'ліхтар', 'лампк', 'lamp',
                    'лампи', 'żarów', 'led', 'акумулятор', 'зарядн', 'батар']

for cat in data_2 + data_3 + data_4:
    cat_name_lower = cat['name'].lower()
    if any(keyword in cat_name_lower for keyword in lighting_keywords):
        new_cat = copy_category_structure(cat, lighting_cat['id'], parent_path=lighting_cat['name'])
        if new_cat:
            lighting_cat['children'].append(new_cat)

unified_structure.append(lighting_cat)
print(f"6. {lighting_cat['name']}: {len(lighting_cat['children'])} підкатегорій")

# ============================================================
# 7. ІНСТРУМЕНТИ ТА ОБЛАДНАННЯ
# ============================================================
tools_cat = {
    "id": current_id,
    "name": "Інструменти та обладнання",
    "children": []
}
current_id += 1
seen_categories.add(tools_cat['name'])

tools_keywords = ['інструмент', 'компресор', 'ключ', 'насос', 'помп', 'лебідк', 'вициагар',
                 'трос', 'лин', 'шекл', 'блок', 'ланцюг']

for cat in data_2 + data_3 + data_4:
    cat_name_lower = cat['name'].lower()
    if any(keyword in cat_name_lower for keyword in tools_keywords):
        new_cat = copy_category_structure(cat, tools_cat['id'], parent_path=tools_cat['name'])
        if new_cat:
            tools_cat['children'].append(new_cat)

unified_structure.append(tools_cat)
print(f"7. {tools_cat['name']}: {len(tools_cat['children'])} підкатегорій")

# ============================================================
# 8. ОДЯГ, ВЗУТТЯ ТА ЗАХИСТ
# ============================================================
clothing_cat = {
    "id": current_id,
    "name": "Одяг, взуття та захист",
    "children": []
}
current_id += 1
seen_categories.add(clothing_cat['name'])

clothing_keywords = ['одяг', 'взутт', 'шолом', 'каск', 'рукав', 'рекав', 'шапк',
                    'шкарпет', 'шорт', 'штан', 'курт', 'футболк', 'толстов',
                    'балаклав', 'комін', 'окуляр', 'захист', 'ochron']

for cat in data_2 + data_3 + data_4:
    cat_name_lower = cat['name'].lower()
    if any(keyword in cat_name_lower for keyword in clothing_keywords):
        new_cat = copy_category_structure(cat, clothing_cat['id'], parent_path=clothing_cat['name'])
        if new_cat:
            clothing_cat['children'].append(new_cat)

unified_structure.append(clothing_cat)
print(f"8. {clothing_cat['name']}: {len(clothing_cat['children'])} підкатегорій")

# ============================================================
# 9. ГАЛЬМІВНІ СИСТЕМИ ТА КОМПОНЕНТИ
# ============================================================
brakes_cat = {
    "id": current_id,
    "name": "Гальмівні системи та компоненти",
    "children": []
}
current_id += 1
seen_categories.add(brakes_cat['name'])

brakes_keywords = ['гальм', 'hamuль']

for cat in data_2 + data_3 + data_4:
    cat_name_lower = cat['name'].lower()
    if any(keyword in cat_name_lower for keyword in brakes_keywords):
        new_cat = copy_category_structure(cat, brakes_cat['id'], parent_path=brakes_cat['name'])
        if new_cat:
            brakes_cat['children'].append(new_cat)

unified_structure.append(brakes_cat)
print(f"9. {brakes_cat['name']}: {len(brakes_cat['children'])} підкатегорій")

# ============================================================
# 10. ХІМІЯ, ОЛІЇ ТА ВИТРАТНІ МАТЕРІАЛИ
# ============================================================
chemicals_cat = {
    "id": current_id,
    "name": "Хімія, олії та витратні матеріали",
    "children": []
}
current_id += 1
seen_categories.add(chemicals_cat['name'])

chemicals_keywords = ['хім', 'оліj', 'мастил', 'фільтр', 'filter', 'запобіжник',
                     'ущільн', 'orіng', 'simering', 'свічк', 'śwіec']

for cat in data_2 + data_3 + data_4:
    cat_name_lower = cat['name'].lower()
    if any(keyword in cat_name_lower for keyword in chemicals_keywords):
        new_cat = copy_category_structure(cat, chemicals_cat['id'], parent_path=chemicals_cat['name'])
        if new_cat:
            chemicals_cat['children'].append(new_cat)

unified_structure.append(chemicals_cat)
print(f"10. {chemicals_cat['name']}: {len(chemicals_cat['children'])} підкатегорій")

# ============================================================
# СТАТИСТИКА
# ============================================================
print("\n" + "="*60)
print("ПІДСУМОК:")
print("="*60)
print(f"Всього головних категорій: {len(unified_structure)}")

def count_all_categories(categories):
    count = len(categories)
    for cat in categories:
        if cat.get('children'):
            count += count_all_categories(cat['children'])
    return count

total_categories = count_all_categories(unified_structure)
print(f"Всього категорій (включно з підкатегоріями): {total_categories}")

def get_max_depth(categories, current_depth=1):
    if not categories:
        return current_depth - 1
    max_d = current_depth
    for cat in categories:
        if cat.get('children'):
            max_d = max(max_d, get_max_depth(cat['children'], current_depth + 1))
    return max_d

max_depth = get_max_depth(unified_structure)
print(f"Максимальна глибина вкладеності: {max_depth} рівнів")

# Сохраняем в файл
output_file = 'unified_category_structure.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(unified_structure, f, ensure_ascii=False, indent=2)

print(f"\nСтруктура збережена у файл: {output_file}")
