import logging
import time
import psutil
import threading
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from collections import deque, defaultdict
from dataclasses import dataclass, field
import json
import os

from config.settings import LOG_FILE, CACHE_DIRECTORY


logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Метрика производительности"""
    name: str
    value: float
    timestamp: datetime
    unit: str = ""
    category: str = "general"
    metadata: Dict = field(default_factory=dict)


@dataclass
class ProcessingStats:
    """Статистика обработки"""
    total_categories: int = 0
    processed_categories: int = 0
    matched_categories: int = 0
    api_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    processing_time: float = 0.0
    api_time: float = 0.0
    filtering_time: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class PerformanceMonitor:
    """Монитор производительности системы"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics_history = deque(maxlen=max_history)
        self.current_session = ProcessingStats()
        self.session_history = deque(maxlen=100)  # Последние 100 сессий
        
        # Метрики системы
        self.system_metrics = {
            'cpu_usage': deque(maxlen=60),  # Последние 60 измерений
            'memory_usage': deque(maxlen=60),
            'api_response_times': deque(maxlen=100),
            'processing_speeds': deque(maxlen=50)
        }
        
        # Пороги для алертов
        self.alert_thresholds = {
            'cpu_usage': 80.0,      # %
            'memory_usage': 85.0,   # %
            'api_response_time': 30.0,  # секунд
            'error_rate': 5.0       # %
        }
        
        # Коллбеки для алертов
        self.alert_callbacks = []
        
        # Блокировка для thread-safety
        self.lock = threading.Lock()
        
        # Запускаем мониторинг системы
        self.start_system_monitoring()
    
    def start_session(self, total_categories: int):
        """Начало новой сессии обработки"""
        with self.lock:
            self.current_session = ProcessingStats(
                total_categories=total_categories,
                start_time=datetime.now()
            )
            logger.info(f"Performance monitoring started for {total_categories} categories")
    
    def end_session(self):
        """Завершение сессии обработки"""
        with self.lock:
            if self.current_session.start_time:
                self.current_session.end_time = datetime.now()
                self.current_session.processing_time = (
                    self.current_session.end_time - self.current_session.start_time
                ).total_seconds()
                
                # Сохраняем сессию в историю
                self.session_history.append(self.current_session)
                
                # Логируем итоговую статистику
                self._log_session_summary()
    
    def record_metric(self, name: str, value: float, unit: str = "", 
                     category: str = "general", metadata: Dict = None):
        """Запись метрики производительности"""
        metric = PerformanceMetric(
            name=name,
            value=value,
            timestamp=datetime.now(),
            unit=unit,
            category=category,
            metadata=metadata or {}
        )
        
        with self.lock:
            self.metrics_history.append(metric)
            
            # Проверяем пороги для алертов
            self._check_alert_thresholds(metric)
    
    def update_processing_stats(self, **kwargs):
        """Обновление статистики текущей сессии"""
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self.current_session, key):
                    setattr(self.current_session, key, value)
    
    def record_api_call(self, response_time: float, success: bool = True):
        """Запись API вызова"""
        with self.lock:
            self.current_session.api_calls += 1
            self.current_session.api_time += response_time
            self.system_metrics['api_response_times'].append(response_time)
            
            if not success:
                self.record_metric("api_error", 1, category="errors")
    
    def record_cache_hit(self):
        """Запись попадания в кеш"""
        with self.lock:
            self.current_session.cache_hits += 1
    
    def record_cache_miss(self):
        """Запись промаха кеша"""
        with self.lock:
            self.current_session.cache_misses += 1
    
    def record_category_processed(self, matched: bool = False):
        """Запись обработки категории"""
        with self.lock:
            self.current_session.processed_categories += 1
            if matched:
                self.current_session.matched_categories += 1
    
    def record_filtering_time(self, time_seconds: float):
        """Запись времени фильтрации"""
        with self.lock:
            self.current_session.filtering_time += time_seconds
    
    def get_current_stats(self) -> Dict:
        """Получение текущей статистики"""
        with self.lock:
            stats = {
                'session': {
                    'total_categories': self.current_session.total_categories,
                    'processed_categories': self.current_session.processed_categories,
                    'matched_categories': self.current_session.matched_categories,
                    'match_rate': (self.current_session.matched_categories / 
                                 max(1, self.current_session.processed_categories) * 100),
                    'api_calls': self.current_session.api_calls,
                    'cache_hits': self.current_session.cache_hits,
                    'cache_misses': self.current_session.cache_misses,
                    'cache_hit_rate': (self.current_session.cache_hits / 
                                     max(1, self.current_session.cache_hits + self.current_session.cache_misses) * 100),
                    'processing_time': self.current_session.processing_time,
                    'api_time': self.current_session.api_time,
                    'filtering_time': self.current_session.filtering_time
                },
                'system': self._get_current_system_metrics(),
                'performance': self._get_performance_metrics()
            }
            
            # Добавляем скорость обработки
            if (self.current_session.processing_time > 0 and 
                self.current_session.processed_categories > 0):
                stats['session']['processing_speed'] = (
                    self.current_session.processed_categories / 
                    self.current_session.processing_time
                )
            
            return stats
    
    def get_historical_stats(self, last_n_sessions: int = 10) -> Dict:
        """Получение исторической статистики"""
        with self.lock:
            recent_sessions = list(self.session_history)[-last_n_sessions:]
            
            if not recent_sessions:
                return {'sessions': 0}
            
            # Агрегированная статистика
            total_categories = sum(s.total_categories for s in recent_sessions)
            total_processed = sum(s.processed_categories for s in recent_sessions)
            total_matched = sum(s.matched_categories for s in recent_sessions)
            total_api_calls = sum(s.api_calls for s in recent_sessions)
            total_time = sum(s.processing_time for s in recent_sessions)
            
            avg_match_rate = (total_matched / max(1, total_processed)) * 100
            avg_processing_speed = total_processed / max(1, total_time)
            
            return {
                'sessions': len(recent_sessions),
                'timerange': {
                    'start': recent_sessions[0].start_time.isoformat() if recent_sessions[0].start_time else None,
                    'end': recent_sessions[-1].end_time.isoformat() if recent_sessions[-1].end_time else None
                },
                'totals': {
                    'categories': total_categories,
                    'processed': total_processed,
                    'matched': total_matched,
                    'api_calls': total_api_calls,
                    'processing_time': total_time
                },
                'averages': {
                    'match_rate': avg_match_rate,
                    'processing_speed': avg_processing_speed,
                    'categories_per_session': total_categories / len(recent_sessions),
                    'api_calls_per_session': total_api_calls / len(recent_sessions)
                }
            }
    
    def _get_current_system_metrics(self) -> Dict:
        """Получение текущих системных метрик"""
        try:
            process = psutil.Process()
            
            return {
                'cpu_usage': psutil.cpu_percent(interval=0.1),
                'memory_usage': {
                    'rss_mb': process.memory_info().rss / 1024 / 1024,
                    'vms_mb': process.memory_info().vms / 1024 / 1024,
                    'percent': process.memory_percent()
                },
                'disk_usage': {
                    path: {
                        'total_gb': usage.total / 1024**3,
                        'free_gb': usage.free / 1024**3,
                        'used_percent': (usage.total - usage.free) / usage.total * 100
                    }
                    for path in [CACHE_DIRECTORY, os.path.dirname(LOG_FILE)]
                    if os.path.exists(path)
                    for usage in [psutil.disk_usage(path)]
                },
                'threads': threading.active_count()
            }
        except Exception as e:
            logger.warning(f"Failed to get system metrics: {e}")
            return {}
    
    def _get_performance_metrics(self) -> Dict:
        """Получение метрик производительности"""
        metrics = {}
        
        # API response times
        if self.system_metrics['api_response_times']:
            api_times = list(self.system_metrics['api_response_times'])
            metrics['api_response_time'] = {
                'avg': sum(api_times) / len(api_times),
                'min': min(api_times),
                'max': max(api_times),
                'count': len(api_times)
            }
        
        # Processing speeds
        if self.system_metrics['processing_speeds']:
            speeds = list(self.system_metrics['processing_speeds'])
            metrics['processing_speed'] = {
                'avg': sum(speeds) / len(speeds),
                'min': min(speeds),
                'max': max(speeds),
                'count': len(speeds)
            }
        
        return metrics
    
    def start_system_monitoring(self):
        """Запуск мониторинга системных ресурсов"""
        self._monitor_stop_event = threading.Event()
        
        def monitor_worker():
            while not self._monitor_stop_event.is_set():
                try:
                    cpu_usage = psutil.cpu_percent(interval=0.1)  # Быстрее для отзывчивости
                    memory_usage = psutil.virtual_memory().percent
                    
                    with self.lock:
                        self.system_metrics['cpu_usage'].append(cpu_usage)
                        self.system_metrics['memory_usage'].append(memory_usage)
                    
                    # Проверяем пороги
                    if cpu_usage > self.alert_thresholds['cpu_usage']:
                        self._trigger_alert('cpu_usage', cpu_usage, 'High CPU usage detected')
                    
                    if memory_usage > self.alert_thresholds['memory_usage']:
                        self._trigger_alert('memory_usage', memory_usage, 'High memory usage detected')
                    
                    # Ждем 60 секунд или до получения сигнала остановки
                    self._monitor_stop_event.wait(60)
                    
                except Exception as e:
                    logger.error(f"System monitoring error: {e}")
                    self._monitor_stop_event.wait(10)
        
        monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
        monitor_thread.start()
        self._monitor_thread = monitor_thread
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        if hasattr(self, '_monitor_stop_event'):
            self._monitor_stop_event.set()
            if hasattr(self, '_monitor_thread'):
                self._monitor_thread.join(timeout=1.0)
    
    def _check_alert_thresholds(self, metric: PerformanceMetric):
        """Проверка порогов для алертов"""
        threshold_key = metric.name.lower().replace(' ', '_')
        
        if threshold_key in self.alert_thresholds:
            threshold = self.alert_thresholds[threshold_key]
            if metric.value > threshold:
                message = f"Metric '{metric.name}' exceeded threshold: {metric.value} > {threshold}"
                self._trigger_alert(threshold_key, metric.value, message)
    
    def _trigger_alert(self, alert_type: str, value: float, message: str):
        """Запуск алерта"""
        alert_data = {
            'type': alert_type,
            'value': value,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.warning(f"ALERT: {message}")
        
        # Вызываем зарегистрированные коллбеки
        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
    
    def add_alert_callback(self, callback: Callable[[Dict], None]):
        """Добавление коллбека для алертов"""
        self.alert_callbacks.append(callback)
    
    def set_alert_threshold(self, metric_name: str, threshold: float):
        """Установка порога для алерта"""
        self.alert_thresholds[metric_name] = threshold
        logger.info(f"Alert threshold set: {metric_name} = {threshold}")
    
    def export_metrics(self, filepath: str):
        """Экспорт метрик в файл"""
        try:
            with self.lock:
                export_data = {
                    'export_time': datetime.now().isoformat(),
                    'current_session': {
                        'total_categories': self.current_session.total_categories,
                        'processed_categories': self.current_session.processed_categories,
                        'matched_categories': self.current_session.matched_categories,
                        'api_calls': self.current_session.api_calls,
                        'cache_hits': self.current_session.cache_hits,
                        'cache_misses': self.current_session.cache_misses,
                        'processing_time': self.current_session.processing_time,
                        'start_time': self.current_session.start_time.isoformat() if self.current_session.start_time else None
                    },
                    'recent_metrics': [
                        {
                            'name': m.name,
                            'value': m.value,
                            'timestamp': m.timestamp.isoformat(),
                            'unit': m.unit,
                            'category': m.category,
                            'metadata': m.metadata
                        }
                        for m in list(self.metrics_history)[-100:]  # Последние 100 метрик
                    ],
                    'system_metrics': {
                        'cpu_usage': list(self.system_metrics['cpu_usage']),
                        'memory_usage': list(self.system_metrics['memory_usage']),
                        'api_response_times': list(self.system_metrics['api_response_times'])
                    },
                    'historical_stats': self.get_historical_stats()
                }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Metrics exported to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
    
    def _log_session_summary(self):
        """Логирование итогов сессии"""
        stats = self.get_current_stats()
        session = stats['session']
        
        logger.info("=== SESSION SUMMARY ===")
        logger.info(f"Categories processed: {session['processed_categories']}/{session['total_categories']}")
        logger.info(f"Match rate: {session['match_rate']:.1f}%")
        logger.info(f"API calls: {session['api_calls']}")
        logger.info(f"Cache hit rate: {session['cache_hit_rate']:.1f}%")
        logger.info(f"Processing time: {session['processing_time']:.2f}s")
        
        if 'processing_speed' in session:
            logger.info(f"Processing speed: {session['processing_speed']:.2f} categories/sec")
        
        logger.info("========================")
    
    def get_recommendations(self) -> List[str]:
        """Получение рекомендаций по оптимизации"""
        recommendations = []
        stats = self.get_current_stats()
        
        # Рекомендации по производительности
        if 'processing_speed' in stats['session'] and stats['session']['processing_speed'] < 1.0:
            recommendations.append("Consider enabling parallel processing or increasing batch size")
        
        # Рекомендации по кешу
        if stats['session']['cache_hit_rate'] < 30:
            recommendations.append("Low cache hit rate. Consider enabling persistent cache or increasing cache TTL")
        
        # Рекомендации по API использованию
        if 'api_response_time' in stats['performance']:
            avg_api_time = stats['performance']['api_response_time']['avg']
            if avg_api_time > 10.0:
                recommendations.append("High API response times. Consider reducing batch size or implementing retry logic")
        
        # Рекомендации по системным ресурсам
        if stats['system'].get('memory_usage', {}).get('percent', 0) > 80:
            recommendations.append("High memory usage. Consider reducing cache size or processing data in smaller chunks")
        
        return recommendations


# Глобальный инстанс монитора
performance_monitor = PerformanceMonitor()


def monitor_performance(func):
    """Декоратор для мониторинга производительности функций"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            performance_monitor.record_metric(
                f"{func.__name__}_execution_time",
                execution_time,
                "seconds",
                "functions"
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            performance_monitor.record_metric(
                f"{func.__name__}_error",
                1,
                "count",
                "errors",
                {"error": str(e), "execution_time": execution_time}
            )
            raise
    return wrapper