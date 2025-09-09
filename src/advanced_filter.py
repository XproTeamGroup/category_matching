import logging
import time
from typing import List, Dict, Tuple, Set, Optional
from difflib import SequenceMatcher
from collections import defaultdict, Counter
import re
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from .smart_matcher import SmartMatcher
from config.settings import (
    KEYWORD_FILTER_THRESHOLD, FUZZY_SIMILARITY_THRESHOLD, 
    HIERARCHY_BONUS_WEIGHT, MAX_CATEGORIES_FOR_CLAUDE,
    PARALLEL_PROCESSING, MAX_WORKERS
)


logger = logging.getLogger(__name__)


class AdvancedCategoryFilter:
    """Продвинутая система фильтрации для работы с большими объемами данных"""
    
    def __init__(self):
        self.keyword_index: Dict[str, Set[str]] = defaultdict(set)  # keyword -> set of category_ids
        self.ngram_index: Dict[str, Set[str]] = defaultdict(set)    # n-gram -> set of category_ids
        self.hierarchy_index: Dict[str, List[str]] = {}             # category_id -> path hierarchy
        self.category_keywords: Dict[str, Set[str]] = {}            # category_id -> keywords
        self.category_data: Dict[str, Dict] = {}                    # category_id -> full category data
        
        # Умный сопоставитель для обработки синонимов и языковых особенностей
        self.smart_matcher = SmartMatcher()
        
        # Статистика производительности
        self.stats = {
            'keyword_filtering_time': 0,
            'fuzzy_filtering_time': 0, 
            'hierarchy_analysis_time': 0,
            'total_categories_processed': 0,
            'average_candidates_per_input': 0
        }
    
    def build_advanced_indexes(self, categories: List[Dict]):
        """Построение продвинутых индексов для быстрого поиска"""
        start_time = time.time()
        logger.info(f"Building advanced indexes for {len(categories)} categories")
        
        # Очистка существующих индексов
        self.keyword_index.clear()
        self.ngram_index.clear()
        self.hierarchy_index.clear()
        self.category_keywords.clear()
        self.category_data.clear()
        
        # Обработка категорий
        for category in categories:
            cat_id = category['id']
            cat_name = category['name']
            cat_path = category.get('path', '')
            
            # Сохраняем полную информацию
            self.category_data[cat_id] = category
            self.hierarchy_index[cat_id] = cat_path.split('>') if cat_path else [cat_id]
            
            # Извлекаем ключевые слова
            keywords = self._extract_advanced_keywords(cat_name)
            self.category_keywords[cat_id] = keywords
            
            # Индекс по ключевым словам
            for keyword in keywords:
                self.keyword_index[keyword].add(cat_id)
            
            # Индекс по n-граммам (2-3 символа для более точного поиска)
            ngrams = self._generate_ngrams(cat_name.lower(), n_range=(2, 4))
            for ngram in ngrams:
                self.ngram_index[ngram].add(cat_id)
        
        build_time = time.time() - start_time
        logger.info(f"Advanced indexes built in {build_time:.2f}s")
        logger.info(f"Keyword index size: {len(self.keyword_index)}")
        logger.info(f"N-gram index size: {len(self.ngram_index)}")
    
    def filter_candidates_for_large_dataset(self, input_category: str, 
                                          max_candidates: int = MAX_CATEGORIES_FOR_CLAUDE) -> List[Dict]:
        """Многоступенчатая фильтрация для больших данных с умным сопоставлением"""
        
        if not self.category_data:
            logger.warning("Indexes not built. Call build_advanced_indexes() first.")
            return []
        
        start_time = time.time()
        
        # ЭТАП 0: Умное сопоставление для поиска очевидных совпадений
        all_categories = list(self.category_data.values())
        smart_matches = self.smart_matcher.find_smart_matches(
            input_category, all_categories, top_k=max_candidates * 2
        )
        
        # Проверяем, есть ли высококачественные совпадения
        high_quality_matches = [
            (match[0]['id'], match[1]) for match in smart_matches 
            if match[1] >= 0.8  # Высокая уверенность
        ]
        
        if high_quality_matches:
            # Если нашли очевидные совпадения, используем их в приоритете
            logger.info(f"Found {len(high_quality_matches)} high-quality smart matches for '{input_category}'")
            priority_candidates = high_quality_matches
        else:
            priority_candidates = []
        
        # ЭТАП 1: Быстрая фильтрация по ключевым словам
        keyword_candidates = self._filter_by_keywords(input_category)
        
        # ЭТАП 2: Фильтрация по n-граммам
        ngram_candidates = self._filter_by_ngrams(input_category)
        
        # ЭТАП 3: Объединение всех кандидатов
        all_candidates = self._merge_candidates_with_smart_matches(
            priority_candidates, keyword_candidates, ngram_candidates
        )
        
        # ЭТАП 4: Нечеткое сравнение для топ-кандидатов (если нет приоритетных)
        if not priority_candidates:
            fuzzy_candidates = self._apply_fuzzy_filtering(input_category, all_candidates)
        else:
            fuzzy_candidates = all_candidates
        
        # ЭТАП 5: Иерархический анализ
        final_candidates = self._apply_hierarchy_bonus(input_category, fuzzy_candidates)
        
        # ЭТАП 6: Финальная сортировка и ограничение
        result = sorted(final_candidates, key=lambda x: x[1], reverse=True)[:max_candidates]
        
        # Конвертируем в формат категорий
        filtered_categories = [self.category_data[cat_id] for cat_id, _ in result]
        
        total_time = time.time() - start_time
        logger.debug(f"Smart filtered {len(self.category_data)} -> {len(filtered_categories)} categories in {total_time:.3f}s")
        
        # Логируем топ совпадения для отладки
        if result and logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Top filtered candidates for '{input_category}':")
            for i, (cat_id, score) in enumerate(result[:3], 1):
                cat_name = self.category_data[cat_id]['name']
                logger.debug(f"  {i}. {cat_name} (score: {score:.3f})")
        
        # Обновляем статистику
        self._update_stats(total_time, len(filtered_categories))
        
        return filtered_categories
    
    def _extract_advanced_keywords(self, text: str) -> Set[str]:
        """Продвинутое извлечение ключевых слов"""
        # Нормализация текста
        text = text.lower()
        
        # Удаляем специальные символы, оставляем только буквы и цифры
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Извлекаем слова
        words = text.split()
        
        # Фильтруем стоп-слова и короткие слова
        stop_words = {
            'и', 'или', 'для', 'в', 'на', 'с', 'по', 'от', 'к', 'из', 'за', 'под', 'над',
            'та', 'або', 'для', 'в', 'на', 'з', 'по', 'від', 'до', 'із', 'за', 'під', 'над',
            'the', 'and', 'or', 'for', 'in', 'on', 'with', 'by', 'from', 'to', 'of', 'at'
        }
        
        keywords = set()
        for word in words:
            if len(word) > 2 and word not in stop_words:
                keywords.add(word)
                
                # Добавляем корень слова (простая стемматизация)
                if len(word) > 4:
                    root = self._simple_stem(word)
                    if root != word:
                        keywords.add(root)
        
        return keywords
    
    def _simple_stem(self, word: str) -> str:
        """Простая стемматизация для русского/украинского"""
        # Удаляем распространенные окончания
        suffixes = ['ов', 'ев', 'ий', 'ый', 'ой', 'ая', 'ое', 'ые', 'ий', 'ні', 'на', 'не', 'ний', 'тий']
        
        for suffix in sorted(suffixes, key=len, reverse=True):
            if word.endswith(suffix) and len(word) > len(suffix) + 2:
                return word[:-len(suffix)]
        
        return word
    
    def _generate_ngrams(self, text: str, n_range: Tuple[int, int] = (2, 3)) -> Set[str]:
        """Генерация n-грамм для точного поиска"""
        text = re.sub(r'[^\w]', '', text)  # Удаляем все кроме букв и цифр
        ngrams = set()
        
        for n in range(n_range[0], n_range[1] + 1):
            for i in range(len(text) - n + 1):
                ngram = text[i:i + n]
                if len(ngram) == n:
                    ngrams.add(ngram)
        
        return ngrams
    
    def _filter_by_keywords(self, input_category: str) -> List[Tuple[str, float]]:
        """Фильтрация по ключевым словам с подсчетом релевантности"""
        start_time = time.time()
        
        input_keywords = self._extract_advanced_keywords(input_category)
        candidates = defaultdict(float)
        
        for keyword in input_keywords:
            if keyword in self.keyword_index:
                # Вес ключевого слова (более редкие слова получают больший вес)
                keyword_weight = math.log(len(self.category_data) / len(self.keyword_index[keyword]) + 1)
                
                for cat_id in self.keyword_index[keyword]:
                    candidates[cat_id] += keyword_weight
        
        # Нормализация по количеству ключевых слов в категории
        normalized_candidates = []
        for cat_id, score in candidates.items():
            cat_keywords = self.category_keywords.get(cat_id, set())
            if cat_keywords:
                # Jaccard similarity
                intersection = len(input_keywords & cat_keywords)
                union = len(input_keywords | cat_keywords)
                jaccard = intersection / union if union > 0 else 0
                
                if jaccard >= KEYWORD_FILTER_THRESHOLD:
                    final_score = score * jaccard
                    normalized_candidates.append((cat_id, final_score))
        
        self.stats['keyword_filtering_time'] += time.time() - start_time
        return normalized_candidates
    
    def _filter_by_ngrams(self, input_category: str) -> List[Tuple[str, float]]:
        """Фильтрация по n-граммам для точного текстового поиска"""
        input_ngrams = self._generate_ngrams(input_category.lower())
        candidates = defaultdict(int)
        
        for ngram in input_ngrams:
            if ngram in self.ngram_index:
                for cat_id in self.ngram_index[ngram]:
                    candidates[cat_id] += 1
        
        # Нормализация по длине текста
        normalized_candidates = []
        for cat_id, ngram_matches in candidates.items():
            cat_name = self.category_data[cat_id]['name'].lower()
            cat_ngrams = self._generate_ngrams(cat_name)
            
            if cat_ngrams:
                similarity = ngram_matches / max(len(input_ngrams), len(cat_ngrams))
                if similarity > 0.2:  # Минимальное n-gram пересечение
                    normalized_candidates.append((cat_id, similarity))
        
        return normalized_candidates
    
    def _merge_candidates(self, keyword_candidates: List[Tuple[str, float]], 
                         ngram_candidates: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
        """Объединение кандидатов с разных этапов"""
        
        merged = defaultdict(float)
        
        # Добавляем кандидатов по ключевым словам
        for cat_id, score in keyword_candidates:
            merged[cat_id] += score * 0.7  # Вес 70%
        
        # Добавляем кандидатов по n-граммам
        for cat_id, score in ngram_candidates:
            merged[cat_id] += score * 0.3  # Вес 30%
        
        return [(cat_id, score) for cat_id, score in merged.items()]
    
    def _merge_candidates_with_smart_matches(self, smart_candidates: List[Tuple[str, float]],
                                           keyword_candidates: List[Tuple[str, float]], 
                                           ngram_candidates: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
        """Объединение кандидатов с приоритетом для умных совпадений"""
        
        merged = defaultdict(float)
        
        # Приоритетные умные совпадения (максимальный вес)
        for cat_id, score in smart_candidates:
            merged[cat_id] = max(merged[cat_id], score * 1.0)  # Полный вес
        
        # Добавляем кандидатов по ключевым словам (если еще не добавлены с высоким приоритетом)
        for cat_id, score in keyword_candidates:
            if cat_id not in merged or merged[cat_id] < 0.8:
                merged[cat_id] = max(merged[cat_id], score * 0.6)
        
        # Добавляем кандидатов по n-граммам
        for cat_id, score in ngram_candidates:
            if cat_id not in merged or merged[cat_id] < 0.8:
                merged[cat_id] = max(merged[cat_id], score * 0.4)
        
        return [(cat_id, score) for cat_id, score in merged.items()]
    
    def _apply_fuzzy_filtering(self, input_category: str, 
                             candidates: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
        """Применение нечеткого сравнения к топ-кандидатам"""
        start_time = time.time()
        
        # Берем только топ-50 кандидатов для нечеткого сравнения (экономим время)
        top_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)[:50]
        
        fuzzy_results = []
        
        if PARALLEL_PROCESSING and len(top_candidates) > 10:
            # Параллельная обработка
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(self._calculate_fuzzy_similarity, input_category, cat_id): cat_id 
                    for cat_id, _ in top_candidates
                }
                
                for future in as_completed(futures):
                    cat_id = futures[future]
                    try:
                        similarity = future.result()
                        if similarity >= FUZZY_SIMILARITY_THRESHOLD:
                            # Комбинируем с предыдущим скором
                            original_score = next(score for cid, score in candidates if cid == cat_id)
                            combined_score = original_score * 0.6 + similarity * 0.4
                            fuzzy_results.append((cat_id, combined_score))
                    except Exception as e:
                        logger.warning(f"Fuzzy similarity calculation failed for {cat_id}: {e}")
        else:
            # Последовательная обработка
            for cat_id, original_score in top_candidates:
                similarity = self._calculate_fuzzy_similarity(input_category, cat_id)
                if similarity >= FUZZY_SIMILARITY_THRESHOLD:
                    combined_score = original_score * 0.6 + similarity * 0.4
                    fuzzy_results.append((cat_id, combined_score))
        
        self.stats['fuzzy_filtering_time'] += time.time() - start_time
        return fuzzy_results
    
    def _calculate_fuzzy_similarity(self, input_category: str, cat_id: str) -> float:
        """Вычисление нечеткой схожести между категориями"""
        cat_name = self.category_data[cat_id]['name']
        
        # Используем SequenceMatcher для нечеткого сравнения
        similarity = SequenceMatcher(None, input_category.lower(), cat_name.lower()).ratio()
        
        return similarity
    
    def _apply_hierarchy_bonus(self, input_category: str, 
                              candidates: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
        """Применение бонуса за иерархическое соответствие"""
        start_time = time.time()
        
        # Извлекаем потенциальные иерархические ключевые слова
        hierarchy_keywords = self._extract_hierarchy_keywords(input_category)
        
        enhanced_candidates = []
        for cat_id, score in candidates:
            hierarchy_bonus = self._calculate_hierarchy_bonus(cat_id, hierarchy_keywords)
            final_score = score + (hierarchy_bonus * HIERARCHY_BONUS_WEIGHT)
            enhanced_candidates.append((cat_id, final_score))
        
        self.stats['hierarchy_analysis_time'] += time.time() - start_time
        return enhanced_candidates
    
    def _extract_hierarchy_keywords(self, input_category: str) -> Set[str]:
        """Извлечение ключевых слов, указывающих на иерархию"""
        hierarchy_indicators = {
            'автомобильный': ['авто', 'машин', 'транспорт'],
            'мотоциклетный': ['мото', 'байк', 'motorcycle'],
            'зимний': ['зима', 'холод', 'снег'],
            'летний': ['лето', 'жара', 'солнце'],
            'детский': ['дети', 'ребенок', 'малыш'],
            'женский': ['женщин', 'дама', 'леди'],
            'мужской': ['мужчин', 'парен', 'мужик']
        }
        
        input_lower = input_category.lower()
        hierarchy_keywords = set()
        
        for base_word, synonyms in hierarchy_indicators.items():
            if base_word in input_lower:
                hierarchy_keywords.update(synonyms)
                hierarchy_keywords.add(base_word)
            
            for synonym in synonyms:
                if synonym in input_lower:
                    hierarchy_keywords.add(base_word)
                    hierarchy_keywords.update(synonyms)
        
        return hierarchy_keywords
    
    def _calculate_hierarchy_bonus(self, cat_id: str, hierarchy_keywords: Set[str]) -> float:
        """Вычисление бонуса за иерархическое соответствие"""
        if not hierarchy_keywords:
            return 0.0
        
        path_parts = self.hierarchy_index.get(cat_id, [])
        bonus = 0.0
        
        # Проверяем каждый уровень иерархии
        for part_id in path_parts:
            if part_id in self.category_data:
                part_name = self.category_data[part_id]['name'].lower()
                part_keywords = self._extract_advanced_keywords(part_name)
                
                # Бонус за совпадение в иерархии
                matches = len(hierarchy_keywords & part_keywords)
                if matches > 0:
                    bonus += matches * 0.1
        
        return min(bonus, 0.5)  # Максимальный бонус 0.5
    
    def _update_stats(self, processing_time: float, candidates_count: int):
        """Обновление статистики производительности"""
        self.stats['total_categories_processed'] += 1
        self.stats['average_candidates_per_input'] = (
            (self.stats['average_candidates_per_input'] * (self.stats['total_categories_processed'] - 1) + 
             candidates_count) / self.stats['total_categories_processed']
        )
    
    def get_performance_stats(self) -> Dict:
        """Получение статистики производительности"""
        return {
            **self.stats,
            'index_sizes': {
                'keywords': len(self.keyword_index),
                'ngrams': len(self.ngram_index),
                'categories': len(self.category_data)
            }
        }