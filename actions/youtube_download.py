# youtube_download.py
"""Download a YouTube video or its audio to disk using yt-dlp.

Accepts a direct URL, or a search query (the first result is downloaded).
Files are saved to ~/Downloads. Audio extraction (kind="audio") needs ffmpeg
installed; without it, the original audio stream is saved as-is.
"""
import shutil
from pathlib import Path

try:
    import yt_dlp
    _YTDLP = True
except ImportError:
    _YTDLP = False


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def youtube_download(parameters: dict, response=None, player=None,
                     session_memory=None) -> str:
    if not _YTDLP:
        return "yt-dlp is not installed — cannot download. Run: pip install yt-dlp"

    params = parameters or {}
    url = str(params.get("url", "")).strip()
    query = str(params.get("query", "")).strip()
    kind = str(params.get("kind", "video")).lower().strip()

    if not url and not query:
        return "Please provide a YouTube URL or a search query to download."

    target = url if url else f"ytsearch1:{query}"
    out_dir = Path.home() / "Downloads"
    out_dir.mkdir(parents=True, exist_ok=True)

    opts = {
        "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch",
    }

    if kind == "audio" and _has_ffmpeg():
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    elif kind == "audio":
        # No ffmpeg → grab the best standalone audio stream as-is.
        opts["format"] = "bestaudio/best"
    else:
        opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

    print(f"[YTDownload] ⬇️  {kind}: {target}")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=True)
            if "entries" in info:  # search result wrapper
                info = info["entries"][0]
            title = info.get("title", "video")
    except Exception as e:
        return f"Download failed: {e}"

    note = ""
    if kind == "audio" and not _has_ffmpeg():
        note = " (saved as original audio format — install ffmpeg for MP3)"
    result = f"Downloaded '{title}' to your Downloads folder{note}."

    if player:
        player.write_log(f"[ytdl] {title[:40]}")
    return result
