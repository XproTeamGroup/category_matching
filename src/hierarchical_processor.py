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
        """Многоуровневый поиск потенциальных совпадений"""
        potential_matches = []
        input_name_lower = input_node.name.lower()
        
        # Уровень 1: Прямое совпадение названия
        direct_matches = self.reference_name_to_nodes.get(input_name_lower, [])
        potential_matches.extend(direct_matches)
        
        if potential_matches:
            return potential_matches
        
        # Уровень 2: Семантические синонимы
        semantic_matches = self._find_semantic_matches(input_node)
        potential_matches.extend(semantic_matches)
        
        if potential_matches:
            return potential_matches
            
        # Уровень 3: Частичные совпадения
        partial_matches = self._find_partial_matches(input_node)
        potential_matches.extend(partial_matches)
        
        if potential_matches:
            return potential_matches
        
        # Уровень 4: Фоллбэк сопоставления
        fallback_matches = self._find_fallback_matches(input_node)
        potential_matches.extend(fallback_matches)
        
        return potential_matches
    
    def find_best_path_match(self, input_node: CategoryNode, name_matches: List[CategoryNode]) -> Optional[CategoryNode]:
        """Находит лучшее совпадение по контексту пути с проверкой логической цепочки"""
        if not name_matches:
            return None
        
        if len(name_matches) == 1:
            # Даже для единственного совпадения проверяем логическую цепочку
            if self._validate_logical_chain(input_node, name_matches[0]):
                return name_matches[0]
            return None
        
        # Сравниваем пути для disambiguation с обязательной проверкой логической цепочки
        input_path = ' > '.join(input_node.full_path_names)
        best_match = None
        best_score = 0
        
        for ref_node in name_matches:
            # Сначала проверяем логическую цепочку
            if not self._validate_logical_chain(input_node, ref_node):
                continue
                
            ref_path = ' > '.join(ref_node.full_path_names)
            score = self._calculate_enhanced_path_similarity(input_path, ref_path)
            
            if score > best_score:
                best_score = score
                best_match = ref_node
        
        # Повышаем порог для более строгого отбора
        return best_match if best_score > 0.5 else None
    
    def _calculate_path_similarity(self, path1: str, path2: str) -> float:
        """Улучшенный расчет схожести путей с учетом семантики"""
        words1 = set(path1.lower().split())
        words2 = set(path2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        # Базовая схожесть по Jaccard
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        base_similarity = intersection / union if union > 0 else 0.0
        
        # Дополнительные бонусы для повышения качества
        bonus = 0.0
        
        # Бонус за семантически связанные слова
        semantic_groups = {
            'одежда': {'одяг', 'екіпірування', 'термобілизна', 'повсякденний', 'дощовики', 'куртки', 'штани', 'рукавички'},
            'электроника': {'електроніка', 'інтеркоми', 'камери', 'gps'},
            'защита': {'захист', 'безпека', 'протектор', 'накладки', 'наколінники'},
            'аксессуары': {'аксесуари', 'accessories'}
        }
        
        for group_words in semantic_groups.values():
            if words1.intersection(group_words) and words2.intersection(group_words):
                bonus += 0.2  # Бонус за принадлежность к одной семантической группе
                break
        
        # Штраф за разные семантические группы
        penalty = 0.0
        for group1_words in semantic_groups.values():
            for group2_words in semantic_groups.values():
                if group1_words != group2_words:
                    if words1.intersection(group1_words) and words2.intersection(group2_words):
                        penalty += 0.3  # Штраф за разные семантические группы
        
        final_similarity = min(1.0, max(0.0, base_similarity + bonus - penalty))
        return final_similarity
    
    def _calculate_enhanced_path_similarity(self, input_path: str, ref_path: str) -> float:
        """Расширенный расчет схожести путей с учетом семантического контекста"""
        # Базовая схожесть слов
        base_score = self._calculate_path_similarity(input_path, ref_path)
        
        # Дополнительные проверки
        input_path_lower = input_path.lower()
        ref_path_lower = ref_path.lower()
        
        # Бонус за схожие семантические группы
        semantic_bonus = 0.0
        
        # Одежда и экипировка
        clothing_keywords = ['одяг', 'екіпірування', 'термобілизна', 'повсякденний', 'дощовики']
        electronics_keywords = ['електроніка', 'інтеркоми', 'електроніка']
        protection_keywords = ['захист', 'безпека', 'протектор']
        accessories_keywords = ['аксесуари', 'аксессуары']
        
        input_has_clothing = any(kw in input_path_lower for kw in clothing_keywords)
        ref_has_clothing = any(kw in ref_path_lower for kw in clothing_keywords)
        
        input_has_electronics = any(kw in input_path_lower for kw in electronics_keywords)
        ref_has_electronics = any(kw in ref_path_lower for kw in electronics_keywords)
        
        input_has_protection = any(kw in input_path_lower for kw in protection_keywords)
        ref_has_protection = any(kw in ref_path_lower for kw in protection_keywords)
        
        # Бонус за совпадение семантических групп
        if (input_has_clothing and ref_has_clothing) or \
           (input_has_electronics and ref_has_electronics) or \
           (input_has_protection and ref_has_protection):
            semantic_bonus = 0.3
        
        # Штраф за несовпадение семантических групп
        elif (input_has_clothing and ref_has_electronics) or \
             (input_has_electronics and ref_has_clothing):
            semantic_bonus = -0.5  # Сильный штраф за смешение одежды и электроники
        
        return max(0.0, base_score + semantic_bonus)
    
    def _validate_logical_chain(self, input_node: CategoryNode, ref_node: CategoryNode) -> bool:
        """Мягкая проверка логической цепочки с большим количеством разрешенных сопоставлений"""
        input_path = ' > '.join(input_node.full_path_names).lower()
        ref_path = ' > '.join(ref_node.full_path_names).lower()
        input_name = input_node.name.lower()
        ref_name = ref_node.name.lower()
        
        # Определяем семантические группы
        clothing_keywords = ['одяг', 'екіпірування', 'термобілизна', 'повсякденний', 'дощовики', 'куртки', 'штани', 'рукавички', 'взуття']
        electronics_keywords = ['електроніка', 'інтеркоми', 'камери', 'навігатори']
        protection_keywords = ['захист', 'безпека', 'протектор', 'накладки', 'наколінники']
        accessories_keywords = ['аксесуари', 'аксессуары']
        
        input_is_clothing = any(kw in input_path for kw in clothing_keywords)
        input_is_electronics = any(kw in input_path for kw in electronics_keywords)
        input_is_protection = any(kw in input_path for kw in protection_keywords)
        input_is_accessories = any(kw in input_path for kw in accessories_keywords)
        
        ref_is_clothing = any(kw in ref_path for kw in clothing_keywords)
        ref_is_electronics = any(kw in ref_path for kw in electronics_keywords)
        ref_is_protection = any(kw in ref_path for kw in protection_keywords)
        ref_is_accessories = any(kw in ref_path for kw in accessories_keywords)
        
        # СТРОГИЕ запреты (оставляем только самые очевидные)
        if input_is_clothing and ref_is_electronics and not input_is_accessories:
            return False
        if input_is_electronics and ref_is_clothing and not ref_is_accessories:
            return False
        
        # СПЕЦИАЛЬНЫЕ правила для семантически схожих категорий
        
        # Мягкие правила для защиты
        protection_synonyms = {
            'накладки на лікті': 'захист ліктів',
            'накладки на коліна': 'наколінники',
            'накладки на зап\'ястя': 'захист зап\'ясть'
        }
        
        for input_variant, ref_variant in protection_synonyms.items():
            if input_variant in input_name and ref_variant in ref_name:
                return True
        
        # Мягкие правила для аксессуаров
        if 'балаклав' in input_name and 'балаклав' in ref_name:
            return True
        
        # Мягкие правила для составных названий
        if '/' in input_name:
            input_parts = [part.strip() for part in input_name.split('/')]
            for part in input_parts:
                if part in ref_name:
                    return True
        
        # Мягкие правила для интеркомов
        if 'інтерком' in input_path and 'інтерком' in ref_path:
            return True
            
        # Мягкие правила для одежды (разрешаем большинство сопоставлений)
        if input_is_clothing and ref_is_clothing:
            return True
        if input_is_protection and ref_is_protection:
            return True
        if input_is_accessories and ref_is_accessories:
            return True
        if input_is_electronics and ref_is_electronics:
            return True
            
        # ОСЛАБЛЕННЫЕ правила для дождевиков (теперь разрешаем общие категории)
        if 'дощовик' in input_path:
            # Разрешаем сопоставление с общими категориями одежды
            return ref_is_clothing or 'дощов' in ref_path
        
        # По умолчанию разрешаем большинство сопоставлений
        return True
    
    def _find_semantic_matches(self, input_node: CategoryNode) -> List[CategoryNode]:
        """Поиск семантических синонимов"""
        semantic_synonyms = {
            # Защита
            'накладки на лікті': ['захист ліктів'],
            'накладки на коліна': ['наколінники / ортези', 'наколінники'],
            'накладки на зап\'ястя і щиколотки': ['захист зап\'ясть'],
            'накладки на зап\'ястя': ['захист зап\'ясть'],
            'накладки на зап\'\'ястя і щиколотки': ['захист зап\'\'ясть'],
            'наколінники та ортези': ['наколінники / ортези', 'наколінники'],
            # Аксессуары
            'балаклави та коміри': ['балаклави і коміри'],
            # Рукавички
            'шосейні / туристичні': ['туристичні'],
            'короткі / літні': ['літні'],
            # Дождевики
            'дощовики': ['дощовики'],
            # Одежда с подогревом
            'підігріваємі': ['з підігрівом'],
            # Обувь
            'пригоди': ['пригодницькі'],
            # Уход
            'чищення / догляд': ['догляд та чищення'],
        }
        
        matches = []
        input_name_lower = input_node.name.lower()
        
        # Проверяем прямые синонимы
        if input_name_lower in semantic_synonyms:
            for synonym in semantic_synonyms[input_name_lower]:
                synonym_matches = self.reference_name_to_nodes.get(synonym.lower(), [])
                matches.extend(synonym_matches)
        
        return matches
    
    def _find_partial_matches(self, input_node: CategoryNode) -> List[CategoryNode]:
        """Поиск частичных совпадений в составных названиях"""
        matches = []
        input_name_lower = input_node.name.lower()
        
        # Обрабатываем составные названия через '/' и ' / '
        if '/' in input_name_lower:
            parts = [part.strip() for part in input_name_lower.split('/')]
            for part in parts:
                if len(part) > 2:  # Игнорируем слишком короткие части
                    part_matches = self.reference_name_to_nodes.get(part, [])
                    matches.extend(part_matches)
        
        # Поиск частичных совпадений в справочнике
        for ref_node in self.reference_leaf_nodes:
            ref_name_lower = ref_node.name.lower()
            # Если input название содержится в reference
            if len(input_name_lower) > 3 and input_name_lower in ref_name_lower:
                matches.append(ref_node)
            # Если reference название содержится в input
            elif len(ref_name_lower) > 3 and ref_name_lower in input_name_lower:
                matches.append(ref_node)
        
        return matches
    
    def _find_fallback_matches(self, input_node: CategoryNode) -> List[CategoryNode]:
        """Фоллбэк сопоставления для специальных случаев"""
        matches = []
        input_name_lower = input_node.name.lower()
        input_path = ' > '.join(input_node.full_path_names).lower()
        
        # Фоллбэк для брендов интеркомов
        intercom_brands = ['sena', 'cardo', 'freedconn', 'eyeride', 'scala', 'rider']
        if ('інтерком' in input_path or 'універсальн' in input_path) and \
           any(brand in input_name_lower for brand in intercom_brands):
            # Находим общие категории интеркомов
            for ref_node in self.reference_leaf_nodes:
                if 'інтерком' in ' > '.join(ref_node.full_path_names).lower():
                    matches.append(ref_node)
                    break
        
        # Фоллбэк для дождевой одежды
        elif 'дощовик' in input_path:
            # Ищем общие категории одежды
            clothing_types = {
                'куртки': ['kurti'], 
                'штани': ['pants', 'штани'],
                'рукавички': ['рукавички'],
                'взуття': ['взуття']
            }
            
            for clothing_type, keywords in clothing_types.items():
                if clothing_type in input_name_lower:
                    for ref_node in self.reference_leaf_nodes:
                        ref_path_lower = ' > '.join(ref_node.full_path_names).lower()
                        if any(keyword in ref_path_lower for keyword in keywords):
                            matches.append(ref_node)
                            break
        
        return matches[:3]  # Ограничиваем количество fallback matches
    
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