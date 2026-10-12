import os
import json
import threading
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from models import Event
from vk_client import fetch_posts, extract_post_content, post_date_str
from ai_extractor import AIExtractor
from logger_config import logger

@dataclass
class ParseState:
    status: str = "idle"
    current_category: str = ""
    current_group: str = ""
    total_groups: int = 0
    done_groups: int = 0
    total_posts: int = 0
    done_posts: int = 0
    events_found: int = 0
    errors: int = 0
    last_events: list = field(default_factory=list)

class Parser(threading.Thread):
    def __init__(self, config: dict, state: ParseState):
        super().__init__(daemon=True)
        self.config = config
        self.state = state
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_event = threading.Event()
        self.events: list[Event] = []
        self.vk_token = config.get("vk_token") or os.getenv("VK_TOKEN", "")
        self.ai = AIExtractor(config.get("ai_provider", "fallback"), config.get("ai_api_key") or os.getenv("AI_API_KEY", ""), config.get("ai_model", ""))
        self.sources_dir = Path(config.get("sources_dir", "sources"))
        self.output_file = config.get("output_file", "events_output.json")
        self.posts_per_group = config.get("posts_per_group", 15)
        self.state_file = "processed_posts.json"
        self.processed_posts = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f: return json.load(f)
            except Exception: pass
        return {}

    def _save_state(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f: json.dump(self.processed_posts, f, ensure_ascii=False, indent=2)
        except Exception as e: logger.error(f"Ошибка сохранения state: {e}")

    def start_parsing(self):
        if not self.is_alive(): self.start()
        self.pause_event.set()
        self.state.status = "running"

    def pause(self): self.pause_event.clear(); self.state.status = "paused"
    def resume(self): self.pause_event.set(); self.state.status = "running"
    def stop(self): self.stop_event.set(); self.pause_event.set(); self.state.status = "stopped"; self._save_state()
    @property
    def is_paused(self) -> bool: return not self.pause_event.is_set()
    
    def _check_pause_stop(self) -> bool:
        while not self.stop_event.is_set() and not self.pause_event.is_set(): self.pause_event.wait(timeout=0.2)
        return self.stop_event.is_set()

    def load_sources(self) -> dict:
        result = {}
        if not self.sources_dir.exists(): return result
        for file in sorted(self.sources_dir.glob("*.txt")):
            groups = []
            for line in file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"): continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2: groups.append((parts[0], [u for u in parts[1:] if u]))
            if groups: result[file.stem] = groups
        return result

    def run(self):
        sources = self.load_sources()
        self.state.total_groups = sum(len(g) for g in sources.values())
        self.state.done_groups = 0
        self.state.status = "running"
        logger.info(f"=== Запуск. Категорий: {len(sources)}, групп: {self.state.total_groups} ===")
        
        for category, groups in sources.items():
            if self._check_pause_stop(): break
            self.state.current_category = category
            logger.info(f"Категория: {category}")
            for group_name, urls in groups:
                if self._check_pause_stop(): break
                self.state.current_group = group_name
                self._process_group(category, group_name, urls)
                self.state.done_groups += 1
                self._save_state()
                
        if not self.stop_event.is_set():
            self.state.status = "done"
            logger.info("=== Парсинг завершён ===")
            
        # Сохранение итоговой статистики
        try:
            with open("stats.json", "w", encoding="utf-8") as f:
                json.dump({"ai_stats": self.ai.get_stats_summary(), "parse_stats": {"total_groups": self.state.total_groups, "done_groups": self.state.done_groups, "total_posts": self.state.total_posts, "done_posts": self.state.done_posts, "events_found": self.state.events_found, "errors": self.state.errors}, "completed_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
            logger.info("📈 Статистика сохранена в stats.json")
        except Exception as e: logger.error(f"Ошибка сохранения статистики: {e}")
        self._save()

    def _process_group(self, category: str, group_name: str, urls: list[str]):
        vk_url = next((u for u in urls if "vk." in u), None)
        if not vk_url:
            logger.warning(f"[{group_name}] Нет VK-ссылки")
            self.state.errors += 1
            return

        posts = fetch_posts(vk_url, self.vk_token, count=self.posts_per_group)
        self.state.total_posts += len(posts)
        if not posts:
            logger.warning(f"[{group_name}] Посты не получены")
            self.state.errors += 1
            return

        owner_id = posts[0].get("from_id", "unknown")
        group_key = f"{category}::{group_name}"
        if group_key not in self.processed_posts: self.processed_posts[group_key] = []

        processed_count = 0
        for post in posts:
            if self._check_pause_stop(): return
            post_id = f"{owner_id}_{post.get('id')}"
            if post_id in self.processed_posts[group_key]: continue

            content = extract_post_content(post)
            if not content["text"] or len(content["text"].strip()) < 30:
                self.processed_posts[group_key].append(post_id)
                self.state.done_posts += 1
                continue

            events_data = self.ai.extract(content["text"])
            self.state.done_posts += 1
            self.processed_posts[group_key].append(post_id)

            for ev in events_data:
                if self._check_pause_stop(): return
                date = ev.get("date") or post_date_str(post)
                event = Event(name=ev.get("name", "Без названия")[:150], category=category, group_name=group_name, date=date, time=ev.get("time"), location=ev.get("location"), photo_url=content.get("photo_url"), price_from=ev.get("price_from"), price_fixed=ev.get("price_fixed"), description=ev.get("description", "")[:500], source_url=content.get("post_url", vk_url))
                self.events.append(event)
                self.state.events_found += 1
                self.state.last_events.append(event)
                if len(self.state.last_events) > 10: self.state.last_events.pop(0)
                logger.info(f"    + Найдено: '{event.name}' ({event.date} {event.time or ''})")
                processed_count += 1

        total_processed = len([p for p in posts if f"{owner_id}_{p.get('id')}" in self.processed_posts[group_key]])
        skipped_short = len([p for p in posts if not extract_post_content(p)["text"] or len(extract_post_content(p)["text"].strip()) < 30])
        logger.info(f"  📊 [{group_name}] Загружено: {len(posts)}, Обработано: {total_processed}, Пропущено: {skipped_short}, Найдено: {processed_count}")

        if processed_count > 0:
           logger.info(f"  ✅ [{group_name}] Успешно обработано")
        else:
            logger.info(f"  [{group_name}] Новых событий не найдено.")

    def _save(self):
        try:
            with open(self.output_file, "w", encoding="utf-8") as f: json.dump({"events": [e.to_dict() for e in self.events], "total": len(self.events)}, f, ensure_ascii=False, indent=2)
            logger.info(f"Результаты сохранены в {self.output_file}")
        except Exception as e: logger.error(f"Ошибка сохранения: {e}")