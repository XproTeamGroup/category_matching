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