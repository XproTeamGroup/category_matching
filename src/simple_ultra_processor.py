import logging
import asyncio
import time
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
from collections import defaultdict
from difflib import SequenceMatcher
import re

from .direct_batch_processor import DirectBatchProcessor

logger = logging.getLogger(__name__)


class SimpleUltraProcessor:
    """Упрощенный ультра-процессор, использующий существующую архитектуру"""
    
    def __init__(self, batch_size: int = 20):
        self.batch_size = batch_size
        self.batch_processor = DirectBatchProcessor(batch_size)
        
        # Статистика
        self.stats = {
            'total_input': 0,
            'auto_matched': 0,
            'ai_processed': 0,
            'api_calls': 0,
            'leaf_categories_only': 0,
            'processing_time': 0
        }
        
    def filter_leaf_categories_only(self, reference_categories: List[Dict]) -> List[Dict]:
        """Фильтрует только конечные категории (листья дерева)"""
        logger.info("Filtering reference categories to leaf nodes only...")
        
        # Строим дерево категорий для определения родительско-дочерних связей
        category_by_id = {cat['id']: cat for cat in reference_categories}
        children_counts = defaultdict(int)
        
        # Подсчитываем количество дочерних категорий по path
        for category in reference_categories:
            path = category.get('path', '')
            if '>' in path:  # У категории есть родители
                path_parts = path.split('>')
                # Проверяем, есть ли у этой категории дочерние по path
                for other_cat in reference_categories:
                    other_path = other_cat.get('path', '')
                    if other_path.startswith(path + '>'):  # Дочерняя категория
                        children_counts[category['id']] += 1
        
        # Фильтруем только листья (категории без дочерних)
        leaf_categories = []
        for category in reference_categories:
            category_id = category['id']
            if children_counts.get(category_id, 0) == 0:  # Нет дочерних категорий
                leaf_categories.append(category)
        
        logger.info(f"Filtered {len(leaf_categories)} leaf categories from {len(reference_categories)} total categories")
        self.stats['leaf_categories_only'] = len(leaf_categories)
        
        return leaf_categories
    
    def smart_pre_filter(self, input_category: Dict, leaf_categories: List[Dict]) -> Optional[Tuple[Dict, float]]:
        """Умная предварительная фильтрация с высоким порогом уверенности"""
        
        input_name = input_category.get('name', '')
        if not input_name:
            return None
        
        input_normalized = self._normalize_category_name(input_name)
        
        # Проверяем точные и очень похожие совпадения
        for ref_cat in leaf_categories:
            ref_name = ref_cat.get('name', '')
            if not ref_name:
                continue
                
            ref_normalized = self._normalize_category_name(ref_name)
            
            # Точное совпадение
            if input_normalized == ref_normalized:
                return ref_cat, 1.0
            
            # Очень высокое сходство (95%+)
            similarity = SequenceMatcher(None, input_normalized, ref_normalized).ratio()
            if similarity >= 0.95:
                return ref_cat, similarity
                
            # Проверяем основные синонимы
            synonym_match = self._check_basic_synonyms(input_normalized, ref_normalized)
            if synonym_match >= 0.9:
                return ref_cat, synonym_match
        
        return None
    
    def _check_basic_synonyms(self, input_text: str, ref_text: str) -> float:
        """Простая проверка основных синонимов"""
        # Базовые синонимы для русского/украинского
        synonyms = {
            'глушители': ['глушники', 'exhaust'],
            'масло': ['масла', 'oil'],
            'моторное': ['моторні', 'motor'],
            'скидки': ['розпродаж', 'sale', 'discount'],
            'товары': ['товари', 'products'],
            'автомобильные': ['автомобільні', 'automotive', 'auto'],
            'запчасти': ['запчастини', 'parts'],
            'аксессуары': ['аксесуари', 'accessories']
        }
        
        input_words = set(input_text.split())
        ref_words = set(ref_text.split())
        
        # Проверяем синонимы
        match_score = 0.0
        total_words = len(input_words)
        
        for input_word in input_words:
            if input_word in ref_words:
                match_score += 1.0
            else:
                # Проверяем синонимы
                for key, syns in synonyms.items():
                    if input_word == key and any(syn in ref_words for syn in syns):
                        match_score += 0.9
                        break
                    elif input_word in syns and key in ref_words:
                        match_score += 0.9
                        break
        
        return match_score / max(total_words, 1) if total_words > 0 else 0.0
    
    def _normalize_category_name(self, name: str) -> str:
        """Нормализация названия категории для сравнения"""
        if not isinstance(name, str):
            return ""
            
        # Приводим к нижнему регистру
        normalized = name.lower().strip()
        
        # Удаляем лишние пробелы и знаки препинания
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    async def process_simple_ultra_optimized(self, input_categories: List[Dict], 
                                           reference_categories: List[Dict],
                                           claude_client) -> List[Dict]:
        """Упрощенная ультра-оптимизированная обработка категорий"""
        
        start_time = time.time()
        self.stats['total_input'] = len(input_categories)
        
        logger.info(f"Starting simple ultra-optimized processing for {len(input_categories)} categories")
        
        # ЭТАП 1: Фильтруем только конечные категории
        leaf_categories = self.filter_leaf_categories_only(reference_categories)
        
        # ЭТАП 2: Умная предварительная фильтрация
        auto_matched = []
        need_ai_processing = []
        
        logger.info("Running smart pre-filtering...")
        processed_ids = set()  # Отслеживаем уже обработанные ID
        
        for input_cat in input_categories:
            try:
                # Пропускаем дубли по ID
                cat_id = input_cat.get('id', '')
                if cat_id in processed_ids:
                    logger.debug(f"Skipping duplicate category ID: {cat_id}")
                    continue
                processed_ids.add(cat_id)
                
                match_result = self.smart_pre_filter(input_cat, leaf_categories)
                
                if match_result:
                    matched_category, confidence = match_result
                    auto_matched.append({
                        'input_category_id': input_cat.get('id', ''),
                        'input_category_name': input_cat.get('name', ''),
                        'input_name': input_cat.get('name', ''),
                        'match_id': matched_category['id'],
                        'match_name': matched_category['name'],
                        'confidence': confidence,
                        'reasoning': 'Автоматическое совпадение',
                        'processing_method': 'auto_smart_match',
                        'is_exact_match': confidence >= 0.95,
                        'needs_review': confidence < 0.7
                    })
                    self.stats['auto_matched'] += 1
                else:
                    need_ai_processing.append(input_cat)
            except Exception as e:
                logger.error(f"Smart pre-filter failed for '{input_cat.get('name', 'unknown')}': {e}")
                need_ai_processing.append(input_cat)
        
        logger.info(f"Auto-matched: {len(auto_matched)}, Need AI processing: {len(need_ai_processing)}")
        
        # ЭТАП 3: Обработка через ПРЯМОЙ batch processor
        ai_processed = []
        if need_ai_processing:
            # Обрабатываем прямыми батчами
            ai_processed = await self.batch_processor.process_categories_direct_batches(
                need_ai_processing, leaf_categories
            )
            
            self.stats['api_calls'] = self.batch_processor.stats.get('api_calls', 0)
        
        # ЭТАП 4: Объединяем результаты
        all_results = auto_matched + ai_processed
        
        # Финальная статистика
        self.stats['processing_time'] = time.time() - start_time
        self.stats['ai_processed'] = len(ai_processed)
        
        logger.info(f"Simple ultra-optimized processing completed in {self.stats['processing_time']:.2f}s")
        logger.info(f"Auto-matched: {self.stats['auto_matched']}, AI processed: {self.stats['ai_processed']}, API calls: {self.stats['api_calls']}")
        
        return all_results
    
    def get_optimization_stats(self) -> Dict:
        """Получает статистику оптимизации"""
        total = self.stats['total_input']
        if total == 0:
            return self.stats
        
        stats_with_percentages = self.stats.copy()
        stats_with_percentages.update({
            'auto_match_rate': (self.stats['auto_matched'] / total) * 100,
            'ai_processing_rate': (self.stats['ai_processed'] / total) * 100,
            'api_call_efficiency': total / max(self.stats['api_calls'], 1),  # категорий на API вызов
            'categories_per_second': total / max(self.stats['processing_time'], 0.001)
        })
        
        return stats_with_percentages