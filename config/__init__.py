# config/__init__.py
import json, os, platform
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "api_keys.json"

def get_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _detect_os() -> str:
    """Map the running platform to 'windows' | 'mac' | 'linux'."""
    return {"Darwin": "mac", "Windows": "windows", "Linux": "linux"} \
        .get(platform.system(), platform.system().lower())

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'.

    Uses the explicit 'os_system' override from api_keys.json when present,
    otherwise auto-detects from the running platform (so a missing or partial
    config no longer silently behaves as Windows)."""
    try:
        override = get_config().get("os_system")
        if override:
            return str(override).lower()
    except Exception:
        pass
    return _detect_os()

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"