# ocr_reader.py
"""Offline text extraction (OCR) from an image file, the screen, or the webcam.

Uses Tesseract via pytesseract. This is a local/offline alternative to the
Gemini-powered screen vision tool — handy for quickly pulling raw text out of
a document image, a screenshot, or a page held up to the camera.

Requires the tesseract binary:
  macOS:    brew install tesseract
  Windows:  winget install UB-Mannheim.TesseractOCR
  Linux:    sudo apt install tesseract-ocr
"""
import os
import platform
import shutil
from pathlib import Path

try:
    import pytesseract
    from PIL import Image
    _PYTESSERACT = True
except ImportError:
    _PYTESSERACT = False

_IS_WINDOWS = platform.system() == "Windows"

# Common locations the tesseract binary lands in, so OCR works even when the
# app is launched with a minimal PATH (e.g. from Finder/Explorer, not a shell).
_TESSERACT_CANDIDATES = (
    "/opt/homebrew/bin/tesseract",                          # Apple-silicon Homebrew
    "/usr/local/bin/tesseract",                             # Intel Homebrew
    "/usr/bin/tesseract",                                   # Linux
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",        # Windows (UB Mannheim)
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",  # Windows (32-bit)
)


def _locate_tesseract() -> str | None:
    found = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if found:
        return found
    candidates = list(_TESSERACT_CANDIDATES)
    local = os.environ.get("LOCALAPPDATA")
    if local:  # winget per-user install location on Windows
        candidates.append(
            str(Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
        )
    for cand in candidates:
        if cand and Path(cand).exists():
            return cand
    return None


def _open_camera(index: int = 0):
    """Open the webcam with the most reliable backend per platform.

    Windows opens far faster (and without warnings) via DirectShow."""
    import cv2
    if _IS_WINDOWS:
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(index)


def _grab_screen():
    import pyautogui
    return pyautogui.screenshot()


def _grab_camera():
    import cv2
    cam = _open_camera(0)
    try:
        # Discard a few warm-up frames so exposure/focus settle.
        frame = None
        for _ in range(5):
            ok, frame = cam.read()
        if not ok or frame is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    finally:
        cam.release()


def ocr_read(parameters: dict, response=None, player=None,
             session_memory=None) -> str:
    if not _PYTESSERACT:
        return "pytesseract / Pillow not installed — cannot run OCR."

    tess = _locate_tesseract()
    if not tess:
        hint = ("winget install UB-Mannheim.TesseractOCR" if _IS_WINDOWS
                else "brew install tesseract")
        return (f"Tesseract OCR engine not found. Install it ({hint}) "
                f"and try again.")
    pytesseract.pytesseract.tesseract_cmd = tess

    params = parameters or {}
    source = str(params.get("source", "screen")).lower().strip()
    path = str(params.get("path", "")).strip()

    print(f"[OCR] 🔎 source={source} {path}")
    try:
        if source in ("file", "image") or path:
            img_path = Path(path).expanduser()
            if not img_path.exists():
                return f"Image file not found: {img_path}"
            img = Image.open(str(img_path))
        elif source in ("camera", "webcam"):
            img = _grab_camera()
            if img is None:
                return "Could not capture from the webcam (no frame / no access)."
        else:  # screen
            img = _grab_screen()

        text = pytesseract.image_to_string(img).strip()
    except Exception as e:
        return f"OCR failed: {e}"

    if not text:
        return "I scanned the image but found no readable text."

    # Collapse noisy whitespace for a cleaner spoken/printed result.
    cleaned = " ".join(text.split())
    if player:
        player.write_log(f"[ocr] {len(cleaned)} chars")

    preview = cleaned if len(cleaned) <= 1500 else cleaned[:1500] + " …(truncated)"
    return f"Here is the text I read: {preview}"
