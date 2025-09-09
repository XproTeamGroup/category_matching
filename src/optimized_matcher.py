import logging
import asyncio
import os
from datetime import datetime
from typing import List, Dict, Optional

from .claude_client import ClaudeAPIClient
from .processor import CategoryProcessor
from .optimized_batch_processor import OptimizedBatchProcessor
from .simple_ultra_processor import SimpleUltraProcessor
from .advanced_filter import AdvancedCategoryFilter
from .vector_search import HybridVectorSearch
from .cache_manager import CacheManager
from .performance_monitor import performance_monitor, monitor_performance
from .exporter import ResultExporter

from config.settings import (
    BATCH_SIZE, CONFIDENCE_THRESHOLD, LARGE_DATASET_THRESHOLD,
    ENABLE_VECTOR_SEARCH, CACHE_DIRECTORY, ENABLE_PERSISTENT_CACHE
)


logger = logging.getLogger(__name__)


class OptimizedCategoryMatcher:
    """Оптимизированный matcher для обработки больших объемов данных"""
    
    def __init__(self, api_key: Optional[str] = None, 
                 reference_file: Optional[str] = None,
                 batch_size: int = BATCH_SIZE):
        
        # Основные компоненты
        self.claude_client = ClaudeAPIClient(api_key)
        self.processor = CategoryProcessor()
        self.batch_processor = OptimizedBatchProcessor(batch_size)
        self.ultra_processor = SimpleUltraProcessor(batch_size)
        self.exporter = ResultExporter()
        
        # Компоненты для больших данных
        self.advanced_filter: Optional[AdvancedCategoryFilter] = None
        self.vector_search: Optional[HybridVectorSearch] = None
        self.cache_manager: Optional[CacheManager] = None
        
        # Данные
        self.reference_categories: List[Dict] = []
        self.category_tree: Dict = {}
        self.large_dataset_mode = False
        
        # Статистика
        self.api_requests_count = 0
        self.processing_start_time: Optional[datetime] = None
        
        # Инициализация компонентов для больших данных
        self._initialize_advanced_components()
        
        # Загружаем справочные категории если указан файл
        if reference_file:
            self.load_reference_categories(reference_file)
    
    def _initialize_advanced_components(self):
        """Инициализация продвинутых компонентов"""
        try:
            # Кеш менеджер
            if ENABLE_PERSISTENT_CACHE:
                self.cache_manager = CacheManager(CACHE_DIRECTORY)
                logger.info("Cache manager initialized")
            
            logger.info("Advanced components initialized")
        except Exception as e:
            logger.error(f"Failed to initialize advanced components: {e}")
    
    @monitor_performance
    def load_reference_categories(self, reference_file: str):
        """Загрузка справочных категорий с оптимизацией"""
        logger.info("Loading reference categories with optimization")
        
        # Загружаем данные
        self.reference_categories = self.processor.load_reference_categories(reference_file)
        dataset_size = len(self.reference_categories)
        
        logger.info(f"Loaded {dataset_size} reference categories")
        
        # Определяем режим работы
        self.large_dataset_mode = dataset_size >= LARGE_DATASET_THRESHOLD
        
        if self.large_dataset_mode:
            logger.info(f"Switching to large dataset mode (threshold: {LARGE_DATASET_THRESHOLD})")
            self._initialize_for_large_dataset()
        else:
            logger.info("Using standard mode")
            # Строим обычное дерево
            self.category_tree = self.processor.build_tree(self.reference_categories)
        
        # Строим индексы в кеш менеджере
        if self.cache_manager:
            self.cache_manager.build_category_index(self.reference_categories)
        
        performance_monitor.record_metric(
            "reference_categories_loaded", 
            dataset_size, 
            "count", 
            "initialization"
        )
    
    def _initialize_for_large_dataset(self):
        """Инициализация компонентов для больших данных"""
        logger.info("Initializing components for large dataset...")
        
        try:
            # Продвинутый фильтр
            logger.info("Building advanced filter indexes...")
            self.advanced_filter = AdvancedCategoryFilter()
            self.advanced_filter.build_advanced_indexes(self.reference_categories)
            
            # Векторный поиск
            if ENABLE_VECTOR_SEARCH:
                logger.info("Building vector search index...")
                self.vector_search = HybridVectorSearch(CACHE_DIRECTORY)
                self.vector_search.build_vector_index(self.reference_categories)
            
            # Инициализируем оптимизированный батч-процессор
            self.batch_processor.initialize_for_large_dataset(self.reference_categories)
            
            logger.info("Large dataset initialization completed")
            
        except Exception as e:
            logger.error(f"Large dataset initialization failed: {e}")
            # Переключаемся на стандартный режим
            self.large_dataset_mode = False
            self.category_tree = self.processor.build_tree(self.reference_categories)
    
    @monitor_performance
    async def match_categories_optimized(self, input_file: str, output_file: str, 
                                       enable_prefiltering: bool = True,
                                       progress_callback: Optional[callable] = None) -> Dict:
        """Оптимизированное сопоставление категорий"""
        
        if not self.reference_categories:
            raise ValueError("Reference categories not loaded. Use load_reference_categories() first.")
        
        # Начинаем мониторинг
        self.processing_start_time = datetime.now()
        
        # Загружаем входные категории
        input_categories = self._load_input_categories_chunked(input_file)
        total_input = len(input_categories)
        
        logger.info(f"Starting optimized matching for {total_input} categories (large_dataset_mode: {self.large_dataset_mode})")
        
        # Инициализируем мониторинг сессии
        performance_monitor.start_session(total_input)
        
        try:
            # Выбираем стратегию обработки
            if self.large_dataset_mode:
                matches = await self._process_large_dataset_optimized(
                    input_categories, enable_prefiltering, progress_callback
                )
            else:
                matches = await self._process_standard_dataset_optimized(
                    input_categories, enable_prefiltering, progress_callback
                )
            
            # Постобработка результатов
            matches = self._post_process_matches_optimized(matches)
            
            # Экспортируем результаты
            result_data = self.exporter.export_results(
                matches, input_categories, self.reference_categories,
                output_file, self.processing_start_time, self.api_requests_count
            )
            
            # Завершаем мониторинг
            performance_monitor.end_session()
            
            # Логируем рекомендации
            recommendations = performance_monitor.get_recommendations()
            if recommendations:
                logger.info("Performance recommendations:")
                for rec in recommendations:
                    logger.info(f"  - {rec}")
            
            logger.info("Optimized category matching completed successfully")
            return result_data
            
        except Exception as e:
            performance_monitor.record_metric("matching_error", 1, "count", "errors")
            logger.error(f"Optimized category matching failed: {e}")
            raise
    
    @monitor_performance
    async def match_categories_ultra_optimized(self, input_file: str, output_file: str, 
                                             progress_callback: Optional[callable] = None) -> Dict:
        """Ультра-оптимизированное сопоставление категорий для максимальной производительности"""
        
        if not self.reference_categories:
            raise ValueError("Reference categories not loaded. Use load_reference_categories() first.")
        
        # Начинаем мониторинг
        self.processing_start_time = datetime.now()
        
        # Загружаем входные категории
        input_categories = self._load_input_categories_chunked(input_file)
        total_input = len(input_categories)
        
        logger.info(f"Starting ULTRA-optimized matching for {total_input} categories")
        logger.info("Features: Leaf-only matching, Smart pre-filtering, Batch AI processing")
        
        # Инициализируем мониторинг сессии
        performance_monitor.start_session(total_input)
        
        try:
            # Используем ультра-оптимизированный процессор
            matches = await self.ultra_processor.process_simple_ultra_optimized(
                input_categories, self.reference_categories, self.claude_client
            )
            
            # Результаты уже в правильном формате
            formatted_matches = matches
            
            # Экспортируем результаты
            result_data = self.exporter.export_results(
                formatted_matches, input_categories, self.reference_categories,
                output_file, self.processing_start_time, self.ultra_processor.stats['api_calls']
            )
            
            # Добавляем статистику ультра-оптимизации
            ultra_stats = self.ultra_processor.get_optimization_stats()
            result_data['ultra_optimization_stats'] = ultra_stats
            
            # Завершаем мониторинг
            performance_monitor.end_session()
            
            # Выводим подробную статистику
            self._log_ultra_optimization_stats(ultra_stats)
            
            logger.info("ULTRA-optimized category matching completed successfully")
            return result_data
            
        except Exception as e:
            performance_monitor.record_metric("matching_error", 1, "count", "errors")
            logger.error(f"ULTRA-optimized category matching failed: {e}")
            raise
    
    def _load_input_categories_chunked(self, input_file: str) -> List[Dict]:
        """Загрузка входных категорий с поддержкой больших файлов"""
        try:
            file_size = os.path.getsize(input_file)
            
            if file_size > 50 * 1024 * 1024:  # 50MB
                logger.info(f"Large input file detected ({file_size / 1024 / 1024:.1f}MB), using chunked loading")
                return self._load_large_json_file(input_file)
            else:
                return self.processor.load_input_categories(input_file)
                
        except Exception as e:
            logger.error(f"Failed to load input categories: {e}")
            raise
    
    def _load_large_json_file(self, file_path: str) -> List[Dict]:
        """Загрузка больших JSON файлов по частям"""
        import json
        
        categories = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    categories = data
                else:
                    logger.warning("Input file is not a list, attempting to extract categories")
                    categories = data.get('categories', [])
                    
            logger.info(f"Loaded {len(categories)} categories from large file")
            return categories
            
        except Exception as e:
            logger.error(f"Failed to load large JSON file: {e}")
            raise
    
    async def _process_large_dataset_optimized(self, input_categories: List[Dict],
                                             enable_prefiltering: bool,
                                             progress_callback: Optional[callable]) -> List[Dict]:
        """Оптимизированная обработка больших данных"""
        
        logger.info("Processing with large dataset optimizations")
        
        # Используем оптимизированный батч-процессор
        matches = await self.batch_processor.process_in_batches_optimized(
            input_categories, self.reference_categories, self.claude_client
        )
        
        # Обновляем статистику API запросов
        batch_processor_stats = self.batch_processor.get_performance_stats()
        self.api_requests_count = batch_processor_stats.get('api_calls', 0)
        
        # Записываем метрики производительности
        performance_monitor.record_metric(
            "large_dataset_processing_time",
            batch_processor_stats.get('total_processing_time', 0),
            "seconds",
            "processing"
        )
        
        return matches
    
    async def _process_standard_dataset_optimized(self, input_categories: List[Dict],
                                                enable_prefiltering: bool,
                                                progress_callback: Optional[callable]) -> List[Dict]:
        """Оптимизированная обработка стандартных данных"""
        
        logger.info("Processing with standard optimizations")
        
        # Предварительная фильтрация если включена
        if enable_prefiltering and len(self.reference_categories) > 100:
            filtered_reference = self.processor.pre_filter_categories(
                input_categories, self.reference_categories
            )
        else:
            filtered_reference = self.reference_categories
        
        # Используем оптимизированный батч-процессор
        matches = await self.batch_processor.process_in_batches_optimized(
            input_categories, filtered_reference, self.claude_client
        )
        
        # Обновляем статистику
        batch_processor_stats = self.batch_processor.get_performance_stats()
        self.api_requests_count = batch_processor_stats.get('api_calls', 0)
        
        return matches
    
    def _post_process_matches_optimized(self, matches: List[Dict]) -> List[Dict]:
        """Оптимизированная постобработка результатов"""
        
        # Создаем индекс справочных категорий
        if self.cache_manager:
            category_index = self.cache_manager.get_category_index()
            if category_index:
                ref_index = category_index['by_id']
            else:
                ref_index = {cat['id']: cat for cat in self.reference_categories}
        else:
            ref_index = {cat['id']: cat for cat in self.reference_categories}
        
        processed_matches = []
        
        for match in matches:
            # Дополняем информацию о сопоставлении
            match_id = match.get('match_id')
            if match_id and match_id in ref_index:
                ref_cat = ref_index[match_id]
                match['match_path'] = ref_cat.get('path', '')
                
                if not match.get('match_name'):
                    match['match_name'] = ref_cat['name']
            
            # Валидируем и нормализуем confidence
            confidence = match.get('confidence', 0.0)
            if isinstance(confidence, str):
                try:
                    confidence = float(confidence)
                except ValueError:
                    confidence = 0.0
            match['confidence'] = max(0.0, min(1.0, confidence))
            
            processed_matches.append(match)
            
            # Записываем статистику
            performance_monitor.record_category_processed(
                matched=bool(match_id and match_id != 'null' and match_id is not None)
            )
        
        return processed_matches
    
    def get_optimized_statistics(self) -> Dict:
        """Получение оптимизированной статистики"""
        stats = {
            'matcher': {
                'reference_categories_loaded': len(self.reference_categories),
                'large_dataset_mode': self.large_dataset_mode,
                'api_requests_made': self.api_requests_count,
                'processing_start_time': self.processing_start_time.isoformat() if self.processing_start_time else None
            },
            'performance': performance_monitor.get_current_stats(),
            'components': {}
        }
        
        # Статистика компонентов
        if self.batch_processor:
            stats['components']['batch_processor'] = self.batch_processor.get_performance_stats()
        
        if self.advanced_filter:
            stats['components']['advanced_filter'] = self.advanced_filter.get_performance_stats()
        
        if self.vector_search:
            stats['components']['vector_search'] = self.vector_search.get_index_info()
        
        if self.cache_manager:
            stats['components']['cache_manager'] = self.cache_manager.get_stats()
        
        return stats
    
    @monitor_performance
    def find_similar_categories_optimized(self, category_name: str, limit: int = 10) -> List[Dict]:
        """Оптимизированный поиск похожих категорий"""
        
        results = []
        
        if self.large_dataset_mode:
            # Используем продвинутые методы поиска
            
            # Продвинутая фильтрация
            if self.advanced_filter:
                filtered = self.advanced_filter.filter_candidates_for_large_dataset(
                    category_name, limit * 2
                )
                for cat in filtered[:limit]:
                    results.append({
                        'id': cat['id'],
                        'name': cat['name'],
                        'path': cat.get('path', ''),
                        'match_type': 'advanced_filter',
                        'score': 0.8  # Примерный скор
                    })
            
            # Векторный поиск
            if self.vector_search and len(results) < limit:
                vector_matches = self.vector_search.find_similar_categories(category_name, limit - len(results))
                for cat, score in vector_matches:
                    if cat['id'] not in [r['id'] for r in results]:
                        results.append({
                            'id': cat['id'],
                            'name': cat['name'],
                            'path': cat.get('path', ''),
                            'match_type': 'vector_search',
                            'score': score
                        })
        else:
            # Используем стандартные методы
            results = self.find_similar_categories(category_name, limit)
        
        return results[:limit]
    
    def find_similar_categories(self, category_name: str, limit: int = 10) -> List[Dict]:
        """Стандартный поиск похожих категорий (для совместимости)"""
        if not self.category_tree:
            return []
        
        results = []
        
        # Точные совпадения
        exact_matches = self.processor.find_exact_matches(category_name)
        for match in exact_matches[:limit]:
            results.append({
                'id': match.id,
                'name': match.name,
                'path': match.path,
                'match_type': 'exact',
                'score': 1.0
            })
        
        # Нечеткие совпадения
        if len(results) < limit:
            fuzzy_matches = self.processor.find_fuzzy_matches(category_name, threshold=0.6)
            for match, score in fuzzy_matches[:limit - len(results)]:
                results.append({
                    'id': match.id,
                    'name': match.name,
                    'path': match.path,
                    'match_type': 'fuzzy',
                    'score': score
                })
        
        return results
    
    def clear_all_caches(self):
        """Очистка всех кешей"""
        if self.batch_processor:
            self.batch_processor.clear_all_caches()
        
        if self.cache_manager:
            self.cache_manager.clear_all()
        
        if self.vector_search:
            self.vector_search.clear_cache()
        
        logger.info("All caches cleared")
    
    def set_confidence_threshold(self, threshold: float):
        """Установка порога уверенности"""
        if 0.0 <= threshold <= 1.0:
            self.exporter.confidence_threshold = threshold
            logger.info(f"Confidence threshold set to {threshold}")
        else:
            raise ValueError("Confidence threshold must be between 0.0 and 1.0")
    
    def export_performance_report(self, filepath: str):
        """Экспорт отчета о производительности"""
        try:
            performance_monitor.export_metrics(filepath)
            logger.info(f"Performance report exported to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export performance report: {e}")
    
    def get_optimization_recommendations(self) -> List[str]:
        """Получение рекомендаций по оптимизации"""
        return performance_monitor.get_recommendations()
    
    async def benchmark_performance(self, input_categories: List[Dict], 
                                  iterations: int = 3) -> Dict:
        """Бенчмарк производительности"""
        logger.info(f"Running performance benchmark ({iterations} iterations)")
        
        results = []
        
        for i in range(iterations):
            logger.info(f"Benchmark iteration {i+1}/{iterations}")
            
            start_time = datetime.now()
            
            # Тестовая обработка (без сохранения результатов)
            if self.large_dataset_mode:
                matches = await self._process_large_dataset_optimized(input_categories, True, None)
            else:
                matches = await self._process_standard_dataset_optimized(input_categories, True, None)
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            iteration_stats = {
                'iteration': i + 1,
                'processing_time': processing_time,
                'categories_processed': len(input_categories),
                'matches_found': len([m for m in matches if m.get('match_id')]),
                'processing_speed': len(input_categories) / processing_time
            }
            
            results.append(iteration_stats)
            logger.info(f"Iteration {i+1} completed in {processing_time:.2f}s")
        
        # Агрегированная статистика
        avg_time = sum(r['processing_time'] for r in results) / len(results)
        avg_speed = sum(r['processing_speed'] for r in results) / len(results)
        
        benchmark_report = {
            'iterations': iterations,
            'input_categories': len(input_categories),
            'large_dataset_mode': self.large_dataset_mode,
            'results': results,
            'summary': {
                'average_processing_time': avg_time,
                'average_processing_speed': avg_speed,
                'min_time': min(r['processing_time'] for r in results),
                'max_time': max(r['processing_time'] for r in results),
                'time_std_dev': self._calculate_std_dev([r['processing_time'] for r in results])
            }
        }
        
        logger.info("=== BENCHMARK RESULTS ===")
        logger.info(f"Average processing time: {avg_time:.2f}s")
        logger.info(f"Average processing speed: {avg_speed:.2f} categories/sec")
        logger.info("==========================")
        
        return benchmark_report
    
    def _calculate_std_dev(self, values: List[float]) -> float:
        """Вычисление стандартного отклонения"""
        if len(values) <= 1:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
    
    def _format_ultra_optimized_results(self, matches: List[Dict]) -> List[Dict]:
        """Форматирует результаты ультра-оптимизированной обработки в стандартный формат"""
        formatted_results = []
        
        for match in matches:
            input_category = match['input_category']
            matched_category = match['matched_category']
            confidence = match['confidence']
            method = match.get('method', 'unknown')
            reason = match.get('reason', '')
            
            formatted_match = {
                'input_category_id': input_category.get('id', ''),
                'input_category_name': input_category.get('name', ''),
                'matched_category_id': matched_category['id'] if matched_category else None,
                'matched_category_name': matched_category['name'] if matched_category else None,
                'confidence': confidence,
                'processing_method': method,
                'match_reason': reason,
                'is_exact_match': confidence >= 0.95,
                'needs_review': confidence < CONFIDENCE_THRESHOLD
            }
            
            formatted_results.append(formatted_match)
        
        return formatted_results
    
    def _log_ultra_optimization_stats(self, stats: Dict):
        """Выводит подробную статистику ультра-оптимизации"""
        logger.info("=== ULTRA-OPTIMIZATION STATS ===")
        logger.info(f"Total input categories: {stats['total_input']}")
        logger.info(f"Auto-matched (no AI): {stats['auto_matched']} ({stats.get('auto_match_rate', 0):.1f}%)")
        logger.info(f"AI processed: {stats['ai_processed']} ({stats.get('ai_processing_rate', 0):.1f}%)")
        logger.info(f"Leaf categories only: {stats['leaf_categories_only']}")
        logger.info(f"API calls made: {stats['api_calls']}")
        logger.info(f"API call efficiency: {stats.get('api_call_efficiency', 0):.1f} categories per call")
        logger.info(f"Processing speed: {stats.get('categories_per_second', 0):.1f} categories/sec")
        logger.info(f"Total processing time: {stats['processing_time']:.2f}s")
        logger.info("=================================")
        
        # Рекомендации по дальнейшей оптимизации
        recommendations = []
        
        if stats.get('auto_match_rate', 0) < 50:
            recommendations.append("Рассмотрите возможность расширения словаря синонимов для увеличения автоматических совпадений")
        
        if stats.get('api_call_efficiency', 0) < 5:
            recommendations.append("Увеличьте размер батча для более эффективных API вызовов")
        
        if stats.get('categories_per_second', 0) < 10:
            recommendations.append("Рассмотрите возможность использования более мощного оборудования или оптимизации алгоритмов")
        
        if recommendations:
            logger.info("Рекомендации по оптимизации:")
            for rec in recommendations:
                logger.info(f"  • {rec}")