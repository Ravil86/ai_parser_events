import re
import requests
from typing import Optional
from datetime import datetime

VK_API = "https://api.vk.com/method"
VK_VERSION = "5.199"


def extract_group_id(url: str, token: str) -> Optional[str]:
    if "vk." not in url:
        return None
    match = re.search(r'vk\.ru/(.+?)(?:\?|$|/)', url)
    if not match:
        return None
    screen_name = match.group(1).strip("/")
    
    if screen_name.startswith(("club", "public", "event")):
        return "-" + screen_name[4:]
    
    if not token:
        return None
    try:
        r = requests.get(f"{VK_API}/groups.getById", params={
            "group_ids": screen_name, "access_token": token, "v": VK_VERSION
        }, timeout=10)
        data = r.json()
        resp = data.get("response", [])
        if isinstance(resp, list) and resp:
            gid = resp[0].get("id")
            return f"-{gid}" if gid else None
        elif isinstance(resp, dict):
            groups = resp.get("groups", [])
            if groups:
                return f"-{groups[0].get('id')}"
    except Exception as e:
        print(f"[VK] resolve error {screen_name}: {e}")
    return None


def fetch_posts(group_url: str, token: str, count: int = 15) -> list[dict]:
    gid = extract_group_id(group_url, token)
    if not gid:
        return []
    try:
        r = requests.get(f"{VK_API}/wall.get", params={
            "owner_id": gid, "count": count, "filter": "owner",
            "extended": 1, "access_token": token, "v": VK_VERSION,
        }, timeout=15)
        data = r.json()
        return data.get("response", {}).get("items", [])
    except Exception as e:
        print(f"[VK] fetch error {group_url}: {e}")
        return []


def extract_post_content(post: dict) -> dict:
    text = post.get("text", "")
    photo_url = None
    for att in post.get("attachments", []):
        if att.get("type") == "photo":
            sizes = att["photo"].get("sizes", [])
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


def post_date_str(post: dict) -> str:
    ts = post.get("date", 0)
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "уточняйте"