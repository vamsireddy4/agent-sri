# geolocation.py
"""Report the user's approximate current location via IP geolocation.

Ported from the gaurav-jarvis "latitude and longitude / current location"
feature, which used the `geocoder` package. This version uses the free,
no-API-key ip-api.com service so no extra dependency is required.

`get_ip_location()` is also reused by weather_report.py to answer
"what's the weather" when no city is given.
"""
import requests

_IP_API = "http://ip-api.com/json/"


def get_ip_location() -> dict | None:
    """Return {city, region, country, lat, lon} for the current IP, or None."""
    try:
        data = requests.get(_IP_API, timeout=8).json()
    except Exception:
        return None
    if data.get("status") != "success":
        return None
    return {
        "city":    data.get("city", ""),
        "region":  data.get("regionName", ""),
        "country": data.get("country", ""),
        "lat":     data.get("lat"),
        "lon":     data.get("lon"),
    }


def my_location(parameters: dict = None, response=None, player=None,
                session_memory=None) -> str:
    loc = get_ip_location()
    if not loc:
        return ("Sorry sir, I couldn't determine your current location. "
                "The geolocation service may be unavailable.")

    place = ", ".join(p for p in (loc["city"], loc["region"], loc["country"]) if p)
    lat, lon = loc["lat"], loc["lon"]

    result = (f"You appear to be in {place}. "
              f"Latitude {lat}, longitude {lon}, sir.")

    print(f"[Location] {place} ({lat}, {lon})")
    if player:
        player.write_log(f"[location] {place}")
    if session_memory:
        try:
            session_memory.set_last_search(query="my location", response=result)
        except Exception:
            pass
    return result
