"""yt-dlp downloader: single videos, playlists, highest available quality."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..config import DOWNLOADS
from ..db import db, dumps, now, uid
from .utils import probe, safe_name, thumbnail

FORMATS = {
    "max": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "audio": "bestaudio/best",
}


def _ydl_options(request, folder: Path, job_id: str | None = None) -> dict[str, Any]:
    audio_only = request.quality == "audio"
    opts: dict[str, Any] = {
        "format": FORMATS.get(request.quality, FORMATS["max"]),
        "merge_output_format": "mp4" if not audio_only else "m4a",
        "outtmpl": str(folder / "%(title).140s [%(id)s].%(ext)s"),
        "restrictfilenames": False,
        "noplaylist": request.mode == "single",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "concurrent_fragment_downloads": 4,
        "retries": 3,
        "socket_timeout": 30,
        "ignoreerrors": False,
    }
    if request.cookies_file:
        opts["cookiefile"] = request.cookies_file
    if job_id:
        def progress(hook: dict[str, Any]) -> None:
            from ..jobs import jobs

            if hook.get("status") == "downloading":
                total = hook.get("total_bytes") or hook.get("total_bytes_estimate") or 0
                done = hook.get("downloaded_bytes") or 0
                pct = (done / total * 100) if total else 0
                jobs.update(job_id, progress=pct, message=f"Downloading {hook.get('_percent_str', '').strip()}")
            elif hook.get("status") == "finished":
                jobs.update(job_id, progress=95, message="Merging / finalizing…")

        opts["progress_hooks"] = [progress]
    return opts


def _require_ytdlp():
    try:
        import yt_dlp  # type: ignore

        return yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. Run: pip install -r backend/requirements.txt") from exc


def inspect(url: str, playlist: bool = False) -> dict[str, Any]:
    """Read metadata only (no download)."""
    yt_dlp = _require_ytdlp()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("No metadata returned for this URL")
    if playlist and info.get("entries"):
        return {
            "title": info.get("title") or "Playlist",
            "url": url,
            "count": len(info["entries"]),
            "items": [
                {
                    "index": i + 1,
                    "id": entry.get("id", ""),
                    "title": entry.get("title") or f"Video {i + 1}",
                    "url": entry.get("url") or entry.get("webpage_url") or "",
                    "duration": entry.get("duration"),
                }
                for i, entry in enumerate(info["entries"])
            ],
        }
    return {
        "title": info.get("title", "Video"),
        "url": url,
        "duration": info.get("duration", 0),
        "width": info.get("width", 0),
        "height": info.get("height", 0),
        "thumbnail": info.get("thumbnail", ""),
        "formats": len(info.get("formats", [])),
    }


def register_file(path: Path, source_url: str = "", playlist_id: str | None = None) -> dict[str, Any]:
    info = probe(path)
    media_id = uid("media_")
    thumb = thumbnail(path, media_id, min(1.0, info["duration"] / 4 or 1.0))
    row = {
        "id": media_id,
        "title": safe_name(path.stem),
        "path": str(path),
        "source_url": source_url or None,
        "duration": info.get("duration", 0),
        "width": info.get("width", 0),
        "height": info.get("height", 0),
        "thumbnail": thumb,
        "playlist_id": playlist_id,
        "metadata": dumps(info),
        "created_at": now(),
    }
    db.insert("media", row)
    return row


async def download(request, job_id: str | None = None) -> dict[str, Any]:
    """Download one or many videos; returns inserted media rows."""
    yt_dlp = _require_ytdlp()
    configured = db.get_setting("download_folder", "")
    folder = Path(request.folder or configured).expanduser() if (request.folder or configured) else DOWNLOADS
    folder.mkdir(parents=True, exist_ok=True)
    opts = _ydl_options(request, folder, job_id)
    if job_id:
        from ..jobs import jobs

        jobs.update(job_id, progress=2, message="Resolving video information…")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = await asyncio.to_thread(ydl.extract_info, request.url, False)
    if not info:
        raise RuntimeError("Could not resolve this URL")

    entries = []
    playlist_id: str | None = None
    if request.mode == "playlist" or (request.mode == "auto" and info.get("entries")):
        entries = list(info.get("entries") or [])
        if request.playlist_items:
            selected = {
                int(part)
                for chunk in request.playlist_items.split(",")
                for part in [chunk.strip()]
                if part.isdigit()
            }
            entries = [entry for i, entry in enumerate(entries, 1) if i in selected]
        playlist_id = uid("pl_")
        db.insert(
            "playlists",
            {
                "id": playlist_id,
                "url": request.url,
                "title": info.get("title") or "Playlist",
                "items": dumps(
                    [
                        {"index": i + 1, "title": e.get("title", f"Video {i+1}"), "id": e.get("id")}
                        for i, e in enumerate(entries)
                    ]
                ),
                "created_at": now(),
            },
        )
    else:
        entries = [info]

    downloaded: list[dict[str, Any]] = []
    total = max(len(entries), 1)
    for index, entry in enumerate(entries):
        if job_id:
            from ..jobs import jobs

            jobs.update(job_id, progress=5 + (index / total) * 90, message=f"Video {index+1}/{total}")
        url = entry.get("webpage_url") or entry.get("url") or request.url
        with yt_dlp.YoutubeDL(opts) as ydl:
            await asyncio.to_thread(ydl.download, [url])
        # yt-dlp writes the final file into folder; pick the newest matching file
        candidates = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".mp4", ".webm", ".mkv", ".m4a", ".mov"}]
        if candidates:
            newest = max(candidates, key=lambda p: p.stat().st_mtime)
            downloaded.append(register_file(newest, url, playlist_id if request.mode != "single" else None))
    if not downloaded:
        raise RuntimeError("No file was downloaded. Check the URL, cookies or network access.")
    return {"media": downloaded, "playlist_id": playlist_id if request.mode != "single" else None}
