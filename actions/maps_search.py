# maps_search.py
"""Open Google Maps for a place, or directions between two places.

Ported from the gaurav-jarvis "Google Map searching" / "location" feature,
which opened a place on Google Maps from a voice command. This version also
supports turn-by-turn directions when both an origin and destination are given.
"""
import webbrowser
from urllib.parse import quote_plus


def maps_search(parameters: dict = None, response=None, player=None,
                session_memory=None) -> str:
    params = parameters or {}
    query = str(params.get("query", "")).strip()
    origin = str(params.get("origin", "")).strip()
    destination = str(params.get("destination", "")).strip()

    # Directions mode: needs at least a destination.
    if destination:
        if origin:
            url = (f"https://www.google.com/maps/dir/?api=1"
                   f"&origin={quote_plus(origin)}&destination={quote_plus(destination)}")
            spoken = f"Showing directions from {origin} to {destination}, sir."
        else:
            url = (f"https://www.google.com/maps/dir/?api=1"
                   f"&destination={quote_plus(destination)}")
            spoken = f"Showing directions to {destination}, sir."
    elif query:
        url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"
        spoken = f"Here is {query} on the map, sir."
    else:
        msg = "Sir, what place or destination should I look up on the map?"
        _log(msg, player)
        return msg

    try:
        opened = webbrowser.open(url)
        if not opened:
            raise RuntimeError("webbrowser.open returned False")
    except Exception as e:
        msg = f"Sir, I couldn't open Google Maps: {e}"
        _log(msg, player)
        return msg

    _log(spoken, player)
    if session_memory:
        try:
            session_memory.set_last_search(query=query or destination, response=spoken)
        except Exception:
            pass
    return spoken


def _log(message: str, player=None) -> None:
    print(f"[Maps] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
