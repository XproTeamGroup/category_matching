import json
import logging
import asyncio
from typing import List, Dict, Optional
import anthropic
from config.settings import (
    CLAUDE_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT, 
    USER_PROMPT_TEMPLATE, MAX_RETRIES, RETRY_DELAY
)


logger = logging.getLogger(__name__)


class ClaudeAPIClient:
    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=api_key or CLAUDE_API_KEY
        )
        self.model = CLAUDE_MODEL
        self.max_retries = MAX_RETRIES
        self.retry_delay = RETRY_DELAY
    
    async def match_batch(self, reference_categories: List[Dict], 
                         input_categories: List[Dict]) -> Dict:
        """Отправка батча категорий на сопоставление"""
        prompt = self._build_prompt(reference_categories, input_categories)
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Sending batch of {len(input_categories)} categories to Claude API")
                
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    system=SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": prompt
                    }]
                )
                
                result = self._parse_response(response.content[0].text)
                logger.info(f"Successfully processed batch with {len(result.get('matches', []))} matches")
                return result
                
            except anthropic.APIError as e:
                logger.warning(f"API error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise
    
    async def match_hierarchical_batch(self, reference_categories: List[Dict], 
                                     input_categories: List[Dict]) -> Dict:
        """Отправка иерархического батча категорий на сопоставление"""
        prompt = self._build_hierarchical_prompt(reference_categories, input_categories)
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Sending hierarchical batch of {len(input_categories)} categories to Claude API")
                
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=6000,  # Больше токенов для иерархических данных
                    system=self._get_hierarchical_system_prompt(),
                    messages=[{
                        "role": "user",
                        "content": prompt
                    }]
                )
                
                result = self._parse_hierarchical_response(response.content[0].text, reference_categories)
                logger.info(f"Successfully processed hierarchical batch with {len(result.get('matches', []))} matches")
                return result
                
            except anthropic.APIError as e:
                logger.warning(f"API error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise
    
    def _build_prompt(self, reference_categories: List[Dict], 
                     input_categories: List[Dict]) -> str:
        """Построение промпта для Claude API"""
        
        # Форматируем справочные категории
        ref_formatted = []
        for cat in reference_categories:
            ref_formatted.append(f"ID: {cat['id']}, Name: {cat['name']}, Path: {cat['path']}")
        
        # Форматируем входные категории
        input_formatted = []
        for i, cat in enumerate(input_categories, 1):
            input_formatted.append(f"{i}. {cat['name']}")
        
        return USER_PROMPT_TEMPLATE.format(
            reference_categories="\n".join(ref_formatted),
            input_categories="\n".join(input_formatted)
        )
    
    def _parse_response(self, response_text: str) -> Dict:
        """Парсинг ответа от Claude API"""
        try:
            # Извлекаем JSON из ответа
            response_text = response_text.strip()
            
            # Находим JSON блок в ответе
            if '```json' in response_text:
                start = response_text.find('```json') + 7
                end = response_text.find('```', start)
                json_text = response_text[start:end].strip()
            elif response_text.startswith('{'):
                json_text = response_text
            else:
                # Пытаемся найти JSON в тексте
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                json_text = response_text[start:end]
            
            result = json.loads(json_text)
            
            # Валидируем структуру ответа
            if 'matches' not in result:
                raise ValueError("Response missing 'matches' field")
            
            for match in result['matches']:
                required_fields = ['input_name', 'match_id', 'match_name', 'confidence', 'reasoning']
                for field in required_fields:
                    if field not in match:
                        logger.warning(f"Match missing field: {field}")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response text: {response_text}")
            return {"matches": [], "error": f"JSON parsing failed: {e}"}
        except Exception as e:
            logger.error(f"Failed to process response: {e}")
            return {"matches": [], "error": f"Response processing failed: {e}"}
    
    def _get_hierarchical_system_prompt(self) -> str:
        """Простой и качественный системный промпт для ЛОГИЧЕСКОГО сопоставления"""
        return """Ты - эксперт по логическому сопоставлению товарных категорий. Твоя задача - найти ЛОГИЧЕСКИ ПОДХОДЯЩЕЕ соответствие или отказаться, если его нет.

ПРИНЦИПЫ ЛОГИЧЕСКОГО СОПОСТАВЛЕНИЯ:

1. ОСНОВНОЙ ПРИНЦИП:
   - НЕ ищи точную схожесть названий
   - Ищи ЛОГИЧЕСКОЕ СООТВЕТСТВИЕ по предназначению товара
   - Если сомневаешься - лучше НЕ сопоставлять

2. ЗАЩИТНЫЕ ЭЛЕМЕНТЫ (ВЫСОКИЙ ПРИОРИТЕТ):
   - "Накладки на лікті" = "Захист ліктів" (одинаковое предназначение)
   - "Накладки на коліна" = "Наколінники / ортези" (защита колен)
   - "Накладки на зап'ястя" = "Захист зап'ясть" (защита запястий)
   - "Наколінники та ортези" = "Наколінники / ортези" (точное соответствие)

3. ОДЕЖДА И ЭКИПИРОВКА:
   - Сопоставляй ТОЛЬКО в рамках "Екіпірування та одяг"
   - Учитывай назначение: дождевые, летние, термобелье и т.д.
   - "Кофти з протекторами" → "Кофти" (основной товар - кофта)

4. БРЭНДЫ И МОДЕЛИ:
   - Сопоставляй ТОЛЬКО к листовым категориям (is_leaf: true)
   - Интерком брэнды → ищи подходящую листовую категорию в интеркомах
   - Если нет подходящей листовой - НЕ сопоставляй

5. СТРОГИЕ ПРАВИЛА ОТКАЗА:
   - НЕ сопоставляй разные семантические группы (одежда ≠ электроника)
   - НЕ сопоставляй к родительским (не листовым) категориям
   - НЕ выдумывай связи - если нет логики, возвращай null
   - Лучше НЕ сопоставить, чем сопоставить неправильно

ПРИМЕРЫ ПРАВИЛЬНЫХ РЕШЕНИЙ:
✓ "Накладки на лікті" → "Захист ліктів" (защита локтей)
✓ "Балаклави та коміри" → "Балаклави і коміри" (одинаковый товар)
✗ "Дощовики > Рукавички" → НЕ сопоставлять с "Літні" (дождевые ≠ летние)
✗ "Midland" интеркомы → НЕ сопоставлять с "Midland" камеры (разные товары)

ФОРМАТ ОТВЕТА - строго JSON:
{
    "matches": [
        {
            "input_id": "123",
            "match_id": "2392", // или null если НЕТ логического соответствия
            "match_name": "Назва категорії", // или null
            "confidence": 0.9, // высокая для логических соответствий, низкая для сомнительных
            "reasoning": "Краткое объяснение логики или причин отказа"
        }
    ]
}"""
    
    def _build_hierarchical_prompt(self, reference_categories: List[Dict], 
                                 input_categories: List[Dict]) -> str:
        """Построение улучшенного промпта для строгого иерархического сопоставления"""
        
        # Форматируем справочные категории с полными путями
        ref_formatted = []
        for cat in reference_categories:
            ref_formatted.append(
                f"ID: {cat['id']}, Name: {cat['name']}, Path: {cat['path']}, "
                f"Full Path: {cat['full_path']}, Leaf: {cat['is_leaf']}"
            )
        
        # Форматируем входные категории с их контекстом
        input_formatted = []
        for cat in input_categories:
            input_formatted.append(
                f"ID: {cat['id']}, Name: {cat['name']}, Path: {cat['path']}, "
                f"Full Path: {cat['full_path']}, Context: {cat['original_context']}"
            )
        
        return f"""СПРАВОЧНИК КАТЕГОРИЙ для сопоставления:
{chr(10).join(ref_formatted)}

ВХОДНЫЕ КАТЕГОРИИ для анализа:
{chr(10).join(input_formatted)}

ВАЖНО: Для каждой входной категории:
1. ПРОАНАЛИЗИРУЙ полную иерархическую цепочку (Full Path)
2. НАЙДИ семантически совместимые категории в справочнике
3. ПРОВЕРЬ логическую корректность сопоставления
4. ЕСЛИ нет подходящего логического соответствия - верни null для match_id
5. НЕ сопоставляй категории из разных семантических групп (одежда ≠ электроника)

Пример правильного анализа:
- Входная: "Одяг > Дощовики > Куртки" → ищем в справочнике дождевые куртки или водонепроницаемые куртки
- Если находим только "Куртки > Зимние" - это НЕ подходит, возвращаем null
- Если находим "Екіпірування > Куртки > Дощові" - это ПОДХОДИТ

Верни результат в строгом JSON формате с детальным обоснованием каждого решения."""
    
    def _parse_hierarchical_response(self, response_text: str, reference_categories: List[Dict] = None) -> Dict:
        """Улучшенный парсинг ответа для иерархического сопоставления с валидацией"""
        try:
            # Извлекаем JSON из ответа
            response_text = response_text.strip()
            
            # Находим JSON блок в ответе
            if '```json' in response_text:
                start = response_text.find('```json') + 7
                end = response_text.find('```', start)
                json_text = response_text[start:end].strip()
            elif response_text.startswith('{'):
                json_text = response_text
            else:
                # Пытаемся найти JSON в тексте
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                json_text = response_text[start:end]
            
            result = json.loads(json_text)
            
            # Валидируем структуру ответа
            if 'matches' not in result:
                raise ValueError("Response missing 'matches' field")
            
            # Создаем индекс листовых категорий для валидации
            leaf_categories = {}
            if reference_categories:
                for cat in reference_categories:
                    if cat.get('is_leaf', False):
                        leaf_categories[cat['id']] = cat

            # Валидируем и очищаем matches
            validated_matches = []
            for match in result['matches']:
                required_fields = ['input_id', 'confidence', 'reasoning']
                if not all(field in match for field in required_fields):
                    logger.warning(f"Match missing required fields, skipping: {match}")
                    continue
                
                # Проверяем корректность match_id
                if match.get('match_id') is None or match.get('match_id') == 'null':
                    # Это правильный случай когда AI отказался от сопоставления
                    match['match_id'] = None
                    match['match_name'] = None
                    logger.info(f"AI refused to match input_id {match['input_id']}: {match['reasoning']}")
                else:
                    # Проверяем что сопоставили к листовой категории
                    match_id = match.get('match_id')
                    if match_id and reference_categories and match_id not in leaf_categories:
                        logger.warning(f"AI matched to non-leaf category {match_id} for input_id {match['input_id']}, rejecting match")
                        match['match_id'] = None
                        match['match_name'] = None
                        match['reasoning'] += " (Отклонено: сопоставление к не-листовой категории)"
                
                # Проверяем уверенность
                confidence = match.get('confidence', 0.0)
                if confidence < 0.0 or confidence > 1.0:
                    logger.warning(f"Invalid confidence {confidence}, clamping to [0.0, 1.0]")
                    match['confidence'] = max(0.0, min(1.0, confidence))
                
                validated_matches.append(match)
            
            result['matches'] = validated_matches
            logger.info(f"Validated {len(validated_matches)} matches from AI response")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse hierarchical JSON response: {e}")
            logger.error(f"Response text: {response_text}")
            return {"matches": [], "error": f"JSON parsing failed: {e}"}
        except Exception as e:
            logger.error(f"Failed to process hierarchical response: {e}")
            return {"matches": [], "error": f"Response processing failed: {e}"}