# ▶️ Running Agent Sri — commands for macOS, Windows & Linux

Quick copy-paste reference. Full details are in [`readme.md`](readme.md) and
[`FEATURES.md`](FEATURES.md).

## 0. Prerequisites (all platforms)

- **Python 3.11+** for the main app (uses `asyncio.TaskGroup`).
- A **3.10–3.12** Python as well if you want the cloned voice (XTTS).
- **git**, a **microphone**, and a free **Gemini API key** → https://aistudio.google.com/apikey

```bash
git clone https://github.com/vamsireddy4/agent-sri.git "Agent Sri"
cd "Agent Sri"
```

---

## 🍎 macOS

```bash
bash install_mac.sh                                   # deps + tesseract + voice engine
echo '{ "gemini_api_key": "YOUR_KEY" }' > config/api_keys.json
.venv/bin/python main.py
```

## 🐧 Linux

```bash
bash install_linux.sh                                 # apt/dnf/pacman system deps + both venvs
echo '{ "gemini_api_key": "YOUR_KEY" }' > config/api_keys.json
.venv/bin/python main.py
```

## 🪟 Windows (Command Prompt, in the project folder)

```bat
install_windows.bat
echo { "gemini_api_key": "YOUR_KEY" } > config\api_keys.json
.venv\Scripts\python main.py
```

> Tip: instead of editing the JSON, just run the app — on first boot Sri shows a
> config screen where you paste the Gemini key.

---

## 🛠️ Manual install (skip the installer scripts)

```bash
# 1) main app venv (Python 3.11+)
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.mac.txt       # macOS
#   Linux:   pip install -r requirements.linux.txt
#   Windows: pip install -r requirements.txt
python -m playwright install chromium

# 2) OCR engine
#   macOS:    brew install tesseract
#   Linux:    sudo apt install tesseract-ocr
#   Windows:  winget install UB-Mannheim.TesseractOCR

# 3) optional cloned-voice engine (separate Python 3.10–3.12 venv)
python3.11 -m venv .venv-tts
.venv-tts/bin/python -m pip install -r requirements.tts.txt
#   Windows: .venv-tts\Scripts\python -m pip install -r requirements.tts.txt
```

---

## ▶️ Run it (after setup)

| OS | Command |
|----|---------|
| macOS / Linux | `.venv/bin/python main.py` |
| Windows | `.venv\Scripts\python main.py` |

Sri starts in standby — **clap or snap** to wake her, then talk. Drop an audio
file on the window and say *"use this as your voice"* to clone a new voice.

---

## 🐛 Quick fixes

| Symptom | Fix |
|---|---|
| `asyncio.TaskGroup` / syntax error on launch | Main venv must be **Python 3.11+** |
| Generic voice instead of the clone | `.venv-tts` not installed, still loading (~30s), or the reply is in a language XTTS can't speak |
| Linux: `PortAudio` / no audio | `sudo apt install libportaudio2 portaudio19-dev` |
| Linux: Qt won't start | `sudo apt install libxcb-cursor0 libegl1 libgl1` (needs a display; X11/XWayland) |
| Browser opens a new, not-signed-in window | Let Sri relaunch your browser once with your real profile |
