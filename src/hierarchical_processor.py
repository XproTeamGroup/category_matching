"""
Иерархический процессор для работы с деревьями категорий
Обрабатывает как reference, так и input файлы с path структурами
"""

import json
import logging
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class CategoryNode:
    """Узел дерева категорий с полной иерархической информацией"""
    id: str
    name: str
    path: str
    parent_id: Optional[str] = None
    children: List['CategoryNode'] = None
    is_leaf: bool = False
    full_path_names: List[str] = None  # Полный путь названий от корня
    
    def __post_init__(self):
        if self.children is None:
            self.children = []
        if self.full_path_names is None:
            self.full_path_names = []


class HierarchicalProcessor:
    """Обработчик иерархических категорий"""
    
    def __init__(self):
        self.reference_tree: Dict[str, CategoryNode] = {}  # id -> node
        self.input_tree: Dict[str, CategoryNode] = {}  # id -> node
        self.reference_leaf_nodes: List[CategoryNode] = []
        self.input_leaf_nodes: List[CategoryNode] = []
        
        # Индексы для быстрого поиска
        self.reference_name_to_nodes: Dict[str, List[CategoryNode]] = defaultdict(list)
        self.reference_path_patterns: Dict[str, List[CategoryNode]] = defaultdict(list)
    
    def load_reference_categories(self, file_path: str) -> None:
        """Загружает и строит дерево reference категорий"""
        logger.info(f"Loading reference categories from {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        # Строим дерево
        self.reference_tree = self._build_tree(categories)
        
        # Находим листья
        self.reference_leaf_nodes = self._find_leaf_nodes(self.reference_tree)
        
        # Строим индексы
        self._build_reference_indexes()
        
        logger.info(f"Loaded {len(categories)} reference categories, {len(self.reference_leaf_nodes)} leaf nodes")
    
    def load_input_categories(self, file_path: str) -> None:
        """Загружает и строит дерево input категорий"""
        logger.info(f"Loading input categories from {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        # Строим дерево
        self.input_tree = self._build_tree(categories)
        
        # Находим листья
        self.input_leaf_nodes = self._find_leaf_nodes(self.input_tree)
        
        logger.info(f"Loaded {len(categories)} input categories, {len(self.input_leaf_nodes)} leaf nodes")
    
    def _build_tree(self, categories: List[Dict]) -> Dict[str, CategoryNode]:
        """Строит дерево из списка категорий"""
        nodes = {}
        
        # Создаем все узлы
        for cat in categories:
            node = CategoryNode(
                id=cat['id'],
                name=cat['name'],
                path=cat['path']
            )
            nodes[cat['id']] = node
        
        # Устанавливаем связи родитель-ребенок
        for cat in categories:
            node = nodes[cat['id']]
            path_ids = cat['path'].split('>')
            
            # Устанавливаем родителя
            if len(path_ids) > 1:
                parent_id = path_ids[-2]
                if parent_id in nodes:
                    node.parent_id = parent_id
                    nodes[parent_id].children.append(node)
        
        # Определяем листья и полные пути
        for node in nodes.values():
            node.is_leaf = len(node.children) == 0
            node.full_path_names = self._get_full_path_names(node, nodes)
        
        return nodes
    
    def _get_full_path_names(self, node: CategoryNode, all_nodes: Dict[str, CategoryNode]) -> List[str]:
        """Получает полный путь названий категорий от корня до узла"""
        path_ids = node.path.split('>')
        path_names = []
        
        for path_id in path_ids:
            if path_id in all_nodes:
                path_names.append(all_nodes[path_id].name)
        
        return path_names
    
    def _find_leaf_nodes(self, tree: Dict[str, CategoryNode]) -> List[CategoryNode]:
        """Находит все листья в дереве"""
        return [node for node in tree.values() if node.is_leaf]
    
    def _build_reference_indexes(self) -> None:
        """Строит индексы для быстрого поиска по reference категориям"""
        self.reference_name_to_nodes.clear()
        self.reference_path_patterns.clear()
        
        for node in self.reference_tree.values():
            # Индекс по названиям (только для листьев)
            if node.is_leaf:
                self.reference_name_to_nodes[node.name.lower()].append(node)
            
            # Индекс по паттернам путей
            path_pattern = ' > '.join(node.full_path_names)
            self.reference_path_patterns[path_pattern.lower()].append(node)
    
    def get_reference_leaf_nodes(self) -> List[CategoryNode]:
        """Возвращает только листья reference дерева"""
        return self.reference_leaf_nodes
    
    def get_input_leaf_nodes(self) -> List[CategoryNode]:
        """Возвращает только листья input дерева"""
        return self.input_leaf_nodes
    
    def find_potential_matches_by_name(self, input_node: CategoryNode) -> List[CategoryNode]:
        """Находит потенциальные совпадения по названию в reference"""
        potential_matches = []
        
        # Прямое совпадение названия
        direct_matches = self.reference_name_to_nodes.get(input_node.name.lower(), [])
        potential_matches.extend(direct_matches)
        
        return potential_matches
    
    def find_best_path_match(self, input_node: CategoryNode, name_matches: List[CategoryNode]) -> Optional[CategoryNode]:
        """Находит лучшее совпадение по контексту пути"""
        if not name_matches:
            return None
        
        if len(name_matches) == 1:
            return name_matches[0]
        
        # Сравниваем пути для disambiguation
        input_path = ' > '.join(input_node.full_path_names)
        best_match = None
        best_score = 0
        
        for ref_node in name_matches:
            ref_path = ' > '.join(ref_node.full_path_names)
            score = self._calculate_path_similarity(input_path, ref_path)
            
            if score > best_score:
                best_score = score
                best_match = ref_node
        
        return best_match if best_score > 0.3 else None  # Минимальный порог схожести
    
    def _calculate_path_similarity(self, path1: str, path2: str) -> float:
        """Вычисляет схожесть путей категорий"""
        words1 = set(path1.lower().split())
        words2 = set(path2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def group_input_nodes_by_target_branch(self, matches: List[Tuple[CategoryNode, CategoryNode]]) -> Dict[str, List[Tuple[CategoryNode, CategoryNode]]]:
        """Группирует input узлы по целевым веткам reference для batch обработки"""
        branch_groups = defaultdict(list)
        
        for input_node, ref_node in matches:
            # Используем корневую категорию как ключ группировки
            root_id = ref_node.path.split('>')[0]
            branch_groups[root_id].append((input_node, ref_node))
        
        return dict(branch_groups)
    
    def get_reference_branch_context(self, root_id: str, max_categories: int = 100) -> List[CategoryNode]:
        """Получает контекст ветки reference для AI обработки"""
        branch_nodes = []
        
        # Собираем все узлы этой ветки
        for node in self.reference_tree.values():
            if node.path.startswith(root_id):
                branch_nodes.append(node)
        
        # Приоритизируем листья и ограничиваем количество
        leaf_nodes = [n for n in branch_nodes if n.is_leaf]
        non_leaf_nodes = [n for n in branch_nodes if not n.is_leaf]
        
        # Берем все листья + несколько родительских для контекста
        result = leaf_nodes[:max_categories]
        remaining_slots = max_categories - len(result)
        
        if remaining_slots > 0:
            result.extend(non_leaf_nodes[:remaining_slots])
        
        return result
    
    def prepare_ai_context(self, input_nodes: List[CategoryNode], ref_context: List[CategoryNode]) -> Dict:
        """Подготавливает контекст для AI с учетом иерархии"""
        
        # Reference категории с полными путями для контекста
        reference_categories = []
        for node in ref_context:
            path_display = ' > '.join(node.full_path_names)
            reference_categories.append({
                'id': node.id,
                'name': node.name,
                'path': node.path,
                'full_path': path_display,
                'is_leaf': node.is_leaf
            })
        
        # Input категории с их путями
        input_categories = []
        for node in input_nodes:
            path_display = ' > '.join(node.full_path_names)
            input_categories.append({
                'id': node.id,
                'name': node.name,
                'path': node.path,
                'full_path': path_display,
                'original_context': path_display  # Контекст откуда пришла категория
            })
        
        return {
            'reference_categories': reference_categories,
            'input_categories': input_categories
        }
    
    def export_tree_structure(self, tree: Dict[str, CategoryNode], file_path: str) -> None:
        """Экспортирует структуру дерева для отладки"""
        tree_data = []
        
        for node in tree.values():
            tree_data.append({
                'id': node.id,
                'name': node.name,
                'path': node.path,
                'parent_id': node.parent_id,
                'is_leaf': node.is_leaf,
                'children_count': len(node.children),
                'full_path': ' > '.join(node.full_path_names)
            })
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(tree_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Tree structure exported to {file_path}")