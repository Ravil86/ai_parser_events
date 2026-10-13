from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime, timezone, timedelta

# Часовой пояс Екатеринбург (UTC+5) — НЕ зависит от часового пояса сервера
YEKATERINBURG_TZ = timezone(timedelta(hours=5))


@dataclass
class Event:
    name: str
    category: str
    group_name: str
    date: str
    time: Optional[str] = None
    location: Optional[str] = None
    photo_url: Optional[str] = None
    price_from: Optional[int] = None
    price_fixed: Optional[int] = None
    description: str = ""
    source_url: str = ""
    found_at: str = ""
    
    def __post_init__(self):
        if not self.found_at:
            # Время находки всегда в часовом поясе Екатеринбурга, независимо от сервера
            self.found_at = datetime.now(YEKATERINBURG_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    
    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}
    
    @property
    def price_str(self) -> str:
        if self.price_fixed:
            return f"{self.price_fixed}₽"
        if self.price_from:
            return f"от {self.price_from}₽"
        return "—"