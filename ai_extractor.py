import requests          # ← ЭТА СТРОКА БЫЛА ПРОПУЩЕНА
import os
import json
import re
import time
import urllib3
from typing import Optional
from datetime import datetime, timedelta
from logger_config import logger

# Отключаем предупреждение о непроверенном HTTPS для прокси по IP
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_prompt(filename: str) -> str:
    """Загружает текст промпта из файла. Если файла нет, возвращает безопасный дефолт."""
    filepath = os.path.join("prompts", filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Ошибка чтения промпта {filename}: {e}")
    
    # Fallback на случай, если файлы еще не созданы
    if filename == "system.txt":
        return "Ты — ассистент для извлечения информации о мероприятиях. Верни СТРОГО валидный JSON с ключом 'events'."
    elif filename == "few_shot.txt":
        return "Пример: Ввод: 🗓 08 сентября | 19:00 📍 STING 💰 600р. Вывод: {\"events\": [{\"name\": \"Мероприятие\", \"date\": \"2026-09-08\", \"time\": \"19:00\", \"location\": \"STING\", \"price_from\": 600}]}"
    return ""

class AIExtractor:
    def __init__(self, provider: str, api_key: str = "", model: str = "", proxy: str = "", config: dict = None, is_fallback: bool = False):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.config = config or {}
        self.is_fallback = is_fallback  # Флаг, чтобы избежать рекурсии
        self.session = requests.Session()
        
        # Настройка прокси
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
            logger.info(f"🌐 Настроен прокси для ИИ запросов")
        
        # Загружаем промпты из файлов
        self.system_prompt = load_prompt("system.txt")
        self.few_shot_examples = load_prompt("few_shot.txt")
        
        # Статистика
        self.stats = {
            "total_calls": 0, "successful_calls": 0, "failed_calls": 0, 
            "fallback_calls": 0, "total_time": 0.0, 
            "events_found_via_ai": 0, "events_found_via_fallback": 0,
            "switched_to_fallback_provider": 0,  # Счётчик переключений
        }
        
        # Создаём fallback-экстрактор (только для основного, чтобы не было рекурсии)
        self.fallback_extractor: Optional[AIExtractor] = None
        if not is_fallback:
            fb_provider = self.config.get("fallback_ai_provider", "")
            fb_api_key = self.config.get("fallback_ai_api_key", "") or os.getenv("FALLBACK_AI_API_KEY", "")
            fb_model = self.config.get("fallback_ai_model", "")
            
            logger.info(f"🔍 Проверка fallback: provider={fb_provider}, api_key={'есть' if fb_api_key else 'НЕТ'}, model={fb_model}")
            
            if fb_provider and fb_api_key:
                self.fallback_extractor = AIExtractor(
                    provider=fb_provider,
                    api_key=fb_api_key,
                    model=fb_model,
                    proxy=proxy,
                    config=self.config,
                    is_fallback=True,  # Важно! Чтобы не было рекурсии
                )
                logger.info(f"🔄 Настроен fallback AI провайдер: {fb_provider.upper()} ({fb_model})")
            else:
                logger.warning(f"⚠️  Fallback AI НЕ настроен (provider={fb_provider}, api_key={'есть' if fb_api_key else 'НЕТ'})")

    def extract(self, text: str) -> list[dict]:
        """Возвращает список событий с учётом rate limiting и fallback-провайдера."""
        if not text or len(text.strip()) < 20:
            return []
        text = re.sub(r'<[^>]+>', '', text)
        
        # Пауза между запросами
        delay = float(self.config.get("ai_delay_between_requests", 3)) if hasattr(self, 'config') else 3.0
        max_retries = int(self.config.get("ai_max_retries", 3)) if hasattr(self, 'config') else 3
        
        if delay > 0 and self.stats["total_calls"] > 0:
            logger.debug(f"⏸️  Пауза {delay}s между запросами к ИИ...")
            time.sleep(delay)
        
        self.stats["total_calls"] += 1
        
        # Попытки с retry
        for attempt in range(max_retries + 1):
            start_time = time.time()
            logger.debug(f"🤖 [{self.provider.upper()}] Запрос ({len(text)} симв.), попытка {attempt + 1}/{max_retries + 1}")
            
            try:
                result = self._call_provider(text)
                elapsed = time.time() - start_time
                self.stats["total_time"] += elapsed
                
                if result and isinstance(result, dict):
                    events = result.get("events", []) if "events" in result else ([result] if not result.get("skip") else [])
                    self.stats["successful_calls"] += 1
                    self.stats["events_found_via_ai"] += len(events)
                    logger.info(f"✅ [{self.provider.upper()}] Ответ за {elapsed:.2f}s | Событий: {len(events)}")
                    return events
                raise ValueError("Пустой ответ от ИИ")
                
            except requests.exceptions.HTTPError as e:
                elapsed = time.time() - start_time
                self.stats["total_time"] += elapsed
                
                if e.response is not None and e.response.status_code == 429:
                    if attempt < max_retries:
                        retry_delay = 5 * (2 ** attempt)
                        logger.warning(f"⏳ [{self.provider.upper()}] Rate limit (429). Пауза {retry_delay}s перед повтором (попытка {attempt + 1}/{max_retries})...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        # Все retry исчерпаны — пробуем fallback-провайдер
                        logger.error(f"❌ [{self.provider.upper()}] Превышен лимит запросов после {max_retries} попыток")
                        self.stats["failed_calls"] += 1
                        
                        if self.fallback_extractor:
                            return self._try_fallback_provider(text)
                        break
                else:
                    logger.warning(f"❌ [{self.provider.upper()}] HTTP ошибка за {elapsed:.2f}s: {e}")
                    self.stats["failed_calls"] += 1
                    
                    # При других критических ошибках тоже пробуем fallback
                    if self.fallback_extractor:
                        return self._try_fallback_provider(text)
                    break
                    
            except Exception as e:
                elapsed = time.time() - start_time
                self.stats["total_time"] += elapsed
                self.stats["failed_calls"] += 1
                logger.warning(f"❌ [{self.provider.upper()}] Ошибка за {elapsed:.2f}s: {e}")
                
                if self.fallback_extractor:
                    return self._try_fallback_provider(text)
                break
        
        # Если ничего не сработало — уходим на regex-fallback
        return self._use_regex_fallback(text)

    def _try_fallback_provider(self, text: str) -> list[dict]:
        """Переключается на fallback AI провайдер."""
        logger.info(f"🔄 Переключаемся на fallback провайдер: {self.fallback_extractor.provider.upper()}")
        self.stats["switched_to_fallback_provider"] += 1
        
        try:
            # У fallback-экстрактора свои retry, но без дальнейшего fallback
            return self.fallback_extractor.extract(text)
        except Exception as e:
            logger.error(f"❌ Fallback провайдер тоже не сработал: {e}")
            return self._use_regex_fallback(text)

    def _use_regex_fallback(self, text: str) -> list[dict]:
        """Использует локальный regex-парсер как последнюю надежду."""
        fallback_events = self._fallback(text)
        self.stats["fallback_calls"] += 1
        self.stats["events_found_via_fallback"] += len(fallback_events)
        if fallback_events:
            logger.info(f"🔄 Regex fallback нашёл событий: {len(fallback_events)}")
        return fallback_events

    def _call_provider(self, text: str) -> dict:
        """Единая точка вызова нужного провайдера."""
        if self.provider == "groq": return self._call_groq(text)
        elif self.provider == "openrouter": return self._call_openrouter(text)
        elif self.provider == "ollama": return self._call_ollama(text)
        elif self.provider == "qwen": return self._call_qwen(text)
        elif self.provider == "together": return self._call_together(text)
        elif self.provider == "yandex": return self._call_yandex(text)
        else: raise ValueError(f"Неизвестный провайдер: {self.provider}")

    def _call_groq(self, text: str) -> dict:
        r = self.session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model or "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self.few_shot_examples + "\n\nТеперь обработай:\n" + text[:4000]},
                ],
                "temperature": 0.1,
                "max_tokens": 1000,
                "response_format": {"type": "json_object"},
            },
            timeout=30
        )
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _call_openrouter(self, text: str) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.68.0",
            "HTTP-Referer": "http://localhost",
            "X-Title": "VK Events Parser"
        }
        r = self.session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": self.model or "qwen/qwen-2.5-72b-instruct",
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self.few_shot_examples + "\n\nТеперь обработай:\n" + text[:4000]},
                ],
                "temperature": 0.1,
            },
            timeout=45
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip().strip("`")
        if content.startswith("json"): content = content[4:].strip()
        return json.loads(content)

    def _call_ollama(self, text: str) -> dict:
        r = self.session.post("http://localhost:11434/api/chat", json={
            "model": self.model or "qwen2.5:14b",
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.few_shot_examples + "\n\n" + text[:4000]},
            ],
            "stream": False, "format": "json",
        }, timeout=120)
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])

    def _call_qwen(self, text: str) -> dict:
        r = self.session.post("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={
            "model": self.model or "qwen-plus",
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.few_shot_examples + "\n\n" + text[:4000]},
            ],
            "temperature": 0.1, "response_format": {"type": "json_object"},
        }, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _call_together(self, text: str) -> dict:
        r = self.session.post("https://api.together.xyz/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={
            "model": self.model or "Qwen/Qwen2.5-72B-Instruct",
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.few_shot_examples + "\n\n" + text[:4000]},
            ],
            "temperature": 0.1, "response_format": {"type": "json_object"},
        }, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _call_yandex(self, text: str) -> dict:
        folder_id = os.getenv("YANDEX_FOLDER_ID", "")
        if not folder_id:
            raise ValueError("YANDEX_FOLDER_ID не указан в .env файле!")

        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        prompt = f"{self.system_prompt}\n\n{self.few_shot_examples}\n\nТекст для обработки:\n{text[:4000]}"

        payload = {
            "modelUri": f"gpt://{folder_id}/yandexgpt/latest",
            "completionOptions": {"stream": False, "temperature": 0.1, "maxTokens": "1000"},
            "messages": [{"role": "user", "text": prompt}]
        }
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        r = self.session.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        result_text = r.json()["result"]["alternatives"][0]["message"]["text"]
        return json.loads(result_text)

    def _fallback(self, text: str) -> list[dict]:
        """Умный fallback-парсер без ИИ (regex)."""
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
        result = {**self.stats, "avg_response_time": round(avg, 2), "provider": self.provider, "model": self.model}
        
        # Добавляем информацию о fallback провайдере, если он есть
        if self.fallback_extractor:
            result["fallback_provider"] = self.fallback_extractor.provider
            result["fallback_model"] = self.fallback_extractor.model
            result["fallback_stats"] = self.fallback_extractor.stats
        
        return result