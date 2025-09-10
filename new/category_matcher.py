import json
import os
import time
import anthropic
import pandas as pd
import re # Добавьте эту строку
from datetime import datetime

# --- Конфигурация ---
NEW_CATEGORIES_FILE = 'new/new.json'
OLD_CATEGORIES_FILE = 'new/old.json'
OUTPUT_CSV_FILE = 'new/category_matches_report.csv'
OUTPUT_JSON_FILE = 'new/category_matches_results.json'
OUTPUT_STATS_FILE = 'new/category_matches_statistics.txt'
CHUNK_SIZE = 20 # Количество старых категорий для обработки за один запрос к Claude
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

def get_leaf_categories(categories_data):
    """
    Определяет конечные категории (те, которые не являются родителями для других)
    и возвращает их вместе с их полным путем в виде списка словарей.
    """
    parent_ids = set()
    category_map = {cat['id']: cat for cat in categories_data}

    for category in categories_data:
        # Проверяем, является ли текущая категория родителем для какой-либо другой
        # Путь дочерней категории должен начинаться с пути родителя + ID родителя
        for other_category in categories_data:
            if category['id'] == other_category['id']: # Не сравниваем категорию саму с собой
                continue
            
            # Если id текущей категории присутствует в пути другой категории,
            # и этот 'другой' путь длиннее, то текущая категория - родитель.
            # Пример: path '36637>36638', id '36638'.
            # Дочерний path: '36637>36638>36639'.
            # Проверяем, что '36638' (id) является частью пути дочерней категории и не равно самой себе.
            if f"{category['id']}" in other_category['path'] and len(other_category['path'].split('>')) > len(category['path'].split('>')):
                parent_ids.add(category['id'])
                break # Эта категория - родитель, можем идти к следующей

    leaf_categories = []
    for category in categories_data:
        if category['id'] not in parent_ids:
            # Создаем полный путь для удобства
            path_parts = []
            current_id = category['id']
            while True:
                current_cat = category_map.get(current_id)
                if not current_cat:
                    break
                path_parts.insert(0, current_cat['name'])
                
                # Ищем родителя
                parent_path_segment = None
                if '>' in current_cat['path']:
                    parent_path_segment = '>'.join(current_cat['path'].split('>')[:-1])
                    
                if parent_path_segment:
                    # Находим ID родителя из сегмента пути
                    parent_id = parent_path_segment.split('>')[-1]
                    current_id = parent_id # Переходим к родителю
                else: # Если нет знака '>', значит, это корневая категория
                    break
            
            full_path_name = " > ".join(path_parts)
            
            leaf_categories.append({
                'id': category['id'],
                'name': category['name'],
                'path': category['path'],
                'full_path_name': full_path_name # Добавляем легкочитаемый полный путь
            })
    return leaf_categories

def chunk_list(lst, chunk_size):
    """Разбивает список на части (батчи)."""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def get_full_path_name(category_id, categories_data_map):
    """Возвращает полный читаемый путь для категории по её ID."""
    path_parts = []
    current_id = category_id
    while True:
        current_cat = categories_data_map.get(current_id)
        if not current_cat:
            break
        path_parts.insert(0, current_cat['name'])
        
        parent_path = current_cat['path'].rsplit('>', 1)[0] # Получаем путь родителя
        if parent_path == current_cat['path']: # Если path не изменился, это корневая категория
            break
        
        # Находим ID родителя из path
        parent_id = parent_path.rsplit('>', 1)[-1] if '>' in parent_path else parent_path
        if parent_id == current_id: # Защита от зацикливания, если путь некорректно построен
            break
        current_id = parent_id
        if current_id not in categories_data_map: # Если родитель не найден в карте
            break
            
    return " > ".join(path_parts)

def save_russian_statistics(total_input, matched, unmatched, percentage_matched, 
                          api_requests, execution_time, all_processed_results):
    """Сохраняет статистику на русском языке в TXT файл."""
    
    with open(OUTPUT_STATS_FILE, 'w', encoding='utf-8') as f:
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
    
    print(f"Статистика на русском языке сохранена в {OUTPUT_STATS_FILE}")

# --- Основная логика сопоставления ---
def run_matching_system():
    start_time = time.time()
    
    # 1. Загрузка данных
    print(f"Loading categories from {NEW_CATEGORIES_FILE} and {OLD_CATEGORIES_FILE}...")
    all_new_categories = load_categories(NEW_CATEGORIES_FILE)
    all_old_categories = load_categories(OLD_CATEGORIES_FILE)

    # Создаем карты ID -> категория для быстрого доступа
    new_categories_map = {cat['id']: cat for cat in all_new_categories}
    old_categories_map = {cat['id']: cat for cat in all_old_categories}
    
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

        # Формируем промпт
        prompt_template = f"""
У меня есть существующая структура категорий. Ниже представлена полная иерархия всех конечных категорий, к которым могут быть привязаны продукты. Каждая строка представляет собой полный путь к конечной категории:

<NEW_STRUCTURE>
{formatted_new_structure_str}
</NEW_STRUCTURE>

Теперь у меня есть список категорий из старой системы, которые мне нужно сопоставить с вашей новой структурой. Для каждой категории из старой системы укажите одну наиболее подходящую конечную категорию из новой структуры. Если нет точного совпадения, найдите наиболее близкое по смыслу или наиболее общую категорию. Если совсем ничего не подходит или категория слишком специфична для новой структуры, укажите "Не найдено" в качестве match_id и match_full_path.

Пожалуйста, выводите результат в формате JSON-массива объектов, где каждый объект имеет следующую структуру:
{{
    "input_id": "ID старой категории",
    "input_name": "Название старой категории",
    "input_path": "Путь старой категории (как в исходном файле)",
    "input_full_path": "Полный читаемый путь старой категории",
    "match_id": "ID сопоставленной новой категории (из NEW_STRUCTURE) или 'Не найдено'",
    "match_name": "Название сопоставленной новой категории или 'Не найдено'",
    "match_path": "Путь сопоставленной новой категории (как в исходном файле) или 'Не найдено'",
    "match_full_path": "Полный читаемый путь сопоставленной новой категории (как в NEW_STRUCTURE) или 'Не найдено'",
    "confidence": "Оценка уверенности в совпадении (от 0.0 до 1.0, где 1.0 - высокая уверенность)",
    "reasoning": "Краткое объяснение причины совпадения или отсутствия совпадения (например, 'Точное совпадение', 'Смысловое совпадение', 'Нет подходящей категории')",
    "method": "Метод сопоставления (например, 'exact', 'semantic', 'general', 'unmatched')"
}}

Вот список старых категорий для сопоставления:

<OLD_CATEGORIES_TO_MATCH>
"""
        for cat in chunk:
            # Передаем Claude ID и полный путь, чтобы он мог вернуть их в ответе
            prompt_template += f"{cat['id']} | {cat['full_path_name']}\n"
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
            print(f"Первые 200 символов ответа: {json_str_to_parse[:200]}...")

            matches_chunk = json.loads(json_str_to_parse)
            print(f"✓ JSON успешно распарсен! Получено результатов: {len(matches_chunk)}")
            
            # КРИТИЧЕСКАЯ ПРОВЕРКА: количество результатов должно совпадать с отправленными
            if len(matches_chunk) != len(chunk):
                print(f"⚠️  ВНИМАНИЕ: Несоответствие количества!")
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
                                'input_path': missing_cat['path'],
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
                print(f"✓ Количество результатов совпадает с отправленными категориями")
            
            processed_in_chunk = 0
            matched_in_chunk = 0
            unmatched_in_chunk = 0
            
            for item in matches_chunk:
                processed_in_chunk += 1
                old_cat_id = item['input_id']
                old_cat_full_path = item['input_full_path'] # Используем полный путь из Claude
                
                # Достаем оригинальные данные из old_categories_map
                original_old_cat = old_categories_map.get(old_cat_id)
                
                if not original_old_cat:
                    print(f"⚠️  Предупреждение: ID {old_cat_id} от Claude не найден в исходных данных")
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
                    item_for_report = {
                        'input_id': original_old_cat['id'],
                        'input_name': original_old_cat['name'],
                        'input_path': original_old_cat['path'],
                        'input_full_path': original_old_cat.get('full_path_name', get_full_path_name(original_old_cat['id'], old_categories_map)),
                        'match_id': item.get('match_id', 'Не найдено'),
                        'match_name': item.get('match_name', 'Не найдено'),
                        'match_path': item.get('match_path', 'Не найдено'),
                        'match_full_path': item.get('match_full_path', 'Не найдено'),
                        'confidence': item.get('confidence', 0.0),
                        'reasoning': item.get('reasoning', 'No reasoning provided'),
                        'method': item.get('method', 'unspecified')
                    }
                    
                    if item_for_report['match_id'] not in ['Не найдено', 'Не знайдено']:
                        matched_results.append(item_for_report)
                        matched_in_chunk += 1
                    else:
                        unmatched_results.append(item_for_report)
                        unmatched_in_chunk += 1
            
            chunk_end_time = time.time()
            print(f"✓ Чанк {i+1} обработан за {chunk_end_time - chunk_start_time:.2f} секунд")
            print(f"  Обработано: {processed_in_chunk}, Сопоставлено: {matched_in_chunk}, Не сопоставлено: {unmatched_in_chunk}")
            print(f"  Всего результатов на данный момент: {len(matched_results) + len(unmatched_results)}")



        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response for chunk {i + 1}: {e}")
            print(f"Raw response (full): {response_text}")  # Выведем весь ответ
            # Добавляем все категории из текущего чанка как "не сопоставленные" из-за ошибки парсинга
            for cat in chunk:
                unmatched_results.append({
                    'input_id': cat['id'],
                    'input_name': cat['name'],
                    'input_path': cat['path'],
                    'input_full_path': cat['full_path_name'],
                    'match_id': 'Parsing Error',
                    'match_name': 'Parsing Error',
                    'match_path': 'Parsing Error',
                    'match_full_path': 'Parsing Error',
                    'confidence': 0.0,
                    'reasoning': f"JSON parsing error: {e}",
                    'method': 'error'
                })

        except Exception as e:  # Общий перехват для других непредвиденных ошибок, включая ValueError
            print(f"An unexpected general error occurred for chunk {i + 1}: {e}")
            print(f"Raw response (full): {response_text}")  # Выведем весь ответ
            for cat in chunk:
                unmatched_results.append({
                    'input_id': cat['id'],
                    'input_name': cat['name'],
                    'input_path': cat['path'],
                    'input_full_path': cat['full_path_name'],
                    'match_id': 'General Error',
                    'match_name': 'General Error',
                    'match_path': 'General Error',
                    'match_full_path': 'General Error',
                    'confidence': 0.0,
                    'reasoning': f"General error: {e}",
                    'method': 'error'
                })

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
        results_df.to_csv(OUTPUT_CSV_FILE, index=False, encoding='utf-8')
        print(f"\nDetailed results saved to {OUTPUT_CSV_FILE}")
        
        # Сохраняем JSON файл с результатами
        json_output = {
            "processed_at": datetime.now().isoformat(),
            "total_input": total_old_leaf_categories,
            "total_matched": num_matched,
            "total_unmatched": num_unmatched,
            "matches": all_results_for_report,
            "statistics": {
                "exact_matches": len([r for r in matched_results if r.get('method') == 'exact']),
                "semantic_matches": len([r for r in matched_results if r.get('method') == 'semantic']),
                "general_matches": len([r for r in matched_results if r.get('method') == 'general']),
                "error_matches": len([r for r in all_results_for_report if r.get('method') == 'error']),
                "api_requests": total_ai_requests,
                "processing_time": f"{total_execution_time:.2f}s",
                "percentage_matched": f"{percentage_matched:.2f}%"
            }
        }
        
        with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, ensure_ascii=False, indent=2)
        print(f"JSON results saved to {OUTPUT_JSON_FILE}")
        
        # Генерация русской статистики в TXT файл
        save_russian_statistics(
            total_old_leaf_categories, num_matched, num_unmatched, 
            percentage_matched, total_ai_requests, total_execution_time,
            all_processed_results
        )
        
    else:
        print("\nNo results to save.")

    print("\n--- System Finished ---")


if __name__ == "__main__":
    # Проверка наличия API ключа
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is not set.")
        print("Please set the environment variable or uncomment and fill in line 16 in the script.")
    else:
        run_matching_system()