import json
import re
import time
import requests
from typing import Optional
from datetime import datetime, timedelta

from logger_config import logger

SYSTEM_PROMPT = """Ты — ассистент для извлечения информации о мероприятиях из постов VK.
В одном посте может быть ОДНО или НЕСКОЛЬКО мероприятий (список игр).

Верни JSON вида:
{
  "events": [
    {
      "name": "название",
      "date": "YYYY-MM-DD",
      "time": "19:00" или null,
      "location": "название места" или null,
      "price_from": число или null,
      "price_fixed": число или null,
      "description": "1-2 предложения"
    }
  ]
}

Если в посте нет анонсов — {"events": []}.
Если нет года — используй текущий. Относительные даты ("завтра") — тоже текущий год.
"600 р.с человека" = price_from: 600. "Стоимость: 600р" = price_from: 600.
ТОЛЬКО валидный JSON без markdown."""

FEW_SHOT_EXAMPLES = """
Пример 1 (пост с одной игрой):
Ввод: 🗓 08 сентября | 19:00\n📍 STING\n💰 600р с игрока.\n💥Туц Туц QUIZ
Вывод: {"events": [{"name": "Туц Туц QUIZ", "date": "2026-09-08", "time": "19:00", "location": "STING", "price_from": 600}]}

Пример 2 (список игр):
Ввод: 👉1 октября, четверг\nПланета, 19:00\n💥Туц Туц\n👉4 октября\nChester Pub, 17:00\n✨Мозгобойня
Вывод: {"events": [
  {"name": "Туц Туц", "date": "2026-10-01", "time": "19:00", "location": "Планета"},
  {"name": "Мозгобойня", "date": "2026-10-04", "time": "17:00", "location": "Chester Pub"}
]}

Пример 3
Ввод: 📍29 октября , ЧЕТВЕРГ\n📍Harat’s pub\n📍сбор в 19:00 , в 19.15 начинаем отвечать на вопросы\n\nРегистрируйтесь:\n📎в комментариях под этим постом.\nСтоимость участия - 600 р.с человека.
Вывод: {"events": [{"name": "Квиз Эйнштейн Party | ХАНТЫ-МАНСИЙСК |", "date": "2026-09-29", "time": "19:00", "location": "Harat’s pub", "price_from": 600}]}
"""

class AIExtractor:
    def __init__(self, provider: str, api_key: str = "", model: str = ""):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.session = requests.Session()
        
        # Статистика работы ИИ
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "fallback_calls": 0,
            "total_time": 0.0,
            "events_found_via_ai": 0,
            "events_found_via_fallback": 0,
        }
    
    def extract(self, text: str) -> list[dict]:
        """Возвращает список событий из поста."""
        if not text or len(text.strip()) < 20:
            return []
        text = re.sub(r'<[^>]+>', '', text)
        
        self.stats["total_calls"] += 1
        start_time = time.time()
        
        # Логируем начало запроса
        text_preview = text[:200].replace('\n', ' ').strip()
        logger.debug(f"🤖 [{self.provider.upper()}] Отправляем запрос ({len(text)} символов)")
        logger.debug(f"   Текст: {text_preview}...")
        
        try:
            if self.provider == "groq":
                result = self._call_groq(text)
            elif self.provider == "openrouter":
                result = self._call_openrouter(text)
            elif self.provider == "ollama":
                result = self._call_ollama(text)
            elif self.provider == "qwen":
                result = self._call_qwen(text)
            elif self.provider == "together":
                result = self._call_together(text)
            else:
                result = None
            
            elapsed = time.time() - start_time
            self.stats["total_time"] += elapsed
            
            if result and isinstance(result, dict):
                events = result.get("events", []) if "events" in result else ([result] if not result.get("skip") else [])
                self.stats["successful_calls"] += 1
                self.stats["events_found_via_ai"] += len(events)
                
                logger.info(f"✅ [{self.provider.upper()}] Ответ за {elapsed:.2f}s | Найдено событий: {len(events)}")
                logger.debug(f"   JSON: {json.dumps(result, ensure_ascii=False)[:500]}")
                
                return events
            else:
                raise ValueError("Пустой или некорректный ответ от ИИ")
                
        except Exception as e:
            elapsed = time.time() - start_time
            self.stats["failed_calls"] += 1
            self.stats["total_time"] += elapsed
            
            logger.warning(f"❌ [{self.provider.upper()}] Ошибка за {elapsed:.2f}s: {e}")
            logger.info(f"⚠️  Переключаемся на fallback-парсер")
            
            fallback_events = self._fallback(text)
            self.stats["fallback_calls"] += 1
            self.stats["events_found_via_fallback"] += len(fallback_events)
            
            if fallback_events:
                logger.info(f"🔄 Fallback нашёл событий: {len(fallback_events)}")
            
            return fallback_events

    def _call_groq(self, text: str) -> dict:
        r = self.session.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model or "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\nТеперь обработай:\n" + text[:4000]},
                ],
                "temperature": 0.1,
                "max_tokens": 1000,
                "response_format": {"type": "json_object"},
            }, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _call_openrouter(self, text: str) -> dict:
        r = self.session.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model or "google/gemini-2.0-flash-exp:free",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\nТеперь обработай:\n" + text[:4000]},
                ],
                "temperature": 0.1,
            }, timeout=45)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip().strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
        return json.loads(content)

    def _call_ollama(self, text: str) -> dict:
        r = self.session.post("http://localhost:11434/api/chat", json={
            "model": self.model or "llama3.1:8b",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\nТеперь обработай:\n" + text[:4000]},
            ],
            "stream": False, "format": "json",
        }, timeout=120)
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])

    def _call_qwen(self, text: str) -> dict:
        r = self.session.post("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model or "qwen-plus",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\nТеперь обработай:\n" + text[:4000]},
                ],
                "temperature": 0.1,
                "max_tokens": 1000,
                "response_format": {"type": "json_object"},
            }, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _call_together(self, text: str) -> dict:
        r = self.session.post("https://api.together.xyz/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model or "Qwen/Qwen2.5-72B-Instruct",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": FEW_SHOT_EXAMPLES + "\n\nТеперь обработай:\n" + text[:4000]},
                ],
                "temperature": 0.1,
                "max_tokens": 1000,
                "response_format": {"type": "json_object"},
            }, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _fallback(self, text: str) -> list[dict]:
        """Умный fallback-парсер без ИИ."""
        logger.debug("🔧 Запуск fallback-парсера (regex)")
        
        lower = text.lower()
        if any(k in lower for k in ("опрос", "реклама", "партнёр", "подпишись")):
            return []

        MONTHS = {
            'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,
            'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12,
            'январь':1,'февраль':2,'март':3,'апрель':4,'май':5,'июнь':6,
            'июль':7,'август':8,'сентябрь':9,'октябрь':10,'ноябрь':11,'декабрь':12
        }

        today = datetime.now()

        def parse_date(s: str) -> str | None:
            s = s.strip()
            if "завтра" in s.lower():
                return (today + timedelta(days=1)).strftime("%Y-%m-%d")
            if "послезавтра" in s.lower():
                return (today + timedelta(days=2)).strftime("%Y-%m-%d")
            if "сегодня" in s.lower():
                return today.strftime("%Y-%m-%d")

            m = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', s)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                try:
                    return datetime(y, mo, d).strftime("%Y-%m-%d")
                except ValueError:
                    pass

            m = re.match(r'(\d{1,2})\s+([а-яё]+)', s, re.I)
            if m:
                day = int(m.group(1))
                mon_name = m.group(2).lower()
                if mon_name in MONTHS:
                    year = today.year
                    if MONTHS[mon_name] < today.month:
                        year += 1
                    try:
                        return datetime(year, MONTHS[mon_name], day).strftime("%Y-%m-%d")
                    except ValueError:
                        pass
            return None

        def parse_time(s: str) -> str | None:
            m = re.search(r'(\d{1,2})[:.](\d{2})', s)
            if m:
                return f"{int(m.group(1)):02d}:{m.group(2)}"
            return None

        def parse_price(s: str) -> tuple[int|None, int|None]:
            p = re.search(r'(\d[\d\s]*)\s*(?:р|руб|₽)[.\s]*(?:с\s*)?(?:человека|игрока|чел|перс|с\s+чел)', s, re.I)
            if p:
                return int(re.sub(r'\D', '', p.group(1))), None
            p = re.search(r'от\s+(\d[\d\s]*)\s*(?:руб|₽|р)', s, re.I)
            if p:
                return int(re.sub(r'\D', '', p.group(1))), None
            p = re.search(r'(?:стоимость|цена|вход|билет)[:\s]*(\d[\d\s]*)\s*(?:руб|₽|р)', s, re.I)
            if p:
                return None, int(re.sub(r'\D', '', p.group(1)))
            return None, None

        def extract_location(s: str) -> str | None:
            m = re.search(r'📍\s*([^\n,|]+)', s)
            if m:
                return m.group(1).strip()
            m = re.match(r'^([A-Za-zА-Яа-яёЁ0-9\s\'"·\-]+),\s*\d{1,2}[:.]\d{2}', s.strip())
            if m:
                loc = m.group(1).strip()
                if len(loc) > 2 and not re.match(r'^\d+$', loc):
                    return loc
            return None

        date_markers = re.compile(
            r'(?m)^(?:[👉🗓📅🗓️]\s*)?'
            r'(?:(\d{1,2})[.\s]+([а-яё]+|\d{1,2})|(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})|завтра|послезавтра|сегодня)',
            re.I
        )

        matches = list(date_markers.finditer(text))
        if not matches:
            return []

        global_price_from, global_price_fixed = parse_price(text)
        global_location = extract_location(text)

        events = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block = text[start:end]
            date_line = block.split('\n')[0]

            date = parse_date(date_line)
            if not date:
                continue

            time = parse_time(block)
            location = None
            for line in block.split('\n')[1:4]:
                loc = extract_location(line)
                if loc:
                    location = loc
                    break
            if not location:
                location = global_location

            price_from, price_fixed = parse_price(block)
            if not price_from:
                price_from = global_price_from
            if not price_fixed:
                price_fixed = global_price_fixed

            name = None
            for line in block.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if re.match(r'^(👉|🗓|📅|📍|💰|💵|👭|👥)', line):
                    continue
                if re.search(r'\d{1,2}[.:]\d{2}', line) and ',' in line:
                    continue
                if re.match(r'^\d{1,2}[.\s]', line):
                    continue
                clean = re.sub(r'^[💥✨🎉🔥⭐️]+\s*', '', line).strip()
                if len(clean) > 3 and not re.match(r'^(всем привет|привет|друзья)', clean, re.I):
                    name = clean[:120]
                    break
            if not name:
                name = "Мероприятие"

            events.append({
                "name": name,
                "date": date,
                "time": time,
                "location": location,
                "price_from": price_from,
                "price_fixed": price_fixed,
                "description": block[:300],
            })

        return events

    def get_stats_summary(self) -> dict:
        """Возвращает сводку статистики."""
        avg_time = self.stats["total_time"] / self.stats["total_calls"] if self.stats["total_calls"] > 0 else 0
        return {
            **self.stats,
            "avg_response_time": round(avg_time, 2),
            "provider": self.provider,
            "model": self.model,
        }