# dictionary.py
"""Define a word using the free dictionaryapi.dev (no API key required)."""
import urllib.parse

import requests

_API = "https://api.dictionaryapi.dev/api/v2/entries/en/"
_HEADERS = {"User-Agent": "MarkXXXIX-JARVIS/1.0"}


def define_word(parameters: dict, response=None, player=None,
                session_memory=None) -> str:
    params = parameters or {}
    word = str(params.get("word", "")).strip()
    if not word:
        return "Please tell me which word to define."

    print(f"[Dictionary] 📖 {word}")
    try:
        resp = requests.get(
            _API + urllib.parse.quote(word.lower()),
            headers=_HEADERS, timeout=8,
        )
        if resp.status_code == 404:
            return f"I couldn't find a definition for '{word}'."
        resp.raise_for_status()
        entries = resp.json()
    except Exception as e:
        return f"Dictionary lookup failed: {e}"

    try:
        meanings = entries[0].get("meanings", [])
        if not meanings:
            return f"No definitions found for '{word}'."

        first = meanings[0]
        part = first.get("partOfSpeech", "")
        definition = first["definitions"][0].get("definition", "").strip()
        example = first["definitions"][0].get("example", "").strip()

        result = f"{word} ({part}): {definition}" if part else f"{word}: {definition}"
        if example:
            result += f" For example: {example}"
    except (KeyError, IndexError, TypeError):
        return f"I found '{word}' but couldn't parse its definition."

    if player:
        player.write_log(f"[define] {word}")
    return result
