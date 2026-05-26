@echo off
REM Agent Sri - Windows setup script
REM Usage (from this folder):  install_windows.bat
setlocal

cd /d "%~dp0"

echo ==> Python version:
python --version
if errorlevel 1 (
    echo Python not found on PATH. Install Python 3.11/3.12 from python.org and re-run.
    exit /b 1
)

echo ==> Creating virtual environment (.venv)...
python -m venv .venv
call .venv\Scripts\activate.bat

echo ==> Upgrading pip...
python -m pip install --upgrade pip

echo ==> Installing Python dependencies...
pip install -r requirements.txt

echo ==> Installing Playwright Chromium...
python -m playwright install chromium

echo ==> Installing Tesseract OCR engine (winget)...
where winget >nul 2>nul
if %errorlevel%==0 (
    winget install --id UB-Mannheim.TesseractOCR -e --accept-source-agreements --accept-package-agreements
) else (
    echo     winget not available. Install Tesseract manually from:
    echo     https://github.com/UB-Mannheim/tesseract/wiki
)

echo ==> Setting up the cloned-voice engine (XTTS-v2)...
REM XTTS (coqui-tts) needs Python 3.10-3.12, separate from the main app's venv.
REM Optional: if it can't be set up, Sri falls back to Gemini's built-in voice.
set "TTS_PY="
for %%V in (3.11 3.12 3.10) do (
    if not defined TTS_PY (
        py -%%V --version >nul 2>nul && set "TTS_PY=py -%%V"
    )
)
if defined TTS_PY (
    echo     Using "%TTS_PY%" for the .venv-tts voice environment...
    %TTS_PY% -m venv .venv-tts
    .venv-tts\Scripts\python.exe -m pip install --upgrade pip
    .venv-tts\Scripts\python.exe -m pip install -r requirements.tts.txt
    echo     Cloned-voice engine installed ^(model ~1.8GB downloads on first use^).
) else (
    echo     No Python 3.10-3.12 found via the 'py' launcher — skipping voice cloning.
    echo     Sri will use Gemini's built-in voice. Install Python 3.11 from python.org to enable it.
)

echo.
echo ============================================================
echo  Setup complete.
echo   1^) Add your Gemini API key to config\api_keys.json
echo   2^) Run:  .venv\Scripts\python main.py
echo ============================================================

endlocal
