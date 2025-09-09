"""
Иерархический матчер с оптимизацией расходов на AI
Использует контекст пути для точного сопоставления категорий
"""

import logging
import asyncio
import json
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict
from datetime import datetime

from .hierarchical_processor import HierarchicalProcessor, CategoryNode
from .claude_client import ClaudeAPIClient
from .performance_monitor import monitor_performance, performance_monitor

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Результат сопоставления категории"""
    input_id: str
    input_name: str
    input_path: str
    input_full_path: str
    match_id: Optional[str] = None
    match_name: Optional[str] = None
    match_path: Optional[str] = None
    match_full_path: Optional[str] = None
    confidence: float = 0.0
    reasoning: str = ""
    match_method: str = ""  # 'exact', 'ai', 'fuzzy', 'none'


class HierarchicalMatcher:
    """Главный класс для иерархического сопоставления категорий"""
    
    def __init__(self, api_key: str, batch_size: int = 15):
        self.processor = HierarchicalProcessor()
        self.claude_client = ClaudeAPIClient(api_key)
        self.batch_size = batch_size
        
        # Статистика
        self.stats = {
            'total_input_categories': 0,
            'exact_matches': 0,
            'ai_matches': 0,
            'no_matches': 0,
            'api_calls': 0,
            'processing_time': 0
        }
    
    @monitor_performance
    def load_data(self, reference_file: str, input_file: str) -> None:
        """Загружает reference и input файлы"""
        logger.info("Loading hierarchical category data")
        
        self.processor.load_reference_categories(reference_file)
        self.processor.load_input_categories(input_file)
        
        self.stats['total_input_categories'] = len(self.processor.input_leaf_nodes)
        
        logger.info(f"Data loaded: {len(self.processor.reference_leaf_nodes)} reference leaves, "
                   f"{len(self.processor.input_leaf_nodes)} input leaves")
    
    async def match_categories(self) -> List[MatchResult]:
        """Основной метод сопоставления категорий"""
        logger.info("Starting hierarchical category matching")
        
        results = []
        
        # Этап 1: Точные совпадения по названию + путь
        exact_matches, remaining_nodes = self._find_exact_matches()
        results.extend(exact_matches)
        
        logger.info(f"Found {len(exact_matches)} exact matches, {len(remaining_nodes)} remaining")
        
        if not remaining_nodes:
            return results
        
        # Этап 2: Группируем оставшиеся категории по веткам для batch обработки
        branch_groups = self._group_by_target_branches(remaining_nodes)
        
        logger.info(f"Grouped remaining categories into {len(branch_groups)} branch groups")
        
        # Этап 3: AI обработка по группам
        ai_matches = await self._process_with_ai_by_branches(branch_groups)
        results.extend(ai_matches)
        
        # Этап 4: Создаем результаты для несопоставленных категорий
        matched_input_ids = {r.input_id for r in results}
        unmatched_nodes = [node for node in self.processor.input_leaf_nodes 
                          if node.id not in matched_input_ids]
        
        for node in unmatched_nodes:
            results.append(MatchResult(
                input_id=node.id,
                input_name=node.name,
                input_path=node.path,
                input_full_path=' > '.join(node.full_path_names),
                reasoning="Не найдено подходящего соответствия",
                match_method='none'
            ))
            self.stats['no_matches'] += 1
        
        logger.info(f"Matching completed: {len(results)} total results")
        self._log_statistics()
        
        return results
    
    def _find_exact_matches(self) -> Tuple[List[MatchResult], List[CategoryNode]]:
        """Находит точные совпадения по названию с учетом контекста пути"""
        exact_matches = []
        remaining_nodes = []
        
        for input_node in self.processor.input_leaf_nodes:
            # Ищем потенциальные совпадения по названию
            name_matches = self.processor.find_potential_matches_by_name(input_node)
            
            if not name_matches:
                remaining_nodes.append(input_node)
                continue
            
            # Если одно совпадение - берем его
            if len(name_matches) == 1:
                ref_node = name_matches[0]
                exact_matches.append(MatchResult(
                    input_id=input_node.id,
                    input_name=input_node.name,
                    input_path=input_node.path,
                    input_full_path=' > '.join(input_node.full_path_names),
                    match_id=ref_node.id,
                    match_name=ref_node.name,
                    match_path=ref_node.path,
                    match_full_path=' > '.join(ref_node.full_path_names),
                    confidence=1.0,
                    reasoning=f"Точное совпадение названия: {input_node.name}",
                    match_method='exact'
                ))
                self.stats['exact_matches'] += 1
                continue
            
            # Если несколько совпадений - используем контекст пути для disambiguation
            best_match = self.processor.find_best_path_match(input_node, name_matches)
            
            if best_match:
                exact_matches.append(MatchResult(
                    input_id=input_node.id,
                    input_name=input_node.name,
                    input_path=input_node.path,
                    input_full_path=' > '.join(input_node.full_path_names),
                    match_id=best_match.id,
                    match_name=best_match.name,
                    match_path=best_match.path,
                    match_full_path=' > '.join(best_match.full_path_names),
                    confidence=0.9,
                    reasoning=f"Совпадение по названию с учетом контекста пути",
                    match_method='exact'
                ))
                self.stats['exact_matches'] += 1
            else:
                # Не смогли однозначно определить - отправляем на AI
                remaining_nodes.append(input_node)
        
        return exact_matches, remaining_nodes
    
    def _group_by_target_branches(self, nodes: List[CategoryNode]) -> Dict[str, List[CategoryNode]]:
        """Группирует узлы по целевым веткам reference для оптимизации AI запросов"""
        
        # Для каждого input узла пытаемся определить наиболее подходящую ветку reference
        branch_groups = defaultdict(list)
        unclear_nodes = []
        
        for input_node in nodes:
            target_branches = self._identify_target_branches(input_node)
            
            if len(target_branches) == 1:
                # Четко определена одна ветка
                branch_groups[target_branches[0]].append(input_node)
            elif len(target_branches) > 1:
                # Несколько потенциальных веток - выбираем наиболее подходящую
                best_branch = self._select_best_branch(input_node, target_branches)
                branch_groups[best_branch].append(input_node)
            else:
                # Не определена ветка - добавляем в общую группу
                unclear_nodes.append(input_node)
        
        # Неопределенные узлы распределяем равномерно по группам
        if unclear_nodes:
            branch_keys = list(branch_groups.keys()) if branch_groups else ['general']
            for i, node in enumerate(unclear_nodes):
                branch_key = branch_keys[i % len(branch_keys)]
                branch_groups[branch_key].append(node)
        
        return dict(branch_groups)
    
    def _identify_target_branches(self, input_node: CategoryNode) -> List[str]:
        """Определяет потенциальные ветки reference для input узла"""
        potential_branches = set()
        
        # Анализируем слова в пути input категории
        input_words = set()
        for name in input_node.full_path_names:
            input_words.update(name.lower().split())
        
        # Ищем пересечения с путями reference категорий
        for ref_node in self.processor.reference_leaf_nodes:
            ref_words = set()
            for name in ref_node.full_path_names:
                ref_words.update(name.lower().split())
            
            # Если есть пересечение слов - это потенциальная ветка
            if input_words.intersection(ref_words):
                root_id = ref_node.path.split('>')[0]
                potential_branches.add(root_id)
        
        return list(potential_branches)
    
    def _select_best_branch(self, input_node: CategoryNode, target_branches: List[str]) -> str:
        """Выбирает наиболее подходящую ветку из нескольких вариантов"""
        input_path = ' > '.join(input_node.full_path_names)
        
        best_branch = target_branches[0]
        best_score = 0
        
        for branch_id in target_branches:
            # Получаем примеры категорий из этой ветки
            branch_nodes = [n for n in self.processor.reference_leaf_nodes 
                          if n.path.startswith(branch_id)][:5]  # Берем первые 5 для анализа
            
            total_score = 0
            for ref_node in branch_nodes:
                ref_path = ' > '.join(ref_node.full_path_names)
                score = self.processor._calculate_path_similarity(input_path, ref_path)
                total_score += score
            
            avg_score = total_score / len(branch_nodes) if branch_nodes else 0
            
            if avg_score > best_score:
                best_score = avg_score
                best_branch = branch_id
        
        return best_branch
    
    async def _process_with_ai_by_branches(self, branch_groups: Dict[str, List[CategoryNode]]) -> List[MatchResult]:
        """Обрабатывает группы категорий через AI по веткам"""
        ai_matches = []
        
        for branch_id, input_nodes in branch_groups.items():
            logger.info(f"Processing branch {branch_id} with {len(input_nodes)} categories")
            
            # Получаем контекст reference ветки
            ref_context = self.processor.get_reference_branch_context(branch_id, max_categories=50)
            
            # Обрабатывает батчами
            for i in range(0, len(input_nodes), self.batch_size):
                batch_nodes = input_nodes[i:i + self.batch_size]
                
                try:
                    batch_matches = await self._process_batch_with_ai(batch_nodes, ref_context)
                    ai_matches.extend(batch_matches)
                    self.stats['api_calls'] += 1
                    
                    # Небольшая задержка между запросами
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Failed to process batch in branch {branch_id}: {e}")
                    
                    # Добавляем как несопоставленные
                    for node in batch_nodes:
                        ai_matches.append(MatchResult(
                            input_id=node.id,
                            input_name=node.name,
                            input_path=node.path,
                            input_full_path=' > '.join(node.full_path_names),
                            reasoning=f"Ошибка AI обработки: {str(e)}",
                            match_method='none'
                        ))
        
        return ai_matches
    
    async def _process_batch_with_ai(self, input_nodes: List[CategoryNode], 
                                   ref_context: List[CategoryNode]) -> List[MatchResult]:
        """Обрабатывает один batch через AI"""
        
        # Подготавливаем данные для AI
        ai_context = self.processor.prepare_ai_context(input_nodes, ref_context)
        
        # Отправляем в Claude
        response = await self.claude_client.match_hierarchical_batch(
            ai_context['reference_categories'],
            ai_context['input_categories']
        )
        
        # Преобразуем ответ в MatchResult
        batch_results = []
        matches_dict = {m['input_id']: m for m in response.get('matches', [])}
        
        for input_node in input_nodes:
            if input_node.id in matches_dict:
                match = matches_dict[input_node.id]
                
                # Находим reference узел для получения полной информации
                ref_node = self.processor.reference_tree.get(match.get('match_id'))
                
                batch_results.append(MatchResult(
                    input_id=input_node.id,
                    input_name=input_node.name,
                    input_path=input_node.path,
                    input_full_path=' > '.join(input_node.full_path_names),
                    match_id=match.get('match_id'),
                    match_name=match.get('match_name'),
                    match_path=ref_node.path if ref_node else '',
                    match_full_path=' > '.join(ref_node.full_path_names) if ref_node else '',
                    confidence=match.get('confidence', 0.0),
                    reasoning=match.get('reasoning', ''),
                    match_method='ai'
                ))
                self.stats['ai_matches'] += 1
            else:
                # Не найдено совпадение
                batch_results.append(MatchResult(
                    input_id=input_node.id,
                    input_name=input_node.name,
                    input_path=input_node.path,
                    input_full_path=' > '.join(input_node.full_path_names),
                    reasoning="AI не нашел подходящего соответствия",
                    match_method='none'
                ))
        
        return batch_results
    
    def export_results(self, results: List[MatchResult], output_file: str) -> None:
        """Экспортирует результаты в JSON файл"""
        
        # Подготавливаем данные для экспорта
        export_data = {
            'processed_at': datetime.now().isoformat(),
            'total_input': self.stats['total_input_categories'],
            'total_matched': self.stats['exact_matches'] + self.stats['ai_matches'],
            'total_unmatched': self.stats['no_matches'],
            'matches': [],
            'unmatched': [],
            'statistics': {
                'exact_matches': self.stats['exact_matches'],
                'ai_matches': self.stats['ai_matches'],
                'no_matches': self.stats['no_matches'],
                'api_requests': self.stats['api_calls'],
                'processing_time': f"{self.stats['processing_time']:.2f}s"
            }
        }
        
        # Добавляем сопоставленные категории
        for result in results:
            if result.match_id:
                export_data['matches'].append({
                    'input_id': result.input_id,
                    'input_name': result.input_name,
                    'input_path': result.input_path,
                    'input_full_path': result.input_full_path,
                    'match_id': result.match_id,
                    'match_name': result.match_name,
                    'match_path': result.match_path,
                    'match_full_path': result.match_full_path,
                    'confidence': result.confidence,
                    'reasoning': result.reasoning,
                    'method': result.match_method
                })
            else:
                export_data['unmatched'].append({
                    'input_id': result.input_id,
                    'input_name': result.input_name,
                    'input_path': result.input_path,
                    'input_full_path': result.input_full_path,
                    'reasoning': result.reasoning
                })
        
        # Сохраняем в файл
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Results exported to {output_file}")
    
    def _log_statistics(self) -> None:
        """Выводит статистику обработки"""
        total = self.stats['total_input_categories']
        exact_pct = (self.stats['exact_matches'] / total * 100) if total > 0 else 0
        ai_pct = (self.stats['ai_matches'] / total * 100) if total > 0 else 0
        unmatched_pct = (self.stats['no_matches'] / total * 100) if total > 0 else 0
        
        logger.info(f"""
=== HIERARCHICAL MATCHING STATISTICS ===
Total input categories: {total}
Exact matches: {self.stats['exact_matches']} ({exact_pct:.1f}%)
AI matches: {self.stats['ai_matches']} ({ai_pct:.1f}%)
Unmatched: {self.stats['no_matches']} ({unmatched_pct:.1f}%)
API calls made: {self.stats['api_calls']}
AI cost optimization: {((total - self.stats['api_calls'] * self.batch_size) / total * 100):.1f}% requests saved
=========================================""")
    
    def get_statistics(self) -> Dict:
        """Возвращает статистику для внешнего использования"""
        return self.stats.copy()