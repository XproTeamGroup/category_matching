import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from .claude_client import ClaudeAPIClient
from .processor import CategoryProcessor
from .batch_processor import BatchProcessor
from .exporter import ResultExporter
from config.settings import BATCH_SIZE, CONFIDENCE_THRESHOLD


logger = logging.getLogger(__name__)


class CategoryMatcher:
    """Основной класс для автоматического сопоставления категорий"""
    
    def __init__(self, api_key: Optional[str] = None, 
                 reference_file: Optional[str] = None,
                 batch_size: int = BATCH_SIZE):
        
        self.claude_client = ClaudeAPIClient(api_key)
        self.processor = CategoryProcessor()
        self.batch_processor = BatchProcessor(batch_size)
        self.exporter = ResultExporter()
        
        self.reference_categories: List[Dict] = []
        self.category_tree: Dict = {}
        
        # Статистика
        self.api_requests_count = 0
        self.processing_start_time: Optional[datetime] = None
        
        # Загружаем справочные категории если указан файл
        if reference_file:
            self.load_reference_categories(reference_file)
    
    def load_reference_categories(self, reference_file: str):
        """Загрузка справочных категорий из файла"""
        logger.info("Loading reference categories")
        
        self.reference_categories = self.processor.load_reference_categories(reference_file)
        self.category_tree = self.processor.build_tree(self.reference_categories)
        
        logger.info(f"Loaded {len(self.reference_categories)} reference categories")
    
    async def match_categories(self, input_file: str, output_file: str, 
                             enable_prefiltering: bool = True) -> Dict:
        """Основная функция сопоставления категорий"""
        
        if not self.reference_categories:
            raise ValueError("Reference categories not loaded. Use load_reference_categories() first.")
        
        self.processing_start_time = datetime.now()
        logger.info("Starting category matching process")
        
        try:
            # Загружаем входные категории
            input_categories = self.processor.load_input_categories(input_file)
            logger.info(f"Loaded {len(input_categories)} input categories")
            
            # Предварительная фильтрация для оптимизации
            if enable_prefiltering:
                filtered_reference = self.processor.pre_filter_categories(
                    input_categories, self.reference_categories
                )
                logger.info(f"Pre-filtered to {len(filtered_reference)} reference categories")
            else:
                filtered_reference = self.reference_categories
            
            # Обрабатываем категории в батчах
            matches = await self.batch_processor.process_in_batches(
                input_categories, filtered_reference, self.claude_client
            )
            
            # Подсчитываем количество API запросов
            self.api_requests_count = len(self.batch_processor._create_batches(input_categories))
            
            # Постобработка результатов
            matches = self._post_process_matches(matches, filtered_reference)
            
            # Экспортируем результаты
            result_data = self.exporter.export_results(
                matches, input_categories, self.reference_categories,
                output_file, self.processing_start_time, self.api_requests_count
            )
            
            logger.info("Category matching completed successfully")
            return result_data
            
        except Exception as e:
            logger.error(f"Category matching failed: {e}")
            raise
    
    def _post_process_matches(self, matches: List[Dict], 
                            reference_categories: List[Dict]) -> List[Dict]:
        """Постобработка результатов сопоставления"""
        
        # Создаем индекс справочных категорий для быстрого поиска
        ref_index = {cat['id']: cat for cat in reference_categories}
        
        processed_matches = []
        
        for match in matches:
            # Дополняем информацию о сопоставлении
            match_id = match.get('match_id')
            if match_id and match_id in ref_index:
                ref_cat = ref_index[match_id]
                match['match_path'] = ref_cat.get('path', '')
                
                # Если match_name не заполнено, берем из справочника
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
        
        return processed_matches
    
    def get_statistics(self) -> Dict:
        """Получение статистики текущего процесса"""
        return {
            'reference_categories_loaded': len(self.reference_categories),
            'api_requests_made': self.api_requests_count,
            'cache_stats': self.batch_processor.get_cache_stats(),
            'processing_start_time': self.processing_start_time.isoformat() if self.processing_start_time else None
        }
    
    def find_similar_categories(self, category_name: str, limit: int = 10) -> List[Dict]:
        """Поиск похожих категорий в справочнике (для отладки)"""
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
        
        # Совпадения по ключевым словам
        if len(results) < limit:
            keyword_matches = self.processor.find_keyword_matches(category_name)
            for match, score in keyword_matches[:limit - len(results)]:
                results.append({
                    'id': match.id,
                    'name': match.name,
                    'path': match.path,
                    'match_type': 'keyword',
                    'score': score
                })
        
        return results
    
    def clear_cache(self):
        """Очистка кеша батч-процессора"""
        self.batch_processor.clear_cache()
        logger.info("Cache cleared")
    
    def set_confidence_threshold(self, threshold: float):
        """Установка порога уверенности для сопоставления"""
        if 0.0 <= threshold <= 1.0:
            self.exporter.confidence_threshold = threshold
            logger.info(f"Confidence threshold set to {threshold}")
        else:
            raise ValueError("Confidence threshold must be between 0.0 and 1.0")