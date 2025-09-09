import logging
from typing import Dict, List, Tuple, Set
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class SmartMatcher:
    """Улучшенная система сопоставления с учетом синонимов и языковых особенностей"""
    
    def __init__(self):
        # Словарь синонимов и переводов
        self.synonym_dictionary = {
            # Автомобильные термины
            'глушители': ['глушник', 'глушники', 'глушитель', 'exhaust', 'muffler'],
            'глушники': ['глушитель', 'глушители', 'exhaust', 'muffler'],
            'глушник': ['глушители', 'глушители', 'exhaust', 'muffler'],
            
            # Масла и жидкости
            'масло': ['масла', 'oil', 'олія', 'олія', 'lubricant'],
            'масла': ['масло', 'oil', 'олія', 'lubricant'],
            'моторное': ['моторний', 'моторна', 'моторні', 'engine', 'motor'],
            'моторні': ['моторное', 'моторный', 'engine', 'motor'],
            'моторний': ['моторное', 'моторная', 'engine', 'motor'],
            
            # Распродажи и скидки
            'распродажа': ['розпродаж', 'sale', 'clearance', 'скидка', 'discount'],
            'розпродаж': ['распродажа', 'sale', 'clearance', 'скидка', 'discount'],
            'скидка': ['розпродаж', 'распродажа', 'sale', 'discount'],
            'скидкой': ['розпродаж', 'распродажа', 'sale', 'discount'],
            'товары': ['товар', 'продукция', 'товари', 'products', 'goods'],
            'товари': ['товары', 'товар', 'продукция', 'products', 'goods'],
            # Фразы для распродаж
            'товары со скидкой': ['розпродаж', 'распродажа', 'sale'],
            'товары на распродаже': ['розпродаж', 'sale'],
            
            # Шлемы и защита
            'шлем': ['шолом', 'шоломи', 'helmet', 'casque'],
            'шлемы': ['шоломи', 'шолом', 'helmets'],
            'шоломи': ['шлемы', 'шлем', 'helmets'],
            'шолом': ['шлем', 'шлемы', 'helmet'],
            
            # Мотоциклетные термины
            'мотоциклетный': ['мотоциклетна', 'мотоциклетні', 'motorcycle', 'байкерский'],
            'мотоциклетна': ['мотоциклетный', 'мотоциклетные', 'motorcycle'],
            'мотоциклетні': ['мотоциклетные', 'мотоциклетный', 'motorcycle'],
            'байкерский': ['мотоциклетный', 'мотоциклетні', 'biker'],
            
            # Автомобильные части
            'фильтр': ['фільтр', 'filter'],
            'фільтр': ['фильтр', 'фильтры', 'filter'],
            'фильтры': ['фільтри', 'фільтр', 'filters'],
            'фільтри': ['фильтры', 'фильтр', 'filters'],
            'воздушный': ['повітряний', 'air'],
            'повітряний': ['воздушный', 'воздушные', 'air'],
            
            # Шины и диски
            'шины': ['шини', 'покрышки', 'tires', 'tyres'],
            'шини': ['шины', 'покрышки', 'tires', 'tyres'],
            'покрышки': ['шины', 'шини', 'tires', 'tyres'],
            'диски': ['диск', 'wheels', 'rims'],
            'литые': ['литий', 'alloy', 'cast'],
            
            # Общие термины
            'автомобильный': ['автомобільний', 'авто', 'car', 'auto'],
            'автомобільний': ['автомобильный', 'авто', 'car', 'auto'],
            'автомобильные': ['автомобільні', 'авто', 'car', 'auto'],
            'автомобільні': ['автомобильные', 'авто', 'car', 'auto'],
            
            # Времена года
            'зимний': ['зимові', 'зимняя', 'winter'],
            'зимові': ['зимний', 'зимние', 'winter'],
            'зимние': ['зимові', 'зимний', 'winter'],
            'летний': ['літні', 'літня', 'summer'],
            'літні': ['летние', 'летний', 'summer'],
            'летние': ['літні', 'летний', 'summer'],
            
            # Инструменты и химия
            'инструменты': ['інструменти', 'tools'],
            'інструменти': ['инструменты', 'инструмент', 'tools'],
            'химия': ['хімія', 'chemistry', 'chemicals'],
            'хімія': ['химия', 'chemistry', 'chemicals'],
            'автохимия': ['автохімія', 'car chemicals'],
            'автохімія': ['автохимия', 'car chemicals'],
            
            # Электроника
            'навигатор': ['навігатор', 'navigator', 'gps'],
            'навігатор': ['навигатор', 'navigator', 'gps'],
            'мультимедиа': ['мультімедіа', 'multimedia'],
            'мультімедіа': ['мультимедиа', 'multimedia'],
            
            # Детали двигателя
            'свечи': ['свічки', 'spark plugs', 'plugs'],
            'свічки': ['свечи', 'spark plugs', 'plugs'],
            'зажигание': ['запалювання', 'ignition'],
            'запалювання': ['зажигание', 'ignition'],
            'колодки': ['колодочки', 'brake pads', 'pads'],
            'тормозные': ['гальмівні', 'brake'],
            'гальмівні': ['тормозные', 'brake']
        }
        
        # Стоп-слова которые можно игнорировать при сравнении
        self.stop_words = {
            'для', 'в', 'на', 'с', 'по', 'от', 'к', 'из', 'за', 'под', 'над',
            'та', 'або', 'в', 'на', 'з', 'по', 'від', 'до', 'із', 'за', 'під', 'над',
            'the', 'and', 'or', 'for', 'in', 'on', 'with', 'by', 'from', 'to', 'of', 'at'
        }
        
        # Правила транслитерации
        self.transliteration_rules = {
            'ї': 'и', 'і': 'и', 'є': 'е', 'ґ': 'г',
            'щ': 'щ', 'ш': 'ш', 'ч': 'ч', 'ц': 'ц',
            'ж': 'ж', 'з': 'з', 'й': 'й', 'х': 'х',
            'ф': 'ф', 'в': 'в', 'у': 'у', 'т': 'т',
            'с': 'с', 'р': 'р', 'п': 'п', 'о': 'о',
            'н': 'н', 'м': 'м', 'л': 'л', 'к': 'к',
            'д': 'д', 'г': 'г', 'б': 'б', 'а': 'а'
        }
    
    def find_smart_matches(self, input_category: str, reference_categories: List[Dict], 
                          top_k: int = 10) -> List[Tuple[Dict, float, str]]:
        """Умный поиск совпадений с учетом синонимов и языковых особенностей"""
        
        matches = []
        input_normalized = self._normalize_text(input_category)
        input_words = self._extract_meaningful_words(input_normalized)
        
        for ref_cat in reference_categories:
            ref_normalized = self._normalize_text(ref_cat['name'])
            ref_words = self._extract_meaningful_words(ref_normalized)
            
            # Различные методы сопоставления
            scores = []
            reasons = []
            
            # 1. Прямое совпадение
            direct_score = self._direct_match_score(input_normalized, ref_normalized)
            if direct_score > 0:
                scores.append(direct_score)
                reasons.append("direct_match")
            
            # 2. Синонимы
            synonym_score = self._synonym_match_score(input_words, ref_words)
            if synonym_score > 0:
                scores.append(synonym_score)
                reasons.append("synonym_match")
            
            # 3. Нечеткое сравнение
            fuzzy_score = self._fuzzy_match_score(input_normalized, ref_normalized)
            if fuzzy_score > 0.6:
                scores.append(fuzzy_score)
                reasons.append("fuzzy_match")
            
            # 4. Транслитерация
            translit_score = self._transliteration_match_score(input_normalized, ref_normalized)
            if translit_score > 0.7:
                scores.append(translit_score)
                reasons.append("transliteration_match")
            
            # 5. Частичное совпадение ключевых слов
            partial_score = self._partial_word_match_score(input_words, ref_words)
            if partial_score > 0.5:
                scores.append(partial_score)
                reasons.append("partial_match")
            
            # Выбираем лучший результат
            if scores:
                best_score = max(scores)
                best_reason = reasons[scores.index(best_score)]
                matches.append((ref_cat, best_score, best_reason))
        
        # Сортируем по убыванию скора
        matches.sort(key=lambda x: x[1], reverse=True)
        
        # Логируем топ совпадения для отладки
        if matches:
            logger.debug(f"Smart matches for '{input_category}':")
            for i, (cat, score, reason) in enumerate(matches[:5]):
                logger.debug(f"  {i+1}. {cat['name']} (score: {score:.3f}, reason: {reason})")
        
        return matches[:top_k]
    
    def _normalize_text(self, text: str) -> str:
        """Нормализация текста"""
        # Приводим к нижнему регистру
        text = text.lower()
        
        # Удаляем лишние символы
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Убираем множественные пробелы
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _extract_meaningful_words(self, text: str) -> List[str]:
        """Извлечение значимых слов (без стоп-слов)"""
        words = text.split()
        meaningful_words = []
        
        for word in words:
            if len(word) > 2 and word not in self.stop_words:
                meaningful_words.append(word)
        
        return meaningful_words
    
    def _direct_match_score(self, input_text: str, ref_text: str) -> float:
        """Прямое совпадение текста"""
        if input_text == ref_text:
            return 1.0
        
        # Частичное прямое совпадение
        shorter = min(input_text, ref_text, key=len)
        longer = max(input_text, ref_text, key=len)
        
        if shorter in longer:
            return len(shorter) / len(longer)
        
        return 0.0
    
    def _synonym_match_score(self, input_words: List[str], ref_words: List[str]) -> float:
        """Сопоставление через синонимы"""
        matches = 0
        total_words = max(len(input_words), len(ref_words))
        
        if total_words == 0:
            return 0.0
        
        # Проверяем полную фразу сначала
        input_phrase = ' '.join(input_words)
        if input_phrase in self.synonym_dictionary:
            phrase_synonyms = self.synonym_dictionary[input_phrase]
            for ref_word in ref_words:
                if ref_word in phrase_synonyms:
                    return 1.0  # Полное совпадение фразы
        
        for input_word in input_words:
            # Прямое совпадение
            if input_word in ref_words:
                matches += 1
                continue
            
            # Поиск через синонимы
            synonyms = self.synonym_dictionary.get(input_word, [])
            for synonym in synonyms:
                if synonym in ref_words:
                    matches += 0.9  # Немного меньший вес для синонимов
                    break
            
            # Обратный поиск синонимов
            for ref_word in ref_words:
                ref_synonyms = self.synonym_dictionary.get(ref_word, [])
                if input_word in ref_synonyms:
                    matches += 0.9
                    break
        
        return matches / total_words
    
    def _fuzzy_match_score(self, input_text: str, ref_text: str) -> float:
        """Нечеткое сравнение"""
        return SequenceMatcher(None, input_text, ref_text).ratio()
    
    def _transliteration_match_score(self, input_text: str, ref_text: str) -> float:
        """Сопоставление с учетом транслитерации"""
        # Транслитерируем украинский текст в русский
        input_translit = self._transliterate(input_text)
        ref_translit = self._transliterate(ref_text)
        
        # Сравниваем транслитерированные версии
        return SequenceMatcher(None, input_translit, ref_translit).ratio()
    
    def _transliterate(self, text: str) -> str:
        """Простая транслитерация украинского в русский"""
        result = []
        for char in text:
            result.append(self.transliteration_rules.get(char, char))
        return ''.join(result)
    
    def _partial_word_match_score(self, input_words: List[str], ref_words: List[str]) -> float:
        """Частичное совпадение слов"""
        if not input_words or not ref_words:
            return 0.0
        
        matches = 0
        
        for input_word in input_words:
            for ref_word in ref_words:
                # Проверяем частичное совпадение
                if len(input_word) >= 4 and len(ref_word) >= 4:
                    if input_word[:4] == ref_word[:4]:  # Первые 4 символа
                        matches += 0.7
                        continue
                
                # Проверяем содержание одного слова в другом
                if input_word in ref_word or ref_word in input_word:
                    matches += 0.8
        
        return matches / max(len(input_words), len(ref_words))
    
    def explain_match(self, input_category: str, matched_category: Dict, 
                     score: float, reason: str) -> str:
        """Объяснение почему категории совпадают"""
        
        explanations = {
            'direct_match': 'Прямое текстовое совпадение',
            'synonym_match': 'Совпадение через синонимы',
            'fuzzy_match': 'Нечеткое текстовое сходство',
            'transliteration_match': 'Совпадение через транслитерацию (рус/укр)',
            'partial_match': 'Частичное совпадение ключевых слов'
        }
        
        base_explanation = explanations.get(reason, 'Неизвестная причина')
        
        if reason == 'synonym_match':
            # Находим конкретные синонимы
            input_words = self._extract_meaningful_words(self._normalize_text(input_category))
            ref_words = self._extract_meaningful_words(self._normalize_text(matched_category['name']))
            
            found_synonyms = []
            for input_word in input_words:
                synonyms = self.synonym_dictionary.get(input_word, [])
                for synonym in synonyms:
                    if synonym in ref_words:
                        found_synonyms.append(f"{input_word} -> {synonym}")
            
            if found_synonyms:
                base_explanation += f" ({', '.join(found_synonyms)})"
        
        return f"{base_explanation}. Уверенность: {score:.2f}"


def test_smart_matcher():
    """Тест умного сопоставления"""
    
    # Тестовые данные
    reference_categories = [
        {"id": "2392", "name": "Глушники", "path": "2352>2392"},
        {"id": "2402", "name": "Масла моторні", "path": "2352>2402"}, 
        {"id": "2394", "name": "Розпродаж", "path": "2352>2394"},
        {"id": "2396", "name": "Шоломи", "path": "2395>2396"},
        {"id": "2401", "name": "Фільтри автомобільні", "path": "2352>2401"}
    ]
    
    test_inputs = [
        "Глушители автомобильные",
        "Моторное масло синтетическое", 
        "Товары со скидкой",
        "Шлемы мотоциклетные",
        "Фильтры воздушные для авто"
    ]
    
    matcher = SmartMatcher()
    
    print("=== ТЕСТ УМНОГО СОПОСТАВЛЕНИЯ ===")
    for input_cat in test_inputs:
        print(f"\nВходная категория: '{input_cat}'")
        matches = matcher.find_smart_matches(input_cat, reference_categories, top_k=3)
        
        for i, (ref_cat, score, reason) in enumerate(matches, 1):
            explanation = matcher.explain_match(input_cat, ref_cat, score, reason)
            print(f"  {i}. {ref_cat['name']} - {explanation}")


if __name__ == "__main__":
    test_smart_matcher()