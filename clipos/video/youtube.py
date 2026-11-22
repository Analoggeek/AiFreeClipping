"""User-initiated downloads of public videos the user is entitled to use.

No cookies, authentication bypass, DRM handling or automatic uploads.
"""
from pathlib import Path
import uuid


def download_youtube(url, destination, progress=None):
    from .importer import ImportError_, describe_media
    from ..core.ffmpeg import require_ffmpeg
    try:
        import yt_dlp
    except ImportError as exc:
        raise ImportError_("This installation is missing yt-dlp. Update CLIPOS or import a local copy.") from exc
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    prefix = destination / f"youtube_{uuid.uuid4().hex}"

    def hook(data):
        if progress and data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done = data.get("downloaded_bytes", 0)
            progress(done / total * 100 if total else 0,
                     f"Downloading {done // 1048576} MB" + (" (size unknown)" if not total else ""))
        elif progress and data.get("status") == "finished":
            progress(99, "Merging highest available video and audio…")

    options = {
        "format": "bestvideo*+bestaudio/best", "noplaylist": True,
        "outtmpl": str(prefix) + ".%(ext)s", "merge_output_format": "mkv",
        "ffmpeg_location": str(Path(require_ffmpeg()).parent),
        "progress_hooks": [hook], "quiet": True, "no_warnings": True,
        "socket_timeout": 30, "retries": 3, "overwrites": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
        candidates = [p for p in destination.glob(prefix.name + ".*")
                      if p.suffix.lower() in (".mkv", ".mp4", ".webm", ".mov")]
        if not candidates:
            raise ImportError_("No merged video was produced. Import a local authorised copy.")
        path = max(candidates, key=lambda p: p.stat().st_size)
        result = describe_media(path)
        result.title = info.get("title") or path.stem
        result.source_type, result.source_url, result.adapter = "url", url, "YouTube"
        if progress:
            progress(100, "Video imported")
        return result
    except Exception as exc:
        raise ImportError_(f"YouTube download failed: {exc}. Private, age-restricted, DRM or sign-in-required videos are not supported. Import an authorised local copy instead.") from exc
