# 🤖 Agent Sri

**A real-time, cross-platform personal AI assistant — she hears, sees, speaks, and controls your computer.**

Agent Sri is a voice assistant built on **Gemini Live**. She listens, talks back in a
**cloned voice**, understands and replies in **your language** (romanized, code-mixed —
Telugu→Tenglish, Hindi→Hinglish, …), sees your screen and webcam, controls apps and your
browser, and runs autonomous multi-step tasks. Runs on **macOS, Windows, and Linux**.

> Built on the open-source [Mark-XXXIX](https://github.com/FatihMakes/Mark-XXXIX) by
> **FatihMakes** (CC BY-NC 4.0), then extended with the cloned voice, romanized
> multilingual replies, signed-in browser control, and Linux support.

---

## ✨ Capabilities

| Feature | Description |
|---|---|
| 🎙️ Real-time voice | Low-latency conversation; wake with a clap/snap from standby |
| 🗣️ Cloned voice | Speaks in a voice cloned from any audio clip (default: bundled **Anika** Indian voice) via XTTS-v2 |
| 🌐 Your language | Detects your language and replies romanized + code-mixed (Tenglish / Hinglish / Tanglish …) |
| 🧩 Autonomous tasks | High-level planning for complex, multi-step goals |
| 🖥️ System control | Launch apps, manage files, run OS actions (volume, brightness, power…) |
| 🌍 Browser control | Drives your **signed-in** browser (attaches over CDP; relaunches your real profile if needed) |
| 👁️ Vision | Real-time screen processing and webcam OCR / face auth |
| 🧠 Memory | Remembers your preferences and context across sessions |
| 🛠️ Tools | Wikipedia, dictionary, jokes, news, weather, maps, location, web/YouTube search & download, email, price tracking, translation, and more |

---

## 📋 Requirements

| | Details |
|---|---|
| **OS** | macOS · Windows 10/11 · Linux (X11; XWayland on Wayland) |
| **Python (main app)** | **3.11+** (uses `asyncio.TaskGroup`) |
| **Python (voice clone)** | **3.10–3.12** for the optional XTTS engine (separate venv) |
| **Microphone** | Required for voice |
| **API key** | Free **Gemini API key** → https://aistudio.google.com/apikey |

The cloned voice is **optional** — if its engine isn't installed, Sri falls back to a built-in Gemini voice.

---

## ⚡ Quick start

```bash
git clone https://github.com/vamsireddy4/agent-sri.git "Agent Sri"
cd "Agent Sri"
```

Then run the installer for your OS (below), add your Gemini key, and launch.

### 🍎 macOS
```bash
bash install_mac.sh
# add your key to config/api_keys.json   (see "Configuration")
.venv/bin/python main.py
```

### 🐧 Linux
```bash
bash install_linux.sh        # installs system deps (PortAudio, tesseract, Qt libs…) via apt/dnf/pacman
# add your key to config/api_keys.json
.venv/bin/python main.py
```

### 🪟 Windows
```bat
install_windows.bat
REM add your key to config\api_keys.json
.venv\Scripts\python main.py
```

---

## 🔧 Manual install (any OS)

```bash
# 1) main app venv (Python 3.11+)
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # Windows
#   or: pip install -r requirements.mac.txt     (macOS)
#   or: pip install -r requirements.linux.txt   (Linux)
python -m playwright install chromium

# 2) OCR engine
#   macOS:    brew install tesseract
#   Linux:    sudo apt install tesseract-ocr
#   Windows:  winget install UB-Mannheim.TesseractOCR
```

### 🎙️ Optional: the cloned-voice engine (XTTS-v2)

XTTS needs Python 3.10–3.12, so it lives in its **own** venv (`.venv-tts`), separate from
the main app. The model (~1.8 GB) downloads automatically on first use.

```bash
# using uv (fast):
uv venv --python python3.11 .venv-tts
uv pip install --python .venv-tts/bin/python -r requirements.tts.txt

# or plain venv:
python3.11 -m venv .venv-tts
.venv-tts/bin/python -m pip install -r requirements.tts.txt   # Windows: .venv-tts\Scripts\python -m pip ...
```

`requirements.tts.txt` pins `coqui-tts[cpu]`, `torchcodec`, and `transformers<5`.

---

## ⚙️ Configuration

Create / edit `config/api_keys.json` (this file is git-ignored and never committed):

```json
{
  "gemini_api_key": "YOUR_GEMINI_KEY",
  "newsapi_key": "optional — https://newsapi.org/register",
  "email_address": "optional, for sending email",
  "email_app_password": "optional Gmail App Password"
}
```

Only `gemini_api_key` is required. See `FEATURES.md` for the full feature & voice-command list.

---

## 🗣️ Using the cloned voice

- Sri speaks in the bundled **Anika** voice by default (`config/voices/anika.wav`).
- To use your own voice: drop an audio clip (mp3/wav) on the UI, or say *"use this audio as your voice"* → she clones it.
- Voice cloning works for languages XTTS supports (e.g. **English, Hindi**). For Telugu/Tamil/etc. she falls back to a built-in Gemini voice.

---

## 🧰 Common commands

```bash
# Run the app
.venv/bin/python main.py                 # macOS / Linux
.venv\Scripts\python main.py             # Windows

# Re-run an installer (idempotent)
bash install_linux.sh                    # / install_mac.sh / install_windows.bat

# Update Playwright browsers
.venv/bin/python -m playwright install chromium

# Sanity-check the modules compile
.venv/bin/python -m py_compile main.py ui.py core/voice_engine.py
```

---

## 🐛 Troubleshooting

| Symptom | Fix |
|---|---|
| `asyncio.TaskGroup` / syntax error on launch | Main venv must be **Python 3.11+** |
| Sri uses a generic voice, not the clone | `.venv-tts` not installed, still loading (~30s), or the reply is in a language XTTS can't speak |
| Linux: no audio / `PortAudio` error | `sudo apt install libportaudio2 portaudio19-dev` |
| Linux: Qt fails to start | `sudo apt install libxcb-cursor0 libegl1 libgl1` (needs a display; X11/XWayland) |
| Browser opens a new, not-signed-in window | Let Sri relaunch your browser once with your real profile (CDP attach) |

---

## 🙌 Credits

Built and maintained by **[@vamsireddy4](https://github.com/vamsireddy4)** — including the
cloned-voice engine (XTTS-v2), romanized multilingual (Tenglish / Hinglish / …) replies,
signed-in browser control over CDP, the QPainter vector-icon UI, and the macOS / Windows /
Linux installers.

Foundation from the open-source [Mark-XXXIX](https://github.com/FatihMakes/Mark-XXXIX)
project by FatihMakes.

---

## ⚠️ License

Personal and non-commercial use only — **[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**, inherited from the upstream Mark-XXXIX project by [FatihMakes](https://www.youtube.com/@FatihMakes).
