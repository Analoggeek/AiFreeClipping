"""Video import: local files and URLs.

URL import uses source-specific adapters for platforms that permit programmatic
download.  Where a platform blocks downloading or requires authentication, the
adapter says so clearly and the user is directed to local import -- CLIPOS never
bypasses DRM or access controls.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core.config import PATHS, SUPPORTED_VIDEO_EXTENSIONS
from ..core.ffmpeg import probe
from ..core.logging_setup import get_logger

log = get_logger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 CLIPOS/1.0"


class ImportError_(RuntimeError):
    """Raised when an import cannot be completed."""


@dataclass
class ImportResult:
    path: str = ""
    title: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    size_bytes: int = 0
    thumbnail: str = ""
    source_type: str = "local"
    source_url: str = ""
    warnings: list[str] = field(default_factory=list)
    adapter: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path, "title": self.title, "duration": self.duration,
            "width": self.width, "height": self.height, "fps": self.fps,
            "has_audio": self.has_audio, "size_bytes": self.size_bytes,
            "thumbnail": self.thumbnail, "source_type": self.source_type,
            "source_url": self.source_url, "warnings": self.warnings,
            "adapter": self.adapter,
        }


# --------------------------------------------------------------------------------------
# URL adapters
# --------------------------------------------------------------------------------------


@dataclass
class AdapterResult:
    """Outcome of trying a source-specific adapter."""
    ok: bool = False
    url: str = ""
    title: str = ""
    extension: str = ".mp4"
    message: str = ""
    requires_auth: bool = False


class SourceAdapter:
    """Base class for a platform adapter."""

    key = "generic"
    name = "Generic URL"
    patterns: list[str] = []
    allows_download = True
    note = ""

    def matches(self, url: str) -> bool:
        host = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
        return any(host == p or host.endswith("." + p) for p in self.patterns)

    def resolve(self, url: str) -> AdapterResult:
        raise NotImplementedError

    def limitation(self) -> str:
        return self.note


class GenericDirectAdapter(SourceAdapter):
    """Handles URLs that point straight at a media file."""

    key = "direct"
    name = "Direct media link"
    patterns: list[str] = []

    def matches(self, url: str) -> bool:
        path = urllib.parse.urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in SUPPORTED_VIDEO_EXTENSIONS)

    def resolve(self, url: str) -> AdapterResult:
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if ext not in SUPPORTED_VIDEO_EXTENSIONS:
            ext = ".mp4"
        return AdapterResult(ok=True, url=url, extension=ext,
                             message="Direct media link")


class YouTubeAdapter(SourceAdapter):
    key = "youtube"
    name = "YouTube"
    patterns = ["youtube.com", "youtu.be", "youtube-nocookie.com"]
    allows_download = True
    note = "Public videos only. Download only content you own or have permission to use; no DRM or sign-in bypass."

    def resolve(self, url: str) -> AdapterResult:
        vid = self.extract_id(url)
        return AdapterResult(ok=True, url=url, extension=".mkv",
            title=f"YouTube video {vid}" if vid else "YouTube video",
            message="Public video download via yt-dlp; permission required. No DRM or sign-in bypass.")

    @staticmethod
    def extract_id(url: str) -> str:
        p = urllib.parse.urlparse(url)
        if "youtu.be" in p.netloc:
            return p.path.lstrip("/")
        qs = urllib.parse.parse_qs(p.query)
        if "v" in qs:
            return qs["v"][0]
        m = re.search(r"/(?:embed|shorts|v)/([\w-]{6,})", p.path)
        return m.group(1) if m else ""


class VimeoAdapter(SourceAdapter):
    key = "vimeo"
    name = "Vimeo"
    patterns = ["vimeo.com"]
    allows_download = False
    note = (
        "Vimeo restricts downloading of most videos to the account that owns them.\n\n"
        "If you own the video, export it from Vimeo and import the file locally."
    )

    def resolve(self, url: str) -> AdapterResult:
        return AdapterResult(
            ok=False, requires_auth=True,
            message=(
                "Vimeo only allows downloads for the owner or via an authorised "
                "download link.\n\n"
                "If you have permission, download the file and use Import Local "
                "Video. If you have a direct download link, paste it here."
            ),
        )


class SocialAdapter(SourceAdapter):
    """TikTok / Instagram / Twitter-style platforms."""

    key = "social"
    name = "Social platform"
    patterns = ["tiktok.com", "instagram.com", "twitter.com", "x.com",
                "facebook.com", "fb.watch", "reddit.com"]

    def resolve(self, url: str) -> AdapterResult:
        host = urllib.parse.urlparse(url).netloc.lower()
        return AdapterResult(
            ok=False, requires_auth=True,
            message=(
                f"{host} does not allow programmatic video downloads without "
                "authentication, and its content is protected against scraping.\n\n"
                "CLIPOS will not bypass that. Please download the video with a tool "
                "you are authorised to use, then import it locally."
            ),
        )


class DirectDownloadAdapter(SourceAdapter):
    """Handles URLs that serve a downloadable media file over HTTP(S)."""

    key = "http_media"
    name = "HTTP media URL"
    patterns = []

    def matches(self, url: str) -> bool:
        return urllib.parse.urlparse(url).scheme in ("http", "https")

    def resolve(self, url: str) -> AdapterResult:
        return AdapterResult(ok=True, url=url, extension=".mp4",
                             message="Downloading media over HTTP")


ADAPTERS: list[SourceAdapter] = [
    YouTubeAdapter(),
    VimeoAdapter(),
    SocialAdapter(),
    GenericDirectAdapter(),
    DirectDownloadAdapter(),
]


def find_adapter(url: str) -> SourceAdapter:
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter
    return ADAPTERS[-1]


def validate_url(url: str) -> tuple[bool, str]:
    """Basic URL validation with a helpful message."""
    url = (url or "").strip()
    if not url:
        return False, "Enter a URL"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "URL must start with http:// or https://"
    if not parsed.netloc:
        return False, "That does not look like a valid URL"
    if "." not in parsed.netloc:
        return False, "That hostname does not look right"
    return True, ""


# --------------------------------------------------------------------------------------
# Downloading
# --------------------------------------------------------------------------------------


def _download(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    timeout: int = 60,
) -> bool:
    """Stream a URL to disk with real progress reporting."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        if total > 0:
                            progress_cb(min(100.0, done / total * 100.0),
                                        f"Downloading… {done // 1024 // 1024} MB / "
                                        f"{total // 1024 // 1024} MB")
                        else:
                            progress_cb(50.0, f"Downloading… {done // 1024 // 1024} MB")
        return dest.exists() and dest.stat().st_size > 0
    except urllib.error.HTTPError as exc:
        raise ImportError_(f"Server returned HTTP {exc.code} ({exc.reason})") from exc
    except urllib.error.URLError as exc:
        raise ImportError_(f"Could not reach the URL: {exc.reason}") from exc
    except Exception as exc:
        raise ImportError_(f"Download failed: {exc}") from exc


def import_url(
    url: str,
    dest_dir: str | Path | None = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    title_hint: str = "",
) -> ImportResult:
    """Import a video from a URL. Raises ImportError_ with a clear message on failure."""
    ok, msg = validate_url(url)
    if not ok:
        raise ImportError_(msg)

    adapter = find_adapter(url)
    if isinstance(adapter, YouTubeAdapter):
        from .youtube import download_youtube
        return download_youtube(url, dest_dir or PATHS.media, progress_cb)
    resolution = adapter.resolve(url)

    if not resolution.ok:
        raise ImportError_(resolution.message)

    dest_dir = Path(dest_dir) if dest_dir else PATHS.media
    dest_dir.mkdir(parents=True, exist_ok=True)

    name = re.sub(r"[^\w\-. ]+", "_", title_hint or "imported_video")[:60].strip() or "imported_video"
    dest = dest_dir / f"{name}{resolution.extension}"
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{name}_{counter}{resolution.extension}"
        counter += 1

    if progress_cb:
        progress_cb(5.0, f"Downloading via {adapter.name}…")
    ok = _download(resolution.url, dest, progress_cb)
    if not ok:
        raise ImportError_("The download produced an empty file")

    result = describe_media(dest)
    result.source_type = "url"
    result.source_url = url
    result.adapter = adapter.name
    if title_hint:
        result.title = title_hint
    return result


def import_local(
    path: str | Path,
    copy_to_media: bool = True,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> ImportResult:
    """Import a local video file, copying it into the CLIPOS media store."""
    path = Path(path).expanduser()
    if not path.exists():
        raise ImportError_(f"File not found: {path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ImportError_(
            f"Unsupported format '{ext}'. Supported: "
            + ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        )

    if progress_cb:
        progress_cb(20.0, "Reading media information")
    result = describe_media(path)

    if copy_to_media:
        if progress_cb:
            progress_cb(60.0, "Copying into the CLIPOS media library")
        PATHS.media.mkdir(parents=True, exist_ok=True)
        dest = PATHS.media / f"{path.stem}_{int(time_marker())}{ext}"
        try:
            shutil.copy2(path, dest)
            result.path = str(dest)
        except Exception as exc:
            log.warning("copy to media failed, using original path: %s", exc)

    if progress_cb:
        progress_cb(100.0, "Import complete")
    return result


def time_marker() -> float:
    import time
    return time.time()


def describe_media(path: str | Path, make_thumb: bool = True) -> ImportResult:
    """Probe a media file and (optionally) extract a thumbnail."""
    path = Path(path)
    info = probe(path)
    result = ImportResult(
        path=str(path),
        title=path.stem.replace("_", " ").replace("-", " ").strip() or path.stem,
        duration=info.duration,
        width=info.video.width if info.video else 0,
        height=info.video.height if info.video else 0,
        fps=info.video.fps if info.video else 0.0,
        has_audio=info.has_audio,
        size_bytes=info.size_bytes,
    )
    if not info.has_video:
        raise ImportError_("This file has no video stream")

    if make_thumb:
        thumb_dir = PATHS.cache / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb = thumb_dir / f"{abs(hash(str(path)))}_thumb.jpg"
        try:
            from ..core.ffmpeg import extract_thumbnail

            ts = min(1.0, max(0.1, info.duration * 0.15))
            if extract_thumbnail(path, thumb, ts):
                result.thumbnail = str(thumb)
        except Exception as exc:
            log.warning("thumbnail failed: %s", exc)
    return result


def supported_extensions() -> list[str]:
    return sorted(SUPPORTED_VIDEO_EXTENSIONS)
