import logging
import pickle
import os
from typing import List, Dict, Tuple, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import joblib
from datetime import datetime, timedelta

from config.settings import (
    VECTOR_TOP_K, MIN_VECTOR_SIMILARITY, CACHE_DIRECTORY,
    ENABLE_PERSISTENT_CACHE, INDEX_REBUILD_INTERVAL
)


logger = logging.getLogger(__name__)


class VectorizedCategorySearch:
    """Векторизованный поиск категорий с использованием TF-IDF и косинусного сходства"""
    
    def __init__(self, cache_dir: str = CACHE_DIRECTORY):
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.category_vectors: Optional[np.ndarray] = None
        self.categories: List[Dict] = []
        self.cache_dir = cache_dir
        
        # Создаем директорию для кеша
        if ENABLE_PERSISTENT_CACHE:
            os.makedirs(cache_dir, exist_ok=True)
        
        # Пути к кешированным файлам
        self.vectorizer_path = os.path.join(cache_dir, 'tfidf_vectorizer.pkl')
        self.vectors_path = os.path.join(cache_dir, 'category_vectors.pkl')
        self.categories_path = os.path.join(cache_dir, 'categories_data.pkl')
        self.metadata_path = os.path.join(cache_dir, 'vector_metadata.pkl')
    
    def build_vector_index(self, categories: List[Dict], force_rebuild: bool = False):
        """Построение векторного индекса с кешированием"""
        
        if not force_rebuild and self._load_from_cache():
            logger.info("Vector index loaded from cache")
            return
        
        start_time = datetime.now()
        logger.info(f"Building vector index for {len(categories)} categories")
        
        self.categories = categories
        
        # Подготавливаем тексты для векторизации
        texts = self._prepare_texts(categories)
        
        # Создаем TF-IDF векторизатор с оптимальными параметрами
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 3),           # Униграммы, биграммы и триграммы
            max_features=10000,           # Максимум 10k признаков
            min_df=1,                     # Минимум в 1 документе
            max_df=0.95,                  # Максимум в 95% документов
            stop_words=None,              # Не используем стандартные стоп-слова
            lowercase=True,
            token_pattern=r'\b\w+\b',     # Только слова
            sublinear_tf=True,            # Логарифмическое масштабирование TF
            norm='l2'                     # L2 нормализация
        )
        
        # Обучаем векторизатор и создаем векторы
        logger.info("Training TF-IDF vectorizer...")
        self.category_vectors = self.vectorizer.fit_transform(texts)
        
        # Сохраняем в кеш
        if ENABLE_PERSISTENT_CACHE:
            self._save_to_cache()
        
        build_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Vector index built in {build_time:.2f}s")
        logger.info(f"Vector dimensions: {self.category_vectors.shape}")
        logger.info(f"Vocabulary size: {len(self.vectorizer.vocabulary_)}")
    
    def find_similar_categories(self, input_category: str, 
                              top_k: int = VECTOR_TOP_K) -> List[Tuple[Dict, float]]:
        """Поиск наиболее похожих категорий с помощью векторного сходства"""
        
        if self.vectorizer is None or self.category_vectors is None:
            logger.warning("Vector index not built. Call build_vector_index() first.")
            return []
        
        # Векторизуем входную категорию
        input_text = self._prepare_single_text(input_category)
        input_vector = self.vectorizer.transform([input_text])
        
        # Вычисляем косинусное сходство со всеми категориями
        similarities = cosine_similarity(input_vector, self.category_vectors)[0]
        
        # Находим топ-K наиболее похожих
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        # Фильтруем по минимальному порогу сходства
        results = []
        for idx in top_indices:
            similarity = similarities[idx]
            if similarity >= MIN_VECTOR_SIMILARITY:
                category = self.categories[idx]
                results.append((category, float(similarity)))
        
        logger.debug(f"Vector search found {len(results)} candidates for '{input_category}'")
        return results
    
    def batch_find_similar(self, input_categories: List[str], 
                          top_k: int = VECTOR_TOP_K) -> List[List[Tuple[Dict, float]]]:
        """Батчевый поиск похожих категорий для повышения производительности"""
        
        if self.vectorizer is None or self.category_vectors is None:
            logger.warning("Vector index not built. Call build_vector_index() first.")
            return [[] for _ in input_categories]
        
        # Векторизуем все входные категории сразу
        input_texts = [self._prepare_single_text(cat) for cat in input_categories]
        input_vectors = self.vectorizer.transform(input_texts)
        
        # Вычисляем сходство для всех пар
        similarities_matrix = cosine_similarity(input_vectors, self.category_vectors)
        
        # Обрабатываем результаты для каждой входной категории
        all_results = []
        for i, input_category in enumerate(input_categories):
            similarities = similarities_matrix[i]
            
            # Топ-K для текущей категории
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            results = []
            for idx in top_indices:
                similarity = similarities[idx]
                if similarity >= MIN_VECTOR_SIMILARITY:
                    category = self.categories[idx]
                    results.append((category, float(similarity)))
            
            all_results.append(results)
        
        return all_results
    
    def _prepare_texts(self, categories: List[Dict]) -> List[str]:
        """Подготовка текстов категорий для векторизации"""
        texts = []
        for category in categories:
            text = self._prepare_single_text(category['name'])
            texts.append(text)
        return texts
    
    def _prepare_single_text(self, category_name: str) -> str:
        """Подготовка одного текста для векторизации"""
        # Нормализация и очистка
        text = category_name.lower()
        
        # Удаляем лишние пробелы и символы
        import re
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _save_to_cache(self):
        """Сохранение индекса в кеш"""
        try:
            # Сохраняем векторизатор
            joblib.dump(self.vectorizer, self.vectorizer_path)
            
            # Сохраняем векторы (используем scipy sparse format)
            with open(self.vectors_path, 'wb') as f:
                pickle.dump(self.category_vectors, f)
            
            # Сохраняем данные категорий
            with open(self.categories_path, 'wb') as f:
                pickle.dump(self.categories, f)
            
            # Сохраняем метаданные
            metadata = {
                'created_at': datetime.now(),
                'categories_count': len(self.categories),
                'vector_dimensions': self.category_vectors.shape,
                'vocabulary_size': len(self.vectorizer.vocabulary_)
            }
            with open(self.metadata_path, 'wb') as f:
                pickle.dump(metadata, f)
            
            logger.info("Vector index saved to cache")
            
        except Exception as e:
            logger.error(f"Failed to save vector index to cache: {e}")
    
    def _load_from_cache(self) -> bool:
        """Загрузка индекса из кеша"""
        try:
            # Проверяем существование всех файлов
            required_files = [
                self.vectorizer_path, self.vectors_path, 
                self.categories_path, self.metadata_path
            ]
            
            if not all(os.path.exists(path) for path in required_files):
                return False
            
            # Проверяем, не истек ли кеш
            with open(self.metadata_path, 'rb') as f:
                metadata = pickle.load(f)
            
            cache_age = datetime.now() - metadata['created_at']
            if cache_age.total_seconds() > INDEX_REBUILD_INTERVAL:
                logger.info("Vector index cache expired, rebuilding...")
                return False
            
            # Загружаем данные
            self.vectorizer = joblib.load(self.vectorizer_path)
            
            with open(self.vectors_path, 'rb') as f:
                self.category_vectors = pickle.load(f)
            
            with open(self.categories_path, 'rb') as f:
                self.categories = pickle.load(f)
            
            logger.info(f"Vector index loaded from cache ({metadata['categories_count']} categories)")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load vector index from cache: {e}")
            return False
    
    def clear_cache(self):
        """Очистка кеша векторного индекса"""
        cache_files = [
            self.vectorizer_path, self.vectors_path,
            self.categories_path, self.metadata_path
        ]
        
        for cache_file in cache_files:
            try:
                if os.path.exists(cache_file):
                    os.remove(cache_file)
            except Exception as e:
                logger.warning(f"Failed to remove cache file {cache_file}: {e}")
        
        logger.info("Vector index cache cleared")
    
    def get_index_info(self) -> Dict:
        """Получение информации о векторном индексе"""
        if self.vectorizer is None or self.category_vectors is None:
            return {'status': 'not_built'}
        
        return {
            'status': 'ready',
            'categories_count': len(self.categories),
            'vector_dimensions': self.category_vectors.shape,
            'vocabulary_size': len(self.vectorizer.vocabulary_),
            'cache_enabled': ENABLE_PERSISTENT_CACHE,
            'top_k': VECTOR_TOP_K,
            'min_similarity': MIN_VECTOR_SIMILARITY
        }
    
    def update_similarity_threshold(self, threshold: float):
        """Обновление порога минимального сходства"""
        if 0.0 <= threshold <= 1.0:
            global MIN_VECTOR_SIMILARITY
            MIN_VECTOR_SIMILARITY = threshold
            logger.info(f"Vector similarity threshold updated to {threshold}")
        else:
            raise ValueError("Similarity threshold must be between 0.0 and 1.0")


class HybridVectorSearch(VectorizedCategorySearch):
    """Гибридный поиск, комбинирующий векторное сходство с другими метриками"""
    
    def __init__(self, cache_dir: str = CACHE_DIRECTORY):
        super().__init__(cache_dir)
        self.keyword_weights = {}  # Веса для ключевых слов
    
    def find_similar_hybrid(self, input_category: str, 
                          keyword_matches: List[Tuple[Dict, float]] = None,
                          top_k: int = VECTOR_TOP_K) -> List[Tuple[Dict, float]]:
        """Гибридный поиск, комбинирующий векторное сходство с ключевыми словами"""
        
        # Получаем векторные совпадения
        vector_matches = self.find_similar_categories(input_category, top_k * 2)
        
        if not keyword_matches:
            return vector_matches
        
        # Создаем индекс векторных совпадений
        vector_scores = {cat['id']: score for cat, score in vector_matches}
        
        # Комбинируем результаты
        combined_results = {}
        
        # Добавляем совпадения по ключевым словам
        for category, keyword_score in keyword_matches:
            cat_id = category['id']
            vector_score = vector_scores.get(cat_id, 0.0)
            
            # Комбинированный скор (60% векторное сходство, 40% ключевые слова)
            combined_score = vector_score * 0.6 + keyword_score * 0.4
            combined_results[cat_id] = (category, combined_score)
        
        # Добавляем чисто векторные совпадения, которых нет в ключевых словах
        for category, vector_score in vector_matches:
            cat_id = category['id']
            if cat_id not in combined_results:
                # Небольшой штраф за отсутствие ключевых слов
                combined_score = vector_score * 0.8
                combined_results[cat_id] = (category, combined_score)
        
        # Сортируем по комбинированному скору
        final_results = list(combined_results.values())
        final_results.sort(key=lambda x: x[1], reverse=True)
        
        return final_results[:top_k]