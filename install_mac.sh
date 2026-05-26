#!/usr/bin/env bash
# Agent Sri — macOS / Linux setup script
# Usage:  bash install_mac.sh
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo "==> Python version:"
"$PY" --version

echo "==> Creating virtual environment (.venv)..."
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Upgrading pip..."
python -m pip install --upgrade pip

echo "==> Installing Python dependencies..."
if [ -f requirements.mac.txt ]; then
  pip install -r requirements.mac.txt
else
  pip install -r requirements.txt
fi

echo "==> Installing Playwright Chromium..."
python -m playwright install chromium

echo "==> Installing Tesseract OCR engine..."
if command -v brew >/dev/null 2>&1; then
  brew list tesseract >/dev/null 2>&1 || brew install tesseract
elif command -v apt >/dev/null 2>&1; then
  sudo apt-get update && sudo apt-get install -y tesseract-ocr
else
  echo "    Could not auto-install tesseract."
  echo "    macOS: install Homebrew (https://brew.sh) then 'brew install tesseract'"
fi

echo "==> Setting up the cloned-voice engine (XTTS-v2)..."
# XTTS (coqui-tts) needs Python 3.10-3.12, separate from the main app's venv.
# It's optional: if it can't be set up, Sri falls back to Gemini's built-in voice.
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
  echo "    Sri will use Gemini's built-in voice. Install e.g. 'brew install python@3.11' to enable voice cloning."
fi

echo ""
echo "============================================================"
echo " Setup complete."
echo "  1) Add your Gemini API key to config/api_keys.json"
echo "  2) Run:  .venv/bin/python main.py"
echo "============================================================"
