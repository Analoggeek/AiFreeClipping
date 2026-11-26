"""ffmpeg rendering engine: viral clips, captions, stickers, SFX, music and full projects."""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

from ..config import CACHE, EXPORTS, ffmpeg_binary
from .sfx import sfx_path
from .utils import escape_filter_path, format_time, probe, safe_name

RESOLUTIONS = {
    ("9:16", "1080p"): (1080, 1920),
    ("9:16", "720p"): (720, 1280),
    ("1:1", "1080p"): (1080, 1080),
    ("1:1", "720p"): (720, 720),
    ("16:9", "1080p"): (1920, 1080),
    ("16:9", "720p"): (1280, 720),
}
CAPTION_PRESETS = {
    "hype": {"FontName": "Arial Black", "Fontsize": 70, "Bold": -1, "Outline": 5, "PrimaryColour": "&H00FFFFFF", "OutlineColour": "&H00000000", "BackColour": "&H80000000"},
    "karaoke": {"FontName": "Arial", "Fontsize": 66, "Bold": -1, "Outline": 4, "PrimaryColour": "&H0000FFFF", "OutlineColour": "&H00000000"},
    "minimal": {"FontName": "Arial", "Fontsize": 52, "Bold": 0, "Outline": 2, "PrimaryColour": "&H00FFFFFF", "OutlineColour": "&H00000000"},
    "premium": {"FontName": "Georgia", "Fontsize": 60, "Bold": -1, "Outline": 3, "PrimaryColour": "&H0000F0FF", "OutlineColour": "&H00141414"},
    "none": {},
}


def resolution_for(aspect: str, resolution: str, source: tuple[int, int] = (1080, 1920)) -> tuple[int, int]:
    if aspect == "source" or resolution == "source":
        return source
    return RESOLUTIONS.get((aspect, resolution), RESOLUTIONS[("9:16", "1080p")])


def write_ass(
    captions: list[dict[str, Any]],
    style: dict[str, Any] | None = None,
    offset: float = 0,
    position: str = "bottom",
) -> str:
    """Write a styled Advanced SubStation Alpha subtitle file."""
    folder = CACHE / "subtitles"
    folder.mkdir(parents=True, exist_ok=True)
    preset = dict(CAPTION_PRESETS.get(style.get("preset", "hype") if style else "hype", CAPTION_PRESETS["hype"]))
    if style:
        for key in ("font_size", "primary_color", "outline_color"):
            if key in style and style[key] is not None:
                preset[{"font_size": "Fontsize", "primary_color": "PrimaryColour", "outline_color": "OutlineColour"}[key]] = style[key]
    alignment = {"bottom": 2, "center": 5, "top": 8}.get(position, 2)
    preset.update({"Alignment": alignment, "MarginV": 90 if alignment == 2 else 20, "BorderStyle": 1})
    fields = [
        "Name", "Fontname", "Fontsize", "PrimaryColour", "SecondaryColour", "OutlineColour",
        "BackColour", "Bold", "Italic", "Underline", "StrikeOut", "ScaleX", "ScaleY",
        "Spacing", "Angle", "BorderStyle", "Outline", "Shadow", "Alignment",
        "MarginL", "MarginR", "MarginV", "Encoding",
    ]
    defaults = {
        "Name": "Default", "Fontname": "Arial", "Fontsize": 64, "PrimaryColour": "&H00FFFFFF",
        "SecondaryColour": "&H0000FFFF", "OutlineColour": "&H00000000", "BackColour": "&H80000000",
        "Bold": -1, "Italic": 0, "Underline": 0, "StrikeOut": 0, "ScaleX": 100, "ScaleY": 100,
        "Spacing": 0, "Angle": 0, "BorderStyle": 1, "Outline": 4, "Shadow": 0, "Alignment": 2,
        "MarginL": 40, "MarginR": 40, "MarginV": 90, "Encoding": 1,
    }
    defaults.update(preset)
    header = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: " + ", ".join(fields),
        "Style: " + ",".join(str(defaults.get(f, "")) for f in fields),
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    lines: list[str] = []
    for caption in captions:
        text = str(caption.get("text") or caption.get("word") or "").replace("\n", "\\N").strip()
        if not text:
            continue
        try:
            start = max(0, float(caption.get("start", 0)) - offset)
            end = max(start + 0.15, float(caption.get("end", start + 0.8)) - offset)
        except (TypeError, ValueError):
            continue
        lines.append(
            f"Dialogue: 0,{format_time(start)[:-2]},{format_time(end)[:-2]},Default,,0,0,0,,{text}"
        )
    path = folder / f"subs_{abs(hash((tuple(lines[:3]), offset, position))) % 10**12}.ass"
    path.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    return str(path)


_ENCODER: str | None = None


def _encoder() -> str:
    global _ENCODER
    if _ENCODER:
        return _ENCODER
    forced = os.getenv("AIFREECLIP_ENCODER")
    if forced and forced != "auto":
        _ENCODER = forced
        return _ENCODER
    if os.getenv("FORCE_SOFTWARE_ENCODER") == "1":
        _ENCODER = "libx264"
        return _ENCODER
    import platform

    try:
        available = subprocess.run(
            [ffmpeg_binary(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=8
        ).stdout
    except Exception:
        available = ""
    preferred = []
    if platform.system() == "Darwin":
        preferred.append("h264_videotoolbox")
    try:
        if subprocess.run(["nvidia-smi"], capture_output=True, timeout=4).returncode == 0:
            preferred.append("h264_nvenc")
    except Exception:
        pass
    preferred.append("libx264")
    _ENCODER = next((name for name in preferred if name in available), "libx264")
    return _ENCODER


def _thread_args() -> list[str]:
    """Use all available cores for software filters without oversubscribing."""
    workers = max(1, min(8, int(os.getenv("RENDER_WORKERS") or (os.cpu_count() or 4))))
    return ["-threads", str(workers), "-filter_threads", str(workers)]


async def encode(args: list[str], duration: float, on_progress=None) -> Path:
    """Run ffmpeg and stream its progress into the job tracker."""
    output = Path(args[-1])
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    assert process.stdout is not None
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", "ignore").strip()
        if text.startswith("out_time_ms=") and duration > 0:
            try:
                current = int(text.split("=", 1)[1]) / 1_000_000
                if on_progress:
                    on_progress(min(95, current / duration * 100), f"Rendering {current:.1f}s / {duration:.1f}s")
            except ValueError:
                pass
    stderr = (await process.stderr.read()).decode("utf-8", "ignore") if process.stderr else ""
    code = await process.wait()
    if code != 0 or not output.exists():
        raise RuntimeError(f"ffmpeg failed ({code}): {stderr[-1200:]}")
    return output


def build_clip_args(
    media_path: str,
    start: float,
    end: float,
    output: str,
    options: dict[str, Any],
    has_audio: bool = True,
) -> list[str]:
    """Pure command builder (unit-testable): all paths passed as argv, never shell."""
    duration = max(0.5, end - start)
    width, height = resolution_for(
        options.get("aspect", "9:16"),
        options.get("resolution", "1080p"),
        (int(options.get("source_width") or 1080), int(options.get("source_height") or 1920)),
    )
    args: list[str] = [ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error"]
    input_count = 0

    def add_input(*tokens: str) -> int:
        nonlocal input_count
        index = input_count
        args.extend(tokens)
        input_count += 1
        return index

    add_input("-i", media_path)
    music_index = None
    if options.get("music") and Path(options["music"]).exists():
        music_index = add_input("-stream_loop", "-1", "-i", options["music"])
    sfx_indices: list[tuple[int, str, float]] = []
    for item in options.get("sfx", []) or []:
        name = item.get("name") if isinstance(item, dict) else item
        at = float(item.get("at", 0)) if isinstance(item, dict) else 0.0
        path = sfx_path(str(name))
        idx = add_input("-i", str(path))
        sfx_indices.append((idx, str(path), at))
    sticker_index = None
    sticker = options.get("sticker")
    if sticker and Path(str(sticker)).exists():
        if str(sticker).lower().endswith(".gif"):
            idx = add_input("-ignore_loop", "0", "-i", str(sticker))
        else:
            idx = add_input("-loop", "1", "-i", str(sticker))
        sticker_index = idx
    silent_index = None
    if not has_audio:
        silent_index = add_input(
            "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"
        )

    video_parts: list[str] = []
    speed = max(0.25, min(float(options.get("speed", 1)), 4))
    trim = f"trim=start={start:.3f}:end={end:.3f},setpts=(PTS-STARTPTS)/{speed:.3f},fps=30"
    focus = options.get("region") or ((options.get("regions") or [None])[0] if options.get("regions") else None)
    if isinstance(focus, dict):
        fx, fy = max(0.0, min(1.0, float(focus.get("x", 0)))), max(0.0, min(1.0, float(focus.get("y", 0))))
        fw = max(0.05, min(1.0 - fx, float(focus.get("w", 1))))
        fh = max(0.05, min(1.0 - fy, float(focus.get("h", 1))))
        # A tiny focus box would produce an unusable, pixelated crop. Always
        # keep at least a quarter of the frame around the selected subject.
        if fw * fh < 0.25:
            scale = (0.25 / max(1e-6, fw * fh)) ** 0.5
            scale = min(scale, 1.0 / max(fw, fh))
            nw, nh = min(1.0, fw * scale), min(1.0, fh * scale)
            fx = max(0.0, min(fx - (nw - fw) / 2, 1.0 - nw))
            fy = max(0.0, min(fy - (nh - fh) / 2, 1.0 - nh))
            fw, fh = nw, nh
        trim = (
            f"crop=iw*{fw:.4f}:ih*{fh:.4f}:iw*{fx:.4f}:ih*{fy:.4f}," + trim
        )
    if options.get("blur_background", True) and options.get("aspect", "9:16") != "source":
        video_parts.append(f"[0:v]{trim},split=2[bg][fg]")
        video_parts.append(
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma=24[bgb]"
        )
        video_parts.append(
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgs]"
        )
        video_parts.append(f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[base]")
        current = "base"
    else:
        video_parts.append(
            f"[0:v]{trim},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}[base]"
        )
        current = "base"
    eq_values = [
        f"brightness={float(options.get('brightness', 0)):.3f}",
        f"contrast={float(options.get('contrast', 0)):.3f}",
        f"saturation={float(options.get('saturation', 1)):.3f}",
    ]
    video_parts.append(f"[{current}]eq={':'.join(eq_values)}[graded]")
    current = "graded"
    caption_style = options.get("caption_style") or {}
    captions = options.get("captions") or []
    if caption_style.get("preset", "hype") != "none" and captions:
        ass_path = write_ass(captions, caption_style, offset=start, position=caption_style.get("position", "bottom"))
        video_parts.append(
            f"[{current}]subtitles=filename='{escape_filter_path(ass_path)}'[captioned]"
        )
        current = "captioned"
    if sticker_index:
        position = options.get("sticker_position") or {}
        scale = float(position.get("scale", 0.22))
        x = f"{float(position.get('x', 0.72)):.3f}*(W-w)"
        y = f"{float(position.get('y', 0.16)):.3f}*(H-h)"
        show_for = min(4.0, duration * 0.35)
        size = int(width * scale)
        video_parts.append(
            f"[{sticker_index}:v]scale={size}:-1:flags=lanczos,format=rgba[st];"
            f"[{current}][st]overlay=x='{x}':y='{y}':enable='between(t,0,{show_for:.2f})'[stuck]"
        )
        current = "stuck"
    watermark = options.get("watermark_path")
    if watermark and Path(str(watermark)).exists():
        wm_index = add_input("-i", str(watermark))
        video_parts.append(
            f"[{wm_index}:v]scale=100:-1[wm];[{current}][wm]overlay=W-w-28:H-h-28:alpha=0.85[branded]"
        )
        current = "branded"
    video_parts.append(f"[{current}]format=yuv420p[vout]")

    audio_inputs: list[str] = []
    tempo = f",atempo={speed:.3f}" if abs(speed - 1.0) > 0.01 else ""
    if silent_index is not None:
        audio_parts = [f"[{silent_index}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS{tempo}[a0]"]
    else:
        audio_parts = [
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS{tempo},volume=1[a0]"
        ]
    if music_index is not None:
        audio_parts.append(
            f"[{music_index}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={float(options.get('music_volume', 0.22)):.3f}[am]"
        )
        audio_inputs.append("[am]")
    for idx, _path, at in sfx_indices:
        delay_ms = int(max(0, at) * 1000)
        audio_parts.append(
            f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume={float(options.get('sfx_volume', 0.5)):.3f}[as{idx}]"
        )
        audio_inputs.append(f"[as{idx}]")
    mix_inputs = "[a0]" + "".join(audio_inputs)
    audio_parts.append(
        f"{mix_inputs}amix=inputs={1 + len(audio_inputs)}:duration=first:normalize=0,apad,atrim=0:{duration / speed:.3f}[aout]"
    )
    codec_args = ["-c:v", _encoder(), "-preset", "veryfast", "-crf", "18", "-b:v", "0"] if _encoder() == "libx264" else ["-c:v", _encoder()]
    args += [
        "-filter_complex", ";".join(video_parts + audio_parts),
        "-map", "[vout]", "-map", "[aout]", *_thread_args(), *codec_args,
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-t", f"{duration / speed:.3f}", "-progress", "pipe:1", "-nostats", output,
    ]
    return args


async def render_clip(
    media_path: str,
    start: float,
    end: float,
    output: str,
    options: dict[str, Any],
    on_progress=None,
) -> str:
    info = probe(media_path)
    options = dict(options)
    options.setdefault("source_width", info.get("width", 1080))
    options.setdefault("source_height", info.get("height", 1920))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    args = build_clip_args(media_path, start, end, output, options, has_audio=bool(info.get("audio_codec")))
    await encode(args, max(0.5, end - start), on_progress)
    return output


async def render_timeline(
    timeline: dict[str, Any], output: str, on_progress=None
) -> str:
    """Render a full CapCut-style multi-track project to a single MP4."""
    tracks = timeline.get("tracks") or {}
    video_items = tracks.get("video") or []
    if not video_items:
        raise RuntimeError("Add at least one video clip to the timeline before exporting")
    aspect = timeline.get("aspect", "9:16")
    resolution = timeline.get("resolution", "1080p")
    width, height = resolution_for(aspect, resolution)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    args: list[str] = [ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error"]
    media_inputs: list[dict[str, Any]] = []
    indexed_video: list[tuple[dict[str, Any], int]] = []
    for item in video_items:
        path = str(item.get("path") or "")
        if not Path(path).exists():
            continue
        args += ["-i", path]
        idx = sum(1 for a in args if a == "-i") - 1
        media_inputs.append(item)
        indexed_video.append((item, idx))
    if not indexed_video:
        raise RuntimeError("None of the timeline video files were found on this machine")

    music_items = [item for item in (tracks.get("audio") or []) if Path(str(item.get("path", ""))).exists()]
    for item in music_items:
        args += ["-stream_loop", "-1", "-i", str(item["path"])]
    sticker_items = [item for item in (tracks.get("stickers") or []) if Path(str(item.get("path", ""))).exists()]
    for item in sticker_items:
        args += ["-loop", "1", "-i", str(item["path"])]

    filters: list[str] = []
    vlabels: list[str] = []
    alabels: list[str] = []
    video_base = len(indexed_video)
    music_base = video_base
    sticker_base = music_base + len(music_items)
    for position, (item, idx) in enumerate(indexed_video):
        source_in = float(item.get("sourceStart", 0))
        duration = max(0.2, float(item.get("duration", 5)))
        filters.append(
            f"[{idx}:v]trim=start={source_in:.3f}:duration={duration:.3f},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=30[v{position}]"
        )
        vlabels.append(f"[v{position}]")
        media = probe(str(item.get("path")))
        if media.get("audio_codec"):
            filters.append(
                f"[{idx}:a]atrim=start={source_in:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS[a{position}]"
            )
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{duration:.3f}[a{position}]")
        alabels.append(f"[a{position}]")
    filters.append("".join(vlabels) + f"concat=n={len(vlabels)}:v=1:a=0[vcat]")
    filters.append("".join(alabels) + f"concat=n={len(alabels)}:v=0:a=1[acat]")

    total = sum(float(item.get("duration", 5)) for item in video_items)
    current = "vcat"
    captions = tracks.get("captions") or []
    if captions:
        ass_path = write_ass(captions, timeline.get("caption_style") or {"preset": "hype"})
        filters.append(f"[{current}]subtitles=filename='{escape_filter_path(ass_path)}'[cap]")
        current = "cap"
    for offset, item in enumerate(sticker_items):
        start = float(item.get("start", 0))
        end = float(item.get("end", min(total, start + 3)))
        x = float(item.get("x", 0.72)) * (width - 200)
        y = float(item.get("y", 0.16)) * (height - 200)
        filters.append(
            f"[{sticker_base + offset}:v]scale=240:-1[st{offset}];"
            f"[{current}][st{offset}]overlay=x={x:.0f}:y={y:.0f}:enable='between(t,{start:.2f},{end:.2f})'[stuck{offset}]"
        )
        current = f"stuck{offset}"
    audio_sources = ["[acat]"]
    for offset, item in enumerate(music_items):
        start = float(item.get("start", 0))
        volume = float(item.get("volume", 0.2))
        filters.append(
            f"[{music_base + offset}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={volume},adelay={int(start*1000)}|{int(start*1000)}[music{offset}]"
        )
        audio_sources.append(f"[music{offset}]")
    filters.append(
        "".join(audio_sources)
        + f"amix=inputs={len(audio_sources)}:duration=first:normalize=0,apad,atrim=0:{total:.3f}[aout]"
    )
    filters.append(f"[{current}]format=yuv420p[vout]")
    args += [
        "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
        *_thread_args(), "-c:v", _encoder(), "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-t", f"{total:.3f}", "-progress", "pipe:1", "-nostats", output,
    ]
    await encode(args, total, on_progress)
    return output


def export_path(name: str) -> str:
    from ..db import db  # local import avoids a config/db cycle

    configured = db.get_setting("clips_folder", "")
    folder = Path(configured).expanduser() if configured else EXPORTS
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / f"{safe_name(name)}.mp4")
