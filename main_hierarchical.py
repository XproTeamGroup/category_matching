#!/usr/bin/env python3
"""
Иерархическая система автоматического сопоставления категорий
Поддерживает path-based сопоставление с оптимизацией расходов на AI
"""

import argparse
import asyncio
import logging
import os
import sys
import signal
from datetime import datetime

# Добавляем текущую директорию в path для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.hierarchical_matcher import HierarchicalMatcher
from config.settings import (
    LOG_LEVEL, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
    BATCH_SIZE, CONFIDENCE_THRESHOLD, CLAUDE_API_KEY
)


def setup_logging(log_level: str = LOG_LEVEL):
    """Настройка системы логирования"""
    
    # Создаем папку для логов если не существует
    log_dir = os.path.dirname(LOG_FILE) if os.path.dirname(LOG_FILE) else '.'
    os.makedirs(log_dir, exist_ok=True)
    
    # Настраиваем ротацию логов
    from logging.handlers import RotatingFileHandler
    
    # Форматтер для логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Файловый обработчик с ротацией
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Подавляем избыточные логи от HTTP клиентов
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)


# Глобальная переменная для хранения объекта matcher
current_matcher = None

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения программы"""
    print(f"\n\nПолучен сигнал {signum}. Завершаем работу программы...")
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}. Initiating shutdown...")
    
    print("Программа завершена.")
    sys.exit(0)


async def run_hierarchical_matching(args):
    """Запуск иерархического процесса сопоставления категорий"""
    
    global current_matcher
    logger = logging.getLogger(__name__)
    
    try:
        # Инициализируем иерархический matcher
        logger.info("Initializing HierarchicalMatcher")
        api_key = args.api_key or CLAUDE_API_KEY
        matcher = HierarchicalMatcher(
            api_key=api_key,
            batch_size=args.batch_size
        )
        
        # Сохраняем matcher для доступа из signal handler
        current_matcher = matcher
        
        # Загружаем данные
        logger.info("Loading hierarchical data")
        matcher.load_data(args.reference, args.input)
        
        # Экспортируем структуру деревьев для отладки
        if args.debug_trees:
            debug_dir = os.path.dirname(args.output)
            matcher.processor.export_tree_structure(
                matcher.processor.reference_tree,
                os.path.join(debug_dir, 'reference_tree_debug.json')
            )
            matcher.processor.export_tree_structure(
                matcher.processor.input_tree,
                os.path.join(debug_dir, 'input_tree_debug.json')
            )
            logger.info("Tree structures exported for debugging")
        
        # Запускаем сопоставление
        logger.info(f"Starting hierarchical matching process: {args.input} -> {args.output}")
        start_time = datetime.now()
        
        results = await matcher.match_categories()
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        matcher.stats['processing_time'] = processing_time
        
        # Экспортируем результаты
        matcher.export_results(results, args.output)
        
        # Выводим статистику
        stats = matcher.get_statistics()
        total = stats['total_input_categories']
        matched = stats['exact_matches'] + stats['ai_matches']
        match_rate = (matched / total * 100) if total > 0 else 0
        
        # Исправленный расчет экономии: процент категорий, обработанных без AI
        cost_savings = (stats['exact_matches'] / total * 100) if total > 0 else 0
        
        print(f"\n=== РЕЗУЛЬТАТЫ ИЕРАРХИЧЕСКОГО СОПОСТАВЛЕНИЯ ===")
        print(f"Всего входных категорий: {total}")
        print(f"Точных совпадений: {stats['exact_matches']} ({stats['exact_matches']/total*100:.1f}%)")
        print(f"AI сопоставлений: {stats['ai_matches']} ({stats['ai_matches']/total*100:.1f}%)")
        print(f"Не сопоставлено: {stats['no_matches']} ({stats['no_matches']/total*100:.1f}%)")
        print(f"Общий процент совпадений: {match_rate:.1f}%")
        print(f"API запросов: {stats['api_calls']}")
        print(f"Экономия от точных совпадений: {cost_savings:.1f}%")
        print(f"Время обработки: {processing_time:.2f} секунд")
        print("=" * 48)
        
        # Экспортируем дополнительные файлы если указаны
        if args.summary_file:
            summary = f"""Иерархическое сопоставление категорий - {datetime.now().isoformat()}

Всего входных категорий: {total}
Точных совпадений: {stats['exact_matches']} ({stats['exact_matches']/total*100:.1f}%)
AI сопоставлений: {stats['ai_matches']} ({stats['ai_matches']/total*100:.1f}%)
Не сопоставлено: {stats['no_matches']} ({stats['no_matches']/total*100:.1f}%)
Общий процент совпадений: {match_rate:.1f}%

Оптимизация:
API запросов: {stats['api_calls']}
Экономия от точных совпадений: {cost_savings:.1f}%
Время обработки: {processing_time:.2f} секунд
"""
            
            with open(args.summary_file, 'w', encoding='utf-8') as f:
                f.write(summary)
        
        logger.info("Hierarchical matching process completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Hierarchical matching process failed: {e}")
        print(f"Ошибка: {e}")
        return 1
    
    finally:
        # Гарантированная очистка ресурсов
        current_matcher = None


def main():
    """Главная функция программы"""
    
    parser = argparse.ArgumentParser(
        description="Иерархическая система автоматического сопоставления категорий с использованием Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  Базовый запуск:
    python main_hierarchical.py --reference data/reference_categories.json \\
                               --input data/input_categories.json \\
                               --output data/output.json

  С отладкой деревьев:
    python main_hierarchical.py --reference data/reference_categories.json \\
                               --input data/input_categories.json \\
                               --output data/output.json \\
                               --debug-trees \\
                               --summary-file data/summary.txt

  Отладочный режим:
    python main_hierarchical.py --reference data/reference_categories.json \\
                               --input data/input_categories.json \\
                               --output data/output.json \\
                               --log-level DEBUG

Особенности иерархического сопоставления:
- Обрабатывает только листовые категории (конечные узлы дерева)  
- Использует контекст пути для разрешения неоднозначности
- Группирует категории по веткам для оптимизации AI запросов
- Автоматически определяет точные совпадения без использования AI
- Экономит до 80% расходов на AI за счет умной предфильтрации

Переменные окружения:
  CLAUDE_API_KEY - API ключ для Claude (обязательно)
        """
    )
    
    # Обязательные аргументы
    parser.add_argument('--reference', '-r', required=True,
                       help='Путь к файлу справочных категорий (JSON с иерархией)')
    parser.add_argument('--input', '-i', required=True,
                       help='Путь к файлу входных категорий для сопоставления (JSON с иерархией)')
    parser.add_argument('--output', '-o', required=True,
                       help='Путь к выходному файлу с результатами (JSON)')
    
    # Необязательные аргументы
    parser.add_argument('--api-key', 
                       help='Claude API ключ (или используйте переменную CLAUDE_API_KEY)')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                       help=f'Размер батча для AI запросов (по умолчанию: {BATCH_SIZE})')
    
    # Дополнительные выходные файлы
    parser.add_argument('--summary-file', 
                       help='Путь к файлу для сохранения краткой сводки')
    
    # Отладка и мониторинг
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default=LOG_LEVEL, help=f'Уровень логирования (по умолчанию: {LOG_LEVEL})')
    parser.add_argument('--debug-trees', action='store_true',
                       help='Экспортировать структуру деревьев для отладки')
    
    args = parser.parse_args()
    
    # Проверяем наличие API ключа
    api_key = args.api_key or CLAUDE_API_KEY
    if not api_key or api_key == "your_api_key":
        print("Ошибка: Необходимо указать Claude API ключ через --api-key или в файле .env")
        print("Создайте файл .env с содержимым: CLAUDE_API_KEY=your_actual_api_key")
        return 1
    
    # Проверяем существование входных файлов
    for file_path, name in [(args.reference, 'reference'), (args.input, 'input')]:
        if not os.path.exists(file_path):
            print(f"Ошибка: Файл {name} не найден: {file_path}")
            return 1
    
    # Создаем директорию для выходного файла
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Настраиваем логирование
    setup_logging(args.log_level)
    
    # Устанавливаем обработчики сигналов для корректного завершения
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Системный сигнал завершения
    
    # Запускаем процесс сопоставления
    return asyncio.run(run_hierarchical_matching(args))


if __name__ == '__main__':
    sys.exit(main())