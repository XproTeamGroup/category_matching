import json
import logging
from typing import List, Dict, Optional, Set
from difflib import SequenceMatcher
import re


logger = logging.getLogger(__name__)


class CategoryNode:
    """Узел дерева категорий"""
    def __init__(self, category_id: str, name: str, path: str):
        self.id = category_id
        self.name = name
        self.path = path
        self.children: List[CategoryNode] = []
        self.parent: Optional[CategoryNode] = None
        self.keywords: Set[str] = self._extract_keywords(name)
    
    def _extract_keywords(self, name: str) -> Set[str]:
        """Извлечение ключевых слов из названия категории"""
        # Очистка и разбиение на слова
        words = re.findall(r'\b\w+\b', name.lower())
        # Убираем короткие слова и стоп-слова
        stop_words = {'и', 'или', 'для', 'в', 'на', 'с', 'по', 'от', 'к', 'из'}
        keywords = {word for word in words if len(word) > 2 and word not in stop_words}
        return keywords
    
    def add_child(self, child: 'CategoryNode'):
        """Добавление дочернего узла"""
        child.parent = self
        self.children.append(child)
    
    def get_full_path(self) -> str:
        """Получение полного пути категории"""
        return self.path
    
    def get_ancestors(self) -> List['CategoryNode']:
        """Получение всех предков узла"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors


class CategoryProcessor:
    """Обработчик категорий и построение иерархии"""
    
    def __init__(self):
        self.category_tree: Dict[str, CategoryNode] = {}
        self.root_nodes: List[CategoryNode] = []
        self.name_index: Dict[str, List[CategoryNode]] = {}
        self.keyword_index: Dict[str, List[CategoryNode]] = {}
    
    def load_reference_categories(self, file_path: str) -> List[Dict]:
        """Загрузка справочных категорий из файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                categories = json.load(f)
            logger.info(f"Loaded {len(categories)} reference categories")
            return categories
        except Exception as e:
            logger.error(f"Failed to load reference categories: {e}")
            raise
    
    def load_input_categories(self, file_path: str) -> List[Dict]:
        """Загрузка входных категорий из файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                categories = json.load(f)
            logger.info(f"Loaded {len(categories)} input categories")
            return categories
        except Exception as e:
            logger.error(f"Failed to load input categories: {e}")
            raise
    
    def build_tree(self, categories: List[Dict]) -> Dict[str, CategoryNode]:
        """Построение иерархического дерева категорий"""
        logger.info("Building category tree")
        
        # Создаем узлы
        nodes = {}
        for cat in categories:
            node = CategoryNode(cat['id'], cat['name'], cat['path'])
            nodes[cat['id']] = node
            self.category_tree[cat['id']] = node
        
        # Строим иерархию по path
        for cat in categories:
            node = nodes[cat['id']]
            path_parts = cat['path'].split('>')
            
            if len(path_parts) > 1:
                parent_id = path_parts[-2]  # Предпоследний элемент - родитель
                if parent_id in nodes:
                    nodes[parent_id].add_child(node)
            else:
                self.root_nodes.append(node)
        
        # Строим индексы
        self._build_indexes()
        
        logger.info(f"Built tree with {len(self.category_tree)} nodes")
        return self.category_tree
    
    def _build_indexes(self):
        """Построение индексов для быстрого поиска"""
        for node in self.category_tree.values():
            # Индекс по названиям
            name_lower = node.name.lower()
            if name_lower not in self.name_index:
                self.name_index[name_lower] = []
            self.name_index[name_lower].append(node)
            
            # Индекс по ключевым словам
            for keyword in node.keywords:
                if keyword not in self.keyword_index:
                    self.keyword_index[keyword] = []
                self.keyword_index[keyword].append(node)
    
    def find_exact_matches(self, category_name: str) -> List[CategoryNode]:
        """Поиск точных совпадений по названию"""
        name_lower = category_name.lower()
        return self.name_index.get(name_lower, [])
    
    def find_fuzzy_matches(self, category_name: str, threshold: float = 0.8) -> List[tuple]:
        """Поиск нечетких совпадений по названию"""
        matches = []
        name_lower = category_name.lower()
        
        for node_name, nodes in self.name_index.items():
            similarity = SequenceMatcher(None, name_lower, node_name).ratio()
            if similarity >= threshold:
                for node in nodes:
                    matches.append((node, similarity))
        
        # Сортируем по убыванию схожести
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    def find_keyword_matches(self, category_name: str) -> List[tuple]:
        """Поиск совпадений по ключевым словам"""
        input_keywords = self._extract_keywords(category_name)
        matches = {}
        
        for keyword in input_keywords:
            if keyword in self.keyword_index:
                for node in self.keyword_index[keyword]:
                    if node.id not in matches:
                        matches[node.id] = {'node': node, 'common_keywords': set()}
                    matches[node.id]['common_keywords'].add(keyword)
        
        # Вычисляем score по количеству общих ключевых слов
        result = []
        for match_data in matches.values():
            node = match_data['node']
            common_keywords = match_data['common_keywords']
            
            # Jaccard similarity
            all_keywords = input_keywords.union(node.keywords)
            if all_keywords:
                score = len(common_keywords) / len(all_keywords)
                result.append((node, score))
        
        # Сортируем по убыванию score
        result.sort(key=lambda x: x[1], reverse=True)
        return result
    
    def _extract_keywords(self, name: str) -> Set[str]:
        """Извлечение ключевых слов из названия категории"""
        words = re.findall(r'\b\w+\b', name.lower())
        stop_words = {'и', 'или', 'для', 'в', 'на', 'с', 'по', 'от', 'к', 'из'}
        keywords = {word for word in words if len(word) > 2 and word not in stop_words}
        return keywords
    
    def pre_filter_categories(self, input_categories: List[Dict], 
                            reference_categories: List[Dict]) -> List[Dict]:
        """Предварительная фильтрация категорий для оптимизации"""
        logger.info("Pre-filtering categories")
        
        # Для каждой входной категории ищем потенциальные совпадения
        filtered_reference = set()
        
        for input_cat in input_categories:
            input_name = input_cat['name']
            
            # Ищем точные совпадения
            exact_matches = self.find_exact_matches(input_name)
            for match in exact_matches:
                filtered_reference.add(match.id)
            
            # Ищем нечеткие совпадения
            fuzzy_matches = self.find_fuzzy_matches(input_name, threshold=0.6)
            for match, _ in fuzzy_matches[:5]:  # Берем топ-5
                filtered_reference.add(match.id)
            
            # Ищем совпадения по ключевым словам
            keyword_matches = self.find_keyword_matches(input_name)
            for match, _ in keyword_matches[:5]:  # Берем топ-5
                filtered_reference.add(match.id)
        
        # Возвращаем отфильтрованный список
        filtered_categories = [
            cat for cat in reference_categories 
            if cat['id'] in filtered_reference
        ]
        
        logger.info(f"Filtered from {len(reference_categories)} to {len(filtered_categories)} categories")
        return filtered_categories