# MARK XXXIX — Features & Voice Commands

This file documents the macOS compatibility work and the new tools added on top
of the upstream project. There are now **30 tools** total.

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

### Requires credentials (in `config/api_keys.json`)
| Tool | Example | Needs |
|------|---------|-------|
| `news` | "What's the news?", "Tech headlines" | `newsapi_key` — free at https://newsapi.org/register |
| `send_email` | "Email bob@x.com saying I'll be late" | `email_address` + `email_app_password` (Gmail App Password) |

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

## Setup notes

```bash
pip install -r requirements.txt        # or requirements.mac.txt on macOS
playwright install
brew install tesseract                 # macOS: OCR engine for ocr_read
python main.py
```

- Face recognition needs **`opencv-contrib-python`** (provides `cv2.face`); it
  replaces plain `opencv-python`.
- OCR needs the **tesseract** binary on PATH (`brew install tesseract`).
- `face_data/` (local biometric model + samples) is git-ignored.
