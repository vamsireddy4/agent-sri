"""Cloned-voice TTS engine for Sri (main app, Python 3.13 side).

Sri's "brain" stays on Gemini Live, but instead of playing Gemini's built-in
voice we synthesize each reply in a *cloned* voice using XTTS-v2. XTTS can't run
on Python 3.13, so the model lives in ``tts/worker.py`` under a dedicated 3.11
venv (``.venv-tts``); this module spawns and drives that worker.

Public API (all safe to call before the worker is ready):

    engine = VoiceEngine()
    engine.start()                       # spawn worker in the background
    engine.set_speaker(path)             # switch the reference/clone audio
    pcm = engine.synthesize(text)        # -> 24kHz int16 PCM bytes, or None

``synthesize`` returns ``None`` whenever we should fall back to Gemini's native
voice: the worker isn't ready yet, synthesis failed, or the reply is in a
language XTTS-v2 doesn't support (e.g. Telugu/Tamil). Callers play the native
Gemini audio in that case.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path

import numpy as np

BASE_DIR        = Path(__file__).resolve().parent.parent
WORKER_PY       = BASE_DIR / "tts" / "worker.py"

# venv layout differs by OS: Scripts\python.exe on Windows, bin/python elsewhere.
if sys.platform == "win32":
    TTS_PYTHON = BASE_DIR / ".venv-tts" / "Scripts" / "python.exe"
else:
    TTS_PYTHON = BASE_DIR / ".venv-tts" / "bin" / "python"

DEFAULT_SPEAKER = BASE_DIR / "config" / "voices" / "anika.wav"
OUTPUT_RATE     = 24000          # XTTS-v2 output sample rate / our playback rate

# Languages XTTS-v2 can actually speak. Anything else -> fall back to Gemini.
_XTTS_LANGS = {
    "en", "es", "fr", "de", "it", "pt", "pl", "tr",
    "ru", "nl", "cs", "ar", "zh-cn", "hu", "ko", "ja", "hi",
}


def detect_language(text: str) -> str | None:
    """Pick an XTTS language code from the script of ``text``.

    Returns a supported code (e.g. 'hi', 'en') or ``None`` when the dominant
    script isn't something XTTS-v2 can synthesize, signalling a fallback.
    """
    counts: dict[str, int] = {}

    def bump(key: str):
        counts[key] = counts.get(key, 0) + 1

    for ch in text:
        o = ord(ch)
        if   0x0900 <= o <= 0x097F: bump("hi")          # Devanagari (Hindi/Marathi)
        elif 0x0C00 <= o <= 0x0C7F: bump("_te")         # Telugu     (unsupported)
        elif 0x0B80 <= o <= 0x0BFF: bump("_ta")         # Tamil      (unsupported)
        elif 0x0C80 <= o <= 0x0CFF: bump("_kn")         # Kannada    (unsupported)
        elif 0x0D00 <= o <= 0x0D7F: bump("_ml")         # Malayalam  (unsupported)
        elif 0x0980 <= o <= 0x09FF: bump("_bn")         # Bengali    (unsupported)
        elif 0x0A80 <= o <= 0x0AFF: bump("_gu")         # Gujarati   (unsupported)
        elif 0x0600 <= o <= 0x06FF: bump("ar")          # Arabic
        elif 0x0400 <= o <= 0x04FF: bump("ru")          # Cyrillic
        elif 0x3040 <= o <= 0x30FF: bump("ja")          # Hiragana/Katakana
        elif 0xAC00 <= o <= 0xD7A3: bump("ko")          # Hangul
        elif 0x4E00 <= o <= 0x9FFF: bump("zh-cn")       # Han
        elif ch.isalpha() and o < 0x250:  bump("en")    # Latin -> default English

    if not counts:
        return "en"
    best = max(counts, key=counts.get)
    if best.startswith("_"):        # detected but unsupported script
        return None
    return best if best in _XTTS_LANGS else None


class VoiceEngine:
    def __init__(self, speaker_wav: str | Path | None = None):
        self.speaker_wav = str(speaker_wav or DEFAULT_SPEAKER)
        self._proc: subprocess.Popen | None = None
        self._ready = threading.Event()
        self._failed = False
        self._io_lock = threading.Lock()     # serialize one req/resp at a time
        self._tmpdir = Path(tempfile.mkdtemp(prefix="sri_tts_"))

    # ── lifecycle ─────────────────────────────────────────────────────────
    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    @property
    def available(self) -> bool:
        """True if the worker can be used (or is still booting), False if the
        venv/worker is missing or has permanently failed."""
        return not self._failed and TTS_PYTHON.exists() and WORKER_PY.exists()

    def start(self) -> None:
        """Spawn the worker in a background thread (non-blocking)."""
        if not (TTS_PYTHON.exists() and WORKER_PY.exists()):
            print(f"[VOICE] XTTS venv/worker not found "
                  f"({TTS_PYTHON} / {WORKER_PY}); using Gemini voice for now.")
            self._failed = True
            return
        threading.Thread(target=self._boot, name="xtts-boot", daemon=True).start()

    def _boot(self) -> None:
        try:
            print("[VOICE] Booting XTTS worker (model load can take ~30s)...")
            self._proc = subprocess.Popen(
                [str(TTS_PYTHON), str(WORKER_PY)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,                 # worker logs straight to our stderr
                text=True,
                bufsize=1,
                cwd=str(BASE_DIR),
            )
            # Wait for the READY line.
            for line in self._proc.stdout:           # type: ignore[union-attr]
                if line.strip() == "READY":
                    self._ready.set()
                    print("[VOICE] ✅ XTTS worker ready — Sri will use the cloned voice.")
                    return
            # stdout closed without READY -> the worker died.
            self._failed = True
            print("[VOICE] ❌ XTTS worker exited before becoming ready; using Gemini voice.")
        except Exception as e:                       # noqa: BLE001
            self._failed = True
            print(f"[VOICE] ❌ Could not start XTTS worker: {e}")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")  # type: ignore[union-attr]
                self._proc.stdin.flush()             # type: ignore[union-attr]
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()

    # ── voice selection ───────────────────────────────────────────────────
    def set_speaker(self, path: str | Path) -> bool:
        """Point the clone at a new reference audio file. Returns True if the
        file exists and was accepted."""
        p = Path(path).expanduser()
        if not p.is_file():
            return False
        self.speaker_wav = str(p)
        print(f"[VOICE] Reference voice set to: {p.name}")
        return True

    # ── synthesis ─────────────────────────────────────────────────────────
    def synthesize(self, text: str, language: str | None = None) -> bytes | None:
        """Synthesize ``text`` in the cloned voice -> 24kHz mono int16 PCM bytes.

        Returns ``None`` to mean "fall back to Gemini's native voice": worker
        not ready, unsupported language, or any failure.
        """
        text = (text or "").strip()
        if not text or not self.ready or self._proc is None:
            return None

        lang = language or detect_language(text)
        if lang is None:
            print("[VOICE] Reply language unsupported by XTTS — using Gemini voice this turn.")
            return None

        out_path = self._tmpdir / f"{uuid.uuid4().hex}.wav"
        req = {
            "text": text,
            "language": lang,
            "speaker_wav": self.speaker_wav,
            "out_path": str(out_path),
        }
        try:
            with self._io_lock:
                if self._proc.poll() is not None:
                    self._failed = True
                    return None
                self._proc.stdin.write(json.dumps(req) + "\n")   # type: ignore[union-attr]
                self._proc.stdin.flush()                          # type: ignore[union-attr]
                resp_line = self._proc.stdout.readline()          # type: ignore[union-attr]
            if not resp_line:
                return None
            resp = json.loads(resp_line)
            if not resp.get("ok"):
                print(f"[VOICE] synth failed: {resp.get('error')}")
                return None
            pcm = _wav_to_pcm16(out_path, OUTPUT_RATE)
            return pcm
        except Exception as e:                       # noqa: BLE001
            print(f"[VOICE] synth error: {e}")
            return None
        finally:
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass


def _wav_to_pcm16(path: Path, target_rate: int) -> bytes:
    """Read a wav file -> mono int16 PCM bytes at ``target_rate``."""
    with wave.open(str(path), "rb") as wf:
        rate     = wf.getframerate()
        channels = wf.getnchannels()
        width    = wf.getsampwidth()
        frames   = wf.readframes(wf.getnframes())

    if width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:  # 8-bit unsigned
        audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128) / 128.0

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    if rate != target_rate and audio.size:
        n_out = int(round(audio.size * target_rate / rate))
        x_old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        audio = np.interp(x_new, x_old, audio).astype(np.float32)

    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767.0).astype("<i2").tobytes()
