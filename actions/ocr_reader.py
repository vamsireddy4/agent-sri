# ocr_reader.py
"""Offline text extraction (OCR) from an image file, the screen, or the webcam.

Uses Tesseract via pytesseract. This is a local/offline alternative to the
Gemini-powered screen vision tool — handy for quickly pulling raw text out of
a document image, a screenshot, or a page held up to the camera.

Requires the tesseract binary:  brew install tesseract  (macOS)
"""
import shutil
from pathlib import Path

try:
    import pytesseract
    from PIL import Image
    _PYTESSERACT = True
except ImportError:
    _PYTESSERACT = False

# Common locations the tesseract binary lands in, so OCR works even when the
# app is launched with a minimal PATH (e.g. from Finder, not a shell).
_TESSERACT_CANDIDATES = (
    "/opt/homebrew/bin/tesseract",   # Apple-silicon Homebrew
    "/usr/local/bin/tesseract",      # Intel Homebrew
    "/usr/bin/tesseract",            # Linux
)


def _locate_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for cand in _TESSERACT_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def _grab_screen():
    import pyautogui
    return pyautogui.screenshot()


def _grab_camera():
    import cv2
    cam = cv2.VideoCapture(0)
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
        return ("Tesseract OCR engine not found. Install it with "
                "'brew install tesseract' (macOS) and try again.")
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
