import os
import json
import requests
from typing import Optional

SYSTEM_PROMPT = """Ты — ассистент для извлечения информации о мероприятиях из текста постов.
Твоя задача — извлечь из текста поста структурированные данные в формате JSON.

Поля:
- "name": краткое название мероприятия (на русском)
- "date": дата проведения (формат YYYY-MM-DD). Если в тексте нет явной даты — "уточняйте"
- "price_from": минимальная цена в рублях (число), если есть "от N руб". Иначе null.
- "price_fixed": фиксированная цена в рублях (число), если цена фиксирована. Иначе null.
- "description": 1-2 предложения о мероприятии.

Если в посте вообще нет анонса мероприятия (это реклама, новость, опрос и т.п.) — верни {"skip": true}.
ВАЖНО: возвращай ТОЛЬКО валидный JSON, без комментариев, markdown-обёртки и пояснений."""


class AIExtractor:
    """Класс для извлечения данных через бесплатные LLM"""
    
    def __init__(self, provider: str, api_key: str = "", model: str = ""):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.session = requests.Session()
    
    def extract(self, text: str) -> Optional[dict]:
        """Отправляет текст в ИИ и парсит ответ"""
        if not text or len(text.strip()) < 20:
            return None
        
        # Убираем HTML-теги
        import re
        text = re.sub(r'<[^>]+>', '', text)
        
        if self.provider == "groq":
            return self._call_groq(text)
        elif self.provider == "openrouter":
            return self._call_openrouter(text)
        elif self.provider == "ollama":
            return self._call_ollama(text)
        else:
            # Fallback — простой regex-парсер без ИИ
            return self._fallback_parse(text)
    
    def _call_groq(self, text: str) -> Optional[dict]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model or "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:4000]},
            ],
            "temperature": 0.1,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=30)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"  ⚠ Groq error: {e}")
            return self._fallback_parse(text)
    
    def _call_openrouter(self, text: str) -> Optional[dict]:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model or "google/gemini-2.0-flash-exp:free",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:4000]},
            ],
            "temperature": 0.1,
        }
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=45)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            # OpenRouter не всегда возвращает JSON-объект
            content = content.strip().strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
            return json.loads(content)
        except Exception as e:
            print(f"  ⚠ OpenRouter error: {e}")
            return self._fallback_parse(text)
    
    def _call_ollama(self, text: str) -> Optional[dict]:
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": self.model or "llama3.1:8b",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:4000]},
            ],
            "stream": False,
            "format": "json",
        }
        try:
            r = self.session.post(url, json=payload, timeout=120)
            r.raise_for_status()
            content = r.json()["message"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"  ⚠ Ollama error: {e}")
            return self._fallback_parse(text)
    
    def _fallback_parse(self, text: str) -> Optional[dict]:
        """Простой парсер без ИИ — работает когда ИИ недоступен"""
        import re
        from datetime import datetime
        
        text_lower = text.lower()
        
        # Пропускаем явную рекламу/опросы
        skip_keywords = ["опрос", "реклама", "партнёр", "подпишись"]
        if any(k in text_lower for k in skip_keywords):
            return {"skip": True}
        
        # Ищем дату
        date = "уточняйте"
        date_patterns = [
            r'(\d{1,2})[.\s]+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(\d{4}))?',
            r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})',
        ]
        months = {'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,
                  'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}
        for p in date_patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                if m.group(2).lower() in months:
                    day = int(m.group(1))
                    mon = months[m.group(2).lower()]
                    year = int(m.group(3)) if m.group(3) else datetime.now().year
                    date = f"{year:04d}-{mon:02d}-{day:02d}"
                else:
                    date = f"{m.group(3)}-{m.group(2):>02}-{m.group(1):>02}"
                break
        
        # Ищем цену
        price_from = None
        price_fixed = None
        price_match = re.search(r'(?:от|с)\s+(\d[\d\s]*)\s*(?:руб|₽|р)', text, re.IGNORECASE)
        if price_match:
            price_from = int(re.sub(r'\D', '', price_match.group(1)))
        else:
            price_match = re.search(r'(\d[\d\s]*)\s*(?:руб|₽|р)(?:\w*\s*)?(?:билет|вход|стоим|цена)', text, re.IGNORECASE)
            if price_match:
                price_fixed = int(re.sub(r'\D', '', price_match.group(1)))
        
        # Ищем название (первая строка или после даты)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        name = lines[0][:100] if lines else "Мероприятие"
        
        return {
            "name": name,
            "date": date,
            "price_from": price_from,
            "price_fixed": price_fixed,
            "description": text[:300],
        }