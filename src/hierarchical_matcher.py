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
        
        # Этап 1: Точные совпадения по названию + путь (с мягкой валидацией)
        exact_matches, remaining_nodes = self._find_exact_matches_simple()
        results.extend(exact_matches)
        
        logger.info(f"Found {len(exact_matches)} exact matches, {len(remaining_nodes)} remaining")
        
        if not remaining_nodes:
            return results
        
        # Этап 2: Группируем оставшиеся категории по веткам для batch обработки
        branch_groups = self._group_by_target_branches(remaining_nodes)
        
        logger.info(f"Grouped remaining categories into {len(branch_groups)} branch groups")
        
        # Этап 3: AI обработка по группам с логическим сопоставлением
        ai_matches = await self._process_with_ai_by_branches(branch_groups)
        results.extend(ai_matches)
        
        # Этап 4: Проверяем и добавляем несопоставленные категории
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
            # Не увеличиваем no_matches здесь - они уже подсчитаны в AI обработке
        
        # Пересчитываем финальную статистику на основе реальных результатов
        self._recalculate_final_statistics(results)
        
        logger.info(f"Matching completed: {len(results)} total results")
        self._log_statistics()
        
        return results
    
    def _find_exact_matches(self) -> Tuple[List[MatchResult], List[CategoryNode], List[CategoryNode]]:
        """Находит точные совпадения с валидацией и выделяет промежуточные категории для расширенной AI обработки"""
        exact_matches = []
        remaining_nodes = []
        enhanced_ai_nodes = []  # Категории с низкой схожестью для расширенной AI обработки
        
        PATH_SIMILARITY_THRESHOLD = 0.5  # 50% схожесть путей для автоматического сопоставления
        ENHANCED_AI_THRESHOLD = 0.15    # 15% схожесть для расширенной AI обработки
        
        for input_node in self.processor.input_leaf_nodes:
            # Ищем потенциальные совпадения по названию
            name_matches = self.processor.find_potential_matches_by_name(input_node)
            
            if not name_matches:
                remaining_nodes.append(input_node)
                continue
            
            # Анализируем схожесть путей для всех найденных совпадений
            valid_matches = []
            enhanced_matches = []  # Совпадения для расширенной AI обработки
            input_path = ' > '.join(input_node.full_path_names)
            
            for ref_node in name_matches:
                ref_path = ' > '.join(ref_node.full_path_names)
                path_similarity = self.processor._calculate_path_similarity(input_path, ref_path)
                
                if path_similarity >= PATH_SIMILARITY_THRESHOLD:
                    valid_matches.append((ref_node, path_similarity))
                elif path_similarity >= ENHANCED_AI_THRESHOLD:
                    enhanced_matches.append((ref_node, path_similarity))
                    logger.info(f"Enhanced AI candidate ({path_similarity:.2f}): "
                              f"'{input_node.name}' {input_path} -> {ref_path}")
                else:
                    logger.info(f"Exact match rejected due to low path similarity ({path_similarity:.2f}): "
                              f"'{input_node.name}' {input_path} -> {ref_path}")
            
            # Обработка результатов
            if valid_matches:
                # Есть хорошие совпадения - используем автоматическое сопоставление
                if len(valid_matches) == 1:
                    ref_node, similarity = valid_matches[0]
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
                        reasoning=f"Точное совпадение названия с высокой схожестью пути ({similarity:.2f}): {input_node.name}",
                        match_method='exact'
                    ))
                    self.stats['exact_matches'] += 1
                else:
                    # Несколько валидных совпадений - выбираем с наивысшей схожестью
                    best_match, best_similarity = max(valid_matches, key=lambda x: x[1])
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
                        reasoning=f"Совпадение по названию с наилучшей схожестью пути ({best_similarity:.2f})",
                        match_method='exact'
                    ))
                    self.stats['exact_matches'] += 1
            elif enhanced_matches:
                # Есть совпадения с низкой схожестью - отправляем на расширенную AI обработку
                input_node.enhanced_candidates = enhanced_matches  # Сохраняем кандидатов
                enhanced_ai_nodes.append(input_node)
                logger.info(f"Sending to enhanced AI processing: '{input_node.name}' with {len(enhanced_matches)} candidates")
            else:
                # Нет подходящих совпадений - стандартная AI обработка
                remaining_nodes.append(input_node)
        
        return exact_matches, remaining_nodes, enhanced_ai_nodes
    
    def _find_exact_matches_simple(self) -> Tuple[List[MatchResult], List[CategoryNode]]:
        """Простое точное сопоставление с мягкой валидацией для захист категорий"""
        exact_matches = []
        remaining_nodes = []
        
        for input_node in self.processor.input_leaf_nodes:
            # Ищем точные совпадения по названию
            name_matches = self.processor.find_potential_matches_by_name(input_node)
            
            if not name_matches:
                remaining_nodes.append(input_node)
                continue
            
            # Для защитных категорий используем мягкую валидацию
            input_path = ' > '.join(input_node.full_path_names).lower()
            is_protection_category = any(word in input_path for word in ['захист', 'защита', 'накладки', 'протектор'])
            
            # Если одно совпадение - берем его (особенно для защитных категорий)
            if len(name_matches) == 1:
                ref_node = name_matches[0]
                ref_path = ' > '.join(ref_node.full_path_names).lower()
                
                # Для защитных категорий - более мягкая проверка
                if is_protection_category and ('захист' in ref_path or 'екіпірування' in ref_path):
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
                        reasoning=f"Точное совпадение названия защитной категории: {input_node.name}",
                        match_method='exact'
                    ))
                    self.stats['exact_matches'] += 1
                    continue
                
                # Обычная валидация для остальных
                path_similarity = self.processor._calculate_path_similarity(
                    ' > '.join(input_node.full_path_names),
                    ' > '.join(ref_node.full_path_names)
                )
                
                if path_similarity >= 0.2:  # Оптимальный порог 20%
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
                        reasoning=f"Точное совпадение названия ({path_similarity:.2f}): {input_node.name}",
                        match_method='exact'
                    ))
                    self.stats['exact_matches'] += 1
                    continue
            
            # Отправляем на AI обработку
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
    
    async def _process_enhanced_ai_categories(self, enhanced_nodes: List[CategoryNode]) -> List[MatchResult]:
        """Обрабатывает категории с низкой схожестью, предоставляя AI больше вариантов для сопоставления"""
        enhanced_results = []
        
        for input_node in enhanced_nodes:
            enhanced_candidates = getattr(input_node, 'enhanced_candidates', [])
            if not enhanced_candidates:
                continue
            
            # Создаем расширенный контекст для AI - включаем всех кандидатов
            reference_context = []
            
            # Добавляем все кандидаты с низкой схожестью
            for ref_node, similarity in enhanced_candidates:
                reference_context.append({
                    'id': ref_node.id,
                    'name': ref_node.name,
                    'path': ref_node.path,
                    'full_path': ' > '.join(ref_node.full_path_names),
                    'is_leaf': ref_node.is_leaf,
                    'similarity_score': similarity,
                    'original_context': f"Enhanced candidate (similarity: {similarity:.2f})"
                })
            
            # Добавляем дополнительные категории из той же ветки для контекста
            if enhanced_candidates:
                # Берем ветку с наивысшей схожестью
                best_branch_id = enhanced_candidates[0][0].path.split('>')[0]
                additional_context = [n for n in self.processor.reference_leaf_nodes 
                                    if n.path.startswith(best_branch_id)][:10]  # Ограничиваем контекст
                
                for ref_node in additional_context:
                    if not any(ctx['id'] == ref_node.id for ctx in reference_context):
                        reference_context.append({
                            'id': ref_node.id,
                            'name': ref_node.name,
                            'path': ref_node.path,
                            'full_path': ' > '.join(ref_node.full_path_names),
                            'is_leaf': ref_node.is_leaf,
                            'original_context': f"Additional context from branch {best_branch_id}"
                        })
            
            # Формируем input для AI
            input_categories = [{
                'id': input_node.id,
                'name': input_node.name,
                'path': input_node.path,
                'full_path': ' > '.join(input_node.full_path_names),
                'original_context': f"Enhanced processing with {len(enhanced_candidates)} candidates"
            }]
            
            logger.info(f"Enhanced AI processing for '{input_node.name}' with {len(reference_context)} reference categories")
            
            # Отправляем на AI обработку
            try:
                ai_response = await self.claude_client.match_hierarchical_batch(
                    reference_context, input_categories
                )
                
                for match in ai_response.get('matches', []):
                    if match.get('match_id'):
                        # Находим соответствующий reference node
                        ref_node = next((n for n in self.processor.reference_leaf_nodes 
                                       if n.id == match['match_id']), None)
                        
                        if ref_node:
                            enhanced_results.append(MatchResult(
                                input_id=match['input_id'],
                                input_name=input_node.name,
                                input_path=input_node.path,
                                input_full_path=' > '.join(input_node.full_path_names),
                                match_id=ref_node.id,
                                match_name=ref_node.name,
                                match_path=ref_node.path,
                                match_full_path=' > '.join(ref_node.full_path_names),
                                confidence=match.get('confidence', 0.8),
                                reasoning=f"Enhanced AI match: {match.get('reasoning', '')}",
                                match_method='enhanced_ai'
                            ))
                            self.stats['ai_matches'] += 1
                            
            except Exception as e:
                logger.error(f"Enhanced AI processing failed for {input_node.name}: {e}")
        
        return enhanced_results
    
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
        """Обрабатывает один batch через AI с предварительной фильтрацией"""
        
        # Предварительная фильтрация reference категорий по логической совместимости
        filtered_ref_context = []
        for input_node in input_nodes:
            for ref_node in ref_context:
                if self.processor._validate_logical_chain(input_node, ref_node):
                    if ref_node not in filtered_ref_context:
                        filtered_ref_context.append(ref_node)
        
        if not filtered_ref_context:
            # Если ни одна reference категория не прошла валидацию
            logger.info(f"No valid reference categories found for batch of {len(input_nodes)} inputs after logical validation")
            return [MatchResult(
                input_id=node.id,
                input_name=node.name,
                input_path=node.path,
                input_full_path=' > '.join(node.full_path_names),
                reasoning="Не найдено логически совместимых категорий в справочнике",
                match_method='none'
            ) for node in input_nodes]
        
        logger.info(f"Filtered reference context from {len(ref_context)} to {len(filtered_ref_context)} logically compatible categories")
        
        # Подготавливаем данные для AI с отфильтрованным контекстом
        ai_context = self.processor.prepare_ai_context(input_nodes, filtered_ref_context)
        
        # Отправляем в Claude
        response = await self.claude_client.match_hierarchical_batch(
            ai_context['reference_categories'],
            ai_context['input_categories']
        )
        
        # Преобразуем ответ в MatchResult с дополнительной валидацией
        batch_results = []
        matches_dict = {m['input_id']: m for m in response.get('matches', [])}
        
        for input_node in input_nodes:
            if input_node.id in matches_dict:
                match = matches_dict[input_node.id]
                match_id = match.get('match_id')
                
                # Проверяем, что AI нашёл соответствие
                if match_id and match_id != 'null':
                    # Находим reference узел для получения полной информации
                    ref_node = self.processor.reference_tree.get(match_id)
                    
                    if ref_node:
                        # Дополнительная проверка логической цепочки
                        if self.processor._validate_logical_chain(input_node, ref_node):
                            batch_results.append(MatchResult(
                                input_id=input_node.id,
                                input_name=input_node.name,
                                input_path=input_node.path,
                                input_full_path=' > '.join(input_node.full_path_names),
                                match_id=match_id,
                                match_name=match.get('match_name'),
                                match_path=ref_node.path,
                                match_full_path=' > '.join(ref_node.full_path_names),
                                confidence=match.get('confidence', 0.0),
                                reasoning=match.get('reasoning', ''),
                                match_method='ai'
                            ))
                            self.stats['ai_matches'] += 1
                        else:
                            # AI предложил нелогичное соответствие
                            logger.warning(f"AI suggested invalid match for {input_node.name}: {ref_node.name} (failed logical validation)")
                            batch_results.append(MatchResult(
                                input_id=input_node.id,
                                input_name=input_node.name,
                                input_path=input_node.path,
                                input_full_path=' > '.join(input_node.full_path_names),
                                reasoning=f"AI предложил нелогичное соответствие: {match.get('match_name', '')} (не прошло валидацию логической цепочки)",
                                match_method='none'
                            ))
                            # Не увеличиваем счетчик - пересчитаем в финале
                    else:
                        # Reference узел не найден
                        batch_results.append(MatchResult(
                            input_id=input_node.id,
                            input_name=input_node.name,
                            input_path=input_node.path,
                            input_full_path=' > '.join(input_node.full_path_names),
                            reasoning=f"Reference категория {match_id} не найдена в справочнике",
                            match_method='none'
                        ))
                        # Не увеличиваем счетчик - пересчитаем в финале
                else:
                    # AI отказался от сопоставления - это правильное поведение
                    batch_results.append(MatchResult(
                        input_id=input_node.id,
                        input_name=input_node.name,
                        input_path=input_node.path,
                        input_full_path=' > '.join(input_node.full_path_names),
                        reasoning=match.get('reasoning', 'AI отказался от сопоставления'),
                        match_method='none'
                    ))
                    # Не увеличиваем счетчик - пересчитаем в финале
            else:
                # Не найдено совпадение в ответе AI
                batch_results.append(MatchResult(
                    input_id=input_node.id,
                    input_name=input_node.name,
                    input_path=input_node.path,
                    input_full_path=' > '.join(input_node.full_path_names),
                    reasoning="AI не включил категорию в ответ",
                    match_method='none'
                ))
                # Не увеличиваем счетчик - пересчитаем в финале
        
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
    
    def _recalculate_final_statistics(self, results: List[MatchResult]) -> None:
        """Пересчитывает финальную статистику на основе реальных результатов"""
        # Обнуляем счетчики для пересчета
        self.stats['exact_matches'] = 0
        self.stats['ai_matches'] = 0
        self.stats['no_matches'] = 0
        
        # Пересчитываем на основе фактических результатов
        for result in results:
            if result.match_id:  # Если есть соответствие
                if result.match_method == 'exact':
                    self.stats['exact_matches'] += 1
                elif result.match_method == 'ai':
                    self.stats['ai_matches'] += 1
            else:  # Несопоставленные
                self.stats['no_matches'] += 1
    
    def _log_statistics(self) -> None:
        """Выводит статистику обработки с исправленными расчетами"""
        total = self.stats['total_input_categories']
        exact_pct = (self.stats['exact_matches'] / total * 100) if total > 0 else 0
        ai_pct = (self.stats['ai_matches'] / total * 100) if total > 0 else 0
        unmatched_pct = (self.stats['no_matches'] / total * 100) if total > 0 else 0
        matched_total = self.stats['exact_matches'] + self.stats['ai_matches']
        matched_pct = (matched_total / total * 100) if total > 0 else 0
        
        # Исправленный расчет экономии API запросов
        # Количество категорий, обработанных без AI (точные совпадения)
        categories_without_ai = self.stats['exact_matches']
        categories_with_ai = self.stats['ai_matches'] + self.stats['no_matches']
        
        # Количество API запросов, которые потребовались бы без оптимизации (все категории через AI)
        total_batches_without_optimization = (total + self.batch_size - 1) // self.batch_size
        actual_api_calls = self.stats['api_calls']
        
        # Экономия = количество запросов, которых мы избежали благодаря точным совпадениям
        if actual_api_calls == 0:
            # Если ни одного AI запроса - 100% экономия
            api_savings_pct = 100.0
        elif categories_without_ai == 0:
            # Если нет точных совпадений - нет экономии
            api_savings_pct = 0.0
        else:
            # Обычный случай: экономия за счет точных совпадений
            api_savings_pct = (categories_without_ai / total * 100)
        
        logger.info(f"""
=== HIERARCHICAL MATCHING STATISTICS ===
Общее количество категорий: {total}
Сопоставлено общего: {matched_total} ({matched_pct:.1f}%)
Точные совпадения: {self.stats['exact_matches']} ({exact_pct:.1f}%)
AI совпадения: {self.stats['ai_matches']} ({ai_pct:.1f}%)
Не сопоставлено: {self.stats['no_matches']} ({unmatched_pct:.1f}%)
API запросов: {actual_api_calls} (без оптимизации: {total_batches_without_optimization})
Экономия от точных совпадений: {api_savings_pct:.1f}%
=========================================""")
    
    def get_statistics(self) -> Dict:
        """Возвращает статистику для внешнего использования"""
        return self.stats.copy()