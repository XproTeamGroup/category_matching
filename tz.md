# Техническое задание: Система автоматического сопоставления категорий

## 1. Общее описание

Система предназначена для автоматического сопоставления категорий товаров из внешних источников с существующими категориями в базе данных с использованием Claude API для интеллектуального анализа и сопоставления.

## 2. Входные данные

### 2.1 Файл существующих категорий (reference_categories.json)
```json
[
    {
        "id": "2396",
        "name": "Шоломи",
        "path": "2395>2396"
    },
    {
        "id": "2394",
        "name": "Розпродаж",
        "path": "2352>2394"
    }
]
```

### 2.2 Файл категорий для сопоставления (input_categories.json)
```json
[
    {
        "name": "Глушители автомобильные"
    },
    {
        "name": "Шлемы мотоциклетные"
    }
]
```

## 3. Архитектура системы

### 3.1 Основные компоненты

1. **CategoryMatcher** - основной класс для сопоставления
2. **ClaudeAPIClient** - клиент для работы с Claude API
3. **CategoryProcessor** - обработчик категорий и построение иерархии
4. **BatchProcessor** - батчевая обработка для оптимизации запросов
5. **ResultExporter** - экспорт результатов в JSON

### 3.2 Структура проекта
```
category_matcher/
├── src/
│   ├── __init__.py
│   ├── matcher.py          # Основная логика сопоставления
│   ├── claude_client.py    # Клиент Claude API
│   ├── processor.py        # Обработка категорий
│   ├── batch_processor.py  # Батчевая обработка
│   └── exporter.py         # Экспорт результатов
├── config/
│   └── settings.py         # Конфигурация
├── data/
│   ├── input/             # Входные файлы
│   └── output/            # Результаты
├── tests/
├── requirements.txt
└── main.py
```

## 4. Алгоритм работы

### 4.1 Предварительная обработка
1. Загрузка существующих категорий
2. Построение иерархического дерева категорий
3. Создание индексов для быстрого поиска
4. Подготовка контекста для Claude API

### 4.2 Батчевая обработка
1. Группировка входных категорий в батчи (по 10-20 категорий)
2. Подготовка промпта с контекстом
3. Отправка запроса к Claude API
4. Парсинг и валидация ответа
5. Сохранение результатов

### 4.3 Оптимизация
- Кеширование результатов сопоставления
- Предварительная фильтрация по ключевым словам
- Использование нечеткого поиска для первичной фильтрации

## 5. Промпт для Claude API

### 5.1 Системный промпт
```
Ты - эксперт по классификации товарных категорий. Твоя задача - сопоставить входные категории с существующими категориями из справочника.

ПРАВИЛА СОПОСТАВЛЕНИЯ:
1. Ищи точные совпадения названий
2. Учитывай синонимы и похожие термины
3. Анализируй иерархию категорий через path
4. Для неоднозначных случаев выбирай наиболее подходящую категорию
5. Если категория не подходит ни к одной - возвращай null для match_id

ФОРМАТ ОТВЕТА - строго JSON:
{
    "matches": [
        {
            "input_name": "Глушители",
            "match_id": "2392",
            "match_name": "Глушники",
            "confidence": 0.95,
            "reasoning": "Прямое соответствие: глушители = глушники"
        }
    ]
}
```

### 5.2 Пользовательский промпт (шаблон)
```
СПРАВОЧНИК КАТЕГОРИЙ:
{reference_categories}

КАТЕГОРИИ ДЛЯ СОПОСТАВЛЕНИЯ:
{input_categories}

Сопоставь каждую входную категорию с наиболее подходящей из справочника. Верни результат в указанном JSON формате.
```

## 6. Реализация основных компонентов

### 6.1 CategoryMatcher (matcher.py)
```python
class CategoryMatcher:
    def __init__(self, api_key: str, reference_file: str):
        self.claude_client = ClaudeAPIClient(api_key)
        self.processor = CategoryProcessor()
        self.batch_processor = BatchProcessor()
        self.reference_categories = self.load_reference_categories(reference_file)
        self.category_tree = self.processor.build_tree(self.reference_categories)
    
    def match_categories(self, input_file: str, output_file: str):
        # Основная логика сопоставления
        pass
    
    def pre_filter_categories(self, input_categories: List[dict]) -> List[dict]:
        # Предварительная фильтрация по ключевым словам
        pass
```

### 6.2 ClaudeAPIClient (claude_client.py)
```python
class ClaudeAPIClient:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
    
    async def match_batch(self, reference_categories: List[dict], 
                         input_categories: List[dict]) -> dict:
        # Отправка батча на сопоставление
        pass
    
    def _build_prompt(self, reference_categories: List[dict], 
                     input_categories: List[dict]) -> str:
        # Построение промпта
        pass
```

### 6.3 BatchProcessor (batch_processor.py)
```python
class BatchProcessor:
    def __init__(self, batch_size: int = 15):
        self.batch_size = batch_size
    
    def process_in_batches(self, input_categories: List[dict], 
                          reference_categories: List[dict],
                          claude_client: ClaudeAPIClient) -> List[dict]:
        # Обработка в батчах
        pass
    
    def _create_batches(self, categories: List[dict]) -> List[List[dict]]:
        # Создание батчей
        pass
```

## 7. Конфигурация системы

### 7.1 settings.py
```python
# Claude API настройки
CLAUDE_API_KEY = "your-api-key"
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Обработка
BATCH_SIZE = 15  # Категорий в одном запросе
MAX_RETRIES = 3  # Количество повторов при ошибке
RETRY_DELAY = 1  # Задержка между повторами (сек)

# Кеширование
ENABLE_CACHE = True
CACHE_TTL = 3600  # Время жизни кеша (сек)

# Выходные данные
OUTPUT_FORMAT = "json"
CONFIDENCE_THRESHOLD = 0.7  # Минимальная уверенность для сопоставления
```

## 8. Оптимизация производительности

### 8.1 По запросам
- Батчевая обработка: до 15 категорий в одном запросе
- Предварительная фильтрация по ключевым словам
- Кеширование результатов сопоставления
- Асинхронные запросы с ограничением concurrency

### 8.2 По финансам
- Использование Claude Sonnet 4 (оптимальное соотношение цена/качество)
- Минимизация размера промптов через умную фильтрацию
- Кеширование для избежания повторных запросов
- Предварительная обработка для исключения очевидных несоответствий

### 8.3 По скорости
- Параллельная обработка батчей
- Предварительное индексирование категорий
- Быстрая фильтрация по n-граммам
- Оптимизированные структуры данных (Trie, индексы)

## 9. Формат выходного файла

### 9.1 Структура результата (output.json)
```json
{
    "processed_at": "2025-09-09T10:00:00Z",
    "total_input": 1000,
    "total_matched": 850,
    "total_unmatched": 150,
    "matches": [
        {
            "input_name": "Глушители автомобильные",
            "match_id": "2392",
            "match_name": "Глушники",
            "match_path": "2352>2392",
            "confidence": 0.95,
            "reasoning": "Прямое соответствие категорий автомобильных глушителей"
        }
    ],
    "unmatched": [
        {
            "input_name": "Неизвестная категория",
            "reasoning": "Не найдено подходящего соответствия в справочнике"
        }
    ],
    "statistics": {
        "high_confidence": 700,
        "medium_confidence": 150,
        "low_confidence": 0,
        "api_requests": 67,
        "processing_time": "00:05:23"
    }
}
```

## 10. Обработка ошибок и логирование

### 10.1 Типы ошибок
- Ошибки Claude API (лимиты, недоступность)
- Ошибки парсинга JSON ответов
- Ошибки валидации входных данных
- Тайм-ауты запросов

### 10.2 Логирование
- Уровни: DEBUG, INFO, WARNING, ERROR
- Ротация логов по размеру
- Отдельные логи для API запросов и результатов

## 11. Тестирование

### 11.1 Типы тестов
- Юнит-тесты для каждого компонента
- Интеграционные тесты с Claude API
- Тесты производительности
- Тесты на реальных данных

## 12. Развертывание и использование

### 12.1 Установка
```bash
pip install -r requirements.txt
```

### 12.2 Запуск
```bash
python main.py --reference data/reference_categories.json \
               --input data/input_categories.json \
               --output data/output.json \
               --batch-size 15
```

## 13. Мониторинг и метрики

### 13.1 Ключевые метрики
- Процент успешных сопоставлений
- Средняя уверенность сопоставления
- Количество API запросов
- Время обработки
- Стоимость обработки

### 13.2 Алерты
- Высокий процент несопоставленных категорий
- Ошибки Claude API
- Превышение бюджета на API запросы