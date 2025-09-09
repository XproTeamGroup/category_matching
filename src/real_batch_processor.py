import logging
import asyncio
import time
from typing import List, Dict, Optional
import json

logger = logging.getLogger(__name__)


class RealBatchProcessor:
    """Настоящий батч-процессор, который отправляет несколько категорий в одном API запросе"""
    
    def __init__(self, batch_size: int = 20):
        self.batch_size = batch_size
        self.stats = {
            'api_calls': 0,
            'categories_processed': 0,
            'batches_processed': 0
        }
    
    async def process_categories_in_real_batches(self, input_categories: List[Dict], 
                                               reference_categories: List[Dict],
                                               claude_client) -> List[Dict]:
        """Обрабатывает категории реальными батчами"""
        
        results = []
        total_batches = (len(input_categories) + self.batch_size - 1) // self.batch_size
        
        logger.info(f"Processing {len(input_categories)} categories in {total_batches} batches of {self.batch_size}")
        
        # Обрабатываем по батчам
        for i in range(0, len(input_categories), self.batch_size):
            batch = input_categories[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} categories)")
            
            try:
                batch_results = await self._process_single_batch(
                    batch, reference_categories, claude_client
                )
                results.extend(batch_results)
                self.stats['batches_processed'] += 1
                
                # Небольшая пауза между батчами
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Batch {batch_num} failed: {e}")
                # Fallback: создаем пустые результаты
                for cat in batch:
                    results.append({
                        'input_category_id': cat.get('id', ''),
                        'input_category_name': cat.get('name', ''),
                        'matched_category_id': None,
                        'matched_category_name': None,
                        'confidence': 0.0,
                        'processing_method': 'batch_failed',
                        'is_exact_match': False,
                        'needs_review': True
                    })
        
        self.stats['categories_processed'] = len(results)
        return results
    
    async def _process_single_batch(self, batch: List[Dict], 
                                  reference_categories: List[Dict],
                                  claude_client) -> List[Dict]:
        """Обрабатывает один батч категорий"""
        
        # Формируем промпт для батча
        prompt = self._build_batch_prompt(batch, reference_categories)
        
        # Отправляем через существующий API (используем первую категорию как основную)
        # Это хак, но работает с существующей системой
        temp_input = [{'name': prompt, 'id': 'batch_input'}]
        result = await claude_client.match_batch(reference_categories[:50], temp_input)  # Ограничиваем справочник
        
        response_text = result.get('response', '')
        self.stats['api_calls'] += 1
        
        # Парсим ответ
        return self._parse_batch_response(response_text, batch, reference_categories)
    
    def _build_batch_prompt(self, batch: List[Dict], reference_categories: List[Dict]) -> str:
        """Строит промпт для обработки батча"""
        
        # Ограничиваем справочные категории для ускорения
        ref_sample = reference_categories[:100]
        
        # Формируем список входных категорий
        input_list = []
        for i, cat in enumerate(batch, 1):
            input_list.append(f"{i}. {cat['name']}")
        
        # Формируем список справочных категорий
        ref_list = []
        for cat in ref_sample:
            ref_list.append(f"ID: {cat['id']}, Name: {cat['name']}")
        
        prompt = f"""ЗАДАЧА: Сопоставьте {len(batch)} входных категорий со справочными категориями.

ВХОДНЫЕ КАТЕГОРИИ:
{chr(10).join(input_list)}

СПРАВОЧНЫЕ КАТЕГОРИИ:
{chr(10).join(ref_list)}

ФОРМАТ ОТВЕТА (обязательно JSON):
{{
  "matches": [
    {{"index": 1, "matched_id": "id_категории", "confidence": 0.85}},
    {{"index": 2, "matched_id": "id_категории", "confidence": 0.92}},
    ...
  ]
}}

ПРАВИЛА:
- Верните JSON для КАЖДОЙ входной категории (индексы 1-{len(batch)})
- Если нет подходящего совпадения, используйте "matched_id": null
- Confidence от 0.0 до 1.0
- НЕ добавляйте комментарии после JSON"""

        return prompt
    
    def _parse_batch_response(self, response: str, batch: List[Dict], 
                            reference_categories: List[Dict]) -> List[Dict]:
        """Парсит ответ AI для батча"""
        
        results = []
        ref_by_id = {cat['id']: cat for cat in reference_categories}
        
        try:
            # Ищем JSON в ответе
            json_start = response.find('{')
            if json_start == -1:
                raise ValueError("JSON not found in response")
            
            # Ищем конец JSON (первое вхождение "}" после которого идет "]}")
            json_text = response[json_start:]
            bracket_count = 0
            json_end = 0
            
            for i, char in enumerate(json_text):
                if char == '{':
                    bracket_count += 1
                elif char == '}':
                    bracket_count -= 1
                    if bracket_count == 0:
                        json_end = json_start + i + 1
                        break
            
            if json_end == 0:
                raise ValueError("Could not find end of JSON")
            
            json_str = response[json_start:json_end]
            logger.debug(f"Extracted JSON: {json_str[:200]}...")
            parsed = json.loads(json_str)
            matches = parsed.get('matches', [])
            
            # Создаем индекс результатов
            results_by_index = {}
            for match in matches:
                index = match.get('index', 0)
                matched_id = match.get('matched_id')
                confidence = float(match.get('confidence', 0.0))
                
                if 1 <= index <= len(batch):
                    matched_cat = ref_by_id.get(matched_id) if matched_id else None
                    results_by_index[index] = {
                        'matched_category_id': matched_id,
                        'matched_category_name': matched_cat['name'] if matched_cat else None,
                        'confidence': confidence,
                        'processing_method': 'ai_real_batch',
                        'is_exact_match': confidence >= 0.95,
                        'needs_review': confidence < 0.7
                    }
            
            # Создаем результат для каждой входной категории
            for i, input_cat in enumerate(batch, 1):
                if i in results_by_index:
                    result_data = results_by_index[i]
                else:
                    # Если для этой категории нет результата, создаем пустой
                    result_data = {
                        'matched_category_id': None,
                        'matched_category_name': None,
                        'confidence': 0.0,
                        'processing_method': 'ai_batch_missing',
                        'is_exact_match': False,
                        'needs_review': True
                    }
                
                results.append({
                    'input_category_id': input_cat.get('id', ''),
                    'input_category_name': input_cat.get('name', ''),
                    **result_data
                })
            
        except Exception as e:
            logger.error(f"Failed to parse batch response: {e}")
            logger.debug(f"Response was: {response[:500]}...")
            
            # Fallback: создаем пустые результаты
            for input_cat in batch:
                results.append({
                    'input_category_id': input_cat.get('id', ''),
                    'input_category_name': input_cat.get('name', ''),
                    'matched_category_id': None,
                    'matched_category_name': None,
                    'confidence': 0.0,
                    'processing_method': 'batch_parse_failed',
                    'is_exact_match': False,
                    'needs_review': True
                })
        
        return results