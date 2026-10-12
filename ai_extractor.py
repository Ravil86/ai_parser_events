import json
import re
import time
import requests
from typing import Optional
from datetime import datetime, timedelta
from logger_config import logger

SYSTEM_PROMPT = """Ты — ассистент для извлечения информации о мероприятиях из постов VK.
Верни JSON вида: {"events": [{"name": "название", "date": "YYYY-MM-DD", "time": "19:00" или null, "location": "место" или null, "price_from": число или null, "price_fixed": число или null, "description": "1-2 предложения"}]}
Если нет анонсов — {"events": []}. "600 р.с человека" = price_from: 600. ТОЛЬКО валидный JSON."""

FEW_SHOT_EXAMPLES = """
Пример 1: 🗓 08 сентября | 19:00\n📍 STING\n💰 600р с игрока.\n💥Туц Туц QUIZ
Вывод: {"events": [{"name": "Туц Туц QUIZ", "date": "2026-09-08", "time": "19:00", "location": "STING", "price_from": 600}]}
"""

class AIExtractor:
    def __init__(self, provider: str, api_key: str = "", model: str = ""):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.session = requests.Session()
        self.stats = {"total_calls": 0, "successful_calls": 0, "failed_calls": 0, "fallback_calls": 0, "total_time": 0.0, "events_found_via_ai": 0, "events_found_via_fallback": 0}
    
    def extract(self, text: str) -> list[dict]:
        if not text or len(text.strip()) < 20:
            return []
        text = re.sub(r'<[^>]+>', '', text)
        
        self.stats["total_calls"] += 1
        start_time = time.time()
        logger.debug(f"🤖 [{self.provider.upper()}] Запрос ({len(text)} симв.)")
        
        try:
            if self.provider == "groq": result = self._call_groq(text)
            elif self.provider == "openrouter": result = self._call_openrouter(text)
            elif self.provider == "ollama": result = self._call_ollama(text)
            elif self.provider == "qwen": result = self._call_qwen(text)
            elif self.provider == "together": result = self._call_together(text)
            else: result = None
            
            elapsed = time.time() - start_time
            self.stats["total_time"] += elapsed
            
            if result and isinstance(result, dict):
                events = result.get("events", []) if "events" in result else ([result] if not result.get("skip") else [])
                self.stats["successful_calls"] += 1
                self.stats["events_found_via_ai"] += len(events)
                logger.info(f"✅ [{self.provider.upper()}] Ответ за {elapsed:.2f}s | Событий: {len(events)}")
                return events
            raise ValueError("Пустой ответ от ИИ")
            
        except Exception as e:
            elapsed = time.time() - start_time
            self.stats["failed_calls"] += 1
            self.stats["total_time"] += elapsed
            logger.warning(f"❌ [{self.provider.upper()}] Ошибка за {elapsed:.2f}s: {e}")
            
            fallback_events = self._fallback(text)
            self.stats["fallback_calls"] += 1
            self.stats["events_found_via_fallback"] += len(fallback_events)
            if fallback_events:
                logger.info(f"🔄 Fallback нашёл событий: {len(fallback_events)}")
            return fallback_events

    def _call_ollama(self, text: str) -> dict:
        r = self.session.post("http://localhost:11434/api/chat", json={
            "model": self.model or "qwen2.5:14b",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\n" + text[:4000]}],
            "stream": False, "format": "json",
        }, timeout=120)
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])

    def _call_groq(self, text: str) -> dict:
        r = self.session.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={
            "model": self.model or "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\n" + text[:4000]}],
            "temperature": 0.1, "max_tokens": 1000, "response_format": {"type": "json_object"},
        }, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _call_openrouter(self, text: str) -> dict:
        r = self.session.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={
            "model": self.model or "qwen/qwen-2.5-72b-instruct", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\n" + text[:4000]}], "temperature": 0.1,
        }, timeout=45)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip().strip("`")
        if content.startswith("json"): content = content[4:].strip()
        return json.loads(content)

    def _call_qwen(self, text: str) -> dict:
        r = self.session.post("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={
            "model": self.model or "qwen-plus", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\n" + text[:4000]}], "temperature": 0.1, "response_format": {"type": "json_object"},
        }, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _call_together(self, text: str) -> dict:
        r = self.session.post("https://api.together.xyz/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={
            "model": self.model or "Qwen/Qwen2.5-72B-Instruct", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\n" + text[:4000]}], "temperature": 0.1, "response_format": {"type": "json_object"},
        }, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _fallback(self, text: str) -> list[dict]:
        logger.debug("🔧 Запуск fallback-парсера (regex)")
        lower = text.lower()
        if any(k in lower for k in ("опрос", "реклама", "партнёр")): return []
        
        MONTHS = {'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}
        today = datetime.now()
        
        def parse_date(s):
            m = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', s)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return datetime(y+2000 if y<100 else y, mo, d).strftime("%Y-%m-%d")
            m = re.match(r'(\d{1,2})\s+([а-яё]+)', s, re.I)
            if m and m.group(2).lower() in MONTHS:
                return datetime(today.year + (1 if MONTHS[m.group(2).lower()] < today.month else 0), MONTHS[m.group(2).lower()], int(m.group(1))).strftime("%Y-%m-%d")
            return None

        def parse_time(s):
            m = re.search(r'(\d{1,2})[:.](\d{2})', s)
            return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None

        def parse_price(s):
            p = re.search(r'(\d[\d\s]*)\s*(?:р|руб|₽)[.\s]*(?:с\s*)?(?:человека|игрока|чел|перс)', s, re.I)
            if p: return int(re.sub(r'\D', '', p.group(1))), None
            p = re.search(r'(?:стоимость|цена|вход)[:\s]*(\d[\d\s]*)\s*(?:руб|₽|р)', s, re.I)
            if p: return None, int(re.sub(r'\D', '', p.group(1)))
            return None, None

        def extract_location(s):
            m = re.search(r'📍\s*([^\n,|]+)', s)
            if m: return m.group(1).strip()
            m = re.match(r'^([A-Za-zА-Яа-яёЁ0-9\s\'"·\-]+),\s*\d{1,2}[:.]\d{2}', s.strip())
            return m.group(1).strip() if m and len(m.group(1)) > 2 else None

        matches = list(re.compile(r'(?m)^(?:[👉🗓📅]\s*)?(?:(\d{1,2})[.\s]+([а-яё]+)|(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4}))', re.I).finditer(text))
        if not matches: return []

        g_pf, g_pfix = parse_price(text)
        g_loc = extract_location(text)
        events = []
        
        for i, m in enumerate(matches):
            block = text[m.start():matches[i+1].start() if i+1 < len(matches) else len(text)]
            date = parse_date(block.split('\n')[0])
            if not date: continue
            
            loc = g_loc
            for line in block.split('\n')[1:4]:
                if extract_location(line): loc = extract_location(line); break
                
            pf, pfix = parse_price(block)
            name = "Мероприятие"
            for line in block.split('\n'):
                clean = re.sub(r'^[💥✨🎉🔥⭐️📍👉🗓📅💰💵👭👥]+\s*', '', line).strip()
                if len(clean) > 3 and not re.match(r'^\d', clean): name = clean[:120]; break
                
            events.append({"name": name, "date": date, "time": parse_time(block), "location": loc, "price_from": pf or g_pf, "price_fixed": pfix or g_pfix, "description": block[:300]})
        return events

    def get_stats_summary(self) -> dict:
        avg = self.stats["total_time"] / self.stats["total_calls"] if self.stats["total_calls"] > 0 else 0
        return {**self.stats, "avg_response_time": round(avg, 2), "provider": self.provider, "model": self.model}