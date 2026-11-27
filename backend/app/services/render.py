"""ffmpeg rendering engine: viral clips, captions, stickers, SFX, music and full projects."""
from __future__ import annotations

import asyncio
import math
import os
import subprocess
from datetime import date
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
    """Choose an even output size while preserving the requested aspect ratio.

    ``source`` quality follows the source pixels instead of silently falling
    back to 1080p. For a changed aspect ratio, it chooses the largest frame of
    that shape that fits inside the source dimensions, avoiding unnecessary
    upscaling of the actual source picture.
    """
    source_width = max(2, int(source[0] or 1080))
    source_height = max(2, int(source[1] or 1920))
    if aspect == "source":
        return source_width - source_width % 2, source_height - source_height % 2
    if resolution == "source":
        ratio = {"9:16": 9 / 16, "1:1": 1.0, "16:9": 16 / 9}.get(aspect)
        if ratio is None:
            return RESOLUTIONS[("9:16", "1080p")]
        if source_width / source_height >= ratio:
            height = source_height
            width = int(height * ratio)
        else:
            width = source_width
            height = int(width / ratio)
        width = max(2, width - width % 2)
        height = max(2, height - height % 2)
        return width, height
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
    title_defaults = {
        **defaults,
        "Name": "Title", "Fontname": "Arial Black", "Fontsize": 68, "PrimaryColour": "&H00FFFFFF",
        "BackColour": "&H880F111B", "Bold": -1, "BorderStyle": 3,
        "OutlineColour": "&H008B5CF6", "Outline": 4, "Shadow": 2, "Alignment": 8,
        "MarginV": 90,
    }
    header = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: " + ", ".join(fields),
        "Style: " + ",".join(str(defaults.get(f, "")) for f in fields),
        "Style: " + ",".join(str(title_defaults.get(f, "")) for f in fields),
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
        # Keep ASR output from being interpreted as ASS override markup, then
        # animate title cards and hype captions without changing their timing.
        is_title = caption.get("kind") == "title"
        text = text.replace("{", "(").replace("}", ")")
        event_style = "Default"
        if is_title:
            event_style = "Title"
            text = r"{\an8\fs68\bord4\shad2\c&H00FFFFFF&\3c&H008B5CF6&\fad(160,220)\fscx92\fscy92\t(0,180,\fscx100\fscy100)}" + text
        elif style and style.get("preset", "hype") in {"hype", "karaoke"}:
            text = r"{\fad(55,100)\fscx90\fscy90\t(0,90,\fscx100\fscy100)}" + text
        lines.append(
            f"Dialogue: 0,{format_time(start)[:-2]},{format_time(end)[:-2]},{event_style},,0,0,0,,{text}"
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


def _video_codec_args() -> list[str]:
    """Choose encoder flags that produce a broadly playable MP4 on every OS."""
    encoder = _encoder()
    if encoder == "libx264":
        args = [
            "-c:v", encoder, "-preset", "veryfast", "-crf", "18", "-profile:v", "high",
            "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709",
        ]
    elif encoder == "h264_videotoolbox":
        args = ["-c:v", encoder, "-b:v", "8M", "-profile:v", "high"]
    elif encoder == "h264_nvenc":
        args = ["-c:v", encoder, "-preset", "p5", "-cq", "19", "-b:v", "0", "-profile:v", "high"]
    else:
        args = ["-c:v", encoder]
    if encoder.startswith("h264") or encoder == "libx264":
        args.extend([
            "-pix_fmt", "yuv420p", "-tag:v", "avc1", "-level:v", "4.1",
            "-color_range", "tv", "-colorspace", "bt709",
            "-color_primaries", "bt709", "-color_trc", "bt709",
        ])
    return args


def _thread_args() -> list[str]:
    """Use all available cores for software filters without oversubscribing."""
    workers = max(1, min(8, int(os.getenv("RENDER_WORKERS") or (os.cpu_count() or 4))))
    return ["-threads", str(workers), "-filter_threads", str(workers)]


def _normalise_contrast(value: Any) -> float:
    """Fix legacy UI values where zero/0.05 were meant to be neutral/slight."""
    try:
        contrast = float(value)
    except (TypeError, ValueError):
        return 1.0
    if 0.0 <= contrast <= 0.1:
        return 1.0 + contrast
    return max(0.0, min(2.0, contrast))


def _atempo_filter(speed: float) -> str:
    """Build an FFmpeg atempo chain for speeds outside its 0.5–2.0 range."""
    remaining = max(0.25, min(float(speed), 4.0))
    factors: list[float] = []
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return ",".join(f"atempo={factor:.3f}" for factor in factors)


def _normalise_region(region: Any, expand_small: bool = True) -> tuple[float, float, float, float] | None:
    """Clamp a normalized focus box and optionally expand tiny focus crops."""
    if not isinstance(region, dict):
        return None
    try:
        x = min(0.95, max(0.0, float(region.get("x", 0))))
        y = min(0.95, max(0.0, float(region.get("y", 0))))
        width = max(0.05, min(1.0 - x, float(region.get("w", 1))))
        height = max(0.05, min(1.0 - y, float(region.get("h", 1))))
    except (TypeError, ValueError):
        return None
    if expand_small and width * height < 0.25:
        scale = (0.25 / max(1e-6, width * height)) ** 0.5
        scale = min(scale, 1.0 / max(width, height))
        new_width, new_height = min(1.0, width * scale), min(1.0, height * scale)
        x = max(0.0, min(x - (new_width - width) / 2, 1.0 - new_width))
        y = max(0.0, min(y - (new_height - height) / 2, 1.0 - new_height))
        width, height = new_width, new_height
    return x, y, width, height


def _crop_filter(region: Any, expand_small: bool = True) -> str | None:
    box = _normalise_region(region, expand_small=expand_small)
    if box is None:
        return None
    x, y, width, height = box
    return f"crop=iw*{width:.4f}:ih*{height:.4f}:iw*{x:.4f}:ih*{y:.4f}"


def _simplify_crop_points(
    points: list[tuple[float, float]], tolerance: float = 0.003, max_points: int = 64,
) -> list[tuple[float, float]]:
    """Reduce expression size without smoothing away an intentional shot snap."""
    if len(points) <= max_points:
        return points
    snap_pairs: list[tuple[float, int, int]] = []
    for index, ((t0, x0), (t1, x1)) in enumerate(zip(points, points[1:])):
        shift = abs(x1 - x0)
        if t1 - t0 <= 0.002 and shift >= 0.03:
            snap_pairs.append((shift, index, index + 1))
    required = {0, len(points) - 1}
    all_snap_keys = {index for _shift, left, right in snap_pairs for index in (left, right)}
    if len(required | all_snap_keys) <= max_points:
        required.update(all_snap_keys)
    elif snap_pairs:
        # Keep important cut snaps spread across the entire clip rather than
        # dropping the moving crop when a dense edit exceeds the key budget.
        budget = max(1, (max_points - len(required)) // 2)
        selected: set[int] = set()
        for slot in range(budget):
            first = slot * len(snap_pairs) // budget
            last = max(first + 1, (slot + 1) * len(snap_pairs) // budget)
            _shift, left, right = max(snap_pairs[first:last], key=lambda item: item[0])
            selected.update((left, right))
        for _shift, left, right in sorted(snap_pairs, key=lambda item: item[0], reverse=True):
            if len(required | selected | {left, right}) <= max_points:
                selected.update((left, right))
        required.update(selected)

    anchors = sorted(required)
    kept = set(required)
    pending = list(zip(anchors, anchors[1:]))
    while pending:
        left, right = pending.pop()
        if right - left <= 1:
            continue
        t0, x0 = points[left]
        t1, x1 = points[right]
        span = t1 - t0
        if span <= 0:
            continue
        worst_index = -1
        worst_error = tolerance
        for index in range(left + 1, right):
            t, x = points[index]
            expected = x0 + (x1 - x0) * (t - t0) / span
            error = abs(x - expected)
            if error > worst_error:
                worst_index, worst_error = index, error
        if worst_index >= 0:
            kept.add(worst_index)
            pending.extend(((left, worst_index), (worst_index, right)))

    if len(kept) > max_points:
        candidates = [index for index in range(len(points)) if index not in required]
        slots = max_points - len(required)
        selected = set(required)
        if slots > 0 and candidates:
            for slot in range(1, slots + 1):
                position = round(slot * (len(candidates) - 1) / (slots + 1))
                selected.add(candidates[position])
        kept = selected
    return [points[index] for index in sorted(kept)]


def _moving_crop_filter(
    path: Any, output_aspect: str, source_width: int, source_height: int,
) -> str | None:
    """Build a frame-evaluated portrait crop from normalized center keyframes.

    Keys use source timestamps, so this filter belongs after trim but before setpts.
    A pair of near-adjacent keys at a cut keeps the old framing to the cut and
    applies the new framing on it instead of interpolating across shots.
    """
    if output_aspect != "9:16" or source_width <= 0 or source_height <= 0:
        return None
    target_ratio = 9 / 16
    if source_width / source_height <= target_ratio + 1e-4:
        return None
    points: list[tuple[float, float]] = []
    for item in path if isinstance(path, (list, tuple)) else []:
        try:
            t, center = float(item[0]), float(item[1])
        except (IndexError, TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(t) and math.isfinite(center):
            points.append((t, max(0.0, min(1.0, center))))
    points.sort(key=lambda item: item[0])
    compact: list[tuple[float, float]] = []
    for point in points:
        if compact and point[0] <= compact[-1][0]:
            compact[-1] = point
        else:
            compact.append(point)
    compact = _simplify_crop_points(compact)
    if not compact:
        return None

    center = f"{compact[-1][1]:.6f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(compact, compact[1:]))):
        duration = t1 - t0
        if duration <= 0:
            continue
        linear = f"({x0:.6f}+({x1 - x0:.6f})*(t-{t0:.6f})/{duration:.6f})"
        center = f"if(lt(t,{t1:.6f}),{linear},{center})"
    first_t, first_x = compact[0]
    center = f"if(lt(t,{first_t:.6f}),{first_x:.6f},{center})"
    crop_width = f"ih*{target_ratio:.10f}"
    x = f"max(0,min(iw-({crop_width}),({center})*iw-({crop_width})/2))"
    return f"crop=w={crop_width}:h=ih:x='{x}':y=0"


_COMPOSITE_LAYOUTS = {
    "top-game-bottom-player": ("vertical", (0.58, 0.42)),
    "top-player-bottom-game": ("vertical", (0.42, 0.58)),
    "side-by-side": ("horizontal", (0.62, 0.38)),
}


def _even_pair(total: int, fraction: float) -> tuple[int, int]:
    safe_fraction = max(0.25, min(0.75, float(fraction)))
    first = max(2, min(total - 2, int(round(total * safe_fraction / 2)) * 2))
    return first, total - first


def _append_outline(
    filters: list[str],
    input_label: str,
    style: str | None,
    width: int,
    height: int,
    prefix: str,
    *,
    split_axis: str | None = None,
    split_at: int | None = None,
    rect: tuple[int, int, int, int] | None = None,
) -> str:
    """Add matching panel outlines to a rendered split or picture-in-picture frame."""
    if style not in {"clean", "neon", "double"}:
        return input_label
    line = max(2, int(round(min(width, height) / 240)))
    current = input_label
    sequence = 0

    def add(expression: str) -> None:
        nonlocal current, sequence
        label = f"{prefix}_outline{sequence}"
        filters.append(f"[{current}]{expression}[{label}]")
        current = label
        sequence += 1

    x, y, box_width, box_height = rect or (0, 0, width, height)

    def box_expression(color: str, thickness: int, inset: int = 0) -> str:
        box_x = x + inset
        box_y = y + inset
        box_w = max(2, box_width - inset * 2)
        box_h = max(2, box_height - inset * 2)
        return f"drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:color={color}:t={thickness}"

    def seam_expression(color: str, thickness: int, offset: int = 0) -> str | None:
        if split_axis not in {"vertical", "horizontal"} or split_at is None:
            return None
        if split_axis == "vertical":
            top = max(0, min(height - thickness, split_at + offset - thickness // 2))
            return f"drawbox=x=0:y={top}:w={width}:h={thickness}:color={color}:t=fill"
        left = max(0, min(width - thickness, split_at + offset - thickness // 2))
        return f"drawbox=x={left}:y=0:w={thickness}:h={height}:color={color}:t=fill"

    if style == "neon":
        glow = line * 3
        add(box_expression("0x22D3EE@0.34", glow))
        seam = seam_expression("0x22D3EE@0.34", glow)
        if seam:
            add(seam)
        add(box_expression("0x22D3EE@0.98", line))
        seam = seam_expression("0x22D3EE@0.98", line)
        if seam:
            add(seam)
    elif style == "double":
        add(box_expression("white@0.96", line))
        add(box_expression("white@0.96", line, inset=line * 3))
        for offset in (-line * 2, line * 2):
            seam = seam_expression("white@0.96", line, offset)
            if seam:
                add(seam)
    else:
        add(box_expression("white@0.94", line))
        seam = seam_expression("white@0.94", line)
        if seam:
            add(seam)
    return current


def _compose_regions(
    input_label: str,
    trim: str,
    regions: Any,
    layout: str | None,
    output_width: int,
    output_height: int,
    prefix: str,
    split_ratio: float | None = None,
    outline_style: str | None = "clean",
) -> tuple[list[str], str] | None:
    """Create a deterministic FFmpeg composite for the multi-region presets.

    The crop order and panel proportions are shared with the browser preview.
    Custom boxes without a known composition preset continue to use the first
    selected crop, preserving the earlier single-focus behavior.
    """
    selected = [region for region in (regions or []) if isinstance(region, dict)]
    if layout in _COMPOSITE_LAYOUTS and len(selected) >= 2:
        axis, fractions = _COMPOSITE_LAYOUTS[layout]
        try:
            requested_ratio = float(split_ratio) if split_ratio is not None else fractions[0]
        except (TypeError, ValueError, OverflowError):
            requested_ratio = fractions[0]
        if not math.isfinite(requested_ratio):
            requested_ratio = fractions[0]
        requested_ratio = max(0.25, min(0.75, requested_ratio))
        if axis == "vertical":
            first_size, second_size = _even_pair(output_height, requested_ratio)
            targets = [(output_width, first_size), (output_width, second_size)]
            stack = "vstack"
        else:
            first_size, second_size = _even_pair(output_width, requested_ratio)
            targets = [(first_size, output_height), (second_size, output_height)]
            stack = "hstack"
        source_labels = [f"{prefix}_src0", f"{prefix}_src1"]
        filters = [f"[{input_label}]{trim},split=2[{source_labels[0]}][{source_labels[1]}]"]
        panel_labels = []
        for index, (region, target, source_label) in enumerate(zip(selected[:2], targets, source_labels)):
            width, height = target
            crop = _crop_filter(region, expand_small=False)
            if not crop:
                return None
            label = f"{prefix}_panel{index}"
            filters.append(
                f"[{source_label}]{crop},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={width}:{height}[{label}]"
            )
            panel_labels.append(f"[{label}]")
        result = f"{prefix}_composite"
        filters.append("".join(panel_labels) + f"{stack}=inputs=2[{result}]")
        result = _append_outline(
            filters, result, outline_style, output_width, output_height, prefix,
            split_axis=axis, split_at=first_size,
        )
        return filters, result

    if layout == "square-player-full-game" and len(selected) >= 2:
        # The full frame remains the gameplay layer; the second marked region is
        # composited as a square picture-in-picture player view.
        pip_size = max(2, int(round(min(output_width, output_height) * 0.34 / 2)) * 2)
        inset = max(2, int(round(min(output_width, output_height) * 0.04 / 2)) * 2)
        source_labels = [f"{prefix}_bgsrc", f"{prefix}_fgsrc", f"{prefix}_pipsrc"]
        filters = [f"[{input_label}]{trim},split=3" + "".join(f"[{label}]" for label in source_labels)]
        filters.extend([
            f"[{source_labels[0]}]scale={output_width}:{output_height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={output_width}:{output_height},gblur=sigma=24[{prefix}_blur]",
            f"[{source_labels[1]}]scale={output_width}:{output_height}:force_original_aspect_ratio=decrease:flags=lanczos[{prefix}_fit]",
            f"[{prefix}_blur][{prefix}_fit]overlay=(W-w)/2:(H-h)/2[{prefix}_game]",
        ])
        pip_crop = _crop_filter(selected[1], expand_small=False)
        if not pip_crop:
            return None
        filters.append(
            f"[{source_labels[2]}]{pip_crop},scale={pip_size}:{pip_size}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={pip_size}:{pip_size}[{prefix}_pip]"
        )
        x = min(output_width - pip_size - 2, inset)
        y = min(output_height - pip_size - 2, inset)
        filters.append(
            f"[{prefix}_game][{prefix}_pip]overlay=x={x}:y={y}:eval=init[{prefix}_composite]"
        )
        result = _append_outline(
            filters, f"{prefix}_composite", outline_style, output_width, output_height,
            prefix, rect=(x, y, pip_size, pip_size),
        )
        return filters, result
    return None


async def encode(args: list[str], duration: float, on_progress=None) -> Path:
    """Run ffmpeg and stream its progress into the job tracker."""
    output = Path(args[-1])
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    assert process.stdout is not None
    try:
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
    except asyncio.CancelledError:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.communicate(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
        output.unlink(missing_ok=True)
        raise
    if code != 0 or not output.exists() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
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
    regions = options.get("regions") or []
    focus = options.get("region") or (regions[0] if regions else None)
    source_width = int(options.get("source_width") or 1080)
    source_height = int(options.get("source_height") or 1920)
    moving_crop = (
        _moving_crop_filter(options.get("crop_path"), options.get("aspect", "9:16"), source_width, source_height)
        if focus is None and not regions else None
    )
    source_trim = ",".join([
        f"trim=start={start:.3f}:end={end:.3f}",
        f"setpts=(PTS-STARTPTS)/{speed:.3f}", "fps=30",
    ])
    crop: str | None = None
    composed = _compose_regions(
        "0:v", source_trim, regions, options.get("region_layout"), width, height, "clip",
        options.get("split_ratio"), options.get("outline_style", "clean"),
    )
    if composed:
        filters, current = composed
        video_parts.extend(filters)
    elif moving_crop:
        # The auto-follow crop fills a portrait canvas directly; it replaces the
        # full-frame blur/contain treatment only when a tracked path is available.
        trim = ",".join([
            f"trim=start={start:.3f}:end={end:.3f}", moving_crop,
            f"setpts=(PTS-STARTPTS)/{speed:.3f}", "fps=30",
        ])
        video_parts.append(f"[0:v]{trim},scale={width}:{height}:flags=lanczos[base]")
        current = "base"
    else:
        trim_parts = [f"trim=start={start:.3f}:end={end:.3f}"]
        crop = _crop_filter(focus)
        if crop:
            # A single-region focus keeps the exact source-relative crop.
            trim_parts.append(crop)
        trim_parts.extend([f"setpts=(PTS-STARTPTS)/{speed:.3f}", "fps=30"])
        trim = ",".join(trim_parts)
        if options.get("blur_background", True) and options.get("aspect", "9:16") != "source":
            video_parts.append(f"[0:v]{trim},split=2[bg][fg]")
            video_parts.append(
                f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma=24[bgb]"
            )
            video_parts.append(
                f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos[fgs]"
            )
            video_parts.append(f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[base]")
            current = "base"
        else:
            video_parts.append(
                f"[0:v]{trim},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height}[base]"
            )
            current = "base"
        focus_box = _normalise_region(focus)
        if crop and focus_box and any(
            abs(actual - expected) > 1e-4
            for actual, expected in zip(focus_box, (0.0, 0.0, 1.0, 1.0))
        ):
            current = _append_outline(
                video_parts, current, options.get("outline_style", "clean"),
                width, height, "clip_focus",
            )
    eq_values = [
        f"brightness={float(options.get('brightness', 0)):.3f}",
        f"contrast={_normalise_contrast(options.get('contrast', 1)):.3f}",
        f"saturation={float(options.get('saturation', 1)):.3f}",
    ]
    video_parts.append(f"[{current}]eq={':'.join(eq_values)}[graded]")
    current = "graded"
    caption_style = options.get("caption_style") or {}
    captions = list(options.get("captions") or [])
    title = str(options.get("title") or "").strip()
    if title:
        captions.append({
            "text": title[:100], "start": start,
            "end": min(end, start + max(1.4, min(2.8, duration * 0.22))), "kind": "title",
        })
    if caption_style.get("preset", "hype") == "none":
        captions = [caption for caption in captions if caption.get("kind") == "title"]
    if captions:
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
    if watermark and Path(str(watermark)).is_file():
        wm_index = add_input("-loop", "1", "-i", str(watermark))
        video_parts.append(
            f"[{wm_index}:v]scale=100:-1,format=rgba,colorchannelmixer=aa=0.85[wm];"
            f"[{current}][wm]overlay=W-w-28:H-h-28[branded]"
        )
        current = "branded"
    # Explicitly normalize the encoded range/aspect and tell QuickTime the
    # filtered 8-bit MP4 is Rec.709 rather than relying on source metadata.
    video_parts.append(f"[{current}]scale=in_range=auto:out_range=tv,setsar=1,format=yuv420p[vout]")

    audio_inputs: list[str] = []
    tempo = f",{_atempo_filter(speed)}" if abs(speed - 1.0) > 0.01 else ""
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
    args += [
        "-filter_complex", ";".join(video_parts + audio_parts),
        "-map", "[vout]", "-map", "[aout]", *_thread_args(), *_video_codec_args(),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-t", f"{duration / speed:.3f}", "-progress", "pipe:1", "-nostats", output,
    ]
    return args


def _validate_mp4(path: str | Path) -> None:
    """Reject empty, non-video, or non-H.264 outputs before marking a clip ready."""
    target = Path(path)
    if not target.exists() or target.stat().st_size < 128:
        raise RuntimeError("Render finished without producing a valid MP4 file.")
    info = probe(target)
    codec = str(info.get("video_codec") or "").lower()
    if codec and codec != "h264":
        raise RuntimeError(f"Render produced {codec}, not broadly compatible H.264 video.")
    if not codec or not info.get("width") or not info.get("height"):
        raise RuntimeError("Render output could not be verified as a playable video. Check the local FFmpeg installation.")


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
    try:
        _validate_mp4(output)
    except Exception:
        Path(output).unlink(missing_ok=True)
        raise
    return output


async def render_timeline(
    timeline: dict[str, Any], output: str, on_progress=None, watermark_path: str | None = None
) -> str:
    """Render a full CapCut-style multi-track project to a single MP4."""
    tracks = timeline.get("tracks") or {}
    video_items = tracks.get("video") or []
    if not video_items:
        raise RuntimeError("Add at least one video clip to the timeline before exporting")
    aspect = timeline.get("aspect", "9:16")
    resolution = timeline.get("resolution", "1080p")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    args: list[str] = [ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error"]
    media_inputs: list[dict[str, Any]] = []
    indexed_video: list[tuple[dict[str, Any], int]] = []
    source_info: list[dict[str, Any]] = []
    for item in video_items:
        path = str(item.get("path") or "")
        if not Path(path).exists():
            continue
        args += ["-i", path]
        idx = sum(1 for a in args if a == "-i") - 1
        media_inputs.append(item)
        indexed_video.append((item, idx))
        source_info.append(probe(path))
    if not indexed_video:
        raise RuntimeError("None of the timeline video files were found on this machine")
    best_source = max(
        source_info,
        key=lambda info: int(info.get("width") or 0) * int(info.get("height") or 0),
    )
    width, height = resolution_for(
        aspect, resolution,
        (int(best_source.get("width") or 1080), int(best_source.get("height") or 1920)),
    )

    audio_items = [item for item in (tracks.get("audio") or []) if Path(str(item.get("path", ""))).is_file()]
    for item in audio_items:
        if item.get("kind") == "sfx":
            args += ["-i", str(item["path"])]
        else:
            args += ["-stream_loop", "-1", "-i", str(item["path"])]
    sticker_items = [item for item in (tracks.get("stickers") or []) if Path(str(item.get("path", ""))).is_file()]
    for item in sticker_items:
        args += ["-loop", "1", "-i", str(item["path"])]
    watermark_index = None
    if watermark_path and Path(watermark_path).is_file():
        watermark_index = len(indexed_video) + len(audio_items) + len(sticker_items)
        args += ["-loop", "1", "-i", watermark_path]

    filters: list[str] = []
    vlabels: list[str] = []
    alabels: list[str] = []
    timeline_titles: list[dict[str, Any]] = []
    timeline_cursor = 0.0
    audio_base = len(indexed_video)
    sticker_base = audio_base + len(audio_items)
    for position, (item, idx) in enumerate(indexed_video):
        source_in = float(item.get("sourceStart", 0))
        duration = max(0.2, float(item.get("duration", 5)))
        effects = item.get("effects") if isinstance(item.get("effects"), dict) else {}
        try:
            speed = max(0.25, min(float(effects.get("speed", 1)), 4))
        except (TypeError, ValueError):
            speed = 1.0
        source_duration = max(0.05, float(item.get("sourceDuration") or duration * speed))
        if item.get("clip_id") and str(item.get("label") or "").strip():
            title_end = timeline_cursor + min(duration, max(1.4, min(2.8, duration * 0.22)))
            timeline_titles.append({
                "text": str(item["label"])[:100], "start": timeline_cursor,
                "end": title_end, "kind": "title",
            })
        trim = (
            f"trim=start={source_in:.3f}:duration={source_duration:.3f},"
            f"setpts=(PTS-STARTPTS)/{speed:.3f},fps=30"
        )
        regions = item.get("regions") or []
        layout = item.get("region_layout")
        split_ratio = item.get("split_ratio")
        if split_ratio is None:
            split_ratio = effects.get("split_ratio")
        outline_style = item.get("outline_style") or effects.get("outline_style") or "clean"
        composed = _compose_regions(
            f"{idx}:v", trim, regions, layout, width, height, f"timeline{position}",
            split_ratio, outline_style,
        )
        if composed:
            composed_filters, video_label = composed
            filters.extend(composed_filters)
        else:
            focus = item.get("region") or (regions[0] if regions else None)
            source = source_info[position]
            moving_crop = (
                _moving_crop_filter(
                    item.get("crop_path"), aspect,
                    int(source.get("width") or 0), int(source.get("height") or 0),
                )
                if focus is None and not regions else None
            )
            crop = _crop_filter(focus)
            video_filter = f"trim=start={source_in:.3f}:duration={source_duration:.3f}"
            if moving_crop:
                video_filter += "," + moving_crop
            elif crop:
                video_filter += "," + crop
            video_filter += (
                f",setpts=(PTS-STARTPTS)/{speed:.3f},"
                f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},fps=30"
            )
            video_label = f"v{position}"
            filters.append(f"[{idx}:v]{video_filter}[{video_label}]")
            focus_box = _normalise_region(focus)
            if crop and focus_box and any(
                abs(actual - expected) > 1e-4
                for actual, expected in zip(focus_box, (0.0, 0.0, 1.0, 1.0))
            ):
                video_label = _append_outline(
                    filters, video_label, outline_style, width, height,
                    f"timeline{position}_focus",
                )
        try:
            brightness = float(effects.get("brightness", 0))
            saturation = float(effects.get("saturation", 1))
        except (TypeError, ValueError):
            brightness, saturation = 0.0, 1.0
        contrast = _normalise_contrast(effects.get("contrast", 1))
        graded = f"v{position}_graded"
        filters.append(
            f"[{video_label}]eq=brightness={brightness:.3f}:contrast={contrast:.3f}:saturation={saturation:.3f}[{graded}]"
        )
        vlabels.append(f"[{graded}]")
        media = source_info[position]
        if media.get("audio_codec"):
            audio_filter = f"atrim=start={source_in:.3f}:duration={source_duration:.3f},asetpts=PTS-STARTPTS"
            if abs(speed - 1.0) > 0.01:
                audio_filter += f",{_atempo_filter(speed)}"
            audio_filter += f",atrim=0:{duration:.3f}"
            filters.append(f"[{idx}:a]{audio_filter}[a{position}]")
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{duration:.3f}[a{position}]")
        alabels.append(f"[a{position}]")
        timeline_cursor += duration
    filters.append("".join(vlabels) + f"concat=n={len(vlabels)}:v=1:a=0[vcat]")
    filters.append("".join(alabels) + f"concat=n={len(alabels)}:v=0:a=1[acat]")

    total = timeline_cursor
    current = "vcat"
    captions = list(tracks.get("captions") or []) + timeline_titles
    caption_style = timeline.get("caption_style") or {"preset": "hype"}
    if caption_style.get("preset", "hype") == "none":
        captions = [caption for caption in captions if caption.get("kind") == "title"]
    if captions:
        ass_path = write_ass(captions, caption_style)
        filters.append(f"[{current}]subtitles=filename='{escape_filter_path(ass_path)}'[cap]")
        current = "cap"
    for offset, item in enumerate(sticker_items):
        start = float(item.get("start", 0))
        end = float(item.get("end", min(total, start + 3)))
        try:
            sticker_scale = float(item.get("scale", 0))
        except (TypeError, ValueError):
            sticker_scale = 0
        sticker_width = max(24, int(width * min(0.8, max(0.05, sticker_scale)))) if sticker_scale else 240
        x = max(0.0, min(1.0, float(item.get("x", 0.72))))
        y = max(0.0, min(1.0, float(item.get("y", 0.16))))
        filters.append(
            f"[{sticker_base + offset}:v]scale={sticker_width}:-1[st{offset}];"
            f"[{current}][st{offset}]overlay=x='{x:.3f}*(W-w)':y='{y:.3f}*(H-h)':"
            f"enable='between(t,{start:.2f},{end:.2f})'[stuck{offset}]"
        )
        current = f"stuck{offset}"
    if watermark_index is not None:
        filters.append(
            f"[{watermark_index}:v]scale=100:-1,format=rgba,colorchannelmixer=aa=0.85[wm];"
            f"[{current}][wm]overlay=W-w-28:H-h-28[branded]"
        )
        current = "branded"
    audio_sources = ["[acat]"]
    for offset, item in enumerate(audio_items):
        start = max(0.0, float(item.get("start", 0)))
        end = min(total, max(start + 0.05, float(item.get("end", total))))
        duration = max(0.05, end - start)
        volume = max(0.0, min(2.0, float(item.get("volume", 0.2))))
        label = f"audio{offset}"
        filters.append(
            f"[{audio_base + offset}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume={volume:.3f},adelay={int(start * 1000)}|{int(start * 1000)}[{label}]"
        )
        audio_sources.append(f"[{label}]")
    filters.append(
        "".join(audio_sources)
        + f"amix=inputs={len(audio_sources)}:duration=first:normalize=0,apad,atrim=0:{total:.3f}[aout]"
    )
    filters.append(f"[{current}]scale=in_range=auto:out_range=tv,setsar=1,format=yuv420p[vout]")
    args += [
        "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
        *_thread_args(), *_video_codec_args(),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-t", f"{total:.3f}", "-progress", "pipe:1", "-nostats", output,
    ]
    await encode(args, total, on_progress)
    try:
        _validate_mp4(output)
    except Exception:
        Path(output).unlink(missing_ok=True)
        raise
    return output


def export_path(name: str, export_day: date | None = None) -> str:
    """Return the export path inside a local-date folder for the current day."""
    from ..db import db  # local import avoids a config/db cycle

    configured = db.get_setting("exports_folder", "") or db.get_setting("clips_folder", "")
    root = Path(configured).expanduser() if configured else EXPORTS
    day_folder = root / (export_day or date.today()).isoformat()
    day_folder.mkdir(parents=True, exist_ok=True)
    return str(day_folder / f"{safe_name(name)}.mp4")
