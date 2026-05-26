# weather_report.py
"""Live weather report.

Upgraded from the original browser-search version to speak real data
(temperature, "feels like", humidity, wind, and a sky description) — the
behaviour ported from gaurav-jarvis, which read live numbers aloud.

Uses the free, no-API-key Open-Meteo service:
  - geocoding : https://geocoding-api.open-meteo.com/v1/search
  - forecast  : https://api.open-meteo.com/v1/forecast

If no city is given, it falls back to the user's current location via IP
geolocation. If the live API ever fails, it falls back to opening a Google
weather search in the browser (the original behaviour).
"""
import webbrowser
from urllib.parse import quote_plus

import requests

try:
    from actions.geolocation import get_ip_location
except Exception:  # pragma: no cover - allow standalone import
    from geolocation import get_ip_location

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes -> human description
_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snowfall", 73: "moderate snowfall", 75: "heavy snowfall",
    77: "snow grains",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with slight hail",
    99: "thunderstorms with heavy hail",
}


def _geocode(city: str) -> dict | None:
    try:
        resp = requests.get(
            _GEOCODE, params={"name": city, "count": 1}, timeout=8
        ).json()
    except Exception:
        return None
    results = resp.get("results") or []
    if not results:
        return None
    r = results[0]
    label = ", ".join(p for p in (r.get("name"), r.get("country")) if p)
    return {"lat": r.get("latitude"), "lon": r.get("longitude"), "label": label}


def _fetch_weather(lat, lon) -> dict | None:
    try:
        return requests.get(_FORECAST, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                       "weather_code,wind_speed_10m",
            "wind_speed_unit": "kmh", "temperature_unit": "celsius",
        }, timeout=8).json().get("current")
    except Exception:
        return None


def _browser_fallback(city: str, when: str, player) -> str:
    search_query = f"weather in {city} {when}".strip()
    url = f"https://www.google.com/search?q={quote_plus(search_query)}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    msg = f"I couldn't fetch live data, so I've opened the weather search for {city}, sir."
    _log(msg, player)
    return msg


def weather_action(parameters: dict = None, response=None, player=None,
                   session_memory=None) -> str:
    params = parameters or {}
    city = str(params.get("city", "")).strip()
    when = str(params.get("time", "now") or "now").strip()

    # No city -> use current location via IP geolocation.
    if not city:
        loc = get_ip_location()
        if loc and loc.get("lat") is not None:
            lat, lon = loc["lat"], loc["lon"]
            label = ", ".join(p for p in (loc.get("city"), loc.get("country")) if p) or "your location"
        else:
            msg = "Sir, which city would you like the weather for?"
            _log(msg, player)
            return msg
    else:
        geo = _geocode(city)
        if not geo:
            return _browser_fallback(city, when, player)
        lat, lon, label = geo["lat"], geo["lon"], geo["label"]

    cur = _fetch_weather(lat, lon)
    if not cur:
        return _browser_fallback(city or label, when, player)

    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    humidity = cur.get("relative_humidity_2m")
    wind = cur.get("wind_speed_10m")
    desc = _WMO.get(cur.get("weather_code"), "unknown conditions")

    result = (f"The weather in {label} is {desc}, with a temperature of "
              f"{temp}°C (feels like {feels}°C). "
              f"Humidity is {humidity}%, and wind speed is {wind} kilometres per hour, sir.")

    _log(result, player)
    if session_memory:
        try:
            session_memory.set_last_search(query=f"weather in {label}", response=result)
        except Exception:
            pass
    return result


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
