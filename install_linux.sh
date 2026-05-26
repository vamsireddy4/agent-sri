#!/usr/bin/env bash
# Agent Sri — Linux setup script
# Usage:  bash install_linux.sh
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo "==> Python version:"
"$PY" --version

# ── System packages ─────────────────────────────────────────────────────────
# sounddevice -> PortAudio; pyautogui -> scrot/xdotool; OCR -> tesseract.
echo "==> Installing system packages (sudo may prompt)..."
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y \
    python3-venv python3-dev \
    libportaudio2 portaudio19-dev \
    tesseract-ocr \
    scrot xdotool \
    libxcb-cursor0 libegl1 libgl1   # Qt/PyQt6 runtime libs
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3-virtualenv python3-devel \
    portaudio portaudio-devel tesseract scrot xdotool \
    libxcb mesa-libEGL mesa-libGL
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -Sy --needed --noconfirm \
    python-virtualenv portaudio tesseract scrot xdotool \
    xcb-util-cursor libglvnd
else
  echo "    Unknown package manager — please install manually:"
  echo "    PortAudio, tesseract-ocr, scrot, xdotool, and Qt/EGL/GL libs."
fi

# ── Main app virtual environment ─────────────────────────────────────────────
echo "==> Creating virtual environment (.venv)..."
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Upgrading pip..."
python -m pip install --upgrade pip

echo "==> Installing Python dependencies..."
if [ -f requirements.linux.txt ]; then
  pip install -r requirements.linux.txt
else
  pip install -r requirements.mac.txt    # same non-Windows set
fi

echo "==> Installing Playwright Chromium + OS deps..."
python -m playwright install --with-deps chromium

deactivate || true

# ── Cloned-voice engine (XTTS-v2) ────────────────────────────────────────────
echo "==> Setting up the cloned-voice engine (XTTS-v2)..."
# XTTS (coqui-tts) needs Python 3.10-3.12, separate from the main app's venv.
# Optional: if it can't be set up, Sri falls back to Gemini's built-in voice.
TTS_PY="$(command -v python3.11 || command -v python3.12 || command -v python3.10 || true)"
if [ -n "$TTS_PY" ]; then
  echo "    Using $TTS_PY for the .venv-tts voice environment..."
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "$TTS_PY" .venv-tts && \
      uv pip install --python .venv-tts/bin/python -r requirements.tts.txt
  else
    "$TTS_PY" -m venv .venv-tts && \
      .venv-tts/bin/python -m pip install --upgrade pip && \
      .venv-tts/bin/python -m pip install -r requirements.tts.txt
  fi
  echo "    Cloned-voice engine installed (model ~1.8GB downloads on first use)."
else
  echo "    No Python 3.10-3.12 found — skipping the cloned-voice engine."
  echo "    Sri will use Gemini's built-in voice. Install e.g. 'sudo apt install python3.11-venv' to enable voice cloning."
fi

echo ""
echo "============================================================"
echo " Setup complete."
echo "  1) Add your Gemini API key to config/api_keys.json"
echo "  2) Run:  .venv/bin/python main.py"
echo "============================================================"
