import json

def add_parent_ids(categories, parent_id=None):
    """
    Рекурсивно добавляет parent_id к каждой категории.

    Args:
        categories: список категорий
        parent_id: ID родительской категории (None для корневых)
    """
    if not isinstance(categories, list):
        categories = [categories]

    for category in categories:
        # Сохраняем children для последующей обработки
        children = category.get('children', [])

        # Создаем новый упорядоченный словарь
        ordered_category = {}

        # Копируем все поля кроме parent_id и children в правильном порядке
        for key in category:
            if key not in ['parent_id', 'children']:
                ordered_category[key] = category[key]

        # Добавляем parent_id сразу после основных полей
        ordered_category['parent_id'] = parent_id

        # Добавляем children в конец
        ordered_category['children'] = children if children else []

        # Обновляем категорию
        category.clear()
        category.update(ordered_category)

        # Рекурсивно обрабатываем дочерние категории
        if category['children']:
            add_parent_ids(category['children'], category['id'])

    return categories


if __name__ == '__main__':
    # Загружаем new.json
    input_file = 'new.json'
    output_file = 'new.json'

    print(f'Загрузка {input_file}...')
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print('Добавление parent_id...')
    # Обрабатываем данные
    data = add_parent_ids(data, parent_id=None)

    print(f'Сохранение в {output_file}...')
    # Сохраняем обратно
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print('Готово! parent_id добавлены во все категории.')
