# translate.py
"""Translate text between languages using deep-translator (Google backend).

No API key required. Target language may be a name ("spanish") or an ISO code
("es"); source defaults to auto-detect.
"""
try:
    from deep_translator import GoogleTranslator
    _TRANSLATOR = True
except ImportError:
    _TRANSLATOR = False

# Common spoken language names → ISO codes accepted by the backend.
_LANG_ALIASES = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh-CN", "mandarin": "zh-CN", "arabic": "ar",
    "hindi": "hi", "turkish": "tr", "dutch": "nl", "greek": "el",
    "polish": "pl", "swedish": "sv", "telugu": "te", "tamil": "ta",
}


def _norm_lang(value: str, default: str) -> str:
    value = (value or "").lower().strip()
    if not value:
        return default
    return _LANG_ALIASES.get(value, value)


def translate(parameters: dict, response=None, player=None,
              session_memory=None) -> str:
    if not _TRANSLATOR:
        return "deep-translator is not installed — cannot translate."

    params = parameters or {}
    text = str(params.get("text", "")).strip()
    target = _norm_lang(params.get("target", ""), "en")
    source = _norm_lang(params.get("source", ""), "auto")

    if not text:
        return "Please tell me what text to translate."

    print(f"[Translate] 🌐 {source} → {target}: {text[:50]}")
    try:
        result = GoogleTranslator(source=source, target=target).translate(text)
    except Exception as e:
        return f"Translation failed: {e}"

    if player:
        player.write_log(f"[translate] → {target}")
    return result or "Translation returned nothing."
