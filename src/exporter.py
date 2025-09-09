import json
import logging
from datetime import datetime
from typing import List, Dict, Optional
from config.settings import OUTPUT_FORMAT, CONFIDENCE_THRESHOLD


logger = logging.getLogger(__name__)


class ResultExporter:
    """Экспорт результатов сопоставления в различные форматы"""
    
    def __init__(self, confidence_threshold: float = CONFIDENCE_THRESHOLD):
        self.confidence_threshold = confidence_threshold
    
    def export_results(self, matches: List[Dict], input_categories: List[Dict], 
                      reference_categories: List[Dict], output_file: str,
                      processing_start_time: datetime, api_requests_count: int = 0) -> Dict:
        """Экспорт результатов в файл с полной статистикой"""
        
        # Анализируем результаты
        analysis = self._analyze_matches(matches, input_categories)
        
        # Формируем финальную структуру
        result_data = {
            "processed_at": datetime.now().isoformat(),
            "total_input": len(input_categories),
            "total_matched": analysis['matched_count'],
            "total_unmatched": analysis['unmatched_count'],
            "matches": analysis['matches'],
            "unmatched": analysis['unmatched'],
            "statistics": {
                "high_confidence": analysis['high_confidence_count'],
                "medium_confidence": analysis['medium_confidence_count'], 
                "low_confidence": analysis['low_confidence_count'],
                "api_requests": api_requests_count,
                "processing_time": self._format_duration(datetime.now() - processing_start_time),
                "confidence_threshold": self.confidence_threshold,
                "reference_categories_count": len(reference_categories)
            }
        }
        
        # Экспортируем в файл
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Results exported to {output_file}")
            logger.info(f"Matched: {analysis['matched_count']}/{len(input_categories)} "
                       f"({analysis['matched_count']/len(input_categories)*100:.1f}%)")
            
            return result_data
            
        except Exception as e:
            logger.error(f"Failed to export results: {e}")
            raise
    
    def _analyze_matches(self, matches: List[Dict], input_categories: List[Dict]) -> Dict:
        """Анализ результатов сопоставления"""
        
        # Создаем словарь входных категорий для быстрого поиска
        input_names = {cat['name'] for cat in input_categories}
        
        # Разделяем на matched и unmatched
        matched = []
        unmatched = []
        matched_names = set()
        
        # Счетчики по уровням уверенности
        high_confidence = 0  # >= 0.8
        medium_confidence = 0  # >= 0.5 and < 0.8
        low_confidence = 0  # < 0.5
        
        for match in matches:
            if (match.get('match_id') and 
                match.get('match_id') != 'null' and 
                match.get('match_id') is not None):
                
                # Форматируем matched запись
                confidence = float(match.get('confidence', 0.0))
                
                # Пропускаем совпадения с низкой уверенностью
                if confidence < self.confidence_threshold:
                    continue
                
                matched_entry = {
                    "input_name": match['input_name'],
                    "match_id": match['match_id'],
                    "match_name": match.get('match_name', ''),
                    "match_path": match.get('match_path', ''),
                    "confidence": confidence,
                    "reasoning": match.get('reasoning', '')
                }
                matched.append(matched_entry)
                matched_names.add(match['input_name'])
                
                # Подсчитываем уровни уверенности
                if confidence >= 0.8:
                    high_confidence += 1
                elif confidence >= 0.5:
                    medium_confidence += 1
                else:
                    low_confidence += 1
        
        # Находим несопоставленные категории
        for cat in input_categories:
            if cat['name'] not in matched_names:
                unmatched_entry = {
                    "input_name": cat['name'],
                    "reasoning": "Не найдено подходящего соответствия в справочнике"
                }
                unmatched.append(unmatched_entry)
        
        return {
            'matches': matched,
            'unmatched': unmatched,
            'matched_count': len(matched),
            'unmatched_count': len(unmatched),
            'high_confidence_count': high_confidence,
            'medium_confidence_count': medium_confidence,
            'low_confidence_count': low_confidence
        }
    
    def _format_duration(self, duration) -> str:
        """Форматирование длительности обработки"""
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def export_summary(self, result_data: Dict, summary_file: Optional[str] = None) -> str:
        """Экспорт краткой сводки результатов"""
        
        stats = result_data['statistics']
        summary = f"""
=== СВОДКА РЕЗУЛЬТАТОВ СОПОСТАВЛЕНИЯ ===

Обработано: {result_data['processed_at']}
Время обработки: {stats['processing_time']}

СТАТИСТИКА:
- Входных категорий: {result_data['total_input']}
- Сопоставлено: {result_data['total_matched']} ({result_data['total_matched']/result_data['total_input']*100:.1f}%)
- Не сопоставлено: {result_data['total_unmatched']} ({result_data['total_unmatched']/result_data['total_input']*100:.1f}%)

УРОВНИ УВЕРЕННОСТИ:
- Высокая (≥0.8): {stats['high_confidence']}
- Средняя (≥0.5): {stats['medium_confidence']}
- Низкая (<0.5): {stats['low_confidence']}

API ЗАПРОСЫ: {stats['api_requests']}
ПОРОГ УВЕРЕННОСТИ: {stats['confidence_threshold']}
СПРАВОЧНЫХ КАТЕГОРИЙ: {stats['reference_categories_count']}
        """.strip()
        
        if summary_file:
            try:
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write(summary)
                logger.info(f"Summary exported to {summary_file}")
            except Exception as e:
                logger.error(f"Failed to export summary: {e}")
        
        return summary
    
    def export_unmatched_only(self, result_data: Dict, unmatched_file: str):
        """Экспорт только несопоставленных категорий для дальнейшего анализа"""
        try:
            unmatched_data = {
                "processed_at": result_data['processed_at'],
                "total_unmatched": result_data['total_unmatched'],
                "confidence_threshold": result_data['statistics']['confidence_threshold'],
                "unmatched": result_data['unmatched']
            }
            
            with open(unmatched_file, 'w', encoding='utf-8') as f:
                json.dump(unmatched_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Unmatched categories exported to {unmatched_file}")
            
        except Exception as e:
            logger.error(f"Failed to export unmatched categories: {e}")
            raise