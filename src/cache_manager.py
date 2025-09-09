import logging
import os
import json
import pickle
import hashlib
import time
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from threading import Lock
import threading
from collections import OrderedDict

from config.settings import (
    CACHE_DIRECTORY, CACHE_TTL, MEMORY_LIMIT_MB, 
    ENABLE_PERSISTENT_CACHE, INDEX_REBUILD_INTERVAL
)


logger = logging.getLogger(__name__)


class LRUCache:
    """Thread-safe LRU кеш с ограничением по размеру"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.lock = Lock()
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                # Перемещаем в конец (most recently used)
                value = self.cache.pop(key)
                self.cache[key] = value
                self.hits += 1
                return value
            else:
                self.misses += 1
                return None
    
    def put(self, key: str, value: Any):
        with self.lock:
            if key in self.cache:
                # Обновляем существующий
                self.cache.pop(key)
            elif len(self.cache) >= self.max_size:
                # Удаляем наименее используемый
                self.cache.popitem(last=False)
            
            self.cache[key] = value
    
    def clear(self):
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
    
    def stats(self) -> Dict:
        with self.lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total * 100) if total > 0 else 0
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': hit_rate
            }


class DatabaseCache:
    """Кеш на основе SQLite для persistent хранения"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock = Lock()
        self._init_database()
    
    def _init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB,
                    created_at INTEGER,
                    accessed_at INTEGER,
                    size_bytes INTEGER
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_accessed_at ON cache(accessed_at)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_created_at ON cache(created_at)
            ''')
    
    def get(self, key: str) -> Optional[Any]:
        """Получение значения из кеша"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        'SELECT value, created_at FROM cache WHERE key = ?', 
                        (key,)
                    )
                    row = cursor.fetchone()
                    
                    if row:
                        value_blob, created_at = row
                        
                        # Проверяем TTL
                        if time.time() - created_at > CACHE_TTL:
                            self._delete(key)
                            return None
                        
                        # Обновляем время доступа
                        conn.execute(
                            'UPDATE cache SET accessed_at = ? WHERE key = ?',
                            (int(time.time()), key)
                        )
                        
                        return pickle.loads(value_blob)
                    
                    return None
                    
            except Exception as e:
                logger.error(f"Database cache get error: {e}")
                return None
    
    def put(self, key: str, value: Any):
        """Сохранение значения в кеш"""
        with self.lock:
            try:
                value_blob = pickle.dumps(value)
                size_bytes = len(value_blob)
                current_time = int(time.time())
                
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute('''
                        INSERT OR REPLACE INTO cache 
                        (key, value, created_at, accessed_at, size_bytes)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (key, value_blob, current_time, current_time, size_bytes))
                    
            except Exception as e:
                logger.error(f"Database cache put error: {e}")
    
    def _delete(self, key: str):
        """Удаление записи из кеша"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM cache WHERE key = ?', (key,))
        except Exception as e:
            logger.error(f"Database cache delete error: {e}")
    
    def cleanup_expired(self):
        """Очистка просроченных записей"""
        with self.lock:
            try:
                cutoff_time = int(time.time() - CACHE_TTL)
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        'DELETE FROM cache WHERE created_at < ?', 
                        (cutoff_time,)
                    )
                    deleted_count = cursor.rowcount
                    if deleted_count > 0:
                        logger.info(f"Cleaned up {deleted_count} expired cache entries")
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
    
    def get_stats(self) -> Dict:
        """Получение статистики кеша"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT COUNT(*), SUM(size_bytes) FROM cache')
                count, total_size = cursor.fetchone()
                
                cursor = conn.execute('''
                    SELECT COUNT(*) FROM cache 
                    WHERE created_at > ?
                ''', (int(time.time() - CACHE_TTL),))
                active_count = cursor.fetchone()[0]
                
                return {
                    'total_entries': count or 0,
                    'active_entries': active_count or 0,
                    'total_size_bytes': total_size or 0,
                    'total_size_mb': (total_size or 0) / 1024 / 1024
                }
        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {'total_entries': 0, 'active_entries': 0, 'total_size_bytes': 0, 'total_size_mb': 0}
    
    def clear(self):
        """Полная очистка кеша"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute('DELETE FROM cache')
                logger.info("Database cache cleared")
            except Exception as e:
                logger.error(f"Cache clear error: {e}")


class IndexManager:
    """Менеджер индексов для быстрого поиска"""
    
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.indices = {}
        self.index_timestamps = {}
        self.lock = Lock()
    
    def build_category_index(self, categories: List[Dict]) -> Dict[str, Dict]:
        """Построение индекса категорий"""
        index_key = "category_index"
        
        with self.lock:
            # Проверяем актуальность индекса
            if self._is_index_fresh(index_key):
                return self.indices[index_key]
            
            logger.info("Building category index...")
            
            # Основной индекс по ID
            id_index = {cat['id']: cat for cat in categories}
            
            # Индекс по названиям (нормализованным)
            name_index = {}
            for cat in categories:
                normalized_name = self._normalize_text(cat['name'])
                if normalized_name not in name_index:
                    name_index[normalized_name] = []
                name_index[normalized_name].append(cat['id'])
            
            # Индекс по путям (иерархия)
            path_index = {}
            for cat in categories:
                path = cat.get('path', '')
                if path:
                    path_parts = path.split('>')
                    for part in path_parts:
                        if part not in path_index:
                            path_index[part] = []
                        path_index[part].append(cat['id'])
            
            # Индекс по ключевым словам
            keyword_index = {}
            for cat in categories:
                keywords = self._extract_keywords(cat['name'])
                for keyword in keywords:
                    if keyword not in keyword_index:
                        keyword_index[keyword] = []
                    keyword_index[keyword].append(cat['id'])
            
            index = {
                'by_id': id_index,
                'by_name': name_index,
                'by_path': path_index,
                'by_keyword': keyword_index,
                'metadata': {
                    'total_categories': len(categories),
                    'total_keywords': len(keyword_index),
                    'build_time': datetime.now().isoformat()
                }
            }
            
            self.indices[index_key] = index
            self.index_timestamps[index_key] = time.time()
            
            # Сохраняем на диск
            self._save_index_to_disk(index_key, index)
            
            logger.info(f"Category index built: {len(categories)} categories, {len(keyword_index)} keywords")
            return index
    
    def get_category_index(self) -> Optional[Dict]:
        """Получение индекса категорий"""
        return self.indices.get("category_index")
    
    def _is_index_fresh(self, index_key: str) -> bool:
        """Проверка актуальности индекса"""
        if index_key not in self.index_timestamps:
            # Пытаемся загрузить с диска
            if self._load_index_from_disk(index_key):
                return True
            return False
        
        age = time.time() - self.index_timestamps[index_key]
        return age < INDEX_REBUILD_INTERVAL
    
    def _save_index_to_disk(self, index_key: str, index: Dict):
        """Сохранение индекса на диск"""
        if not ENABLE_PERSISTENT_CACHE:
            return
        
        try:
            index_file = os.path.join(self.cache_dir, f"{index_key}.pkl")
            with open(index_file, 'wb') as f:
                pickle.dump(index, f)
        except Exception as e:
            logger.error(f"Failed to save index to disk: {e}")
    
    def _load_index_from_disk(self, index_key: str) -> bool:
        """Загрузка индекса с диска"""
        if not ENABLE_PERSISTENT_CACHE:
            return False
        
        try:
            index_file = os.path.join(self.cache_dir, f"{index_key}.pkl")
            if os.path.exists(index_file):
                # Проверяем возраст файла
                file_age = time.time() - os.path.getmtime(index_file)
                if file_age > INDEX_REBUILD_INTERVAL:
                    os.remove(index_file)
                    return False
                
                with open(index_file, 'rb') as f:
                    index = pickle.load(f)
                
                self.indices[index_key] = index
                self.index_timestamps[index_key] = os.path.getmtime(index_file)
                
                logger.info(f"Index '{index_key}' loaded from disk")
                return True
        except Exception as e:
            logger.error(f"Failed to load index from disk: {e}")
        
        return False
    
    def _normalize_text(self, text: str) -> str:
        """Нормализация текста для индексирования"""
        import re
        # Приводим к нижнему регистру и удаляем лишние символы
        normalized = re.sub(r'[^\w\s]', ' ', text.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Извлечение ключевых слов из текста"""
        normalized = self._normalize_text(text)
        words = normalized.split()
        
        # Фильтруем стоп-слова и короткие слова
        stop_words = {'и', 'или', 'для', 'в', 'на', 'с', 'по', 'от', 'к', 'из'}
        keywords = [word for word in words if len(word) > 2 and word not in stop_words]
        
        return keywords
    
    def clear_indices(self):
        """Очистка всех индексов"""
        with self.lock:
            self.indices.clear()
            self.index_timestamps.clear()
            
            # Удаляем файлы с диска
            if ENABLE_PERSISTENT_CACHE and os.path.exists(self.cache_dir):
                for file in os.listdir(self.cache_dir):
                    if file.endswith('_index.pkl'):
                        try:
                            os.remove(os.path.join(self.cache_dir, file))
                        except Exception as e:
                            logger.warning(f"Failed to remove index file {file}: {e}")
            
            logger.info("All indices cleared")


class CacheManager:
    """Центральный менеджер кеширования"""
    
    def __init__(self, cache_dir: str = CACHE_DIRECTORY):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # Инициализируем компоненты
        self.memory_cache = LRUCache(max_size=1000)
        self.db_cache = DatabaseCache(os.path.join(cache_dir, 'cache.db')) if ENABLE_PERSISTENT_CACHE else None
        self.index_manager = IndexManager(cache_dir)
        
        # Запускаем фоновую очистку
        self._start_cleanup_thread()
    
    def get(self, key: str) -> Optional[Any]:
        """Получение значения из кеша (многоуровневый)"""
        # Сначала проверяем memory кеш
        value = self.memory_cache.get(key)
        if value is not None:
            return value
        
        # Затем database кеш
        if self.db_cache:
            value = self.db_cache.get(key)
            if value is not None:
                # Сохраняем в memory кеш для быстрого доступа
                self.memory_cache.put(key, value)
                return value
        
        return None
    
    def put(self, key: str, value: Any):
        """Сохранение значения в кеш (многоуровневый)"""
        # Сохраняем в memory кеш
        self.memory_cache.put(key, value)
        
        # Сохраняем в database кеш
        if self.db_cache:
            self.db_cache.put(key, value)
    
    def build_category_index(self, categories: List[Dict]) -> Dict:
        """Построение индекса категорий"""
        return self.index_manager.build_category_index(categories)
    
    def get_category_index(self) -> Optional[Dict]:
        """Получение индекса категорий"""
        return self.index_manager.get_category_index()
    
    def get_stats(self) -> Dict:
        """Получение статистики кеширования"""
        stats = {
            'memory_cache': self.memory_cache.stats(),
            'indices': {
                'count': len(self.index_manager.indices),
                'keys': list(self.index_manager.indices.keys())
            }
        }
        
        if self.db_cache:
            stats['database_cache'] = self.db_cache.get_stats()
        
        return stats
    
    def clear_all(self):
        """Полная очистка всех кешей"""
        self.memory_cache.clear()
        if self.db_cache:
            self.db_cache.clear()
        self.index_manager.clear_indices()
        logger.info("All caches cleared")
    
    def _start_cleanup_thread(self):
        """Запуск фонового потока очистки"""
        self._cleanup_stop_event = threading.Event()
        
        def cleanup_worker():
            while not self._cleanup_stop_event.is_set():
                try:
                    if self.db_cache:
                        self.db_cache.cleanup_expired()
                    # Ждем час или до получения сигнала остановки
                    self._cleanup_stop_event.wait(3600)
                except Exception as e:
                    logger.error(f"Cleanup thread error: {e}")
                    self._cleanup_stop_event.wait(60)
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        self._cleanup_thread = cleanup_thread
    
    def stop_cleanup_thread(self):
        """Остановка фонового потока очистки"""
        if hasattr(self, '_cleanup_stop_event'):
            self._cleanup_stop_event.set()
            if hasattr(self, '_cleanup_thread'):
                self._cleanup_thread.join(timeout=1.0)
    
    def generate_key(self, *args) -> str:
        """Генерация ключа кеша из аргументов"""
        content = json.dumps(args, sort_keys=True, default=str)
        return hashlib.md5(content.encode()).hexdigest()