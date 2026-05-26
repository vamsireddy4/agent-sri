import asyncio
import re
import threading
import json
import sys
import time
import traceback
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.system_stats      import system_stats
from actions.wikipedia_lookup  import wikipedia_lookup
from actions.dictionary        import define_word
from actions.joke              import tell_joke
from actions.news              import news as news_action
from actions.email_sender      import send_email
from actions.translate         import translate as translate_action
from actions.youtube_download  import youtube_download
from actions.ocr_reader        import ocr_read
from actions.face_auth         import face_auth
from actions.geolocation       import my_location
from actions.maps_search       import maps_search
from actions.price_tracker     import track_price
from actions.voice_switch      import resolve_voice
from core.voice_engine         import VoiceEngine


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LANG_SAMPLE_PATH = BASE_DIR / "config" / "last_language.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


class _ClapDetector:
    """Detects a wake sound — a single clap OR a finger snap — in a stream of
    int16 PCM chunks. Used to wake JARVIS from standby.

    A clap and a snap are both brief, sharp transients after quiet; a snap is
    just quieter and shorter than a clap. So instead of an absolute loudness
    threshold we look for an *onset*: a sudden peak that is (a) above a small
    floor, and (b) many times louder than the quiet moments just before it.
    Requiring a settled-quiet baseline first rejects speech, steady noise, and
    the mic's startup transient. `sensitivity` (0..1) eases both conditions.
    """

    _INT16_MAX = 32767.0

    def __init__(self, sensitivity: float = 0.6):
        self.set_sensitivity(sensitivity)
        self._recent = deque(maxlen=6)     # ~0.4s of recent chunk RMS
        self._cooldown_until = 0.0

    def set_sensitivity(self, s: float):
        s = max(0.0, min(1.0, float(s)))
        # Absolute floor: low enough for a finger snap, high enough to ignore
        # tiny noises. Onset ratio: peak must dwarf the recent quiet baseline.
        self.peak_floor   = self._INT16_MAX * (0.26 - 0.16 * s)   # ~ 8500..3300
        self.onset_ratio  = 9.0 - 4.0 * s                          # ~ 9x..5x
        self.quiet_rms    = 2400.0          # "was it quiet just before?" gate

    def reset(self, cooldown: float = 2.5):
        self._recent.clear()
        self._cooldown_until = time.time() + cooldown

    def feed(self, chunk: "np.ndarray") -> bool:
        now = time.time()
        x = chunk.astype(np.float32)
        peak = float(np.abs(x).max())
        rms  = float(np.sqrt(np.mean(x * x)))

        # Need a settled, genuinely-quiet baseline (full history) before a spike
        # counts — this rejects the mic's startup transient and steady noise.
        baseline = (sum(self._recent) / len(self._recent)) if self._recent else 0.0
        was_quiet = (len(self._recent) >= self._recent.maxlen and
                     baseline < self.quiet_rms)
        self._recent.append(rms)

        if now < self._cooldown_until:
            return False
        # Sudden onset: loud enough AND a sharp jump above the quiet baseline.
        sudden = peak >= self.peak_floor and peak >= self.onset_ratio * max(baseline, 180.0)
        if sudden and was_quiet:
            self._cooldown_until = now + 1.2
            return True
        return False


def _clap_sensitivity() -> float:
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return float(cfg.get("clap_sensitivity", 0.6))
    except Exception:
        return 0.6


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are Sri, the user's own personal AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


def _load_lang_sample() -> str:
    """A short sample of the user's last utterance, used so the wake greeting
    can be spoken in their language even after a restart."""
    try:
        return LANG_SAMPLE_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _save_lang_sample(text: str) -> None:
    try:
        LANG_SAMPLE_PATH.write_text(text.strip()[:160], encoding="utf-8")
    except Exception:
        pass

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)


class _VoiceSwitch(Exception):
    """Raised internally to break the live session so it reconnects with a
    different Gemini voice (used by the switch_voice tool)."""


def _is_voice_switch(exc: BaseException) -> bool:
    """True if exc is (or an ExceptionGroup containing) a _VoiceSwitch."""
    if isinstance(exc, _VoiceSwitch):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_voice_switch(e) for e in exc.exceptions)
    return False


def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": (
            "Reports live weather (temperature, feels-like, humidity, wind, and "
            "sky conditions). If no city is given, uses the user's current "
            "location. Use whenever the user asks about the weather."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name (optional; omit to use current location)"},
                "time": {"type": "STRING", "description": "Optional time qualifier, e.g. 'now' or 'today'"}
            },
            "required": []
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "system_stats",
        "description": (
            "Reports live system metrics: CPU load, memory/RAM usage, battery level, "
            "or disk space. Use when the user asks how the computer/PC is doing, "
            "CPU usage, how much battery/RAM/storage is left, etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "metric": {"type": "STRING", "description": "cpu | memory | battery | disk | all (default: all)"}
            },
            "required": []
        }
    },
    {
        "name": "wikipedia_lookup",
        "description": (
            "Looks up a topic on Wikipedia and returns a short factual summary. "
            "Use for 'who is', 'what is', 'tell me about', or any encyclopedic question."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":     {"type": "STRING", "description": "The topic, person, or thing to look up"},
                "sentences": {"type": "NUMBER", "description": "How many sentences to return (1-5, default 2)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "define_word",
        "description": "Gives the dictionary definition of an English word.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "word": {"type": "STRING", "description": "The word to define"}
            },
            "required": ["word"]
        }
    },
    {
        "name": "tell_joke",
        "description": "Tells a random light-hearted programming joke when the user asks for a joke.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "neutral (default) | chuck | all"}
            },
            "required": []
        }
    },
    {
        "name": "news",
        "description": (
            "Reads the top news headlines. Use when the user asks for news, headlines, "
            "or what's happening. Can filter by category, country, or a topic keyword."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "count":    {"type": "NUMBER", "description": "Number of headlines (1-10, default 5)"},
                "category": {"type": "STRING", "description": "business|entertainment|general|health|science|sports|technology"},
                "country":  {"type": "STRING", "description": "2-letter country code, e.g. us, gb, in (default us)"},
                "topic":    {"type": "STRING", "description": "Optional keyword to search headlines for"}
            },
            "required": []
        }
    },
    {
        "name": "send_email",
        "description": (
            "Sends an email via the user's Gmail account. Use when the user asks to "
            "email someone. The recipient can be an email address or a saved contact name."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "to":      {"type": "STRING", "description": "Recipient email address or saved contact name"},
                "subject": {"type": "STRING", "description": "Email subject line"},
                "body":    {"type": "STRING", "description": "The email message body"}
            },
            "required": ["to", "body"]
        }
    },
    {
        "name": "translate",
        "description": (
            "Translates text from one language to another. Use when the user asks "
            "how to say something in another language, or to translate a phrase."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text":   {"type": "STRING", "description": "The text to translate"},
                "target": {"type": "STRING", "description": "Target language name or ISO code, e.g. 'spanish' or 'es'"},
                "source": {"type": "STRING", "description": "Source language (default: auto-detect)"}
            },
            "required": ["text", "target"]
        }
    },
    {
        "name": "youtube_download",
        "description": (
            "Downloads a YouTube video or its audio to the Downloads folder. "
            "Accepts a direct URL or a search query."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url":   {"type": "STRING", "description": "Direct YouTube video URL"},
                "query": {"type": "STRING", "description": "Search query (used if no URL given)"},
                "kind":  {"type": "STRING", "description": "video (default) or audio"}
            },
            "required": []
        }
    },
    {
        "name": "ocr_read",
        "description": (
            "Extracts raw text from an image using offline OCR (Tesseract). "
            "Use to read text from an image file, the current screen, or a "
            "document/page held up to the webcam. This is a fast local text "
            "reader; for richer visual understanding use screen_process instead."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "source": {"type": "STRING", "description": "file | screen | camera (default: screen)"},
                "path":   {"type": "STRING", "description": "Path to the image file (when source is 'file')"}
            },
            "required": []
        }
    },
    {
        "name": "face_auth",
        "description": (
            "Local face recognition for identity verification. Use to enroll a "
            "person's face under a name, verify/login who is at the webcam, list "
            "enrolled people, or remove someone. All processing is on-device."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "enroll | verify | list | remove (default: verify)"},
                "name":    {"type": "STRING", "description": "Person's name (required for enroll and remove)"},
                "samples": {"type": "NUMBER", "description": "Face samples to capture when enrolling (10-60, default 30)"}
            },
            "required": []
        }
    },
    {
        "name": "my_location",
        "description": (
            "Reports the user's approximate current location (city, region, "
            "country) and latitude/longitude via IP geolocation. Use for "
            "'where am I', 'what's my location', or 'my latitude and longitude'."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "maps_search",
        "description": (
            "Opens Google Maps for a place, or directions between two places. "
            "Use for 'show me X on the map', 'where is X', or 'directions from "
            "A to B'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":       {"type": "STRING", "description": "A place or address to locate on the map"},
                "origin":      {"type": "STRING", "description": "Start point for directions (optional)"},
                "destination": {"type": "STRING", "description": "End point for directions"}
            },
            "required": []
        }
    },
    {
        "name": "track_price",
        "description": (
            "Checks the current price of an online product from its URL "
            "(Amazon and similar shops). Optionally compares against a target "
            "price and emails an alert if the price is at or below it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url":          {"type": "STRING", "description": "Full product page URL"},
                "target":       {"type": "NUMBER", "description": "Optional target price to compare against"},
                "notify_email": {"type": "STRING", "description": "Optional email/contact to alert if price is at/below target"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "switch_voice",
        "description": (
            "Switches the assistant's voice. Sri only ever uses a FEMALE voice. "
            "Use when the user asks to switch to a different female voice. The "
            "session briefly reconnects to apply the new voice. Male voices are "
            "not available."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "voice": {"type": "STRING", "description": "A female Gemini voice: Aoede (default) | Kore | Leda | Zephyr"}
            },
            "required": []
        }
    },
    {
        "name": "set_voice_sample",
        "description": (
            "Clones the assistant's speaking voice from an audio file the user "
            "uploaded or pointed to. Use when the user says to use a specific "
            "audio file / recording / sample as the voice, or uploads an audio "
            "clip to be used as the voice. Works for languages XTTS supports "
            "(e.g. English, Hindi)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Absolute path to the audio file (mp3/wav) to clone the voice from"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "standby",
        "description": (
            "Puts the assistant into standby / sleep mode. Use when the user "
            "says go to sleep, standby, power down, that's all, or goodbye for "
            "now. After this, the assistant waits silently for a clap or finger "
            "snap to wake."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        # Voice/persona (switch_voice tool). Default Sri = Aoede.
        self.voice_name          = "Aoede"
        self.persona             = "Sri"
        self._reconnect_event: asyncio.Event | None = None
        self._announce_voice     = False
        # Standby / clap-to-wake. Starts asleep; a clap (or wake hook) wakes it.
        self.asleep              = True
        self._woke_at            = 0.0
        self._clap               = _ClapDetector(_clap_sensitivity())
        self.ui.on_wake          = self._request_wake
        # Last user utterance sample → lets the wake greeting match their
        # language across restarts. Restored from disk on launch.
        self._last_user_text     = _load_lang_sample()
        # Cloned-voice TTS (XTTS-v2). Defaults to the Anika reference voice.
        # Until the worker is ready (or for languages XTTS can't speak), Sri
        # falls back to Gemini's built-in voice automatically.
        self.voice_engine        = VoiceEngine()
        self.voice_engine.start()

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _enqueue_pcm(self, pcm: bytes):
        """Push synthesized 24kHz int16 PCM into the playback queue in
        playback-sized chunks so set_speaking() toggles smoothly."""
        step = CHUNK_SIZE * 2          # int16 mono -> 2 bytes/frame
        for i in range(0, len(pcm), step):
            self.audio_in_queue.put_nowait(pcm[i:i + step])

    def set_voice_sample(self, args: dict) -> str:
        """Switch the cloned voice to a user-supplied audio file (upload)."""
        path = str(args.get("path") or args.get("file") or "").strip()
        if not path:
            return "I didn't get an audio file path to clone the voice from, sir."
        if self.voice_engine.set_speaker(path):
            name = Path(path).name
            self.ui.write_log(f"SYS: Voice sample set to {name}.")
            return (f"Got it — I'll speak using the voice from {name} from now on. "
                    f"Note this works for supported languages like English and Hindi.")
        return f"I couldn't find that audio file, sir: {path}"

    def _switch_voice(self, args: dict) -> str:
        """Apply a new voice/persona and trigger a session reconnect."""
        choice = resolve_voice(args)
        if choice["voice"] == self.voice_name:
            return f"I'm already using the {self.persona} voice, sir."

        self.voice_name      = choice["voice"]
        self.persona         = choice["persona"]
        self._announce_voice = True
        self.ui.write_log(f"SYS: Switching voice to {self.persona} ({self.voice_name}).")

        # Break the current session so run() reconnects with the new voice.
        if self._reconnect_event is not None:
            self._reconnect_event.set()
        return f"Switching to the {self.persona} voice now, sir."

    # ── Standby / clap-to-wake ─────────────────────────────────────────────
    def _request_wake(self):
        """Thread-safe wake trigger (called from the audio or GUI thread)."""
        if self._loop and self.asleep:
            self._loop.call_soon_threadsafe(self._schedule_wake)

    def _schedule_wake(self):
        if self.asleep and self.session:
            asyncio.create_task(self._wake())

    async def _wake(self):
        if not self.asleep:
            return
        self.asleep = False
        self._woke_at = time.time()
        print("[JARVIS] 👏 Wake signal — booting up.")
        self.ui.write_log("SYS: Wake signal detected.")
        self.ui.set_state("WAKING")
        # Let the boot-up animation play before greeting.
        await asyncio.sleep(2.2)
        if self.asleep:        # went back to sleep mid-boot
            return
        self.ui.set_state("LISTENING")
        self._send_wake_greeting()

    def _send_wake_greeting(self):
        sample = (self._last_user_text or "").strip()
        if sample:
            lang_clause = (
                f"The user has been speaking in this language: \"{sample}\". "
                f"Greet them in THAT SAME language (do not translate to English). "
            )
        else:
            lang_clause = "Greet them in English (no prior language is known yet). "
        self.speak(
            "SYSTEM: The user just activated you. " + lang_clause +
            "Reply now with one brief, warm spoken greeting for the current "
            "time of day and ask how you can help. Do not call any tools — just "
            "speak the greeting."
        )

    def _enter_standby(self) -> str:
        """Put JARVIS to sleep; it then waits for a clap or snap to wake."""
        # Guard against a spurious standby right after waking (e.g. the model
        # misfiring on the wake greeting). Ignore standby within 4s of waking.
        if time.time() - self._woke_at < 4.0:
            return "I just woke up, sir — standing by and ready to help."
        self.asleep = True
        self._clap.reset(cooldown=2.0)
        self.ui.set_state("ASLEEP")
        self.ui.write_log("SYS: Entering standby — clap or snap to wake.")
        print("[JARVIS] 😴 Standby. Clap or snap to wake.")
        return "Going into standby, sir. Clap or snap when you need me."

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)
        if self.persona and self.persona != "J.A.R.V.I.S":
            parts.append(
                f"\n[PERSONA]\nYou are currently operating as {self.persona}. "
                f"Refer to yourself as {self.persona} when naming yourself.\n"
            )

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_stats":
                r = await loop.run_in_executor(None, lambda: system_stats(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "wikipedia_lookup":
                r = await loop.run_in_executor(None, lambda: wikipedia_lookup(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "define_word":
                r = await loop.run_in_executor(None, lambda: define_word(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "tell_joke":
                r = await loop.run_in_executor(None, lambda: tell_joke(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "news":
                r = await loop.run_in_executor(None, lambda: news_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_email":
                r = await loop.run_in_executor(None, lambda: send_email(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "translate":
                r = await loop.run_in_executor(None, lambda: translate_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "youtube_download":
                r = await loop.run_in_executor(None, lambda: youtube_download(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "ocr_read":
                r = await loop.run_in_executor(None, lambda: ocr_read(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "face_auth":
                r = await loop.run_in_executor(None, lambda: face_auth(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "my_location":
                r = await loop.run_in_executor(None, lambda: my_location(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "maps_search":
                r = await loop.run_in_executor(None, lambda: maps_search(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "track_price":
                r = await loop.run_in_executor(None, lambda: track_price(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "switch_voice":
                result = self._switch_voice(args)

            elif name == "set_voice_sample":
                result = self.set_voice_sample(args)

            elif name == "standby":
                result = self._enter_standby()

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    try:
                        self.voice_engine.stop()
                    except Exception:
                        pass
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _watch_reconnect(self):
        """Wait for a voice-switch request, then break the session so run()
        reconnects with the newly-selected voice."""
        await self._reconnect_event.wait()
        raise _VoiceSwitch()

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking

            # While asleep, listen only for a clap to wake — don't stream to
            # Gemini. Skip detection while JARVIS is speaking (its own audio
            # could leak into the mic).
            if self.asleep:
                if not jarvis_speaking:
                    try:
                        if self._clap.feed(indata[:, 0]):
                            loop.call_soon_threadsafe(self._schedule_wake)
                    except Exception:
                        pass
                return

            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _speak_cloned(self, text: str, native_buf: list):
        """Speak this reply in the cloned (uploaded) voice when possible, else
        play the buffered Gemini audio we held back as a fallback."""
        pcm = None
        if text:
            self.ui.set_state("THINKING")
            pcm = await asyncio.to_thread(self.voice_engine.synthesize, text)
        if pcm:
            self._enqueue_pcm(pcm)
        else:
            for chunk in native_buf:
                self.audio_in_queue.put_nowait(chunk)

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []
        native_buf      = []      # raw Gemini audio, held back for fallback
        clone_turn      = False   # latched per turn: clone this reply?
        turn_started    = False

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        if not turn_started:
                            turn_started = True
                            # Decide once per turn: clone only if the voice
                            # worker is ready now; otherwise stream Gemini live.
                            clone_turn = self.voice_engine.ready
                        if clone_turn:
                            native_buf.append(response.data)   # hold for fallback
                        else:
                            self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                # Remember the language for the next wake greeting.
                                self._last_user_text = full_in
                                _save_lang_sample(full_in)
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Sri: {full_out}")
                            out_buf = []

                            # Cloned-voice playback (or fallback to Gemini audio).
                            if clone_turn:
                                await self._speak_cloned(full_out, native_buf)
                            native_buf   = []
                            turn_started = False
                            clone_turn   = False

                            if self._turn_done_event:
                                self._turn_done_event.set()

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()
                    self._reconnect_event = asyncio.Event()

                    print(f"[JARVIS] ✅ Connected ({self.persona} / {self.voice_name}).")
                    if self.asleep:
                        self._clap.reset(cooldown=1.0)
                        self.ui.set_state("ASLEEP")
                        self.ui.write_log("SYS: JARVIS online — standby. Clap or snap to wake.")
                    else:
                        self.ui.set_state("LISTENING")
                        self.ui.write_log("SYS: JARVIS online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._watch_reconnect())

                    # After a voice switch, greet in the new voice so the user
                    # immediately hears the change.
                    if self._announce_voice and not self.asleep:
                        self._announce_voice = False
                        await asyncio.sleep(0.4)
                        self.speak(f"This is {self.persona}. How do I sound now, sir?")

            except Exception as e:
                if _is_voice_switch(e):
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    print(f"[JARVIS] 🎚️  Switching voice → {self.voice_name}; reconnecting now...")
                    continue
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)

def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()