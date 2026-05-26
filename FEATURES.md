# Agent Sri — Features & Voice Commands

This file documents the macOS compatibility work and the new tools added on top
of the upstream project. There are now **35 tools** total.

## Standby & clap/snap-to-wake + minimal UI

The assistant boots into **standby**: a dim, dormant glowing-iris HUD that says
"CLAP OR SNAP TO WAKE". It listens (locally, not streamed to Gemini) only for a
wake sound.

- **Clap or snap to wake** — a single clap *or* a finger snap powers it up with
  a boot-up animation, then JARVIS greets you by time of day (in your language)
  and asks how it can help, and the conversation begins. Detection is by sound
  *onset* (a sharp spike after quiet), so both a loud clap and a quieter snap
  trigger it. You can also wake it with **Space** or by **clicking the iris**
  (handy if the mic detection misfires).
- **`standby` tool** — say "go to sleep", "standby", "that's all", etc. and it
  returns to the dormant state, waiting for the next clap or snap.
- **Wake sensitivity** is tunable: set `"clap_sensitivity"` (0.0–1.0, default
  0.6) in `config/api_keys.json`. Higher = easier to trigger (catches softer
  snaps, but more prone to false wakes).
- **Minimal iris-centric UI** — the glowing teal iris is the centerpiece; the
  activity log and command box appear as small bottom overlays only when awake.
  Press **P** to toggle the full dashboard (sys-monitor, file-drop, full log),
  **F4** to mute, **F11** for fullscreen.

## macOS compatibility

The assistant runs natively on macOS. Key fixes:

- **OS auto-detection** — `config.get_os()` and the per-module OS helpers now
  auto-detect from `platform.system()` (with an optional `os_system` override in
  `config/api_keys.json`) instead of silently defaulting to Windows.
- **OS-aware shortcuts** — clipboard/select-all/clear in `computer_control.py`
  use ⌘ on macOS instead of Ctrl.
- **Window snapping** — `snap_left` / `snap_right` are implemented for macOS via
  AppleScript (resize the frontmost window to the left/right half).
- **Run dialog** — maps to **Spotlight** (⌘+Space) on macOS.

### macOS permissions
Grant these under **System Settings → Privacy & Security**:
- **Microphone** — voice input
- **Accessibility** — keyboard/mouse control + window snapping
- **Screen Recording** — screen vision & screen OCR
- **Camera** — webcam vision, OCR-from-camera, face recognition

---

## New feature tools

### No setup required
| Tool | Example voice command |
|------|------------------------|
| `system_stats` | "How's my CPU?", "What's my battery?", "How much disk space is left?" |
| `wikipedia_lookup` | "Who is Alan Turing?", "Tell me about black holes" |
| `define_word` | "Define serendipity" |
| `tell_joke` | "Tell me a joke" |
| `translate` | "How do you say good morning in Spanish?" |
| `youtube_download` | "Download this video", "Download the song <name> as audio" → saved to `~/Downloads` |
| `ocr_read` | "Read the text on my screen", "Read this document" (held to camera), "Read the text in <path>" |
| `face_auth` | "Verify my face", "Register my face as <name>", "Who's enrolled?", "Remove <name>'s face" |
| `weather_report` | "What's the weather?", "Weather in Tokyo" — speaks live temp/feels-like/humidity/wind (uses Open-Meteo; current location if no city) |
| `my_location` | "Where am I?", "What's my latitude and longitude?" (IP geolocation via ip-api.com) |
| `maps_search` | "Show me the Eiffel Tower on the map", "Directions from Paris to Lyon" (opens Google Maps) |
| `track_price` | "What's the price of this?" → give a product URL. "Tell me if it drops below 40" → checks an Amazon/shop page price |
| `switch_voice` | "Switch to a different voice" — Sri only ever uses a **female** voice (Aoede default; or name a female Gemini voice: Kore, Leda, Zephyr). Used only when the cloned voice isn't active. |
| `set_voice_sample` | "Use this audio as your voice" (after uploading an audio clip) — clones Sri's speaking voice from the file via XTTS-v2. Defaults to the bundled **Anika** Indian voice (`config/voices/anika.wav`). |
| `standby` | "Go to sleep", "standby", "that's all" — returns to the dormant clap-to-wake state |

### Requires credentials (in `config/api_keys.json`)
| Tool | Example | Needs |
|------|---------|-------|
| `news` | "What's the news?", "Tech headlines" | `newsapi_key` — free at https://newsapi.org/register |
| `send_email` | "Email bob@x.com saying I'll be late" | `email_address` + `email_app_password` (Gmail App Password) |
| `track_price` *(email alert only)* | "Email me if <url> drops below 40" | `email_address` + `email_app_password` — only when you ask for an email alert; checking the price needs no credentials |

### Ported from gaurav-jarvis
The `weather_report`, `my_location`, `maps_search`, `track_price`, and
`switch_voice` tools port the J.A.R.V.I.S (gauravsingh9356) features (live
weather, latitude/longitude, Google Maps search, the Amazon price tracker, and
the JARVIS↔FRIDAY voice switch) into Agent Sri's tool format. Because Agent Sri
speaks through a Gemini Live voice (set when the session connects), `switch_voice`
changes the stored voice and briefly reconnects the session to apply it. All
other gaurav-jarvis features (Wikipedia, dictionary, jokes, news, email,
translate, YouTube download/search, Google search, CPU/battery stats, OCR, face
recognition, screenshots, app/website launching, music, remember/recall, telling
the time, shutting down the PC) were already covered by existing Agent Sri tools.

---

## Cloned voice (Sri speaks in an uploaded voice)

Sri's "brain" is Gemini Live, but her **spoken voice** is cloned from an audio
sample using **XTTS-v2** (local, offline). The bundled default is the **Anika**
Indian voice (`config/voices/anika.wav`); upload any audio clip and say "use
this as your voice" (the `set_voice_sample` tool) to switch.

**How it runs.** XTTS-v2 (`coqui-tts`) needs Python 3.10–3.12, but the main app
runs on 3.13, so the model lives in a **separate process** under its own
`.venv-tts` (Python 3.11). `tts/worker.py` loads the model once; the main app
(`core/voice_engine.py`) sends it each reply's text and plays back the cloned
audio. The XTTS-v2 model (~1.8GB) downloads automatically on first use.

**Setup** (done by `install_mac.sh`, or manually):
```bash
uv venv --python python3.11 .venv-tts
uv pip install --python .venv-tts/bin/python "coqui-tts[cpu]" "coqui-tts[codec]"
# (pin transformers<5 if a 5.x version gets pulled in)
```

**Language support.** XTTS-v2 covers ~17 languages including **English** and
**Hindi** (great for Indian voices). For languages it can't speak — e.g.
**Telugu, Tamil, Kannada, Malayalam, Bengali** — Sri automatically falls back to
Gemini's built-in female voice for that reply, so she always responds. The
cloned voice also falls back to Gemini while the model is still loading or if
the `.venv-tts` isn't installed.

---

## Configuration (`config/api_keys.json`)

> This file is git-ignored — it holds your secrets and is never committed.

```json
{
    "gemini_api_key": "your Gemini key (aistudio.google.com/apikey)",
    "os_system": "mac",
    "newsapi_key": "your NewsAPI key (optional)",
    "email_address": "you@gmail.com (optional)",
    "email_app_password": "16-char Gmail App Password (optional)",
    "email_contacts": { "mom": "mom@example.com" }
}
```

- **Gmail App Password** (not your normal password) requires 2FA:
  https://myaccount.google.com/apppasswords
- `email_contacts` lets you say "email mom" instead of dictating the address.

---

## Installation (terminal)

The OCR and face-recognition tools work on **both macOS and Windows**. Use the
matching install script from a terminal in the project folder:

**macOS / Linux**
```bash
bash install_mac.sh
```

**Windows** (Command Prompt or PowerShell)
```bat
install_windows.bat
```

Each script creates a `.venv`, installs the Python dependencies + Playwright
Chromium, and installs the **Tesseract** OCR engine (Homebrew on macOS,
`winget` on Windows). Then add your Gemini key to `config/api_keys.json` and run:

```bash
# macOS/Linux
.venv/bin/python main.py
# Windows
.venv\Scripts\python main.py
```

### Manual install (if you prefer)
```bash
pip install -r requirements.txt        # use requirements.mac.txt on macOS
playwright install chromium
# OCR engine:
#   macOS:    brew install tesseract
#   Windows:  winget install UB-Mannheim.TesseractOCR
#   Linux:    sudo apt install tesseract-ocr
```

### Notes
- Face recognition needs **`opencv-contrib-python`** (provides `cv2.face`); it
  replaces plain `opencv-python` (which is removed from requirements).
- OCR needs the **tesseract** binary; the app auto-locates it in the standard
  Homebrew / `Program Files` / winget locations even if it isn't on PATH.
- The webcam opens via DirectShow (`CAP_DSHOW`) on Windows for fast, warning-free
  startup, and the default backend on macOS/Linux.
- `face_data/` (local biometric model + samples) is git-ignored.
