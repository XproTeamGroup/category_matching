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
                
                result = self._parse_hierarchical_response(response.content[0].text)
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
        """Системный промпт для иерархического сопоставления"""
        return """Ты - эксперт по классификации иерархических товарных категорий. Твоя задача - сопоставить входные категории с существующими категориями из справочника с учетом иерархической структуры.

ПРАВИЛА СОПОСТАВЛЕНИЯ:
1. Ищи точные совпадения названий в контексте их иерархии
2. Учитывай полный путь категорий (full_path) для правильного понимания контекста
3. Если категория "Аксесуари" есть в разных ветках, выбирай ту, которая соответствует контексту входной категории
4. Анализируй родительские категории для понимания правильной области применения
5. Для неоднозначных случаев выбирай наиболее подходящую категорию по контексту
6. Если категория не подходит ни к одной - возвращай null для match_id

ВАЖНО: Обращай особое внимание на исходный контекст (original_context) входных категорий - это поможет понять в какую ветку справочника они должны попасть.

ФОРМАТ ОТВЕТА - строго JSON:
{
    "matches": [
        {
            "input_id": "123",
            "match_id": "2392",
            "match_name": "Аксесуари",
            "confidence": 0.95,
            "reasoning": "Сопоставление по контексту: входная категория из ветки мотоциклов соответствует аксессуарам для мотоциклов"
        }
    ]
}"""
    
    def _build_hierarchical_prompt(self, reference_categories: List[Dict], 
                                 input_categories: List[Dict]) -> str:
        """Построение промпта для иерархического сопоставления"""
        
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
                f"Full Path: {cat['full_path']}, Original Context: {cat['original_context']}"
            )
        
        return f"""СПРАВОЧНИК КАТЕГОРИЙ (с иерархией):
{chr(10).join(ref_formatted)}

КАТЕГОРИИ ДЛЯ СОПОСТАВЛЕНИЯ (с исходным контекстом):
{chr(10).join(input_formatted)}

Сопоставь каждую входную категорию с наиболее подходящей из справочника, учитывая иерархический контекст. Верни результат в указанном JSON формате."""
    
    def _parse_hierarchical_response(self, response_text: str) -> Dict:
        """Парсинг ответа для иерархического сопоставления"""
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
                required_fields = ['input_id', 'match_id', 'match_name', 'confidence', 'reasoning']
                for field in required_fields:
                    if field not in match:
                        logger.warning(f"Match missing field: {field}")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse hierarchical JSON response: {e}")
            logger.error(f"Response text: {response_text}")
            return {"matches": [], "error": f"JSON parsing failed: {e}"}
        except Exception as e:
            logger.error(f"Failed to process hierarchical response: {e}")
            return {"matches": [], "error": f"Response processing failed: {e}"}