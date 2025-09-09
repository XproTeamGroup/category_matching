import logging
import asyncio
import time
import json
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
from collections import defaultdict
from difflib import SequenceMatcher
import re

from .claude_client import ClaudeAPIClient
from .smart_matcher import SmartMatcher
from config.settings import BATCH_SIZE, CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


class UltraOptimizedProcessor:
    """Ультра-оптимизированный процессор для максимальной производительности"""
    
    def __init__(self, batch_size: int = BATCH_SIZE):
        self.batch_size = batch_size
        self.smart_matcher = SmartMatcher()
        
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
        
        # Подсчитываем количество дочерних категорий
        for category in reference_categories:
            parent_id = category.get('parent_id')
            if parent_id and parent_id in category_by_id:
                children_counts[parent_id] += 1
        
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
        
        # Временно используем упрощенную версию вместо SmartMatcher
        # TODO: Исправить SmartMatcher для работы с Dict вместо строк
        
        input_name = input_category.get('name', '')
        if not input_name:
            return None
        
        # Дополнительная проверка на точные совпадения после нормализации
        input_normalized = self._normalize_category_name(input_category['name'])
        
        for ref_cat in leaf_categories:
            ref_normalized = self._normalize_category_name(ref_cat['name'])
            
            # Точное совпадение
            if input_normalized == ref_normalized:
                return ref_cat, 1.0
            
            # Очень высокое сходство (95%+)
            similarity = SequenceMatcher(None, input_normalized, ref_normalized).ratio()
            if similarity >= 0.95:
                return ref_cat, similarity
        
        return None
    
    def _normalize_category_name(self, name) -> str:
        """Нормализация названия категории для сравнения"""
        # Проверяем тип входных данных
        if isinstance(name, dict):
            name = name.get('name', '')
        elif not isinstance(name, str):
            name = str(name)
        
        # Приводим к нижнему регистру
        normalized = name.lower().strip()
        
        # Удаляем лишние пробелы и знаки препинания
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    async def process_ultra_optimized(self, input_categories: List[Dict], 
                                    reference_categories: List[Dict],
                                    claude_client: ClaudeAPIClient) -> List[Dict]:
        """Ультра-оптимизированная обработка категорий"""
        
        start_time = time.time()
        self.stats['total_input'] = len(input_categories)
        
        logger.info(f"Starting ultra-optimized processing for {len(input_categories)} categories")
        
        # ЭТАП 1: Фильтруем только конечные категории
        leaf_categories = self.filter_leaf_categories_only(reference_categories)
        
        # ЭТАП 2: Умная предварительная фильтрация
        auto_matched = []
        need_ai_processing = []
        
        logger.info("Running smart pre-filtering...")
        for i, input_cat in enumerate(input_categories):
            try:
                match_result = self.smart_pre_filter(input_cat, leaf_categories)
                
                if match_result:
                    matched_category, confidence = match_result
                    auto_matched.append({
                        'input_category': input_cat,
                        'matched_category': matched_category,
                        'confidence': confidence,
                        'method': 'auto_smart_match'
                    })
                    self.stats['auto_matched'] += 1
                else:
                    need_ai_processing.append(input_cat)
            except Exception as e:
                logger.error(f"Smart pre-filter failed for category {i} '{input_cat.get('name', 'unknown')}': {e}")
                need_ai_processing.append(input_cat)
        
        logger.info(f"Auto-matched: {len(auto_matched)}, Need AI processing: {len(need_ai_processing)}")
        
        # ЭТАП 3: Пакетная обработка через AI для оставшихся категорий
        ai_processed = []
        if need_ai_processing:
            ai_processed = await self._batch_process_with_ai(
                need_ai_processing, leaf_categories, claude_client
            )
        
        # ЭТАП 4: Объединяем результаты
        all_results = auto_matched + ai_processed
        
        # Финальная статистика
        self.stats['processing_time'] = time.time() - start_time
        self.stats['ai_processed'] = len(ai_processed)
        
        logger.info(f"Ultra-optimized processing completed in {self.stats['processing_time']:.2f}s")
        logger.info(f"Auto-matched: {self.stats['auto_matched']}, AI processed: {self.stats['ai_processed']}, API calls: {self.stats['api_calls']}")
        
        return all_results
    
    async def _batch_process_with_ai(self, categories: List[Dict], 
                                   leaf_categories: List[Dict],
                                   claude_client: ClaudeAPIClient) -> List[Dict]:
        """Пакетная обработка нескольких категорий в одном API запросе"""
        
        if not categories:
            return []
        
        results = []
        
        # Разбиваем на батчи по batch_size категорий
        for i in range(0, len(categories), self.batch_size):
            batch = categories[i:i + self.batch_size]
            
            try:
                batch_results = await self._process_batch_with_ai(batch, leaf_categories, claude_client)
                results.extend(batch_results)
                self.stats['api_calls'] += 1
                
                logger.info(f"Processed batch {i//self.batch_size + 1}/{(len(categories) + self.batch_size - 1)//self.batch_size}")
                
                # Небольшая пауза между запросами для избежания rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
                # Fallback: обрабатываем по одной категории
                for single_cat in batch:
                    try:
                        single_result = await self._process_single_category_fallback(
                            single_cat, leaf_categories, claude_client
                        )
                        results.append(single_result)
                        self.stats['api_calls'] += 1
                        await asyncio.sleep(0.1)
                    except Exception as single_e:
                        logger.error(f"Single category fallback failed for '{single_cat['name']}': {single_e}")
                        results.append({
                            'input_category': single_cat,
                            'matched_category': None,
                            'confidence': 0.0,
                            'method': 'failed'
                        })
        
        return results
    
    async def _process_batch_with_ai(self, batch: List[Dict], 
                                   leaf_categories: List[Dict],
                                   claude_client: ClaudeAPIClient) -> List[Dict]:
        """Обработка батча категорий одним AI запросом"""
        
        # Ограничиваем количество справочных категорий для производительности
        max_ref_categories = 100  # Топ-100 наиболее релевантных
        
        # Получаем наиболее релевантные справочные категории
        relevant_categories = self._get_most_relevant_categories(batch, leaf_categories, max_ref_categories)
        
        # Формируем промпт для батча
        prompt = self._build_batch_prompt(batch, relevant_categories)
        
        # Отправляем запрос к AI
        # Создаем временный формат для совместимости с существующим API
        temp_input_categories = [{'name': cat['name'], 'id': f"temp_{i}"} for i, cat in enumerate(batch)]
        result = await claude_client.match_batch(relevant_categories, temp_input_categories)
        response = result.get('response', '')
        
        # Парсим ответ
        return self._parse_batch_response(response, batch, relevant_categories)
    
    def _get_most_relevant_categories(self, batch: List[Dict], 
                                    leaf_categories: List[Dict], 
                                    max_count: int) -> List[Dict]:
        """Получает наиболее релевантные справочные категории для батча"""
        
        # Простая эвристика: берем категории с наибольшим количеством общих слов
        batch_words = set()
        for cat in batch:
            words = self._extract_words(cat['name'])
            batch_words.update(words)
        
        # Оцениваем релевантность каждой справочной категории
        category_scores = []
        for ref_cat in leaf_categories:
            ref_words = set(self._extract_words(ref_cat['name']))
            common_words = len(batch_words & ref_words)
            if common_words > 0:
                category_scores.append((ref_cat, common_words))
        
        # Сортируем по релевантности и берем топ-N
        category_scores.sort(key=lambda x: x[1], reverse=True)
        return [cat for cat, score in category_scores[:max_count]]
    
    def _extract_words(self, text: str) -> Set[str]:
        """Извлекает слова из текста"""
        normalized = self._normalize_category_name(text)
        words = normalized.split()
        # Фильтруем короткие слова и стоп-слова
        stop_words = {'и', 'или', 'для', 'в', 'на', 'с', 'по', 'от', 'к', 'из', 'все', 'товары'}
        return {word for word in words if len(word) > 2 and word not in stop_words}
    
    def _build_batch_prompt(self, batch: List[Dict], reference_categories: List[Dict]) -> str:
        """Строит промпт для обработки батча категорий"""
        
        # Формируем список входных категорий
        input_list = []
        for i, cat in enumerate(batch, 1):
            input_list.append(f"{i}. {cat['name']}")
        
        # Формируем список справочных категорий
        ref_list = []
        for cat in reference_categories:
            ref_list.append(f"ID: {cat['id']}, Name: {cat['name']}")
        
        prompt = f"""Вам нужно сопоставить {len(batch)} входных категорий со справочными категориями.

ВХОДНЫЕ КАТЕГОРИИ:
{chr(10).join(input_list)}

СПРАВОЧНЫЕ КАТЕГОРИИ (только конечные/листья):
{chr(10).join(ref_list)}

Для каждой входной категории найдите наиболее подходящую справочную категорию.

ФОРМАТ ОТВЕТА (строго JSON):
{{
  "matches": [
    {{"input_index": 1, "matched_id": "найденный_id", "confidence": 0.85, "reason": "краткое объяснение"}},
    {{"input_index": 2, "matched_id": "найденный_id", "confidence": 0.92, "reason": "краткое объяснение"}},
    ...
  ]
}}

ВАЖНО: 
- Возвращайте ТОЛЬКО JSON без дополнительного текста
- input_index начинается с 1
- confidence должен быть от 0.0 до 1.0
- Если подходящей категории нет, используйте "matched_id": null"""

        return prompt
    
    def _parse_batch_response(self, response: str, batch: List[Dict], 
                            reference_categories: List[Dict]) -> List[Dict]:
        """Парсит ответ AI для батча категорий"""
        
        results = []
        ref_by_id = {cat['id']: cat for cat in reference_categories}
        
        try:
            # Извлекаем JSON из ответа
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("JSON not found in response")
            
            json_str = response[json_start:json_end]
            parsed = json.loads(json_str)
            matches = parsed.get('matches', [])
            
            # Обрабатываем каждое совпадение
            for match in matches:
                input_index = match.get('input_index', 0) - 1  # Переводим в 0-based индекс
                matched_id = match.get('matched_id')
                confidence = float(match.get('confidence', 0.0))
                reason = match.get('reason', '')
                
                if 0 <= input_index < len(batch):
                    input_cat = batch[input_index]
                    matched_cat = ref_by_id.get(matched_id) if matched_id else None
                    
                    results.append({
                        'input_category': input_cat,
                        'matched_category': matched_cat,
                        'confidence': confidence,
                        'method': 'ai_batch',
                        'reason': reason
                    })
                
        except Exception as e:
            logger.error(f"Failed to parse batch response: {e}")
            # Fallback: создаем пустые результаты
            for input_cat in batch:
                results.append({
                    'input_category': input_cat,
                    'matched_category': None,
                    'confidence': 0.0,
                    'method': 'parse_failed'
                })
        
        # Убеждаемся что у нас есть результат для каждой входной категории
        while len(results) < len(batch):
            missing_index = len(results)
            results.append({
                'input_category': batch[missing_index],
                'matched_category': None,
                'confidence': 0.0,
                'method': 'missing_result'
            })
        
        return results
    
    async def _process_single_category_fallback(self, input_category: Dict,
                                              leaf_categories: List[Dict],
                                              claude_client: ClaudeAPIClient) -> Dict:
        """Fallback обработка одной категории"""
        
        # Берем топ-20 наиболее релевантных категорий
        relevant_categories = self._get_most_relevant_categories([input_category], leaf_categories, 20)
        
        prompt = f"""Найдите наиболее подходящую категорию для сопоставления.

ВХОДНАЯ КАТЕГОРИЯ: {input_category['name']}

СПРАВОЧНЫЕ КАТЕГОРИИ:
{chr(10).join([f"ID: {cat['id']}, Name: {cat['name']}" for cat in relevant_categories])}

Верните JSON: {{"matched_id": "id", "confidence": 0.85, "reason": "объяснение"}}"""

        # Используем существующий API
        temp_input = [{'name': input_category['name'], 'id': 'temp_single'}]
        result = await claude_client.match_batch(relevant_categories, temp_input)
        response = result.get('response', '')
        
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            json_str = response[json_start:json_end]
            parsed = json.loads(json_str)
            
            matched_id = parsed.get('matched_id')
            confidence = float(parsed.get('confidence', 0.0))
            reason = parsed.get('reason', '')
            
            ref_by_id = {cat['id']: cat for cat in relevant_categories}
            matched_cat = ref_by_id.get(matched_id) if matched_id else None
            
            return {
                'input_category': input_category,
                'matched_category': matched_cat,
                'confidence': confidence,
                'method': 'ai_single_fallback',
                'reason': reason
            }
            
        except Exception as e:
            logger.error(f"Failed to parse single category response: {e}")
            return {
                'input_category': input_category,
                'matched_category': None,
                'confidence': 0.0,
                'method': 'single_fallback_failed'
            }
    
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