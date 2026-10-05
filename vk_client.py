import re
import requests
from typing import Optional
from datetime import datetime

VK_API = "https://api.vk.com/method"
VK_VERSION = "5.199"


def _extract_group_id(url: str, token: str) -> Optional[str]:
    """Извлекает ID сообщества из ссылки VK"""
    if not url.startswith("https://vk.") and not url.startswith("https://m.vk."):
        return None
    
    # Извлекаем screen_name
    match = re.search(r'vk\.ru/(.+?)(?:\?|$)', url)
    if not match:
        return None
    screen_name = match.group(1).strip("/")
    
    # Если уже ID
    if screen_name.startswith("club") or screen_name.startswith("public") or screen_name.startswith("event"):
        return "-" + screen_name[4:]
    
    # Resolve через API
    if not token:
        return None
    try:
        r = requests.get(f"{VK_API}/groups.getById", params={
            "group_ids": screen_name, "access_token": token, "v": VK_VERSION
        }, timeout=10)
        data = r.json()
        if "response" in data and data["response"]:
            group = data["response"][0] if isinstance(data["response"], list) else data["response"].get("groups", [{}])[0]
            gid = group.get("id")
            return f"-{gid}" if gid else None
    except Exception as e:
        print(f"  ⚠ Ошибка резолва {screen_name}: {e}")
    return None


def fetch_posts(group_url: str, token: str, count: int = 15) -> list[dict]:
    """Получает последние посты сообщества"""
    gid = _extract_group_id(group_url, token)
    if not gid:
        return []
    
    params = {
        "owner_id": gid,
        "count": count,
        "filter": "owner",
        "extended": 1,
        "access_token": token,
        "v": VK_VERSION,
    }
    try:
        r = requests.get(f"{VK_API}/wall.get", params=params, timeout=15)
        data = r.json()
        items = data.get("response", {}).get("items", [])
        return items
    except Exception as e:
        print(f"  ⚠ Ошибка загрузки постов {group_url}: {e}")
        return []


def extract_post_content(post: dict) -> dict:
    """Извлекает текст и главное фото из поста"""
    text = post.get("text", "")
    
    # Ищем фото
    photo_url = None
    attachments = post.get("attachments", [])
    for att in attachments:
        if att.get("type") == "photo":
            sizes = att["photo"].get("sizes", [])
            # Берём самое большое фото
            best = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0), default=None)
            if best:
                photo_url = best.get("url")
                break
    
    return {
        "text": text,
        "photo_url": photo_url,
        "post_url": f"https://vk.ru/wall{post.get('from_id', '')}_{post.get('id', '')}",
        "date_ts": post.get("date", 0),
    }


def extract_post_date(post: dict) -> str:
    """Конвертирует timestamp поста в YYYY-MM-DD"""
    ts = post.get("date", 0)
    if ts:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    return "неизвестно"