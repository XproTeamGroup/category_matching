import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# Claude API настройки
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
CLAUDE_MODEL = "claude-3-5-haiku-20241022"

# Обработка
BATCH_SIZE = 25  # Категорий в одном запросе
MAX_RETRIES = 3  # Количество повторов при ошибке
RETRY_DELAY = 1  # Задержка между повторами (сек)

# Кеширование
ENABLE_CACHE = True
CACHE_TTL = 3600  # Время жизни кеша (сек)

# Выходные данные
OUTPUT_FORMAT = "json"
CONFIDENCE_THRESHOLD = 0.7  # Минимальная уверенность для сопоставления

# Настройки для больших данных
LARGE_DATASET_THRESHOLD = 100  # Переключение на оптимизированный режим
MAX_CATEGORIES_FOR_CLAUDE = 25  # Максимум категорий для отправки в Claude
KEYWORD_FILTER_THRESHOLD = 0.15  # Минимальное пересечение ключевых слов
FUZZY_SIMILARITY_THRESHOLD = 0.4  # Минимальная нечеткая схожесть
HIERARCHY_BONUS_WEIGHT = 0.2  # Бонус за иерархическое соответствие

# Векторный поиск
ENABLE_VECTOR_SEARCH = True
VECTOR_TOP_K = 50  # Количество кандидатов после векторного поиска
MIN_VECTOR_SIMILARITY = 0.3  # Минимальная векторная схожесть

# Производительность
PARALLEL_PROCESSING = True
MAX_WORKERS = 4  # Количество параллельных потоков
CHUNK_SIZE = 1000  # Размер чанка для обработки больших файлов
MEMORY_LIMIT_MB = 2048  # Лимит памяти для кешей

# Индексы и кеширование
ENABLE_PERSISTENT_CACHE = True
CACHE_DIRECTORY = "cache"
INDEX_REBUILD_INTERVAL = 3600  # Перестроение индексов каждый час

# Логирование
LOG_LEVEL = "INFO"
LOG_FILE = "category_matcher.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Промпт системы
SYSTEM_PROMPT = """Ты - эксперт по классификации товарных категорий. Твоя задача - сопоставить входные категории с существующими категориями из справочника.

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
}"""

# Шаблон пользовательского промпта
USER_PROMPT_TEMPLATE = """СПРАВОЧНИК КАТЕГОРИЙ:
{reference_categories}

КАТЕГОРИИ ДЛЯ СОПОСТАВЛЕНИЯ:
{input_categories}

Сопоставь каждую входную категорию с наиболее подходящей из справочника. Верни результат в указанном JSON формате."""