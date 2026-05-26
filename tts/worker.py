#!/usr/bin/env python
"""XTTS-v2 voice-cloning worker (runs under the dedicated Python 3.11 venv).

The main Sri app runs on Python 3.13, which coqui-tts does not support, so the
heavy TTS model lives in this separate long-lived process. It loads XTTS-v2
once, then serves synthesis requests line-by-line over stdin/stdout:

    request  (stdin) : {"text": ..., "language": "en", "speaker_wav": "...",
                        "out_path": "/tmp/sri_xxx.wav"}
    response (stdout): {"ok": true, "out_path": "..."}  |  {"ok": false, "error": ...}

Audio is written to ``out_path`` (a wav file) rather than piped, so we never
push raw PCM through the pipe. One JSON object per line, both directions.
The line "READY" is printed to stdout once the model is loaded.
"""

import json
import os
import sys
import traceback

# Accept the Coqui model licence non-interactively so the first run does not
# block on a TTY prompt.
os.environ.setdefault("COQUI_TOS_AGREED", "1")

MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def _log(msg: str) -> None:
    print(f"[xtts-worker] {msg}", file=sys.stderr, flush=True)


def main() -> None:
    _log("loading torch + TTS ...")
    import torch
    from TTS.api import TTS

    # XTTS runs on Apple Silicon CPU here; allow MPS if it ever becomes stable.
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _log(f"device={device}; loading model {MODEL_NAME} (first run downloads ~1.8GB) ...")
    tts = TTS(MODEL_NAME).to(device)
    _log("model ready")

    # Signal readiness to the parent on stdout.
    print("READY", flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("cmd") == "quit":
                break
            text        = (req.get("text") or "").strip()
            language    = req.get("language") or "en"
            speaker_wav = req["speaker_wav"]
            out_path    = req["out_path"]
            if not text:
                raise ValueError("empty text")
            tts.tts_to_file(
                text=text,
                speaker_wav=speaker_wav,
                language=language,
                file_path=out_path,
                split_sentences=True,
            )
            print(json.dumps({"ok": True, "out_path": out_path}), flush=True)
        except Exception as e:  # noqa: BLE001 — report any failure, keep serving
            _log("synthesis error:\n" + traceback.format_exc())
            print(json.dumps({"ok": False, "error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
