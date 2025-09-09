import logging
import asyncio
import time
import json
from typing import List, Dict, Optional
import anthropic
from config.settings import CLAUDE_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)


class DirectBatchProcessor:
    """Прямой батч-процессор, использующий Anthropic API напрямую"""
    
    def __init__(self, batch_size: int = 20):
        self.batch_size = batch_size
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.model = CLAUDE_MODEL
        self.stats = {
            'api_calls': 0,
            'categories_processed': 0,
            'batches_processed': 0
        }
    
    async def process_categories_direct_batches(self, input_categories: List[Dict], 
                                             reference_categories: List[Dict]) -> List[Dict]:
        """Обрабатывает категории напрямую через Anthropic API"""
        
        # Удаляем дубли по ID
        unique_categories = {}
        for cat in input_categories:
            cat_id = cat.get('id', '')
            if cat_id and cat_id not in unique_categories:
                unique_categories[cat_id] = cat
        
        input_categories = list(unique_categories.values())
        results = []
        total_batches = (len(input_categories) + self.batch_size - 1) // self.batch_size
        
        logger.info(f"Processing {len(input_categories)} unique categories in {total_batches} batches of {self.batch_size}")
        
        # Обрабатываем по батчам
        for i in range(0, len(input_categories), self.batch_size):
            batch = input_categories[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} categories)")
            
            try:
                batch_results = await self._process_single_batch_direct(
                    batch, reference_categories
                )
                results.extend(batch_results)
                self.stats['batches_processed'] += 1
                
                # Небольшая пауза между батчами
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Batch {batch_num} failed: {e}")
                # Fallback: создаем пустые результаты
                for cat in batch:
                    results.append({
                        'input_category_id': cat.get('id', ''),
                        'input_category_name': cat.get('name', ''),
                        'input_name': cat.get('name', ''),
                        'match_id': None,
                        'match_name': None,
                        'confidence': 0.0,
                        'reasoning': 'Ошибка обработки батча',
                        'processing_method': 'batch_failed',
                        'is_exact_match': False,
                        'needs_review': True
                    })
        
        self.stats['categories_processed'] = len(results)
        return results
    
    async def _process_single_batch_direct(self, batch: List[Dict], 
                                         reference_categories: List[Dict]) -> List[Dict]:
        """Обрабатывает один батч через прямой API"""
        
        # Ограичиваем справочные категории для производительности
        ref_sample = reference_categories[:100]
        
        # Формируем промпт
        prompt = self._build_batch_prompt(batch, ref_sample)
        
        # Отправляем напрямую к Anthropic API
        response = await self._send_direct_request(prompt)
        self.stats['api_calls'] += 1
        
        # Парсим ответ
        return self._parse_batch_response(response, batch, reference_categories)
    
    async def _send_direct_request(self, prompt: str) -> str:
        """Отправляет запрос напрямую к Anthropic API"""
        try:
            # Используем синхронный API в отдельном потоке
            def make_request():
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    system="Вы помощник по сопоставлению категорий. Возвращайте только JSON без дополнительных комментариев.",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
                return message.content[0].text
            
            # Выполняем в отдельном потоке
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(make_request)
                response = future.result(timeout=60)
            
            return response
            
        except Exception as e:
            logger.error(f"Direct API request failed: {e}")
            return '{"matches": []}'
    
    def _build_batch_prompt(self, batch: List[Dict], reference_categories: List[Dict]) -> str:
        """Строит промпт для обработки батча"""
        
        # Формируем список входных категорий
        input_list = []
        for i, cat in enumerate(batch, 1):
            input_list.append(f"{i}. {cat['name']}")
        
        # Формируем список справочных категорий
        ref_list = []
        for cat in reference_categories:
            ref_list.append(f"ID: {cat['id']}, Name: {cat['name']}")
        
        prompt = f"""Сопоставьте {len(batch)} входных категорий со справочными категориями.

ВХОДНЫЕ КАТЕГОРИИ:
{chr(10).join(input_list)}

СПРАВОЧНЫЕ КАТЕГОРИИ:
{chr(10).join(ref_list)}

Верните ТОЛЬКО JSON в этом формате:
{{
  "matches": [
    {{"index": 1, "matched_id": "id_или_null", "confidence": 0.85}},
    {{"index": 2, "matched_id": "id_или_null", "confidence": 0.92}},
    ...
  ]
}}

ВАЖНО:
- Верните результат для КАЖДОГО индекса от 1 до {len(batch)}
- Если нет подходящего совпадения, используйте null
- Confidence от 0.0 до 1.0
- НЕ добавляйте комментарии или объяснения, ТОЛЬКО JSON"""

        return prompt
    
    def _parse_batch_response(self, response: str, batch: List[Dict], 
                            reference_categories: List[Dict]) -> List[Dict]:
        """Парсит ответ для батча"""
        
        results = []
        ref_by_id = {cat['id']: cat for cat in reference_categories}
        
        try:
            # Очищаем ответ от лишнего текста
            response = response.strip()
            
            # Ищем JSON
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("JSON not found in response")
            
            json_str = response[json_start:json_end]
            logger.debug(f"Parsing JSON: {json_str[:200]}...")
            
            parsed = json.loads(json_str)
            matches = parsed.get('matches', [])
            
            logger.info(f"Parsed {len(matches)} matches from batch response")
            
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
                        'processing_method': 'ai_direct_batch',
                        'is_exact_match': confidence >= 0.95,
                        'needs_review': confidence < 0.7
                    }
                    
                    if matched_cat:
                        logger.info(f"Match: '{batch[index-1]['name']}' -> '{matched_cat['name']}' ({confidence:.2f})")
            
            # Создаем результат для каждой входной категории
            for i, input_cat in enumerate(batch, 1):
                if i in results_by_index:
                    result_data = results_by_index[i]
                else:
                    result_data = {
                        'matched_category_id': None,
                        'matched_category_name': None,
                        'confidence': 0.0,
                        'processing_method': 'ai_direct_missing',
                        'is_exact_match': False,
                        'needs_review': True
                    }
                
                results.append({
                    'input_category_id': input_cat.get('id', ''),
                    'input_category_name': input_cat.get('name', ''),
                    'input_name': input_cat.get('name', ''),
                    'match_id': result_data['matched_category_id'],
                    'match_name': result_data['matched_category_name'],
                    'confidence': result_data['confidence'],
                    'reasoning': 'AI батч обработка',
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
                    'input_name': input_cat.get('name', ''),
                    'match_id': None,
                    'match_name': None,
                    'confidence': 0.0,
                    'reasoning': 'Ошибка парсинга ответа',
                    'processing_method': 'direct_parse_failed',
                    'is_exact_match': False,
                    'needs_review': True
                })
        
        return results