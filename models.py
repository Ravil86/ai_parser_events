from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class Event:
    """Модель мероприятия"""
    name: str
    category: str
    group_name: str
    date: str  # YYYY-MM-DD или "уточняйте"
    photo_url: Optional[str] = None
    price_from: Optional[int] = None
    price_fixed: Optional[int] = None
    description: str = ""
    source_url: str = ""
    
    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, "")}
    
    def __str__(self):
        price = ""
        if self.price_fixed:
            price = f"💰 {self.price_fixed}₽"
        elif self.price_from:
            price = f"💰 от {self.price_from}₽"
        return (
            f"[{self.category}] {self.name}\n"
            f"  📅 {self.date}  {price}\n"
            f"  🖼  {self.photo_url or '—'}\n"
            f"  🔗 {self.source_url}"
        )