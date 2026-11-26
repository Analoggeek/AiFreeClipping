"""Shared media helpers built on ffmpeg/ffprobe."""
from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from fastapi.responses import Response, StreamingResponse

from ..config import CACHE, ffprobe_binary, ffmpeg_binary


def safe_name(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", value).strip()[:140] or "media"


def run_command(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _probe_from_text(text: str) -> dict[str, Any]:
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    dimensions = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
    duration = 0.0
    if duration_match:
        h, m, s = duration_match.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)
    video_codec = re.search(r"Video:\s*([a-zA-Z0-9_]+)", text)
    audio_codec = re.search(r"Audio:\s*([a-zA-Z0-9_]+)", text)
    return {
        "duration": duration,
        "width": int(dimensions.group(1)) if dimensions else 0,
        "height": int(dimensions.group(2)) if dimensions else 0,
        "fps": float(fps_match.group(1)) if fps_match else 0.0,
        "video_codec": video_codec.group(1) if video_codec else "",
        "audio_codec": audio_codec.group(1) if audio_codec else "",
        "bitrate": 0,
        "format": "",
    }


def probe(path: str | Path) -> dict[str, Any]:
    """Return duration, dimensions, codecs and bitrate for a media file.

    Uses ffprobe when available; offline bundles without ffprobe fall back to
    parsing `ffmpeg -i` output, so duration and aspect ratio still work.
    """
    binary = ffprobe_binary()
    ffprobe_available = "ffprobe" in Path(binary).name.lower()
    data: dict[str, Any] = {}
    text = ""
    try:
        if ffprobe_available:
            proc = run_command(
                [binary, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                timeout=60,
            )
            try:
                data = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError:
                data = {}
            text = proc.stderr or ""
        else:
            proc = run_command([binary, "-hide_banner", "-i", str(path)], timeout=60)
            text = proc.stderr or ""
    except subprocess.TimeoutExpired:
        return {}
    if not data.get("streams"):
        return _probe_from_text(text)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {
        "duration": float(data.get("format", {}).get("duration") or video.get("duration") or 0),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": _parse_ratio(video.get("avg_frame_rate", "")),
        "video_codec": video.get("codec_name", ""),
        "audio_codec": audio.get("codec_name", ""),
        "bitrate": int(data.get("format", {}).get("bit_rate") or 0),
        "format": data.get("format", {}).get("format_name", ""),
    }


def _parse_ratio(value: str) -> float:
    try:
        num, den = value.split("/")
        return round(float(num) / float(den), 3) if float(den) else 0.0
    except Exception:
        return 0.0


def thumbnail(path: str | Path, media_id: str, at: float = 1.0) -> str | None:
    """Create a cached JPEG thumbnail and return its API route."""
    folder = CACHE / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{media_id}.jpg"
    if out.exists() and out.stat().st_size > 0:
        return f"/api/media/{media_id}/thumbnail"
    proc = run_command(
        [
            ffmpeg_binary(), "-y", "-loglevel", "error", "-ss", str(max(at, 0)),
            "-i", str(path), "-frames:v", "1", "-vf", "scale=480:-2", str(out),
        ],
        timeout=60,
    )
    return f"/api/media/{media_id}/thumbnail" if out.exists() and proc.returncode == 0 else None


def escape_filter_path(path: str | Path) -> str:
    """Escape a file path for ffmpeg filter arguments (Windows drive colon included)."""
    text = str(path).replace("\\", "/").replace(":", r"\:")
    return text.replace("'", r"\'")


def format_time(seconds: float) -> str:
    seconds = max(0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def file_stream(path: str | Path, request, media_type: str = "video/mp4") -> Response:
    """HTTP Range capable file response so the in-app player can seek instantly."""
    file_path = Path(path)
    if not file_path.exists():
        return Response("File not found", status_code=404)
    size = file_path.stat().st_size
    range_header = request.headers.get("range", "")
    start, end = 0, size - 1
    if range_header.startswith("bytes="):
        parts = range_header[6:].split("-")
        try:
            if parts[0]:
                start = int(parts[0])
            if len(parts) > 1 and parts[1]:
                end = min(int(parts[1]), size - 1)
        except ValueError:
            start, end = 0, size - 1
    if start > end or start >= size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    length = end - start + 1

    def iterator():
        with file_path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 512, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Disposition": "inline",
    }
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        iterator(),
        status_code=206 if range_header else 200,
        media_type=media_type,
        headers=headers,
    )


def iou(box_a: list[float], box_b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def nice_number(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, 3)
