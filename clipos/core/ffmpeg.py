"""Real FFmpeg / FFprobe integration.

This module is the backbone of CLIPOS: every import, analysis, edit and export step
ultimately shells out to a genuine ffmpeg/ffprobe binary. Nothing here is simulated.

Binary resolution order:
  1. ``CLIPOS_FFMPEG`` / ``CLIPOS_FFPROBE`` environment variables
  2. ffmpeg shipped inside the application bundle (``resources/ffmpeg``)
  3. ``imageio-ffmpeg`` bundled wheel (pip installable on every platform)
  4. system ``ffmpeg`` on PATH
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Sequence

from .logging_setup import get_logger

log = get_logger(__name__)

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg invocation fails."""

    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str) -> None:
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = stderr
        tail = "\n".join(stderr.strip().splitlines()[-25:])
        super().__init__(f"ffmpeg failed (exit {returncode}):\n{tail}")


class FFmpegCancelled(RuntimeError):
    """Raised when an ffmpeg invocation was stopped at the user's request."""

    def __init__(self, cmd: Sequence[str] | None = None) -> None:
        self.cmd = list(cmd or [])
        super().__init__("the render was cancelled")


def _platform_keys() -> list[str]:
    """Candidate vendored binary directory keys, most specific first."""
    machine = platform.machine().lower()
    if sys.platform == "win32":
        arch = "x64" if machine in ("amd64", "x86_64") else "ia32"
        return [f"win32-{arch}", "win32-x64"]
    if sys.platform == "darwin":
        if machine in ("arm64", "aarch64"):
            return ["darwin-arm64", "darwin-x64"]
        return ["darwin-x64", "darwin-arm64"]
    arch = "x64" if machine in ("amd64", "x86_64") else "ia32"
    return [f"linux-{arch}", "linux-x64"]


def _resource_ffmpeg_dir() -> Path:
    """Locate the bundled ``resources/ffmpeg`` directory."""
    from .resources import resource_dir

    return resource_dir("ffmpeg")


def _binary_name(stem: str) -> str:
    return f"{stem}.exe" if sys.platform == "win32" else stem


def _find_binary(stem: str) -> str | None:
    env_key = f"CLIPOS_{stem.upper()}"
    if os.environ.get(env_key):
        p = os.environ[env_key]
        if Path(p).exists():
            return p

    root = _resource_ffmpeg_dir()
    exe_name = _binary_name(stem)
    for key in _platform_keys():
        cand = root / key / exe_name
        if cand.exists():
            return str(cand)
    flat = root / exe_name
    if flat.exists():
        return str(flat)

    # imageio-ffmpeg ships a static ffmpeg build
    try:
        import imageio_ffmpeg  # type: ignore

        if stem == "ffmpeg":
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and Path(exe).exists():
                return exe
        elif stem == "ffprobe":
            # imageio does not ship ffprobe; check alongside the ffmpeg binary
            sibling = Path(imageio_ffmpeg.get_ffmpeg_exe()).with_name(_binary_name("ffprobe"))
            if sibling.exists():
                return str(sibling)
    except Exception:
        pass

    found = shutil.which(stem)
    if found:
        return found
    return None


FFMPEG: str | None = _find_binary("ffmpeg")
FFPROBE: str | None = _find_binary("ffprobe")


def ffmpeg_available() -> bool:
    return bool(FFMPEG)


def ffprobe_available() -> bool:
    return bool(FFPROBE)


def require_ffmpeg() -> str:
    if not FFMPEG:
        raise FFmpegError(
            ["ffmpeg"], -1, "FFmpeg binary not found. Install FFmpeg or set CLIPOS_FFMPEG."
        )
    return FFMPEG


def require_ffprobe() -> str:
    if not FFPROBE:
        raise FFmpegError(
            ["ffprobe"], -1, "FFprobe binary not found. Install FFmpeg or set CLIPOS_FFPROBE."
        )
    return FFPROBE


def ffmpeg_version() -> str:
    if not FFMPEG:
        return "not installed"
    try:
        out = subprocess.run(
            [FFMPEG, "-version"], capture_output=True, text=True, timeout=20,
            creationflags=_CREATE_NO_WINDOW,
        )
        return out.stdout.splitlines()[0] if out.stdout else "unknown"
    except Exception as exc:  # pragma: no cover
        return f"error: {exc}"


# --------------------------------------------------------------------------------------
# Probe
# --------------------------------------------------------------------------------------


@dataclass
class VideoStream:
    index: int = 0
    codec: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    bitrate: int = 0
    duration: float = 0.0
    pix_fmt: str = ""
    rotation: int = 0
    is_hdr: bool = False


@dataclass
class AudioStream:
    index: int = 0
    codec: str = ""
    channels: int = 0
    sample_rate: int = 0
    bitrate: int = 0
    duration: float = 0.0
    channel_layout: str = ""


@dataclass
class MediaInfo:
    path: str = ""
    duration: float = 0.0
    size_bytes: int = 0
    container: str = ""
    bitrate: int = 0
    format_name: str = ""
    video: VideoStream | None = None
    audio: AudioStream | None = None
    has_video: bool = False
    has_audio: bool = False
    raw: dict = field(default_factory=dict)

    @property
    def resolution(self) -> str:
        if not self.video:
            return "—"
        return f"{self.video.width}×{self.video.height}"

    @property
    def fps_label(self) -> str:
        if not self.video or not self.video.fps:
            return "—"
        return f"{self.video.fps:.0f} fps"

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _parse_fraction(value) -> float:
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    if "/" in s:
        num, _, den = s.partition("/")
        try:
            den_f = float(den)
            return float(num) / den_f if den_f else 0.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def probe(path: str | Path, timeout: int = 90) -> MediaInfo:
    """Gather real metadata via ffprobe."""
    path = str(path)
    if not Path(path).exists():
        raise FileNotFoundError(f"File not found: {path}")
    exe = require_ffprobe()
    cmd = [
        exe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, creationflags=_CREATE_NO_WINDOW
    )
    if proc.returncode != 0:
        raise FFmpegError(cmd, proc.returncode, proc.stderr)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise FFmpegError(cmd, proc.returncode, f"invalid ffprobe json: {exc}")

    info = MediaInfo(path=path, raw=data)
    fmt = data.get("format", {}) or {}
    info.container = fmt.get("format_name", "")
    info.format_name = fmt.get("format_long_name", "")
    info.duration = float(fmt.get("duration", 0) or 0)
    info.size_bytes = int(fmt.get("size", 0) or 0)
    info.bitrate = int(fmt.get("bit_rate", 0) or 0)

    for st in data.get("streams", []) or []:
        ctype = st.get("codec_type")
        if ctype == "video" and not info.has_video:
            tags = st.get("tags", {}) or {}
            rot = 0
            sd = st.get("side_data_list") or []
            for sd_item in sd:
                if "rotation" in sd_item:
                    try:
                        rot = int(float(sd_item["rotation"])) % 360
                    except (TypeError, ValueError):
                        rot = 0
            if not rot and tags.get("rotate"):
                try:
                    rot = int(float(tags["rotate"])) % 360
                except (TypeError, ValueError):
                    rot = 0
            v = VideoStream(
                index=int(st.get("index", 0)),
                codec=st.get("codec_name", ""),
                width=int(st.get("width", 0) or 0),
                height=int(st.get("height", 0) or 0),
                fps=_parse_fraction(st.get("avg_frame_rate") or st.get("r_frame_rate")),
                bitrate=int(st.get("bit_rate", 0) or 0),
                duration=float(st.get("duration", 0) or 0),
                pix_fmt=st.get("pix_fmt", ""),
                rotation=rot,
                is_hdr="10" in (st.get("pix_fmt", "") or "") or "12" in (st.get("pix_fmt", "") or ""),
            )
            info.video = v
            info.has_video = True
        elif ctype == "audio" and not info.has_audio:
            a = AudioStream(
                index=int(st.get("index", 0)),
                codec=st.get("codec_name", ""),
                channels=int(st.get("channels", 0) or 0),
                sample_rate=int(st.get("sample_rate", 0) or 0),
                bitrate=int(st.get("bit_rate", 0) or 0),
                duration=float(st.get("duration", 0) or 0),
                channel_layout=st.get("channel_layout", ""),
            )
            info.audio = a
            info.has_audio = True

    if info.duration <= 0:
        if info.video and info.video.duration:
            info.duration = info.video.duration
        elif info.audio and info.audio.duration:
            info.duration = info.audio.duration
    return info


# --------------------------------------------------------------------------------------
# Progress-aware ffmpeg runner
# --------------------------------------------------------------------------------------


class FFmpegRunner:
    """Run ffmpeg and report real progress parsed from stderr.

    Progress is derived from the ffmpeg ``time=HH:MM:SS.ms`` output against the known
    output duration -- this is a genuine measurement of encoder progress, never a timer.
    """

    def __init__(
        self,
        total_duration: float = 0.0,
        progress_cb=None,
        log_cb=None,
        cancel_cb=None,
    ) -> None:
        self.total_duration = max(0.001, float(total_duration or 0.0))
        self.progress_cb = progress_cb
        self.log_cb = log_cb
        self.cancel_cb = cancel_cb
        self._last_pct = -1.0
        self.stderr_lines: list[str] = []
        self.cancelled = False

    @staticmethod
    def _parse_time(line: str) -> float | None:
        m = re.search(r"time=\s*(-?)(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", line)
        if not m:
            return None
        sign = -1 if m.group(1) == "-" else 1
        h = int(m.group(2))
        mi = int(m.group(3))
        s = float(m.group(4))
        return sign * (h * 3600 + mi * 60 + s)

    def run(self, args: Sequence[str], total_duration: float | None = None) -> str:
        exe = require_ffmpeg()
        cmd = [exe, "-hide_banner", "-nostdin", "-y", *args]
        log.debug("ffmpeg: %s", " ".join(cmd))
        if self.log_cb:
            self.log_cb(" ".join(cmd))
        total = float(total_duration or self.total_duration)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            creationflags=_CREATE_NO_WINDOW,
        )
        assert proc.stderr is not None
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if not line:
                    continue
                # Check for cancellation on every line ffmpeg emits so a long
                # render stops promptly when the user presses Cancel.
                if self.cancel_cb is not None and self.cancel_cb():
                    self.cancelled = True
                    self._terminate(proc)
                    break
                self.stderr_lines.append(line)
                if len(self.stderr_lines) > 400:
                    self.stderr_lines.pop(0)
                t = self._parse_time(line)
                if t is not None and total > 0 and self.progress_cb:
                    pct = max(0.0, min(100.0, (t / total) * 100.0))
                    if pct - self._last_pct >= 0.5 or pct >= 100.0:
                        self._last_pct = pct
                        try:
                            self.progress_cb(pct, t)
                        except Exception:
                            pass
        finally:
            # Always close the pipe so the file descriptor is not leaked.
            try:
                proc.stderr.close()
            except Exception:
                pass
        rc = proc.wait()
        if self.cancelled:
            raise FFmpegCancelled(cmd)
        if rc != 0:
            raise FFmpegError(cmd, rc, "\n".join(self.stderr_lines))
        return "\n".join(self.stderr_lines)

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        """Stop ffmpeg, escalating to a kill if it ignores the polite ask."""
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            proc.kill()
        except Exception:
            pass


# Some filter graphs (many jump cuts, long caption chains) grow past the
# operating system's command-line length limit.  Writing the graph to a file
# and passing it with -filter_complex_script avoids "Argument list too long".
MAX_INLINE_ARGS = 24_000


def write_filter_script(graph: str, path: str | Path) -> Path:
    """Write a filter graph to disk and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph, encoding="utf-8")
    return path


def run_ffmpeg(args: Sequence[str], timeout: int = 3600) -> str:
    """Simple blocking ffmpeg call (no progress)."""
    exe = require_ffmpeg()
    cmd = [exe, "-hide_banner", "-nostdin", "-y", *args]
    log.debug("ffmpeg: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, creationflags=_CREATE_NO_WINDOW
    )
    if proc.returncode != 0:
        raise FFmpegError(cmd, proc.returncode, proc.stderr)
    return proc.stderr


def extract_thumbnail(
    src: str | Path, out: str | Path, timestamp: float = 1.0, width: int = 640
) -> bool:
    """Grab a single real frame as a JPEG thumbnail."""
    try:
        run_ffmpeg([
            "-ss", f"{max(0.0, timestamp):.3f}", "-i", str(src),
            "-frames:v", "1", "-vf", f"scale={width}:-2:flags=lanczos",
            "-q:v", "3", str(out),
        ], timeout=120)
        return Path(out).exists()
    except (FFmpegError, subprocess.TimeoutExpired) as exc:
        log.warning("thumbnail extraction failed: %s", exc)
        return False


def extract_frames(
    src: str | Path,
    out_dir: str | Path,
    timestamps: Iterable[float],
    width: int = 480,
) -> list[str]:
    """Extract individual frames at specific timestamps. Returns written paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for i, ts in enumerate(timestamps):
        out = out_dir / f"frame_{i:04d}.jpg"
        try:
            run_ffmpeg([
                "-ss", f"{max(0.0, float(ts)):.3f}", "-i", str(src),
                "-frames:v", "1", "-vf", f"scale={width}:-2:flags=lanczos",
                "-q:v", "3", str(out),
            ], timeout=120)
            if out.exists():
                written.append(str(out))
        except (FFmpegError, subprocess.TimeoutExpired) as exc:
            log.warning("frame extraction failed @ %.2fs: %s", ts, exc)
    return written


def extract_audio_wav(
    src: str | Path, out: str | Path, sample_rate: int = 16000, mono: bool = True
) -> bool:
    """Decode the audio track to 16 kHz mono PCM WAV for STT / DSP analysis."""
    args = ["-i", str(src)]
    if mono:
        args += ["-ac", "1"]
    args += ["-ar", str(sample_rate), "-c:a", "pcm_s16le", str(out)]
    try:
        run_ffmpeg(args, timeout=1800)
        return Path(out).exists()
    except (FFmpegError, subprocess.TimeoutExpired) as exc:
        log.warning("audio extraction failed: %s", exc)
        return False


def loudness_stats(src: str | Path) -> dict:
    """Real integrated loudness via ffmpeg ebur128 filter."""
    exe = require_ffmpeg()
    cmd = [
        exe, "-hide_banner", "-nostdin", "-i", str(src),
        "-filter_complex", "ebur128=peak=true",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, creationflags=_CREATE_NO_WINDOW
        )
    except subprocess.TimeoutExpired:
        return {}
    text = proc.stderr or ""
    result: dict = {}
    tail = text[-4000:]
    for key, label in (("I", "integrated"), ("LRA", "range"), ("Threshold", "threshold")):
        idx = tail.rfind(f"{key}:")
        if idx != -1:
            seg = tail[idx: idx + 40]
            nums = re.findall(r"-?\d+(?:\.\d+)?", seg)
            if nums:
                result[label] = float(nums[0])
    if "Peak:" in tail:
        idx = tail.rfind("Peak:")
        nums = re.findall(r"-?\d+(?:\.\d+)?", tail[idx: idx + 40])
        if nums:
            result["peak_db"] = float(nums[0])
    return result


def list_encoders() -> dict:
    """Return available h264/h265/aac encoders for the hardware-acceleration panel.

    ``ffmpeg -encoders`` writes its table to stderr, and each row starts with a
    6-character capability/flags column (``V.....`` / ``A.....``).
    """
    exe = require_ffmpeg()
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-encoders"], capture_output=True, text=True,
            timeout=60, creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return {}
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    out: dict = {}
    want = {"libx264", "libx265", "h264_nvenc", "hevc_nvenc", "h264_qsv",
            "hevc_qsv", "h264_videotoolbox", "hevc_videotoolbox", "aac",
            "libvpx-vp9", "libsvtav1"}
    for line in text.splitlines():
        parts = line.split()
        # parts[0] is the flags blob like "V....." ; parts[1] is the encoder name
        if len(parts) >= 2 and parts[0][:1] in ("V", "A") and parts[1] in want:
            out[parts[1]] = parts[2] if len(parts) > 2 else ""
    return out
