# joke.py
"""Tell a random joke via pyjokes."""
try:
    import pyjokes
    _PYJOKES = True
except ImportError:
    _PYJOKES = False


def tell_joke(parameters: dict = None, response=None, player=None,
              session_memory=None) -> str:
    if not _PYJOKES:
        return "pyjokes is not installed — I have no jokes to tell right now."

    params = parameters or {}
    category = str(params.get("category", "neutral")).lower().strip()
    if category not in ("neutral", "chuck", "all"):
        category = "neutral"

    try:
        result = pyjokes.get_joke(language="en", category=category)
    except Exception as e:
        return f"Couldn't fetch a joke: {e}"

    print(f"[Joke] 😄 {result}")
    if player:
        player.write_log("[joke]")
    return result
