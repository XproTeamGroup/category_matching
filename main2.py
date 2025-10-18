import json
import os
import time
import anthropic
import pandas as pd
import re # Добавьте эту строку
from datetime import datetime

# --- Конфигурация ---
NEW_CATEGORIES_FILE = 'new.json'
OLD_CATEGORIES_FILES = ['4_1.json']
OUTPUT_DIR = 'report_matching_3'  # Базовая директория для отчетов
CHUNK_SIZE = 10 # Количество старых категорий для обработки за один запрос к Claude (уменьшено для тестирования)
CLAUDE_MODEL = "claude-3-5-haiku-20241022" # Можно использовать "claude-3-sonnet-20240229" для меньших затрат
MAX_TOKENS_RESPONSE = 8000 # Максимальное количество токенов в ответе Claude
TEMPERATURE = 0.0 # Температура для Claude (0.0 для более детерминированных ответов)
# --- Конец конфигурации ---

# Убедитесь, что ваш API-ключ установлен как переменная окружения
# export ANTHROPIC_API_KEY="YOUR_CLAUDE_API_KEY"
# Если не установлено, можно раскомментировать и вставить здесь:
os.environ["ANTHROPIC_API_KEY"] = "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"

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# --- Вспомогательные функции ---
def load_categories(filepath):
    """Загружает категории из JSON файла."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def flatten_categories(categories_data, parent_path_names=None):
    """
    Рекурсивно обходит иерархическую структуру категорий и возвращает плоский список всех категорий
    с полными путями.
    """
    if parent_path_names is None:
        parent_path_names = []
    
    flattened = []
    
    for category in categories_data:
        current_path_names = parent_path_names + [category['name']]
        full_path_name = " > ".join(current_path_names)
        
        # Добавляем текущую категорию
        flattened.append({
            'id': category['id'],
            'name': category['name'],
            'parent_id': category['parent_id'],
            'full_path_name': full_path_name,
            'has_children': len(category.get('children', [])) > 0
        })
        
        # Рекурсивно обрабатываем дочерние категории
        if category.get('children'):
            flattened.extend(flatten_categories(category['children'], current_path_names))
    
    return flattened

def get_leaf_categories_from_hierarchical(categories_data):
    """
    Определяет конечные категории из иерархической структуры (новый формат)
    """
    # Получаем плоский список всех категорий
    all_categories = flatten_categories(categories_data)
    
    # Фильтруем только конечные категории (без детей)
    leaf_categories = [cat for cat in all_categories if not cat['has_children']]
    
    return leaf_categories

def get_leaf_categories_from_old_format(categories_data):
    """
    Определяет конечные категории из старого формата с path
    """
    # Создаем плоскую карту
    flat_map = create_flat_category_map_from_old_format(categories_data)
    
    # Фильтруем только конечные категории (без детей)
    leaf_categories = [cat for cat in flat_map.values() if not cat['has_children']]
    
    return leaf_categories

def get_leaf_categories(categories_data):
    """
    Автоматически определяет формат и возвращает конечные категории
    """
    if not categories_data:
        return []
    
    # Проверяем формат данных
    first_item = categories_data[0] if isinstance(categories_data, list) else categories_data
    
    if 'children' in first_item:
        # Новый иерархический формат
        return get_leaf_categories_from_hierarchical(categories_data)
    elif 'path' in first_item:
        # Старый формат с path
        return get_leaf_categories_from_old_format(categories_data)
    else:
        # Неизвестный формат
        print("Warning: Unknown category format")
        return []

def chunk_list(lst, chunk_size):
    """Разбивает список на части (батчи)."""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def create_flat_category_map_from_hierarchical(categories_data):
    """Создает плоскую карту всех категорий из иерархической структуры (новый формат)."""
    all_categories = flatten_categories(categories_data)
    # Приводим все ID к строкам для единообразия
    return {str(cat['id']): cat for cat in all_categories}

def create_flat_category_map_from_old_format(categories_data):
    """Создает плоскую карту категорий из старого формата с path."""
    category_map = {}
    
    for cat in categories_data:
        # Строим полный путь для старого формата
        path_parts = []
        if 'path' in cat:
            path_ids = cat['path'].split('>')
            for path_id in path_ids:
                # Найти категорию с таким ID
                found_cat = next((c for c in categories_data if str(c['id']) == str(path_id)), None)
                if found_cat:
                    path_parts.append(found_cat['name'])
        else:
            path_parts = [cat['name']]
        
        full_path_name = " > ".join(path_parts)
        
        category_map[str(cat['id'])] = {
            'id': str(cat['id']),
            'name': cat['name'],
            'path': cat.get('path', ''),
            'full_path_name': full_path_name,
            'has_children': False  # Определим позже
        }
    
    # Определяем какие категории имеют детей
    for cat in categories_data:
        cat_id = str(cat['id'])
        if 'path' in cat:
            # Проверяем, есть ли категории с путем, который начинается с текущего пути + ID
            current_path_prefix = cat['path'] + '>'
            has_children = any(
                other_cat.get('path', '').startswith(current_path_prefix) 
                for other_cat in categories_data 
                if str(other_cat['id']) != cat_id
            )
            category_map[cat_id]['has_children'] = has_children
    
    return category_map

def get_full_path_name(category_id, categories_flat_map):
    """Возвращает полный читаемый путь для категории по её ID."""
    category = categories_flat_map.get(category_id)
    if category:
        return category['full_path_name']
    return "Unknown category"

def find_category_by_full_path(full_path_name, categories_flat_map):
    """Находит категорию по полному пути и возвращает её ID."""
    for cat_id, cat_data in categories_flat_map.items():
        if cat_data['full_path_name'] == full_path_name:
            return cat_id
    return None

def save_russian_statistics(total_input, matched, unmatched, percentage_matched,
                          api_requests, execution_time, all_processed_results, output_stats_file):
    """Сохраняет статистику на русском языке в TXT файл."""

    with open(output_stats_file, 'w', encoding='utf-8') as f:
        f.write("=== ОТЧЕТ ПО СОПОСТАВЛЕНИЮ КАТЕГОРИЙ ===\n\n")
        f.write(f"Дата и время обработки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n")
        
        f.write("=== ОБЩАЯ СТАТИСТИКА ===\n")
        f.write(f"Всего обработано категорий: {total_input}\n")
        f.write(f"Успешно сопоставлено: {matched}\n")
        f.write(f"Не сопоставлено: {unmatched}\n")
        f.write(f"Процент успешного сопоставления: {percentage_matched:.2f}%\n")
        f.write(f"Количество запросов к ИИ: {api_requests}\n")
        f.write(f"Общее время выполнения: {execution_time:.2f} секунд\n\n")
        
        # Разделение на успешные и неуспешные результаты
        matched_results_local = [r for r in all_processed_results if r['match_id'] not in ['Не найдено', 'Parsing Error', 'General Error', 'ERROR: Original not found']]
        unmatched_results_local = [r for r in all_processed_results if r['match_id'] in ['Не найдено', 'Parsing Error', 'General Error', 'ERROR: Original not found']]
        
        f.write(f"Всего обработано результатов: {len(all_processed_results)}\n")
        if len(all_processed_results) != total_input:
            f.write(f"ВНИМАНИЕ: Потеряно {total_input - len(all_processed_results)} категорий!\n")
        f.write("\n")
        
        # Статистика по методам сопоставления
        exact_count = len([r for r in matched_results_local if r.get('method') == 'exact'])
        semantic_count = len([r for r in matched_results_local if r.get('method') == 'semantic'])
        general_count = len([r for r in matched_results_local if r.get('method') == 'general'])
        error_count = len([r for r in all_processed_results if r.get('method') == 'error'])
        
        f.write("=== МЕТОДЫ СОПОСТАВЛЕНИЯ ===\n")
        f.write(f"Точные совпадения: {exact_count}\n")
        f.write(f"Семантические совпадения: {semantic_count}\n")
        f.write(f"Общие совпадения: {general_count}\n")
        f.write(f"Ошибки обработки: {error_count}\n\n")
        
        # Статистика по уровням уверенности
        high_confidence = len([r for r in matched_results_local if r.get('confidence', 0) >= 0.8])
        medium_confidence = len([r for r in matched_results_local if 0.5 <= r.get('confidence', 0) < 0.8])
        low_confidence = len([r for r in matched_results_local if r.get('confidence', 0) < 0.5])
        
        f.write("=== УРОВНИ УВЕРЕННОСТИ ===\n")
        f.write(f"Высокая уверенность (≥0.8): {high_confidence}\n")
        f.write(f"Средняя уверенность (0.5-0.8): {medium_confidence}\n")
        f.write(f"Низкая уверенность (<0.5): {low_confidence}\n\n")
        
        # Примеры успешных сопоставлений
        f.write("=== ПРИМЕРЫ УСПЕШНЫХ СОПОСТАВЛЕНИЙ ===\n")
        for i, result in enumerate(matched_results_local[:10], 1):
            f.write(f"{i}. {result['input_full_path']}\n")
            f.write(f"   → {result['match_full_path']}\n")
            f.write(f"   Уверенность: {result['confidence']:.2f}\n")
            f.write(f"   Причина: {result['reasoning']}\n\n")
        
        if len(matched_results_local) > 10:
            f.write(f"... и еще {len(matched_results_local) - 10} успешных сопоставлений\n\n")
        
        # Примеры несопоставленных категорий
        if unmatched_results_local:
            f.write("=== НЕСОПОСТАВЛЕННЫЕ КАТЕГОРИИ ===\n")
            for i, result in enumerate(unmatched_results_local[:10], 1):
                f.write(f"{i}. {result['input_full_path']}\n")
                f.write(f"   Причина: {result['reasoning']}\n\n")
            
            if len(unmatched_results_local) > 10:
                f.write(f"... и еще {len(unmatched_results_local) - 10} несопоставленных категорий\n\n")
        
        f.write("=== КОНЕЦ ОТЧЕТА ===\n")

    print(f"Статистика на русском языке сохранена в {output_stats_file}")

# --- Основная логика сопоставления ---
def run_matching_system(old_categories_file, output_csv_file, output_json_file, output_stats_file):
    """
    Запускает систему сопоставления категорий для указанного файла.

    Args:
        old_categories_file: путь к файлу со старыми категориями
        output_csv_file: путь для сохранения CSV отчета
        output_json_file: путь для сохранения JSON отчета
        output_stats_file: путь для сохранения текстовой статистики
    """
    start_time = time.time()

    # 1. Загрузка данных
    print(f"Loading categories from {NEW_CATEGORIES_FILE} and {old_categories_file}...")
    all_new_categories = load_categories(NEW_CATEGORIES_FILE)
    all_old_categories = load_categories(old_categories_file)

    # Создаем плоские карты категорий для быстрого доступа
    new_categories_flat_map = create_flat_category_map_from_hierarchical(all_new_categories)
    # Автоматически определяем формат старых категорий
    if 'children' in all_old_categories[0]:
        old_categories_flat_map = create_flat_category_map_from_hierarchical(all_old_categories)
    else:
        old_categories_flat_map = create_flat_category_map_from_old_format(all_old_categories)
    
    # 2. Получение конечных категорий
    new_leaf_categories = get_leaf_categories(all_new_categories)
    old_leaf_categories = get_leaf_categories(all_old_categories)

    print(f"Found {len(new_leaf_categories)} leaf categories in new structure.")
    print(f"Found {len(old_leaf_categories)} leaf categories in old structure.")

    # Форматируем new_leaf_categories для Claude
    # Claude получит полный путь, например: "Экипировка и одежда > Куртки > Кожаные"
    formatted_new_structure = [lc['full_path_name'] for lc in new_leaf_categories]
    formatted_new_structure_str = "\n".join(formatted_new_structure)

    # 3. Батчевая обработка старых категорий
    old_leaf_chunks = list(chunk_list(old_leaf_categories, CHUNK_SIZE))
    
    matched_results = []
    unmatched_results = []
    total_ai_requests = 0

    print(f"Starting matching process for {len(old_leaf_categories)} old leaf categories in {len(old_leaf_chunks)} chunks...")

    for i, chunk in enumerate(old_leaf_chunks):
        total_ai_requests += 1
        chunk_start_time = time.time()
        print(f"\n=== CHUNK {i+1}/{len(old_leaf_chunks)} ===")
        print(f"Отправляем на обработку: {len(chunk)} категорий")
        print(f"ID категорий в чанке: {[cat['id'] for cat in chunk]}")

        # Создаем словарь для быстрого поиска ID по полному пути
        new_path_to_id_map = {lc['full_path_name']: lc['id'] for lc in new_leaf_categories}
        
        # Формируем промпт
        prompt_template = f"""
У меня есть существующая структура категорий. Ниже представлена полная иерархия всех конечных категорий, к которым могут быть привязаны продукты. 

ФОРМАТ: ID | Полный путь категории

<NEW_STRUCTURE>
"""
        for lc in new_leaf_categories:
            prompt_template += f"{lc['id']} | {lc['full_path_name']}\n"
        
        prompt_template += f"""</NEW_STRUCTURE>

Теперь у меня есть список категорий из старой системы, которые мне нужно сопоставить с вашей новой структурой.

ВАЖНЫЕ ПРАВИЛА СОПОСТАВЛЕНИЯ:
1. СТРОГО соблюдайте семантику товаров - обувь только с обувью, одежда только с одеждой, электроника только с электроникой
2. НЕ сопоставляйте товары разных типов - "Взуття" (обувь) НЕ может быть "Дощовики" (дождевики)
3. НЕ сопоставляйте "Штани" (штаны) с "Дощовики" (дождевики) - это разные типы товаров
4. Учитывайте ПОЛНЫЙ путь категории - если в старой системе "Дощовики > Взуття", это обувь для дождя, а не дождевики
5. Если категория находится НЕ в своей семантической группе - укажите "Не найдено"

ВАЖНО ДЛЯ MATCH_ID:
- Используйте ТОЧНЫЙ ID из NEW_STRUCTURE (числовой ID, например "36639")
- НЕ придумывайте ID - используйте только те, что указаны в NEW_STRUCTURE
- Если не нашли подходящую категорию - указывайте match_id: "Не найдено"

ПРИМЕРЫ ПРАВИЛЬНОГО СОПОСТАВЛЕНИЯ:
- "Дощовики > Взуття" → найти ID категории обуви из NEW_STRUCTURE
- "Дощовики > Штани" → найти ID категории штанов из NEW_STRUCTURE
- "Дощовики > Куртки" → найти ID категории курток из NEW_STRUCTURE

КРИТЕРИИ ОТКЛОНЕНИЯ:
- Коэффициент уверенности < 0.8 → match_id: "Не найдено"
- Семантически неподходящая категория → match_id: "Не найдено"
- Нет точного соответствия типу товара → match_id: "Не найдено"

Не придумывайте свою структуру, используйте ТОЛЬКО предоставленные ID и пути из NEW_STRUCTURE.
Не пропускайте категории - всегда давайте результат на каждую категорию. 

Пожалуйста, выводите результат в формате JSON-массива объектов, где каждый объект имеет следующую структуру:
{{
    "input_id": "ID старой категории",
    "input_name": "Название старой категории", 
    "input_full_path": "Полный читаемый путь старой категории",
    "match_id": "ТОЧНЫЙ ID из NEW_STRUCTURE (например '36639') или 'Не найдено'",
    "match_full_path": "ТОЧНЫЙ полный путь из NEW_STRUCTURE или 'Не найдено'",
    "confidence": Числовое значение от 0.0 до 1.0,
    "reasoning": "Краткое объяснение",
    "method": "exact/semantic/general/unmatched"
}}

Вот список старых категорий для сопоставления:

<OLD_CATEGORIES_TO_MATCH>
"""
        for cat in chunk:
            # Передаем Claude ID и полный путь, чтобы он мог вернуть их в ответе
            prompt_template += f"ID {cat['id']} | {cat['full_path_name']}\n"
        prompt_template += "</OLD_CATEGORIES_TO_MATCH>"

        try:
            print(f"Отправляем запрос к Claude API...")
            request_start_time = time.time()
            
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS_RESPONSE,
                temperature=TEMPERATURE,
                system="Вы - ассистент, специализирующийся на очень точном сопоставлении категорий товаров. Вы должны строго следовать предоставленной структуре и формату вывода. Возвращайте ТОЛЬКО JSON-массив объектов, без какого-либо дополнительного текста, объяснений или форматирования Markdown (например, ```json). Вашим единственным ответом должен быть JSON-массив.",
                messages=[
                    {"role": "user", "content": prompt_template}
                ]
            )
            
            request_end_time = time.time()
            print(f"API запрос выполнен за {request_end_time - request_start_time:.2f} секунд")
            
            response_text = message.content[0].text
            print(f"Получен ответ длиной: {len(response_text)} символов")

            # --- Упрощенная логика парсинга ---
            # Предполагаем, что Claude следует инструкциям и возвращает чистый JSON.
            # Удаляем любые внешние пробелы, если они есть.
            json_str_to_parse = response_text.strip()

            print(f"Попытка парсинга JSON ответа...")
            # print(f"Первые 200 символов ответа: {json_str_to_parse[:200]}...")

            matches_chunk = json.loads(json_str_to_parse)
            print(f"JSON успешно распарсен! Получено результатов: {len(matches_chunk)}")
            
            # КРИТИЧЕСКАЯ ПРОВЕРКА: количество результатов должно совпадать с отправленными
            if len(matches_chunk) != len(chunk):
                print(f"ВНИМАНИЕ: Несоответствие количества!")
                print(f"   Отправлено категорий: {len(chunk)}")
                print(f"   Получено результатов: {len(matches_chunk)}")
                print(f"   Потеряно категорий: {len(chunk) - len(matches_chunk)}")
                
                # Найдем какие ID отсутствуют в ответе
                sent_ids = {cat['id'] for cat in chunk}
                received_ids = {item.get('input_id') for item in matches_chunk}
                missing_ids = sent_ids - received_ids
                
                if missing_ids:
                    print(f"   Пропущенные ID: {list(missing_ids)}")
                    # Добавляем пропущенные категории как ошибки
                    for missing_id in missing_ids:
                        missing_cat = next((cat for cat in chunk if cat['id'] == missing_id), None)
                        if missing_cat:
                            unmatched_results.append({
                                'input_id': missing_cat['id'],
                                'input_name': missing_cat['name'],
                                'input_path': missing_cat.get('path', ''),
                                'input_full_path': missing_cat['full_path_name'],
                                'match_id': 'Missing from Claude Response',
                                'match_name': 'Missing from Claude Response',
                                'match_path': 'Missing from Claude Response',
                                'match_full_path': 'Missing from Claude Response',
                                'confidence': 0.0,
                                'reasoning': f"Категория отсутствует в ответе Claude для чанка {i+1}",
                                'method': 'error'
                            })
                            print(f"   Добавлена пропущенная категория: {missing_id} - {missing_cat['name']}")
            else:
                print(f"Количество результатов совпадает с отправленными категориями")
            
            processed_in_chunk = 0
            matched_in_chunk = 0
            unmatched_in_chunk = 0
            
            def validate_and_correct_match_id(item, new_categories_flat_map, new_path_to_id_map):
                """Валидирует и корректирует match_id от AI"""
                match_id = item.get('match_id', 'Не найдено')
                match_full_path = item.get('match_full_path', 'Не найдено')
                
                # Если AI не нашел совпадения
                if match_id in ['Не найдено', 'Не знайдено']:
                    return match_id, 'Не найдено', 'Не найдено'
                
                # Проверяем, существует ли указанный ID в новых категориях
                if match_id in new_categories_flat_map:
                    # ID существует, проверяем соответствие полного пути
                    expected_path = new_categories_flat_map[match_id]['full_path_name']
                    if match_full_path != expected_path:
                        print(f"   Исправляем match_full_path для ID {match_id}: '{match_full_path}' -> '{expected_path}'")
                        match_full_path = expected_path
                    return match_id, expected_path, expected_path
                else:
                    # ID не существует, возможно AI ошибся
                    print(f"   Неверный match_id от AI: '{match_id}' не существует в новой структуре")
                    
                    # Пытаемся найти ID по полному пути, если AI указал правильный путь
                    if match_full_path != 'Не найдено' and match_full_path in new_path_to_id_map:
                        correct_id = new_path_to_id_map[match_full_path]
                        print(f"   Исправляем match_id по пути: '{match_id}' -> '{correct_id}'")
                        return correct_id, match_full_path, match_full_path
                    else:
                        print(f"   Не удалось исправить match_id, отмечаем как 'Не найдено'")
                        return 'Не найдено', 'Не найдено', 'Не найдено'

            for item in matches_chunk:
                processed_in_chunk += 1
                old_cat_id = item['input_id']
                old_cat_full_path = item['input_full_path'] # Используем полный путь из Claude
                
                # Валидируем и корректируем match_id
                corrected_match_id, corrected_match_name, corrected_match_full_path = validate_and_correct_match_id(
                    item, new_categories_flat_map, new_path_to_id_map
                )
                
                # Достаем оригинальные данные из old_categories_flat_map
                original_old_cat = old_categories_flat_map.get(old_cat_id)
                
                if not original_old_cat:
                    print(f"Предупреждение: ID {old_cat_id} от Claude не найден в исходных данных")
                    # Если Claude вернул ID, которого нет в исходных данных (очень маловероятно)
                    item_for_report = {
                        'input_id': item.get('input_id'),
                        'input_name': item.get('input_name'),
                        'input_path': item.get('input_path'),
                        'input_full_path': item.get('input_full_path'),
                        'match_id': 'ERROR: Original not found',
                        'match_name': 'ERROR: Original not found',
                        'match_path': 'ERROR: Original not found',
                        'match_full_path': 'ERROR: Original not found',
                        'confidence': 0.0,
                        'reasoning': 'Claude returned ID not in original data',
                        'method': 'error'
                    }
                    unmatched_results.append(item_for_report)
                    unmatched_in_chunk += 1
                else:
                    # Получаем правильное название категории для match_name
                    if corrected_match_id not in ['Не найдено', 'Не знайдено'] and corrected_match_id in new_categories_flat_map:
                        corrected_match_name = new_categories_flat_map[corrected_match_id]['name']
                    else:
                        corrected_match_name = 'Не найдено'
                    
                    item_for_report = {
                        'input_id': original_old_cat['id'],
                        'input_name': original_old_cat['name'],
                        'input_path': original_old_cat.get('path', ''),  # старая структура может не иметь path
                        'input_full_path': original_old_cat.get('full_path_name', get_full_path_name(original_old_cat['id'], old_categories_flat_map)),
                        'match_id': corrected_match_id,
                        'match_name': corrected_match_name,
                        'match_path': '',  # новая структура не использует старый формат path
                        'match_full_path': corrected_match_full_path,
                        'confidence': item.get('confidence', 0.0),
                        'reasoning': item.get('reasoning', 'No reasoning provided'),
                        'method': item.get('method', 'unspecified')
                    }
                    
                    if corrected_match_id not in ['Не найдено', 'Не знайдено']:
                        matched_results.append(item_for_report)
                        matched_in_chunk += 1
                    else:
                        unmatched_results.append(item_for_report)
                        unmatched_in_chunk += 1
            
            chunk_end_time = time.time()
            print(f"Чанк {i+1} обработан за {chunk_end_time - chunk_start_time:.2f} секунд")
            print(f"  Обработано: {processed_in_chunk}, Сопоставлено: {matched_in_chunk}, Не сопоставлено: {unmatched_in_chunk}")
            print(f"  Всего результатов на данный момент: {len(matched_results) + len(unmatched_results)}")



        except json.JSONDecodeError as e:
            chunk_end_time = time.time()
            print(f"ОШИБКА ПАРСИНГА JSON в чанке {i + 1}!")
            print(f"   Время обработки чанка: {chunk_end_time - chunk_start_time:.2f} секунд")
            print(f"   Ошибка: {e}")
            print(f"   Длина ответа: {len(response_text)} символов")
            print(f"   Первые 500 символов ответа: {response_text[:500]}")
            print(f"   Последние 200 символов ответа: {response_text[-200:]}")
            
            # Добавляем все категории из текущего чанка как "не сопоставленные" из-за ошибки парсинга
            print(f"   Добавляем {len(chunk)} категорий как ошибки парсинга:")
            for cat in chunk:
                print(f"     - {cat['id']}: {cat['name']}")
                unmatched_results.append({
                    'input_id': cat['id'],
                    'input_name': cat['name'],
                    'input_path': cat.get('path', ''),
                    'input_full_path': cat['full_path_name'],
                    'match_id': 'Parsing Error',
                    'match_name': 'Parsing Error',
                    'match_path': 'Parsing Error',
                    'match_full_path': 'Parsing Error',
                    'confidence': 0.0,
                    'reasoning': f"JSON parsing error in chunk {i+1}: {e}",
                    'method': 'error'
                })
            print(f"   Всего результатов после ошибки: {len(matched_results) + len(unmatched_results)}")

        except Exception as e:  # Общий перехват для других непредвиденных ошибок, включая ValueError
            chunk_end_time = time.time()
            print(f"ОБЩАЯ ОШИБКА в чанке {i + 1}!")
            print(f"   Время обработки чанка: {chunk_end_time - chunk_start_time:.2f} секунд")
            print(f"   Тип ошибки: {type(e).__name__}")
            print(f"   Ошибка: {e}")
            
            # Проверяем, определена ли переменная response_text
            try:
                print(f"   Длина ответа: {len(response_text)} символов")
                print(f"   Первые 300 символов ответа: {response_text[:300]}")
            except NameError:
                print("   Ответ от API не получен (ошибка при запросе)")
            
            print(f"   Добавляем {len(chunk)} категорий как общие ошибки:")
            for cat in chunk:
                print(f"     - {cat['id']}: {cat['name']}")
                unmatched_results.append({
                    'input_id': cat['id'],
                    'input_name': cat['name'],
                    'input_path': cat.get('path', ''),
                    'input_full_path': cat['full_path_name'],
                    'match_id': 'General Error',
                    'match_name': 'General Error',
                    'match_path': 'General Error',
                    'match_full_path': 'General Error',
                    'confidence': 0.0,
                    'reasoning': f"General error in chunk {i+1}: {e}",
                    'method': 'error'
                })
            print(f"   Всего результатов после ошибки: {len(matched_results) + len(unmatched_results)}")

    end_time = time.time()
    total_execution_time = end_time - start_time

    # --- Статистика и вывод ---
    total_old_leaf_categories = len(old_leaf_categories)
    all_processed_results = matched_results + unmatched_results
    
    # Правильный подсчет на основе всех обработанных результатов
    num_matched = len([r for r in all_processed_results if r['match_id'] not in ['Не найдено', 'Parsing Error', 'General Error', 'ERROR: Original not found']])
    num_unmatched = len(all_processed_results) - num_matched
    
    # Убедимся, что все обработанные категории учтены, даже если были ошибки API/парсинга
    if total_old_leaf_categories != (num_matched + num_unmatched):
        print(f"WARNING: Mismatched counts! Total old leaf categories: {total_old_leaf_categories}, Matched: {num_matched}, Unmatched: {num_unmatched}")
        # Это может произойти, если в батче были ошибки, и мы добавили категории в unmatched_results.
        # Для корректного процента используем num_matched относительно total_old_leaf_categories
        
    percentage_matched = (num_matched / total_old_leaf_categories * 100) if total_old_leaf_categories > 0 else 0

    print("\n--- Matching Report ---")
    print(f"Total Old Leaf Categories: {total_old_leaf_categories}")
    print(f"Successfully Matched Categories: {num_matched}")
    print(f"Unmatched Categories: {num_unmatched}")
    print(f"Percentage Matched: {percentage_matched:.2f}%")
    print(f"Total AI Requests: {total_ai_requests}")
    print(f"Total Execution Time: {total_execution_time:.2f} seconds")

    print("\nMatched Categories Details:")
    for res in matched_results[:5]: # Показываем первые 5
        print(f"  Input: {res['input_full_path']} -> Matched: {res['match_full_path']} (Confidence: {res['confidence']:.2f}, Reason: {res['reasoning']})")
    if len(matched_results) > 5:
        print(f"  ...and {len(matched_results) - 5} more matched categories.")

    print("\nUnmatched Categories Details:")
    for res in unmatched_results[:5]: # Показываем первые 5
        print(f"  Input: {res['input_full_path']} -> Reason: {res['reasoning']}")
    if len(unmatched_results) > 5:
        print(f"  ...and {len(unmatched_results) - 5} more unmatched categories.")

    # Объединяем все результаты для сохранения
    all_results_for_report = matched_results + unmatched_results
    
    if all_results_for_report:
        # Сохраняем CSV отчет
        results_df = pd.DataFrame(all_results_for_report)
        results_df.to_csv(output_csv_file, index=False, encoding='utf-8')
        print(f"\nDetailed results saved to {output_csv_file}")

        # Разделяем результаты на сопоставленные и несопоставленные для удобства анализа
        matched_final = [r for r in all_results_for_report if r['match_id'] not in ['Не найдено', 'Не знайдено', 'Parsing Error', 'General Error', 'ERROR: Original not found', 'Missing from Claude Response']]
        unmatched_final = [r for r in all_results_for_report if r['match_id'] in ['Не найдено', 'Не знайдено', 'Parsing Error', 'General Error', 'ERROR: Original not found', 'Missing from Claude Response']]

        # Сохраняем JSON файл с результатами в удобной структуре
        json_output = {
            "processed_at": datetime.now().isoformat(),
            "summary": {
                "total_input": total_old_leaf_categories,
                "total_matched": num_matched,
                "total_unmatched": num_unmatched,
                "percentage_matched": f"{percentage_matched:.2f}%",
                "api_requests": total_ai_requests,
                "processing_time": f"{total_execution_time:.2f}s"
            },
            "matched_categories": {
                "count": len(matched_final),
                "items": matched_final
            },
            "unmatched_categories": {
                "count": len(unmatched_final),
                "items": unmatched_final
            },
            "statistics": {
                "by_method": {
                    "exact_matches": len([r for r in matched_final if r.get('method') == 'exact']),
                    "semantic_matches": len([r for r in matched_final if r.get('method') == 'semantic']),
                    "general_matches": len([r for r in matched_final if r.get('method') == 'general'])
                },
                "by_error_type": {
                    "not_found": len([r for r in unmatched_final if r.get('match_id') in ['Не найдено', 'Не знайдено']]),
                    "parsing_errors": len([r for r in unmatched_final if r.get('match_id') == 'Parsing Error']),
                    "general_errors": len([r for r in unmatched_final if r.get('match_id') == 'General Error']),
                    "missing_from_response": len([r for r in unmatched_final if r.get('match_id') == 'Missing from Claude Response']),
                    "original_not_found": len([r for r in unmatched_final if r.get('match_id') == 'ERROR: Original not found'])
                },
                "by_confidence": {
                    "high_confidence": len([r for r in matched_final if float(r.get('confidence', 0)) >= 0.8]),
                    "medium_confidence": len([r for r in matched_final if 0.5 <= float(r.get('confidence', 0)) < 0.8]),
                    "low_confidence": len([r for r in matched_final if float(r.get('confidence', 0)) < 0.5])
                }
            }
        }

        with open(output_json_file, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, ensure_ascii=False, indent=2)
        print(f"JSON results saved to {output_json_file}")

        # Генерация русской статистики в TXT файл
        save_russian_statistics(
            total_old_leaf_categories, num_matched, num_unmatched,
            percentage_matched, total_ai_requests, total_execution_time,
            all_processed_results, output_stats_file
        )
        
    else:
        print("\nNo results to save.")

    print("\n--- System Finished ---")


def process_all_files():
    """
    Обрабатывает все файлы из списка OLD_CATEGORIES_FILES последовательно.
    """
    # Создаем выходную директорию, если её нет
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Создана директория для отчетов: {OUTPUT_DIR}")

    print(f"\n{'='*80}")
    print(f"Начинаем обработку {len(OLD_CATEGORIES_FILES)} файлов")
    print(f"{'='*80}\n")

    overall_start_time = time.time()

    for file_index, old_file in enumerate(OLD_CATEGORIES_FILES, 1):
        print(f"\n{'='*80}")
        print(f"ФАЙЛ {file_index}/{len(OLD_CATEGORIES_FILES)}: {old_file}")
        print(f"{'='*80}\n")

        # Формируем имена выходных файлов для каждого входного файла
        # Например, для 2_1.json создаем problem.csv, report_2_1.json, report_2_1.txt
        file_basename = os.path.splitext(os.path.basename(old_file))[0]
        output_csv = os.path.join(OUTPUT_DIR, f"report_{file_basename}.csv")
        output_json = os.path.join(OUTPUT_DIR, f"report_{file_basename}.json")
        output_stats = os.path.join(OUTPUT_DIR, f"report_{file_basename}.txt")

        try:
            # Запускаем обработку для текущего файла
            run_matching_system(old_file, output_csv, output_json, output_stats)
        except Exception as e:
            import traceback
            print(f"\nОШИБКА при обработке файла {old_file}:")
            print(f"   Тип ошибки: {type(e).__name__}")
            print(f"   Сообщение: {e}")
            print(f"\nПолный traceback:")
            traceback.print_exc()
            print(f"\n   Пропускаем этот файл и продолжаем...")
            continue

    overall_end_time = time.time()
    total_time = overall_end_time - overall_start_time

    print(f"\n{'='*80}")
    print(f"ВСЕ ФАЙЛЫ ОБРАБОТАНЫ")
    print(f"{'='*80}")
    print(f"Обработано файлов: {len(OLD_CATEGORIES_FILES)}")
    print(f"Общее время выполнения: {total_time:.2f} секунд ({total_time/60:.2f} минут)")
    print(f"Результаты сохранены в директории: {OUTPUT_DIR}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    # Проверка наличия API ключа
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is not set.")
        print("Please set the environment variable or uncomment and fill in line 16 in the script.")
    else:
        process_all_files()