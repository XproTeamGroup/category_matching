#!/usr/bin/env python3
"""
Система автоматического сопоставления категорий
Основной скрипт для запуска процесса сопоставления категорий
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

from src.optimized_matcher import OptimizedCategoryMatcher
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
    
    if current_matcher:
        # Останавливаем фоновые потоки
        if hasattr(current_matcher, 'performance_monitor'):
            current_matcher.performance_monitor.stop()
        if hasattr(current_matcher, 'cache_manager'):
            current_matcher.cache_manager.stop_cleanup_thread()
    
    print("Программа завершена.")
    sys.exit(0)


async def run_matching(args):
    """Запуск процесса сопоставления категорий"""
    
    global current_matcher
    logger = logging.getLogger(__name__)
    
    try:
        # Инициализируем optimized matcher
        logger.info("Initializing OptimizedCategoryMatcher")
        api_key = args.api_key or CLAUDE_API_KEY
        matcher = OptimizedCategoryMatcher(
            api_key=api_key,
            reference_file=args.reference,
            batch_size=args.batch_size
        )
        
        # Сохраняем matcher для доступа из signal handler
        current_matcher = matcher
        
        # Устанавливаем порог уверенности если указан
        if args.confidence_threshold:
            matcher.set_confidence_threshold(args.confidence_threshold)
        
        # Очищаем кеш если указано
        if args.clear_cache:
            matcher.clear_all_caches()
        
        # Бенчмарк производительности
        if args.benchmark:
            logger.info("Running performance benchmark...")
            input_categories = matcher.processor.load_input_categories(args.input)
            benchmark_results = await matcher.benchmark_performance(input_categories, iterations=3)
            print(f"\n=== BENCHMARK RESULTS ===")
            print(f"Среднее время обработки: {benchmark_results['summary']['average_processing_time']:.2f}s")
            print(f"Средняя скорость: {benchmark_results['summary']['average_processing_speed']:.2f} категорий/сек")
            print(f"Режим: {'Большие данные' if benchmark_results['large_dataset_mode'] else 'Стандартный'}")
        
        # Выбираем режим обработки
        if getattr(args, 'ultra_optimize', False):
            logger.info(f"Starting ULTRA-optimized matching process: {args.input} -> {args.output}")
            result_data = await matcher.match_categories_ultra_optimized(
                args.input, 
                args.output
            )
        else:
            logger.info(f"Starting optimized matching process: {args.input} -> {args.output}")
            result_data = await matcher.match_categories_optimized(
                args.input, 
                args.output,
                enable_prefiltering=not args.no_prefilter
            )
        
        # Выводим краткую сводку
        summary = matcher.exporter.export_summary(result_data)
        print("\n" + summary)
        
        # Экспортируем дополнительные файлы если указаны
        if args.summary_file:
            matcher.exporter.export_summary(result_data, args.summary_file)
        
        if args.unmatched_file:
            matcher.exporter.export_unmatched_only(result_data, args.unmatched_file)
        
        # Выводим детальную статистику
        if args.show_stats:
            stats = matcher.get_optimized_statistics()
            print(f"\n=== ДЕТАЛЬНАЯ СТАТИСТИКА ===")
            print(f"Режим работы: {'Большие данные' if stats['matcher']['large_dataset_mode'] else 'Стандартный'}")
            print(f"Загружено справочных категорий: {stats['matcher']['reference_categories_loaded']}")
            print(f"API запросов выполнено: {stats['matcher']['api_requests_made']}")
            
            # Статистика производительности
            perf_stats = stats['performance']['session']
            print(f"Скорость обработки: {perf_stats.get('processing_speed', 0):.2f} категорий/сек")
            print(f"Процент попаданий в кеш: {perf_stats.get('cache_hit_rate', 0):.1f}%")
            
            # Рекомендации
            recommendations = matcher.get_optimization_recommendations()
            if recommendations:
                print(f"\nРекомендации по оптимизации:")
                for rec in recommendations:
                    print(f"  • {rec}")
        
        # Экспорт отчета о производительности
        if args.export_performance:
            matcher.export_performance_report(args.export_performance)
            print(f"\nОтчет о производительности сохранен: {args.export_performance}")
        
        logger.info("Matching process completed successfully")
        
        # Останавливаем фоновые потоки при нормальном завершении
        if hasattr(matcher, 'performance_monitor'):
            matcher.performance_monitor.stop()
        if hasattr(matcher, 'cache_manager'):
            matcher.cache_manager.stop_cleanup_thread()
        
        return 0
        
    except Exception as e:
        logger.error(f"Matching process failed: {e}")
        print(f"Ошибка: {e}")
        
        # Останавливаем фоновые потоки при ошибке
        if current_matcher:
            if hasattr(current_matcher, 'performance_monitor'):
                current_matcher.performance_monitor.stop()
            if hasattr(current_matcher, 'cache_manager'):
                current_matcher.cache_manager.stop_cleanup_thread()
        
        return 1
    
    finally:
        # Гарантированная очистка ресурсов
        current_matcher = None


def main():
    """Главная функция программы"""
    
    parser = argparse.ArgumentParser(
        description="Система автоматического сопоставления категорий с использованием Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  Базовый запуск:
    python main.py --reference data/reference_categories.json \\
                   --input data/input_categories.json \\
                   --output data/output.json

  С дополнительными параметрами:
    python main.py --reference data/reference_categories.json \\
                   --input data/input_categories.json \\
                   --output data/output.json \\
                   --batch-size 10 \\
                   --confidence-threshold 0.8 \\
                   --summary-file data/summary.txt

  Отладочный режим:
    python main.py --reference data/reference_categories.json \\
                   --input data/input_categories.json \\
                   --output data/output.json \\
                   --log-level DEBUG \\
                   --show-stats \\
                   --no-prefilter

  Ультра-оптимизированный режим (для больших объемов):
    python main.py --reference data/reference_categories.json \\
                   --input data/input_categories.json \\
                   --output data/output.json \\
                   --ultra-optimize \\
                   --batch-size 20

Переменные окружения:
  CLAUDE_API_KEY - API ключ для Claude (обязательно)
        """
    )
    
    # Обязательные аргументы
    parser.add_argument('--reference', '-r', required=True,
                       help='Путь к файлу справочных категорий (JSON)')
    parser.add_argument('--input', '-i', required=True,
                       help='Путь к файлу входных категорий для сопоставления (JSON)')
    parser.add_argument('--output', '-o', required=True,
                       help='Путь к выходному файлу с результатами (JSON)')
    
    # Необязательные аргументы
    parser.add_argument('--api-key', 
                       help='Claude API ключ (или используйте переменную CLAUDE_API_KEY)')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                       help=f'Размер батча для API запросов (по умолчанию: {BATCH_SIZE})')
    parser.add_argument('--confidence-threshold', type=float, default=CONFIDENCE_THRESHOLD,
                       help=f'Минимальный порог уверенности (по умолчанию: {CONFIDENCE_THRESHOLD})')
    
    # Дополнительные выходные файлы
    parser.add_argument('--summary-file', 
                       help='Путь к файлу для сохранения краткой сводки')
    parser.add_argument('--unmatched-file',
                       help='Путь к файлу для сохранения несопоставленных категорий')
    
    # Настройки обработки
    parser.add_argument('--no-prefilter', action='store_true',
                       help='Отключить предварительную фильтрацию категорий')
    parser.add_argument('--clear-cache', action='store_true',
                       help='Очистить кеш перед запуском')
    
    # Отладка и мониторинг
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default=LOG_LEVEL, help=f'Уровень логирования (по умолчанию: {LOG_LEVEL})')
    parser.add_argument('--show-stats', action='store_true',
                       help='Показать подробную статистику после обработки')
    parser.add_argument('--benchmark', action='store_true',
                       help='Запустить бенчмарк производительности')
    parser.add_argument('--export-performance', 
                       help='Экспорт отчета о производительности в файл')
    parser.add_argument('--disable-vector-search', action='store_true',
                       help='Отключить векторный поиск (для больших данных)')
    parser.add_argument('--memory-limit', type=int,
                       help='Лимит памяти в MB для кешей')
    parser.add_argument('--ultra-optimize', action='store_true',
                       help='Ультра-оптимизированный режим: только конечные категории, умная предфильтрация, батчевая обработка AI')
    
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
    return asyncio.run(run_matching(args))


if __name__ == '__main__':
    sys.exit(main())