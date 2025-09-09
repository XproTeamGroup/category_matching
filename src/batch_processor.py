import logging
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from .claude_client import ClaudeAPIClient
from config.settings import BATCH_SIZE, ENABLE_CACHE, CACHE_TTL


logger = logging.getLogger(__name__)


class BatchProcessor:
    """Батчевая обработка категорий для оптимизации запросов"""
    
    def __init__(self, batch_size: int = BATCH_SIZE):
        self.batch_size = batch_size
        self.cache: Dict[str, Dict] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        self.enable_cache = ENABLE_CACHE
        self.cache_ttl = CACHE_TTL
    
    async def process_in_batches(self, input_categories: List[Dict], 
                               reference_categories: List[Dict],
                               claude_client: ClaudeAPIClient) -> List[Dict]:
        """Обработка категорий в батчах"""
        logger.info(f"Processing {len(input_categories)} categories in batches of {self.batch_size}")
        
        all_matches = []
        batches = self._create_batches(input_categories)
        
        for i, batch in enumerate(batches, 1):
            logger.info(f"Processing batch {i}/{len(batches)} with {len(batch)} categories")
            
            # Проверяем кеш для батча
            batch_key = self._get_batch_cache_key(batch, reference_categories)
            cached_result = self._get_from_cache(batch_key)
            
            if cached_result:
                logger.info(f"Using cached result for batch {i}")
                batch_matches = cached_result
            else:
                # Обрабатываем батч через Claude API
                try:
                    result = await claude_client.match_batch(reference_categories, batch)
                    batch_matches = result.get('matches', [])
                    
                    # Кешируем результат
                    if self.enable_cache:
                        self._save_to_cache(batch_key, batch_matches)
                        
                except Exception as e:
                    logger.error(f"Failed to process batch {i}: {e}")
                    # Возвращаем пустые результаты для этого батча
                    batch_matches = [
                        {
                            'input_name': cat['name'],
                            'match_id': None,
                            'match_name': None,
                            'confidence': 0.0,
                            'reasoning': f'Processing failed: {str(e)}'
                        } for cat in batch
                    ]
            
            all_matches.extend(batch_matches)
            
            # Добавляем небольшую паузу между батчами для избежания rate limiting
            if i < len(batches):
                await asyncio.sleep(0.5)
        
        logger.info(f"Completed processing all batches. Total matches: {len(all_matches)}")
        return all_matches
    
    def _create_batches(self, categories: List[Dict]) -> List[List[Dict]]:
        """Создание батчей из списка категорий"""
        batches = []
        for i in range(0, len(categories), self.batch_size):
            batch = categories[i:i + self.batch_size]
            batches.append(batch)
        
        logger.info(f"Created {len(batches)} batches")
        return batches
    
    def _get_batch_cache_key(self, batch: List[Dict], reference_categories: List[Dict]) -> str:
        """Генерация ключа кеша для батча"""
        # Создаем хеш на основе названий категорий в батче и количества справочных категорий
        batch_names = sorted([cat['name'] for cat in batch])
        ref_count = len(reference_categories)
        cache_key = f"batch_{hash(tuple(batch_names))}_{ref_count}"
        return cache_key
    
    def _get_from_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """Получение результата из кеша"""
        if not self.enable_cache or cache_key not in self.cache:
            return None
        
        # Проверяем не истек ли TTL
        if cache_key in self.cache_timestamps:
            cache_time = self.cache_timestamps[cache_key]
            if datetime.now() - cache_time > timedelta(seconds=self.cache_ttl):
                # Удаляем устаревшую запись
                del self.cache[cache_key]
                del self.cache_timestamps[cache_key]
                return None
        
        return self.cache[cache_key]
    
    def _save_to_cache(self, cache_key: str, result: List[Dict]):
        """Сохранение результата в кеш"""
        if not self.enable_cache:
            return
        
        self.cache[cache_key] = result
        self.cache_timestamps[cache_key] = datetime.now()
        
        # Очищаем старые записи кеша
        self._cleanup_cache()
    
    def _cleanup_cache(self):
        """Очистка устаревших записей кеша"""
        current_time = datetime.now()
        expired_keys = []
        
        for cache_key, timestamp in self.cache_timestamps.items():
            if current_time - timestamp > timedelta(seconds=self.cache_ttl):
                expired_keys.append(cache_key)
        
        for key in expired_keys:
            if key in self.cache:
                del self.cache[key]
            if key in self.cache_timestamps:
                del self.cache_timestamps[key]
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def clear_cache(self):
        """Очистка всего кеша"""
        self.cache.clear()
        self.cache_timestamps.clear()
        logger.info("Cache cleared")
    
    def get_cache_stats(self) -> Dict:
        """Получение статистики кеша"""
        return {
            'cache_size': len(self.cache),
            'cache_enabled': self.enable_cache,
            'cache_ttl': self.cache_ttl
        }