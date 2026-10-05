import os
import threading
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from models import Event
from vk_client import fetch_posts, extract_post_content, post_date_str
from ai_extractor import AIExtractor


@dataclass
class ParseState:
    """Состояние парсера — доступно из UI потока."""
    status: str = "idle"          # idle | running | paused | stopped | done
    current_category: str = ""
    current_group: str = ""
    total_groups: int = 0
    done_groups: int = 0
    total_posts: int = 0
    done_posts: int = 0
    events_found: int = 0
    errors: int = 0
    last_events: list = field(default_factory=list)  # последние N событий
    
    def to_snapshot(self) -> dict:
        from dataclasses import asdict
        d = asdict(self)
        return d


class Parser(threading.Thread):
    """Поток парсинга с управлением через события."""
    
    def __init__(self, config: dict, state: ParseState):
        super().__init__(daemon=True)
        self.config = config
        self.state = state
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_event = threading.Event()
        self.events: list[Event] = []
        
        # Секреты теперь берутся из env (main.py уже подгрузил их в config)
        self.vk_token = config.get("vk_token") or os.getenv("VK_TOKEN", "")
        ai_key = config.get("ai_api_key") or os.getenv("AI_API_KEY", "")
        
        self.ai = AIExtractor(
            provider=config.get("ai_provider", "fallback"),
            api_key=ai_key,
            model=config.get("ai_model", ""),
        )
        self.sources_dir = Path(config.get("sources_dir", "sources"))
        self.output_file = config.get("output_file", "events_output.json")
        self.posts_per_group = config.get("posts_per_group", 15)
    
    # ----- Управление -----
    def start_parsing(self):
        if not self.is_alive():
            self.start()
        self.pause_event.set()
        self.state.status = "running"
    
    def pause(self):
        self.pause_event.clear()
        self.state.status = "paused"
    
    def resume(self):
        self.pause_event.set()
        self.state.status = "running"
    
    def stop(self):
        self.stop_event.set()
        self.pause_event.set()  # разбудить если был на паузе
        self.state.status = "stopped"
    
    @property
    def is_paused(self) -> bool:
        return not self.pause_event.is_set()
    
    def _check_pause_stop(self):
        """Блокируется если на паузе, выходит если стоп."""
        while not self.stop_event.is_set() and not self.pause_event.is_set():
            self.pause_event.wait(timeout=0.2)
        return self.stop_event.is_set()
    
    # ----- Загрузка sources -----
    def load_sources(self) -> dict[str, list[tuple[str, list[str]]]]:
        """
        Возвращает: { category_name: [ (group_name, [urls]), ... ], ... }
        """
        result = {}
        if not self.sources_dir.exists():
            return result
        for file in sorted(self.sources_dir.glob("*.txt")):
            category = file.stem
            groups = []
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 2:
                    continue
                name = parts[0]
                urls = [u for u in parts[1:] if u]
                if name and urls:
                    groups.append((name, urls))
            if groups:
                result[category] = groups
        return result
    
    # ----- Основной цикл -----
    def run(self):
        sources = self.load_sources()
        total_groups = sum(len(g) for g in sources.values())
        self.state.total_groups = total_groups
        self.state.done_groups = 0
        self.state.status = "running"
        
        for category, groups in sources.items():
            if self._check_pause_stop():
                break
            self.state.current_category = category
            
            for group_name, urls in groups:
                if self._check_pause_stop():
                    break
                self.state.current_group = group_name
                self._process_group(category, group_name, urls)
                self.state.done_groups += 1
        
        if not self.stop_event.is_set():
            self.state.status = "done"
        self._save()
    
    def _process_group(self, category: str, group_name: str, urls: list[str]):
        vk_url = next((u for u in urls if "vk." in u), None)
        if not vk_url:
            self.state.errors += 1
            return
        
        posts = fetch_posts(vk_url, self.vk_token, count=self.posts_per_group)
        self.state.total_posts += len(posts)
        
        for post in posts:
            if self._check_pause_stop():
                return
            content = extract_post_content(post)
            if not content["text"] or len(content["text"].strip()) < 30:
                self.state.done_posts += 1
                continue
            
            result = self.ai.extract(content["text"])
            self.state.done_posts += 1
            
            if not result or result.get("skip"):
                continue
            
            date = result.get("date", "")
            if not date or date == "уточняйте":
                date = post_date_str(post)
            
            event = Event(
                name=result.get("name", "Без названия")[:150],
                category=category,
                group_name=group_name,
                date=date,
                photo_url=content.get("photo_url"),
                price_from=result.get("price_from"),
                price_fixed=result.get("price_fixed"),
                description=result.get("description", "")[:500],
                source_url=content.get("post_url", vk_url),
            )
            self.events.append(event)
            self.state.events_found += 1
            self.state.last_events.append(event)
            if len(self.state.last_events) > 10:
                self.state.last_events.pop(0)
    
    def _save(self):
        data = {"events": [e.to_dict() for e in self.events], "total": len(self.events)}
        try:
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SAVE] error: {e}")