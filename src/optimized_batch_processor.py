import logging
import asyncio
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import json
import hashlib
import os
from collections import defaultdict

from .claude_client import ClaudeAPIClient
from .advanced_filter import AdvancedCategoryFilter
from .vector_search import VectorizedCategorySearch, HybridVectorSearch
from config.settings import (
    BATCH_SIZE, ENABLE_CACHE, CACHE_TTL, LARGE_DATASET_THRESHOLD,
    MAX_CATEGORIES_FOR_CLAUDE, ENABLE_VECTOR_SEARCH, PARALLEL_PROCESSING,
    MAX_WORKERS, CHUNK_SIZE, MEMORY_LIMIT_MB, CACHE_DIRECTORY,
    ENABLE_PERSISTENT_CACHE
)


logger = logging.getLogger(__name__)


class OptimizedBatchProcessor:
    """Оптимизированный батч-процессор для больших объемов данных"""
    
    def __init__(self, batch_size: int = BATCH_SIZE):
        self.batch_size = batch_size
        self.large_dataset_mode = False
        
        # Кеши
        self.memory_cache: Dict[str, Dict] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        self.persistent_cache_dir = CACHE_DIRECTORY
        
        # Компоненты для больших данных
        self.advanced_filter: Optional[AdvancedCategoryFilter] = None
        self.vector_search: Optional[VectorizedCategorySearch] = None
        
        # Статистика производительности
        self.stats = {
            'total_batches': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'api_calls': 0,
            'filtering_time': 0,
            'api_time': 0,
            'total_processing_time': 0,
            'memory_usage_mb': 0
        }
        
        # Создаем директорию для кеша
        if ENABLE_PERSISTENT_CACHE:
            os.makedirs(self.persistent_cache_dir, exist_ok=True)
    
    def initialize_for_large_dataset(self, reference_categories: List[Dict]):
        """Инициализация для работы с большими объемами данных"""
        dataset_size = len(reference_categories)
        
        if dataset_size >= LARGE_DATASET_THRESHOLD:
            self.large_dataset_mode = True
            logger.info(f"Switching to large dataset mode ({dataset_size} categories)")
            
            # Инициализируем продвинутый фильтр
            logger.info("Initializing advanced filter...")
            self.advanced_filter = AdvancedCategoryFilter()
            self.advanced_filter.build_advanced_indexes(reference_categories)
            
            # Инициализируем векторный поиск если включен
            if ENABLE_VECTOR_SEARCH:
                logger.info("Initializing vector search...")
                self.vector_search = HybridVectorSearch(self.persistent_cache_dir)
                self.vector_search.build_vector_index(reference_categories)
        else:
            logger.info(f"Using standard mode ({dataset_size} categories)")
    
    async def process_in_batches_optimized(self, input_categories: List[Dict],
                                         reference_categories: List[Dict],
                                         claude_client: ClaudeAPIClient) -> List[Dict]:
        """Оптимизированная обработка в батчах"""
        
        start_time = time.time()
        self.stats['total_processing_time'] = start_time
        
        logger.info(f"Processing {len(input_categories)} categories (large_dataset_mode: {self.large_dataset_mode})")
        
        # Инициализация для больших данных
        if not hasattr(self, '_initialized'):
            self.initialize_for_large_dataset(reference_categories)
            self._initialized = True
        
        # Выбираем стратегию обработки
        if self.large_dataset_mode:
            results = await self._process_large_dataset(
                input_categories, reference_categories, claude_client
            )
        else:
            results = await self._process_standard_dataset(
                input_categories, reference_categories, claude_client
            )
        
        # Обновляем статистику
        total_time = time.time() - start_time
        self.stats['total_processing_time'] = total_time
        
        logger.info(f"Batch processing completed in {total_time:.2f}s")
        self._log_performance_stats()
        
        return results
    
    async def _process_large_dataset(self, input_categories: List[Dict],
                                   reference_categories: List[Dict],
                                   claude_client: ClaudeAPIClient) -> List[Dict]:
        """Обработка больших данных с предварительной фильтрацией"""
        
        all_matches = []
        
        # Создаем чанки для параллельной обработки
        chunks = self._create_chunks(input_categories, CHUNK_SIZE)
        
        if PARALLEL_PROCESSING and len(chunks) > 1:
            # Параллельная обработка чанков
            tasks = []
            for chunk in chunks:
                task = self._process_chunk_async(chunk, reference_categories, claude_client)
                tasks.append(task)
            
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in chunk_results:
                if isinstance(result, Exception):
                    logger.error(f"Chunk processing failed: {result}")
                else:
                    all_matches.extend(result)
        else:
            # Последовательная обработка
            for chunk in chunks:
                chunk_matches = await self._process_chunk_async(chunk, reference_categories, claude_client)
                all_matches.extend(chunk_matches)
        
        return all_matches
    
    async def _process_chunk_async(self, chunk: List[Dict],
                                 reference_categories: List[Dict],
                                 claude_client: ClaudeAPIClient) -> List[Dict]:
        """Асинхронная обработка чанка данных"""
        
        chunk_matches = []
        
        # Предварительно фильтруем категории для каждой входной категории
        filtered_batches = []
        
        for input_cat in chunk:
            # Используем продвинутую фильтрацию
            filtered_refs = await self._smart_filter_references(
                input_cat['name'], reference_categories
            )
            
            if filtered_refs:
                filtered_batches.append({
                    'input': [input_cat],
                    'references': filtered_refs
                })
        
        # Обрабатываем отфильтрованные батчи
        for batch_data in filtered_batches:
            batch_matches = await self._process_filtered_batch(
                batch_data['input'], batch_data['references'], claude_client
            )
            chunk_matches.extend(batch_matches)
        
        return chunk_matches
    
    async def _smart_filter_references(self, input_category: str,
                                     reference_categories: List[Dict]) -> List[Dict]:
        """Умная фильтрация справочных категорий"""
        
        filter_start = time.time()
        
        if self.advanced_filter:
            # Используем продвинутый фильтр
            filtered = self.advanced_filter.filter_candidates_for_large_dataset(
                input_category, MAX_CATEGORIES_FOR_CLAUDE
            )
        else:
            # Fallback к простой фильтрации
            filtered = reference_categories[:MAX_CATEGORIES_FOR_CLAUDE]
        
        # Дополняем векторным поиском если включен
        if ENABLE_VECTOR_SEARCH and self.vector_search:
            vector_matches = self.vector_search.find_similar_categories(input_category, 15)
            vector_categories = [match[0] for match in vector_matches]
            
            # Объединяем результаты, избегая дублей
            seen_ids = {cat['id'] for cat in filtered}
            for vec_cat in vector_categories:
                if vec_cat['id'] not in seen_ids and len(filtered) < MAX_CATEGORIES_FOR_CLAUDE:
                    filtered.append(vec_cat)
                    seen_ids.add(vec_cat['id'])
        
        filter_time = time.time() - filter_start
        self.stats['filtering_time'] += filter_time
        
        logger.debug(f"Filtered {len(reference_categories)} -> {len(filtered)} for '{input_category}'")
        return filtered
    
    async def _process_standard_dataset(self, input_categories: List[Dict],
                                      reference_categories: List[Dict],
                                      claude_client: ClaudeAPIClient) -> List[Dict]:
        """Стандартная обработка для небольших данных"""
        
        all_matches = []
        batches = self._create_batches(input_categories)
        
        # Обрабатываем батчи последовательно или параллельно
        if PARALLEL_PROCESSING and len(batches) > 2:
            # Ограничиваем параллелизм для избежания rate limiting
            semaphore = asyncio.Semaphore(2)  # Максимум 2 одновременных запроса
            
            tasks = []
            for batch in batches:
                task = self._process_single_batch_with_semaphore(
                    semaphore, batch, reference_categories, claude_client
                )
                tasks.append(task)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch processing failed: {result}")
                else:
                    all_matches.extend(result)
        else:
            # Последовательная обработка
            for i, batch in enumerate(batches, 1):
                logger.info(f"Processing batch {i}/{len(batches)}")
                batch_matches = await self._process_single_batch(
                    batch, reference_categories, claude_client
                )
                all_matches.extend(batch_matches)
        
        return all_matches
    
    async def _process_single_batch_with_semaphore(self, semaphore: asyncio.Semaphore,
                                                 batch: List[Dict],
                                                 reference_categories: List[Dict],
                                                 claude_client: ClaudeAPIClient) -> List[Dict]:
        """Обработка одного батча с семафором для контроля параллелизма"""
        async with semaphore:
            return await self._process_single_batch(batch, reference_categories, claude_client)
    
    async def _process_filtered_batch(self, batch: List[Dict],
                                    filtered_references: List[Dict],
                                    claude_client: ClaudeAPIClient) -> List[Dict]:
        """Обработка предварительно отфильтрованного батча"""
        return await self._process_single_batch(batch, filtered_references, claude_client)
    
    async def _process_single_batch(self, batch: List[Dict],
                                  reference_categories: List[Dict],
                                  claude_client: ClaudeAPIClient) -> List[Dict]:
        """Обработка одного батча с кешированием"""
        
        # Проверяем кеш
        batch_key = self._get_batch_cache_key(batch, reference_categories)
        
        # Память кеш
        cached_result = self._get_from_memory_cache(batch_key)
        if cached_result:
            self.stats['cache_hits'] += 1
            logger.debug("Using memory cache for batch")
            return cached_result
        
        # Persistent кеш
        if ENABLE_PERSISTENT_CACHE:
            cached_result = self._get_from_persistent_cache(batch_key)
            if cached_result:
                # Сохраняем в memory кеш для быстрого доступа
                self._save_to_memory_cache(batch_key, cached_result)
                self.stats['cache_hits'] += 1
                logger.debug("Using persistent cache for batch")
                return cached_result
        
        # Кеш промах - обрабатываем через API
        self.stats['cache_misses'] += 1
        
        api_start = time.time()
        try:
            result = await claude_client.match_batch(reference_categories, batch)
            batch_matches = result.get('matches', [])
            
            api_time = time.time() - api_start
            self.stats['api_time'] += api_time
            self.stats['api_calls'] += 1
            
            # Сохраняем в кеши
            self._save_to_memory_cache(batch_key, batch_matches)
            if ENABLE_PERSISTENT_CACHE:
                self._save_to_persistent_cache(batch_key, batch_matches)
            
            return batch_matches
            
        except Exception as e:
            logger.error(f"Failed to process batch: {e}")
            # Возвращаем пустые результаты
            return [
                {
                    'input_name': cat['name'],
                    'match_id': None,
                    'match_name': None,
                    'confidence': 0.0,
                    'reasoning': f'Processing failed: {str(e)}'
                } for cat in batch
            ]
    
    def _create_chunks(self, categories: List[Dict], chunk_size: int) -> List[List[Dict]]:
        """Создание чанков для параллельной обработки"""
        chunks = []
        for i in range(0, len(categories), chunk_size):
            chunk = categories[i:i + chunk_size]
            chunks.append(chunk)
        return chunks
    
    def _create_batches(self, categories: List[Dict]) -> List[List[Dict]]:
        """Создание батчей стандартного размера"""
        batches = []
        for i in range(0, len(categories), self.batch_size):
            batch = categories[i:i + self.batch_size]
            batches.append(batch)
        return batches
    
    def _get_batch_cache_key(self, batch: List[Dict], reference_categories: List[Dict]) -> str:
        """Генерация ключа кеша для батча"""
        batch_content = json.dumps([cat['name'] for cat in batch], sort_keys=True)
        ref_hash = hashlib.md5(
            json.dumps([cat['id'] for cat in reference_categories], sort_keys=True).encode()
        ).hexdigest()[:8]
        
        content_hash = hashlib.md5(batch_content.encode()).hexdigest()[:16]
        return f"batch_{content_hash}_{ref_hash}"
    
    def _get_from_memory_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """Получение из memory кеша"""
        if not ENABLE_CACHE or cache_key not in self.memory_cache:
            return None
        
        # Проверяем TTL
        if cache_key in self.cache_timestamps:
            cache_time = self.cache_timestamps[cache_key]
            if datetime.now() - cache_time > timedelta(seconds=CACHE_TTL):
                del self.memory_cache[cache_key]
                del self.cache_timestamps[cache_key]
                return None
        
        return self.memory_cache[cache_key]
    
    def _save_to_memory_cache(self, cache_key: str, result: List[Dict]):
        """Сохранение в memory кеш"""
        if not ENABLE_CACHE:
            return
        
        # Контроль размера кеша
        self._cleanup_memory_cache()
        
        self.memory_cache[cache_key] = result
        self.cache_timestamps[cache_key] = datetime.now()
    
    def _get_from_persistent_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """Получение из persistent кеша"""
        cache_file = os.path.join(self.persistent_cache_dir, f"{cache_key}.json")
        
        try:
            if os.path.exists(cache_file):
                # Проверяем возраст файла
                file_age = time.time() - os.path.getmtime(cache_file)
                if file_age > CACHE_TTL:
                    os.remove(cache_file)
                    return None
                
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load from persistent cache: {e}")
        
        return None
    
    def _save_to_persistent_cache(self, cache_key: str, result: List[Dict]):
        """Сохранение в persistent кеш"""
        cache_file = os.path.join(self.persistent_cache_dir, f"{cache_key}.json")
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save to persistent cache: {e}")
    
    def _cleanup_memory_cache(self):
        """Очистка memory кеша при превышении лимитов"""
        import psutil
        import sys
        
        # Проверяем использование памяти
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        if memory_mb > MEMORY_LIMIT_MB:
            # Удаляем 25% самых старых записей
            items_to_remove = len(self.memory_cache) // 4
            if items_to_remove > 0:
                sorted_items = sorted(
                    self.cache_timestamps.items(), 
                    key=lambda x: x[1]
                )
                
                for cache_key, _ in sorted_items[:items_to_remove]:
                    if cache_key in self.memory_cache:
                        del self.memory_cache[cache_key]
                    if cache_key in self.cache_timestamps:
                        del self.cache_timestamps[cache_key]
                
                logger.info(f"Cleaned up {items_to_remove} cache entries (memory: {memory_mb:.1f}MB)")
    
    def _log_performance_stats(self):
        """Логирование статистики производительности"""
        stats = self.get_performance_stats()
        
        logger.info("=== PERFORMANCE STATS ===")
        logger.info(f"Total processing time: {stats['total_processing_time']:.2f}s")
        logger.info(f"API calls: {stats['api_calls']}")
        logger.info(f"Cache hits/misses: {stats['cache_hits']}/{stats['cache_misses']}")
        logger.info(f"Cache hit rate: {stats['cache_hit_rate']:.1f}%")
        logger.info(f"Average API time: {stats['avg_api_time']:.2f}s")
        logger.info(f"Filtering time: {stats['filtering_time']:.2f}s")
        
        if self.advanced_filter:
            filter_stats = self.advanced_filter.get_performance_stats()
            logger.info(f"Advanced filter stats: {filter_stats}")
    
    def get_performance_stats(self) -> Dict:
        """Получение статистики производительности"""
        total_cache_requests = self.stats['cache_hits'] + self.stats['cache_misses']
        cache_hit_rate = (self.stats['cache_hits'] / total_cache_requests * 100 
                         if total_cache_requests > 0 else 0)
        
        avg_api_time = (self.stats['api_time'] / self.stats['api_calls'] 
                       if self.stats['api_calls'] > 0 else 0)
        
        return {
            **self.stats,
            'cache_hit_rate': cache_hit_rate,
            'avg_api_time': avg_api_time,
            'large_dataset_mode': self.large_dataset_mode,
            'memory_cache_size': len(self.memory_cache)
        }
    
    def clear_all_caches(self):
        """Очистка всех кешей"""
        # Memory кеш
        self.memory_cache.clear()
        self.cache_timestamps.clear()
        
        # Persistent кеш
        if os.path.exists(self.persistent_cache_dir):
            for file in os.listdir(self.persistent_cache_dir):
                if file.endswith('.json'):
                    try:
                        os.remove(os.path.join(self.persistent_cache_dir, file))
                    except Exception as e:
                        logger.warning(f"Failed to remove cache file {file}: {e}")
        
        # Vector кеш
        if self.vector_search:
            self.vector_search.clear_cache()
        
        logger.info("All caches cleared")