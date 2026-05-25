# wikipedia_lookup.py
"""Speak a short Wikipedia summary for any topic.

Uses Wikipedia's public REST + opensearch APIs directly (no API key, no extra
dependency). The opensearch step resolves the best matching article title so
loose queries like "albert einstein" still find "Albert Einstein".
"""
import urllib.parse

import requests

_HEADERS = {"User-Agent": "MarkXXXIX-JARVIS/1.0 (personal assistant)"}
_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def _resolve_title(query: str) -> str | None:
    try:
        resp = requests.get(
            _SEARCH_URL,
            params={"action": "opensearch", "search": query,
                    "limit": 1, "namespace": 0, "format": "json"},
            headers=_HEADERS, timeout=8,
        )
        data = resp.json()
        titles = data[1] if len(data) > 1 else []
        return titles[0] if titles else None
    except Exception:
        return None


def wikipedia_lookup(parameters: dict, response=None, player=None,
                     session_memory=None) -> str:
    params = parameters or {}
    query = str(params.get("query", "")).strip()
    try:
        sentences = int(params.get("sentences", 2))
    except (TypeError, ValueError):
        sentences = 2
    sentences = max(1, min(sentences, 5))

    if not query:
        return "Please tell me what topic to look up on Wikipedia."

    title = _resolve_title(query) or query
    print(f"[Wikipedia] 🔎 {query} → {title}")

    try:
        resp = requests.get(
            _SUMMARY_URL + urllib.parse.quote(title.replace(" ", "_")),
            headers=_HEADERS, timeout=8,
        )
        if resp.status_code == 404:
            return f"I couldn't find a Wikipedia article for '{query}'."
        data = resp.json()

        if data.get("type", "").endswith("disambiguation"):
            return (f"'{title}' has several meanings on Wikipedia. "
                    f"Please be more specific.")

        extract = (data.get("extract") or "").strip()
        if not extract:
            return f"I found '{title}' but it has no summary."

        # Trim to the requested number of sentences.
        parts = extract.replace("\n", " ").split(". ")
        summary = ". ".join(parts[:sentences]).strip()
        if summary and not summary.endswith("."):
            summary += "."
    except Exception as e:
        return f"Wikipedia lookup failed: {e}"

    result = f"According to Wikipedia: {summary}"
    if player:
        player.write_log(f"[wiki] {title}")
    return result
