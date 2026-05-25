# news.py
"""Read top news headlines via NewsAPI.org.

Requires a free API key stored in config/api_keys.json under "newsapi_key".
Get one at https://newsapi.org/register
"""
import json
import sys
from pathlib import Path

import requests

_API = "https://newsapi.org/v2/top-headlines"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _newsapi_key() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return str(cfg.get("newsapi_key", "")).strip()
    except Exception:
        return ""


def news(parameters: dict = None, response=None, player=None,
         session_memory=None) -> str:
    key = _newsapi_key()
    if not key or key.startswith("PASTE_"):
        return ("No NewsAPI key configured. Add a free key from "
                "newsapi.org to 'newsapi_key' in config/api_keys.json.")

    params = parameters or {}
    try:
        count = int(params.get("count", 5))
    except (TypeError, ValueError):
        count = 5
    count = max(1, min(count, 10))

    category = str(params.get("category", "")).lower().strip()
    country = str(params.get("country", "us")).lower().strip() or "us"
    topic = str(params.get("topic", "")).strip()

    query = {"apiKey": key, "pageSize": count}
    if topic:
        query["q"] = topic
    else:
        query["country"] = country
        if category in ("business", "entertainment", "general", "health",
                        "science", "sports", "technology"):
            query["category"] = category

    print(f"[News] 📰 {query.get('q') or query.get('category') or country}")
    try:
        resp = requests.get(_API, params=query, timeout=8)
        data = resp.json()
        if data.get("status") != "ok":
            return f"News fetch failed: {data.get('message', 'unknown error')}."
        articles = data.get("articles", [])[:count]
    except Exception as e:
        return f"Could not fetch news: {e}"

    if not articles:
        return "No headlines found for that request."

    headlines = [a.get("title", "").split(" - ")[0].strip()
                 for a in articles if a.get("title")]
    body = " ".join(f"{i}. {h}." for i, h in enumerate(headlines, 1))
    result = f"Here are the top {len(headlines)} headlines. {body}"

    if player:
        player.write_log(f"[news] {len(headlines)} headlines")
    return result
