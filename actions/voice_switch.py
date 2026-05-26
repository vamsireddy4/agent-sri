# voice_switch.py
"""Resolve a requested voice/persona to a Gemini Live prebuilt voice.

Sri ONLY ever speaks in a FEMALE voice. The default is Aoede. The user can
switch between the available female Gemini voices, but a male voice is never
used — any male/JARVIS request falls back to the default female Sri voice.

Female Gemini Live voices: Aoede (default), Kore, Leda, Zephyr.
"""

# request keyword -> (gemini voice, persona label). Female voices only.
_PRESETS = {
    "sri":    ("Aoede", "Sri"),
    "friday": ("Aoede", "Sri"),
    "female": ("Aoede", "Sri"),
    "woman":  ("Aoede", "Sri"),
}

# Female Gemini voice names the user may name explicitly. Male voices
# (Puck, Charon, Fenrir, Orus) are intentionally excluded so Sri always
# sounds female.
_GEMINI_VOICES = {
    "aoede": "Aoede", "kore": "Kore", "leda": "Leda", "zephyr": "Zephyr",
}


def resolve_voice(parameters: dict = None) -> dict:
    """Return {voice, persona} for the requested voice — always female.

    Any unrecognised request — including male/JARVIS requests, which are not
    allowed — falls back to the default female Sri voice (Aoede).
    """
    params = parameters or {}
    req = str(params.get("voice") or params.get("persona") or
              params.get("gender") or "").lower().strip()

    if req in _PRESETS:
        voice, persona = _PRESETS[req]
    elif req in _GEMINI_VOICES:
        # A specific female voice was named; keep the Sri persona.
        voice, persona = _GEMINI_VOICES[req], "Sri"
    else:
        # Anything else (including male / JARVIS) -> default female Sri voice.
        voice, persona = _PRESETS["sri"]

    return {"voice": voice, "persona": persona}
