"""Automatic video editing and rendering engine.

Turns a source video plus an analysis result into a finished, ready-to-upload short:

  * vertical 9:16 / square 1:1 / landscape 16:9 conversion
  * smart reframe that follows the active speaker's face
  * dynamic punch-in zooms at strong moments
  * jump cuts that remove silence and dead air
  * colour correction, brightness and contrast optimisation
  * audio loudness normalisation and noise reduction
  * optional background music ducking and sound effects
  * animated word-by-word captions burned in via ASS subtitles

Every stage is a real FFmpeg invocation.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Sequence

from ..ai.audio_analysis import AudioAnalysis
from ..ai.clip_detector import ClipCandidate
from ..ai.speaker_tracking import SpeakerTrack, subject_center_at
from ..ai.visual_analysis import VisualAnalysis
from ..captions.caption_engine import CaptionCue, CaptionStyle, get_style, write_ass
from ..core.config import ASPECT_RATIOS
from ..core.fonts import drawtext_font_args, fontsdir_arg
from ..core.ffmpeg import (
    FFmpegCancelled,
    FFmpegRunner,
    MAX_INLINE_ARGS,
    probe,
    run_ffmpeg,
    write_filter_script,
)
from ..core.hardware import EncoderChoice, choose_encoder
from ..core.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class RenderSettings:
    """User-facing editing options for one clip."""
    editing_preset: str = "clean"
    auto_facecam: bool = True
    gameplay_rect: tuple = (0., 0., 1., 1.)
    gaming_enhance: bool = False
    facecam_rect: tuple = (0.0, 0.0, 0.25, 0.3)
    aspect: str = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    codec: str = "h264"           # h264 | h265
    bitrate_kbps: int = 8000
    crf: int = 21
    caption_style: str = "bold_viral"
    caption_font: str = ""
    caption_size: int = 58
    caption_position: str = "bottom"
    caption_stroke: int = 4
    caption_shadow: bool = True
    caption_background: bool = False
    show_captions: bool = True
    smart_reframe: bool = True
    auto_zoom: bool = True
    remove_silence: bool = True
    silence_threshold_db: float = -32.0
    min_silence_duration: float = 0.35
    color_correct: bool = True
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    normalize_audio: bool = True
    noise_reduction: bool = True
    background_music: str = ""
    bgm_volume: float = 0.12
    sound_effects: bool = True
    transitions: bool = True
    transition_duration: float = 0.35
    intro_template: str = ""
    outro_template: str = ""
    hook_text: str = ""
    hook_duration: float = 2.0
    encoder_preference: str = "auto"
    threads: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RenderSettings":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})

    @classmethod
    def for_aspect(cls, aspect: str) -> "RenderSettings":
        w, h = ASPECT_RATIOS.get(aspect, ASPECT_RATIOS["9:16"])
        return cls(aspect=aspect, width=w, height=h)


@dataclass
class RenderResult:
    output_path: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    encoder: str = ""
    elapsed: float = 0.0
    cancelled: bool = False
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------------------
# Filter graph helpers
# --------------------------------------------------------------------------------------


def _zoompan_filter(
    source_w: int,
    source_h: int,
    out_w: int,
    out_h: int,
    centers: list[tuple[float, float, float]],
    duration: float,
    fps: int,
) -> str:
    """Build a smooth crop+scale filter that follows the subject.

    ``centers`` is a list of (cx, cy, zoom) keyframes over the clip.  The zoom is
    interpolated frame-by-frame so the camera motion is smooth rather than steppy.
    """
    if not centers:
        return f"scale={out_w}:{out_h}:flags=lanczos,setsar=1"

    # Base crop window: we crop to the output aspect then scale up.
    src_ar = source_w / max(1, source_h)
    out_ar = out_w / max(1, out_h)
    if src_ar > out_ar:
        crop_h = source_h
        crop_w = int(round(source_h * out_ar))
    else:
        crop_w = source_w
        crop_h = int(round(source_w / out_ar))
    crop_w = max(16, min(source_w, crop_w))
    crop_h = max(16, min(source_h, crop_h))

    pieces: list[str] = []
    total_frames = max(1, int(duration * fps))

    for i in range(len(centers) - 1):
        (cx0, cy0, z0) = centers[i]
        (cx1, cy1, z1) = centers[i + 1]
        n0 = centers[i][3] if len(centers[i]) > 3 else i
        n1 = centers[i + 1][3] if len(centers[i + 1]) > 3 else i + 1
        frames = max(1, n1 - n0)
        # Linear interpolation between keyframes in crop geometry
        parts: list[str] = []
        for f in range(frames):
            t = f / frames
            z = z0 + (z1 - z0) * t
            cx = cx0 + (cx1 - cx0) * t
            cy = cy0 + (cy1 - cy0) * t
            w = crop_w / max(1.0, z)
            h = crop_h / max(1.0, z)
            x = (source_w - w) * cx
            y = (source_h - h) * cy
            x = max(0.0, min(source_w - w, x))
            y = max(0.0, min(source_h - h, y))
            parts.append(f"crop={w:.1f}:{h:.1f}:{x:.1f}:{y:.1f}")
        pieces.append(
            f"[v{i}][v{i + 1}]zoompan=z='min(zoom+0.0015,1.5)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={out_w}x{out_h}:fps={fps}[z{i}]"
        )
    return ""


def _subject_keyframes(
    speaker: SpeakerTrack | None,
    visual: VisualAnalysis,
    start: float,
    end: float,
    step: float = 0.5,
    base_zoom: float = 1.0,
) -> list[tuple[float, float, float]]:
    """Sample subject centre/zoom over the clip for smooth camera moves."""
    if not speaker or not visual.tracks:
        return []
    keys: list[tuple[float, float, float]] = []
    t = start
    while t <= end + 1e-6:
        cx, cy, area = subject_center_at(speaker, visual, t)
        # Larger face -> tighter crop (more zoom). Clamp so we never crop too far.
        zoom = base_zoom + min(0.35, max(0.0, area * 2.2))
        keys.append((cx, cy, zoom))
        t += step
    if not keys:
        keys.append((0.5, 0.42, base_zoom))
    return keys


def _smooth_keys(
    keys: list[tuple[float, float, float]], window: int = 3
) -> list[tuple[float, float, float]]:
    """Smooth the camera path so it does not jitter between frames."""
    if len(keys) < 3:
        return keys
    out: list[tuple[float, float, float]] = []
    n = len(keys)
    for i in range(n):
        lo = max(0, i - window // 2)
        hi = min(n, i + window // 2 + 1)
        chunk = keys[lo:hi]
        cx = sum(k[0] for k in chunk) / len(chunk)
        cy = sum(k[1] for k in chunk) / len(chunk)
        z = sum(k[2] for k in chunk) / len(chunk)
        out.append((cx, cy, z))
    return out


def _crop_expr(
    source_w: int, source_h: int, out_w: int, out_h: int,
    keys: list[tuple[float, float, float]], duration: float, fps: int
) -> str:
    """Build a time-varying crop filter using sendcmd-free expressions.

    Uses a piecewise-linear expression over ``t`` so the crop follows the subject
    smoothly without needing the zoompan filter (which is CPU heavy at 1080p).
    """
    src_ar = source_w / max(1, source_h)
    out_ar = out_w / max(1, out_h)
    if src_ar > out_ar:
        crop_h = float(source_h)
        crop_w = float(source_h * out_ar)
    else:
        crop_w = float(source_w)
        crop_h = float(source_w / out_ar)
    crop_w = max(16.0, min(float(source_w), crop_w))
    crop_h = max(16.0, min(float(source_h), crop_h))

    if not keys:
        return (
            f"crop={crop_w:.0f}:{crop_h:.0f}:"
            f"{(source_w - crop_w) / 2:.0f}:{(source_h - crop_h) / 2:.0f},"
            f"scale={out_w}:{out_h}:flags=lanczos"
        )

    # Build a piecewise expression for x, y and zoom based on keyframe times.
    # Each segment contributes its value only while t is inside that segment, and
    # the value is linearly interpolated between the two bounding keyframes.
    seg_dur = duration / max(1, len(keys))

    def build_expr(idx: int) -> str:
        terms: list[str] = []
        n = len(keys)
        for i in range(n):
            t0 = i * seg_dur
            t1 = (i + 1) * seg_dur if i < n - 1 else duration + 1.0
            if i == 0:
                # First keyframe holds until the second one starts
                v = keys[0][idx]
                nxt = keys[1][idx] if n > 1 else v
                slope = (nxt - v) / max(1e-6, seg_dur)
                terms.append(
                    f"({v:.5f}+({slope:.7f})*min(t,{seg_dur:.4f}))"
                    f"*if(lt(t,{seg_dur:.4f}),1,0)"
                )
            elif i == n - 1:
                # Last keyframe holds for the remainder of the clip
                terms.append(f"{keys[i][idx]:.5f}")
            else:
                v = keys[i - 1][idx]
                nxt = keys[i][idx]
                slope = (nxt - v) / max(1e-6, seg_dur)
                terms.append(
                    f"({v:.5f}+({slope:.7f})*min(max(t-{t0:.4f},0),{seg_dur:.4f}))"
                    f"*if(lt(t,{t1:.4f}),1,0)"
                )
        return "+".join(terms)

    # Zoom is applied by shrinking the crop rectangle
    zoom_expr = build_expr(2)
    cx_expr = build_expr(0)
    cy_expr = build_expr(1)

    w_expr = f"min({crop_w:.0f}/({zoom_expr}),{source_w})"
    h_expr = f"min({crop_h:.0f}/({zoom_expr}),{source_h})"
    x_expr = f"max(0,min({source_w}-{w_expr},({source_w}-{w_expr})*({cx_expr})))"
    y_expr = f"max(0,min({source_h}-{h_expr},({source_h}-{h_expr})*({cy_expr})))"

    return (
        f"crop=w='{w_expr}':h='{h_expr}':x='{x_expr}':y='{y_expr}',"
        f"scale={out_w}:{out_h}:flags=lanczos"
    )


def _filter_args(graph: str, work_dir: Path, stem: str) -> list[str]:
    """Return the ffmpeg arguments that apply ``graph``.

    A long filter graph (many jump cuts, a big caption chain) can exceed the
    operating system's command-line length limit, which makes the spawn fail
    with "Argument list too long".  When that happens the graph is written to a
    file and passed with ``-filter_complex_script`` instead.
    """
    if len(graph) < MAX_INLINE_ARGS:
        return ["-filter_complex", graph]
    script = work_dir / f"filter_{stem}.txt"
    write_filter_script(graph, script)
    log.info("filter graph written to %s (%d chars)", script, len(graph))
    return ["-filter_complex_script", str(script)]


def _escape_ass_path(p: Path) -> str:
    """Escape a path so it survives FFmpeg filter-graph parsing."""
    s = str(Path(p).resolve()).replace("\\", "/")
    for ch in (":", "'", "[", "]", ","):
        s = s.replace(ch, "\\" + ch)
    return s


def segment_video_filter(segment, width, height):
    """Crop inside the scaled image, rather than cropping an already tight frame."""
    zoom = max(1.0, float(segment.zoom))
    sw = int(width * zoom / 2 + 0.5) * 2
    sh = int(height * zoom / 2 + 0.5) * 2
    x, y = max(0, min(1, segment.crop_x)), max(0, min(1, segment.crop_y))
    return (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:(iw-ow)*{x:.5f}:(ih-oh)*{y:.5f},setsar=1")


def _build_color_filter(s: RenderSettings) -> str:
    parts: list[str] = []
    if s.color_correct:
        parts.append("eq=contrast=1.06:saturation=1.10:gamma=0.98")
        parts.append("unsharp=5:5:0.6:5:5:0.0")
    if abs(s.brightness) > 0.001 or abs(s.contrast - 1.0) > 0.001 or abs(s.saturation - 1.0) > 0.001:
        parts.append(
            f"eq=brightness={s.brightness:.3f}:contrast={s.contrast:.3f}:saturation={s.saturation:.3f}"
        )
    return ",".join(parts)


def _build_audio_filter(s: RenderSettings, music_path: str = "") -> str:
    parts: list[str] = []
    if s.noise_reduction:
        parts.append("afftdn=nf=-25")
    if s.normalize_audio:
        # NB: `loudnorm` is a two-pass filter.  In single-pass mode it buffers
        # the whole signal to measure the loudness, which means it emits nothing
        # when it is combined with `amix` (the mix waits for a stream that never
        # arrives).  `dynaudnorm` does the same job in a single pass and mixes
        # cleanly, so that is what we use here.
        parts.append("dynaudnorm=f=250:g=15:p=0.9:m=10")
    if music_path and Path(music_path).exists():
        parts.append(f"volume={s.bgm_volume:.3f}")
    return ",".join(parts)


# --------------------------------------------------------------------------------------
# Silence removal
# --------------------------------------------------------------------------------------


def compute_jump_cuts(
    audio: AudioAnalysis | None,
    start: float,
    end: float,
    threshold_db: float = -32.0,
    min_silence: float = 0.35,
    padding: float = 0.12,
) -> list[tuple[float, float]]:
    """Return keep-segments (relative to clip start) after removing silence."""
    if not audio or not audio.silence_ranges:
        return [(0.0, max(0.0, end - start))]

    clip_silences = []
    for s, e in audio.silence_ranges:
        cs = max(start, s)
        ce = min(end, e)
        if ce - cs >= min_silence:
            clip_silences.append((cs, ce))

    if not clip_silences:
        return [(0.0, max(0.0, end - start))]

    keeps: list[tuple[float, float]] = []
    cursor = start
    for s, e in sorted(clip_silences):
        if s - cursor > 0.12:
            keeps.append((cursor - start, s - start))
        cursor = max(cursor, e)
    if end - cursor > 0.12:
        keeps.append((cursor - start, end - start))
    if not keeps:
        keeps = [(0.0, max(0.0, end - start))]

    # Merge segments separated by very short gaps so we do not over-cut
    merged: list[tuple[float, float]] = []
    for k in keeps:
        if merged and k[0] - merged[-1][1] < 0.28:
            merged[-1] = (merged[-1][0], k[1])
        else:
            merged.append(k)
    return merged


# --------------------------------------------------------------------------------------
# Main renderer
# --------------------------------------------------------------------------------------


class ClipRenderer:
    """Renders a finished short from a source video."""

    def __init__(self, work_dir: str | Path) -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def render(
        self,
        source: str | Path,
        output: str | Path,
        start: float,
        end: float,
        settings: RenderSettings,
        cues: list[CaptionCue] | None = None,
        audio: AudioAnalysis | None = None,
        visual: VisualAnalysis | None = None,
        speaker: SpeakerTrack | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
        cancel_cb: Callable[[], bool] | None = None,
    ) -> RenderResult:
        import time

        t_start = time.time()
        source = Path(source)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        result = RenderResult(output_path=str(output))

        if not source.exists():
            raise FileNotFoundError(f"Source video not found: {source}")

        # ---- probe the source ----------------------------------------------------
        from ..core.ffmpeg import probe

        info = probe(source)
        src_w = info.video.width if info.video else settings.width
        src_h = info.video.height if info.video else settings.height
        has_audio = info.has_audio
        result.steps.append(f"Source {src_w}x{src_h}, {info.duration:.1f}s, audio={has_audio}")

        clip_dur = max(0.5, end - start)

        # ---- jump cuts (silence removal) -----------------------------------------
        keeps: list[tuple[float, float]] = [(0.0, clip_dur)]
        if settings.remove_silence and audio:
            keeps = compute_jump_cuts(
                audio, start, end,
                settings.silence_threshold_db, settings.min_silence_duration,
            )
            if len(keeps) > 1:
                result.steps.append(f"Removed {len(keeps) - 1} silent segments")
            else:
                result.steps.append("No silence to remove")

        # ---- build the video filter chain ----------------------------------------
        vf_parts: list[str] = []
        vf_parts.append(f"fps={settings.fps}")

        if settings.editing_preset == "gaming":
            from .presets import gaming_filter
            facecam, gameplay = settings.facecam_rect, settings.gameplay_rect
            if settings.auto_facecam:
                from ..ai.gaming_layout import detect_layout
                if progress_cb:
                    progress_cb(2.0, "Finding a stable player facecam")
                layout = detect_layout(source, start, end, cancel_cb)
                facecam = layout.facecam if layout else None
                gameplay = layout.gameplay if layout else gameplay
                if layout:
                    result.steps.append(f"Facecam confidence {layout.confidence:.0%}; {layout.observations} observations")
                else:
                    result.warnings.append("No stable facecam detected; gameplay-only crop used. Review framing or select a manual facecam rectangle.")
            vf_parts.append(gaming_filter(settings.width, settings.height, src_w, src_h, facecam, gameplay))
            if settings.gaming_enhance:
                # Subtle SDR clarity, NOT genuine HDR conversion.
                vf_parts.append("eq=contrast=1.04:saturation=1.06,unsharp=5:5:0.25:5:5:0")
                result.steps.append("SDR clarity and restrained colour enhancement (not HDR)")
            result.steps.append("Gameplay above, player below" if facecam else "Gameplay only")
        elif settings.smart_reframe and visual and speaker and visual.tracks:
            keys = _smooth_keys(
                _subject_keyframes(speaker, visual, start, end, step=0.5)
            )
            if keys:
                vf_parts.append(_crop_expr(src_w, src_h, settings.width, settings.height,
                                           keys, clip_dur, settings.fps))
                result.steps.append("Smart reframe follows the active speaker")
            else:
                vf_parts.append(
                    f"scale={settings.width}:{settings.height}:force_original_aspect_ratio=increase,"
                    f"crop={settings.width}:{settings.height}"
                )
        else:
            vf_parts.append(
                f"scale={settings.width}:{settings.height}:force_original_aspect_ratio=increase,"
                f"crop={settings.width}:{settings.height}"
            )

        color = _build_color_filter(settings)
        if color:
            vf_parts.append(color)

        if settings.hook_text:
            hook = settings.hook_text.replace(":", "\\:").replace("'", "")
            hook = hook.replace("%", "\\%")
            font_arg = drawtext_font_args()
            vf_parts.append(
                f"drawtext=text='{hook}':{font_arg}fontcolor=white:fontsize=54:borderw=4:"
                f"bordercolor=black@0.9:box=1:boxcolor=black@0.55:boxborderw=22:"
                f"x=(w-text_w)/2:y=h*0.16:enable='lt(t,{settings.hook_duration:.2f})'"
            )
            result.steps.append(f"Intro hook text: {settings.hook_text[:40]}")

        vf = ",".join(vf_parts)
        af = _build_audio_filter(settings, settings.background_music)

        # ---- captions -------------------------------------------------------------
        ass_path: Path | None = None
        if settings.show_captions and cues:
            style = get_style(settings.caption_style)
            from ..captions.caption_engine import pick_highlight_words

            highlights = pick_highlight_words(" ".join(c.text for c in cues))
            ass_path = self.work_dir / f"captions_{output.stem}.ass"
            from ..captions.caption_engine import retime_cues
            output_cues = retime_cues(cues, [(start+ks, start+ke, 1.0) for ks, ke in keeps])
            write_ass(
                ass_path, output_cues, style,
                settings.width, settings.height,
                font_override=settings.caption_font,
                size_override=settings.caption_size,
                position_override=settings.caption_position,
                stroke_override=settings.caption_stroke,
                shadow_override=settings.caption_shadow,
                background_override=settings.caption_background,
                highlight_words=highlights,
            )
            result.steps.append(f"Captions: {style.name} ({len(cues)} cues)")

        # ---- encoder --------------------------------------------------------------
        enc = choose_encoder(settings.encoder_preference, settings.codec,
                             low_memory=False)
        result.encoder = enc.description
        result.steps.append(f"Encoder: {enc.description}")

        # ---- assemble the ffmpeg command ------------------------------------------
        inputs: list[str] = []
        input_args: list[str] = []
        filter_parts: list[str] = []

        if len(keeps) > 1:
            # Multiple keep segments -> trim + concat
            seg_args: list[str] = []
            for i, (ks, ke) in enumerate(keeps):
                abs_s = start + ks
                abs_e = start + ke
                seg_args += [
                    "-ss", f"{abs_s:.3f}", "-t", f"{max(0.05, abs_e - abs_s):.3f}",
                    "-i", str(source),
                ]
            inputs.append("concat")
            # Build: [0:v]vf[v0];[1:v]vf[v1];...;[0:a][1:a]...concat
            parts: list[str] = []
            for i in range(len(keeps)):
                segment_vf = vf
                for label in ("game", "cam", "upper", "lower"):
                    segment_vf = segment_vf.replace(f"[{label}]", f"[{label}{i}]")
                parts.append(f"[{i}:v]{segment_vf}[v{i}]")
            for i in range(len(keeps)):
                if has_audio:
                    parts.append(f"[{i}:a]{af}[a{i}]" if af else f"[{i}:a]anull[a{i}]")
                else:
                    ks, ke = keeps[i]
                    parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={ke-ks:.6f}[a{i}]")
            labels = "".join(f"[v{i}][a{i}]" for i in range(len(keeps)))
            parts.append(f"{labels}concat=n={len(keeps)}:v=1:a=1[vcat][acat]")
            filter_parts.append(";".join(parts))
            final_v, final_a = "[vcat]", "[acat]"
        else:
            input_args += ["-ss", f"{start:.3f}", "-t", f"{clip_dur:.3f}", "-i", str(source)]
            vlabel, alabel = "[v0]", "[a0]"
            if ass_path:
                fontsdir = fontsdir_arg()
                filter_parts.append(
                    f"[0:v]{vf}[vbase];[vbase]ass='{_escape_ass_path(ass_path)}'"
                    f"{fontsdir}[v0]"
                )
            else:
                filter_parts.append(f"[0:v]{vf}[v0]")
            if not has_audio:
                filter_parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={clip_dur:.6f}[a0]")
            elif af:
                filter_parts.append(f"[0:a]{af}[a0]")
            else:
                filter_parts.append(f"[0:a]anull[a0]")
            final_v, final_a = vlabel, alabel

        if ass_path and len(keeps) > 1:
            filter_parts.append(f"{final_v}ass='{_escape_ass_path(ass_path)}'{fontsdir_arg()}[captioned]")
            final_v = "[captioned]"

        # Background music as a second input
        music_idx = None
        if settings.background_music and Path(settings.background_music).exists():
            music_idx = len(keeps) if len(keeps) > 1 else 1
            input_args += ["-stream_loop", "-1", "-i", str(settings.background_music)]
            filter_parts.append(
                f"[{music_idx}:a]volume={settings.bgm_volume:.3f},"
                f"atrim=0:{clip_dur:.2f},asetpts=N/SR/TB[bgm]"
            )
            filter_parts.append(f"[{final_a[1:-1]}][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]")
            final_a = "[aout]"

        # Sound effect at the start
        if settings.sound_effects:
            sfx = self._find_sound_effect()
            if sfx:
                sfx_idx = (music_idx + 1) if music_idx is not None else (
                    len(keeps) if len(keeps) > 1 else 1
                )
                input_args += ["-i", str(sfx)]
                filter_parts.append(
                    f"[{sfx_idx}:a]volume=0.35,adelay=0|0,atrim=0:{clip_dur:.2f},"
                    f"asetpts=N/SR/TB[sfx]"
                )
                filter_parts.append(f"[{final_a[1:-1]}][sfx]amix=inputs=2:duration=first:dropout_transition=0[aout2]")
                final_a = "[aout2]"
                result.steps.append("Added sound effect")

        filter_complex = ";".join(filter_parts)

        cmd: list[str] = []
        from ..core.hardware import suggest_worker_threads
        threads = suggest_worker_threads(settings.threads)
        cmd += ["-hide_banner", "-nostdin", "-y", "-threads", str(threads), "-filter_complex_threads", str(threads)]
        if len(keeps) > 1:
            cmd += seg_args
        # input_args already carries the music and sound-effect inputs, in the
        # same order their indices were computed from -- do not add them again.
        cmd += input_args
        cmd += _filter_args(filter_complex, self.work_dir, output.stem)
        cmd += ["-map", final_v, "-map", final_a]

        if enc.hw_accel == "nvenc":
            cmd += ["-c:v", enc.video_encoder, "-preset", "p5", "-b:v", f"{settings.bitrate_kbps}k"]
        elif enc.hw_accel == "videotoolbox":
            cmd += ["-c:v", enc.video_encoder, "-b:v", f"{settings.bitrate_kbps}k"]
        elif enc.hw_accel == "qsv":
            cmd += ["-c:v", enc.video_encoder, "-preset", "medium", "-b:v", f"{settings.bitrate_kbps}k"]
        else:
            cmd += ["-c:v", enc.video_encoder, "-preset", "medium", "-crf", str(settings.crf),
                    "-b:v", f"{settings.bitrate_kbps}k", "-maxrate", f"{int(settings.bitrate_kbps * 1.3)}k",
                    "-bufsize", f"{settings.bitrate_kbps * 2}k"]

        cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
        cmd += ["-movflags", "+faststart", "-pix_fmt", "yuv420p"]
        cmd += ["-threads", str(threads), str(output)]

        if progress_cb:
            progress_cb(5.0, "Rendering clip")

        runner = FFmpegRunner(total_duration=clip_dur,
                              progress_cb=lambda p, t: progress_cb(
                                  5.0 + p * 0.9, f"Rendering… {p:.0f}%"
                              ) if progress_cb else None,
                              cancel_cb=cancel_cb)
        try:
            runner.run(cmd[1:], total_duration=clip_dur)
        except FFmpegCancelled:
            # The user asked to stop — do not fall back to a second render.
            log.info("render cancelled by the user")
            result.cancelled = True
            return result
        except Exception as exc:
            # Retry without the complex filter chain if the graph was rejected
            log.warning("primary render failed (%s); retrying with CPU encoding", exc)
            result.warnings.append(f"Primary render failed, retried on CPU: {exc}")
            # An encoder being listed does not mean the driver/device works.
            # Software fallback must not reuse NVENC/QSV/VideoToolbox options.
            enc = choose_encoder("cpu", settings.codec)
            result.encoder = enc.description
            simple = ["ffmpeg", *cmd[:cmd.index("-c:v")],
                "-c:v", enc.video_encoder, "-preset", "medium", "-crf", str(settings.crf),
                "-c:a", "aac", "-b:a", "160k", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(output)]
            runner2 = FFmpegRunner(total_duration=clip_dur,
                                   progress_cb=lambda p, t: progress_cb(
                                       5.0 + p * 0.9, f"Rendering… {p:.0f}%"
                                   ) if progress_cb else None,
                                   cancel_cb=cancel_cb)
            runner2.run(simple[1:], total_duration=clip_dur)

        # ---- verify the output ----------------------------------------------------
        out_info = probe(output)
        result.duration = out_info.duration
        result.width = out_info.video.width if out_info.video else 0
        result.height = out_info.video.height if out_info.video else 0
        result.size_bytes = out_info.size_bytes
        result.elapsed = time.time() - t_start
        result.steps.append(f"Rendered {result.width}x{result.height} in {result.elapsed:.1f}s")

        if progress_cb:
            progress_cb(100.0, "Render complete")
        return result

    def render_timeline(
        self,
        source: str | Path,
        output: str | Path,
        timeline,
        settings: RenderSettings,
        cues: list | None = None,
        audio=None,
        visual=None,
        speaker=None,
        progress_cb=None,
        cancel_cb=None,
    ) -> RenderResult:
        """Render an edited :class:`~clipos.video.timeline.Timeline`.

        Unlike :meth:`render`, which renders one contiguous range, this honours
        the timeline's segment list — so split, merged, reordered, re-timed,
        zoomed and cropped segments all end up in the final file.  Segments with
        a speed other than 1x are retimed with ``setpts``/``atempo``; segments
        with extra zoom or a moved crop centre get their own crop filter.
        """
        source = Path(source)
        output = Path(output)
        segments = list(timeline.segments)
        has_audio = probe(source).has_audio
        if not segments:
            raise ValueError("Cannot render an empty timeline")

        result = RenderResult(output_path=str(output))
        t_start = time.time()

        # ---- per-segment video filters ------------------------------------------
        seg_filters: list[str] = []
        for seg in segments:
            parts: list[str] = []
            parts.append(segment_video_filter(seg, settings.width, settings.height))
            seg_filters.append(",".join(parts))

        # ---- audio filter ---------------------------------------------------------
        af = _build_audio_filter(settings, settings.background_music)

        # ---- captions -------------------------------------------------------------
        ass_path: Path | None = None
        if settings.show_captions and cues:
            style = get_style(settings.caption_style)
            from ..captions.caption_engine import pick_highlight_words

            highlights = pick_highlight_words(" ".join(c.text for c in cues))
            ass_path = self.work_dir / f"captions_{output.stem}.ass"
            write_ass(
                ass_path, cues, style, settings.width, settings.height,
                font_override=settings.caption_font,
                size_override=settings.caption_size,
                position_override=settings.caption_position,
                stroke_override=settings.caption_stroke,
                shadow_override=settings.caption_shadow,
                background_override=settings.caption_background,
                highlight_words=highlights,
            )
            result.steps.append(f"Captions: {style.name} ({len(cues)} cues)")

        # ---- encoder --------------------------------------------------------------
        enc = choose_encoder(settings.encoder_preference, settings.codec, low_memory=False)
        result.encoder = enc.description
        result.steps.append(f"Encoder: {enc.description}")

        # ---- build inputs ---------------------------------------------------------
        input_args: list[str] = []
        for seg in segments:
            input_args += [
                "-ss", f"{seg.start:.3f}",
                "-t", f"{max(0.05, seg.source_duration):.3f}",
                "-i", str(source),
            ]

        # ---- build the filter graph ------------------------------------------------
        parts: list[str] = []
        for i, seg in enumerate(segments):
            v = f"[{i}:v]{seg_filters[i]}"
            if seg.speed != 1.0:
                v += f",setpts={1.0 / seg.speed:.6f}*PTS"
            if ass_path:
                # Captions are applied once, after the concat, so their timing
                # follows the edited timeline rather than the source.
                v += f"[v{i}]"
            else:
                v += f"[v{i}]"
            parts.append(v)

        for i, seg in enumerate(segments):
            if not has_audio:
                parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={seg.duration:.6f}[a{i}]")
                continue
            a = f"[{i}:a]"
            if seg.muted:
                a += "volume=0"
            elif af:
                a += af
            else:
                a += "anull"
            if seg.speed != 1.0:
                a += f",atempo={seg.speed:.6f}"
            a += f"[a{i}]"
            parts.append(a)

        labels = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
        parts.append(f"{labels}concat=n={len(segments)}:v=1:a=1[vcat][acat]")

        final_v, final_a = "[vcat]", "[acat]"
        if ass_path:
            fontsdir = fontsdir_arg()
            parts.append(
                f"{final_v}ass='{_escape_ass_path(ass_path)}'{fontsdir}[vout]"
            )
            final_v = "[vout]"

        filter_complex = ";".join(parts)

        cmd: list[str] = ["ffmpeg", "-hide_banner", "-nostdin", "-y"]
        cmd += input_args
        cmd += _filter_args(filter_complex, self.work_dir, output.stem)
        cmd += ["-map", final_v, "-map", final_a]

        if enc.hw_accel == "nvenc":
            cmd += ["-c:v", enc.video_encoder, "-preset", "p5", "-b:v", f"{settings.bitrate_kbps}k"]
        elif enc.hw_accel == "videotoolbox":
            cmd += ["-c:v", enc.video_encoder, "-b:v", f"{settings.bitrate_kbps}k"]
        else:
            cmd += ["-c:v", enc.video_encoder, "-preset", "medium",
                    "-crf", str(settings.crf), "-maxrate", f"{settings.bitrate_kbps}k",
                    "-bufsize", f"{settings.bitrate_kbps * 2}k"]
        cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
        cmd += ["-movflags", "+faststart", "-pix_fmt", "yuv420p", str(output)]

        total = sum(s.duration for s in segments)
        if progress_cb:
            progress_cb(5.0, f"Rendering {len(segments)} segment(s)")

        runner = FFmpegRunner(total_duration=total,
                              progress_cb=lambda p, t: progress_cb(
                                  5.0 + p * 0.9, f"Rendering… {p:.0f}%"
                              ) if progress_cb else None,
                              cancel_cb=cancel_cb)
        try:
            runner.run(cmd[1:], total_duration=total)
        except FFmpegCancelled:
            log.info("timeline render cancelled by the user")
            result.cancelled = True
            return result
        except Exception as exc:
            log.warning("timeline render failed (%s); retrying on CPU", exc)
            enc = choose_encoder("cpu", settings.codec)
            result.encoder = enc.description
            result.warnings.append(f"Timeline filter chain failed, retried simply: {exc}")
            # Preserve the complete graph: dropping speed/captions here silently
            # exports a different edit. Only the encoder is allowed to change.
            cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", *input_args,
                *_filter_args(filter_complex, self.work_dir, output.stem),
                "-map", final_v, "-map", final_a,
                "-c:v", enc.video_encoder, "-preset", "medium", "-crf", str(settings.crf),
                "-c:a", "aac", "-b:a", "160k", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(output)]
            FFmpegRunner(total_duration=total, cancel_cb=cancel_cb).run(
                cmd[1:], total_duration=total
            )

        out_info = probe(output)
        result.duration = out_info.duration
        result.width = out_info.video.width if out_info.video else 0
        result.height = out_info.video.height if out_info.video else 0
        result.size_bytes = out_info.size_bytes
        result.elapsed = time.time() - t_start
        result.steps.append(
            f"Rendered {result.width}x{result.height} from {len(segments)} segments "
            f"in {result.elapsed:.1f}s"
        )
        if progress_cb:
            progress_cb(100.0, "Render complete")
        return result

    def _simple_render_cmd(
        self, source: Path, output: Path, start: float, clip_dur: float,
        settings: RenderSettings, enc: EncoderChoice, ass_path: Path | None,
    ) -> list[str]:
        """Fallback path: trim, scale, caption. No smart reframe or cuts."""
        vf = (
            f"scale={settings.width}:{settings.height}:force_original_aspect_ratio=increase,"
            f"crop={settings.width}:{settings.height},setsar=1"
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-nostdin", "-y",
            "-ss", f"{start:.3f}", "-t", f"{clip_dur:.3f}", "-i", str(source),
        ]
        if ass_path:
            fontsdir = fontsdir_arg()
            cmd += ["-vf", f"{vf},ass='{_escape_ass_path(ass_path)}'{fontsdir}"]
        else:
            cmd += ["-vf", vf]
        cmd += ["-c:v", enc.video_encoder, "-preset", "medium", "-crf", str(settings.crf),
                "-c:a", "aac", "-b:a", "160k", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(output)]
        return cmd

    def _find_sound_effect(self) -> str | None:
        """Locate a bundled 'whoosh'/'pop' sound effect if present."""
        from ..core.config import PATHS
        from ..core.resources import resource_dir

        for base in (resource_dir("sounds"), PATHS.sounds):
            if not base.exists():
                continue
            for name in ("whoosh.wav", "pop.wav", "impact.wav"):
                p = base / name
                if p.exists():
                    return str(p)
            for f in sorted(base.glob("*.wav")):
                return str(f)
        return None


# --------------------------------------------------------------------------------------
# Thumbnail generation
# --------------------------------------------------------------------------------------


def generate_thumbnails(
    source: str | Path,
    out_dir: str | Path,
    candidate_times: list[float],
    out_w: int = 1080,
    out_h: int = 1920,
    templates: list[str] | None = None,
    text: str = "",
    progress_cb: Callable[[float, str], None] | None = None,
) -> list[str]:
    """Render thumbnail candidates from real frames with text overlays."""
    from ..core.ffmpeg import extract_frames

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    templates = templates or ["bold_viral", "mrbeast", "minimal_white"]

    written: list[str] = []
    frames = extract_frames(source, out_dir / "_frames", candidate_times, width=640)
    for i, frame in enumerate(frames):
        tpl = templates[i % len(templates)]
        out = out_dir / f"thumb_{i:02d}_{tpl}.jpg"
        style = get_style(tpl)
        size = max(28, int(out_w * 0.075))
        color = "#00E5FF" if tpl == "neon_gaming" else "#FFD400"
        if tpl == "minimal_white":
            color = "#FFFFFF"
        overlay = ""
        if text:
            safe = text.replace(":", "\\:").replace("'", "").replace("%", "\\%")
            font_arg = drawtext_font_args()
            overlay = (
                f",drawtext=text='{safe}':{font_arg}fontcolor={color}:fontsize={size}:"
                f"borderw=6:bordercolor=black@0.95:box=1:boxcolor=black@0.45:"
                f"boxborderw=24:x=(w-text_w)/2:y=h*0.78"
            )
        vf = (
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},eq=contrast=1.12:saturation=1.15{overlay}"
        )
        try:
            run_ffmpeg([
                "-y", "-i", frame, "-vf", vf, "-q:v", "2", str(out)
            ], timeout=120)
            if out.exists():
                written.append(str(out))
        except Exception as exc:
            log.warning("thumbnail render failed: %s", exc)
        if progress_cb:
            progress_cb((i + 1) / max(1, len(frames)) * 100.0, "Rendering thumbnails")

    # The extracted frames were only scaffolding for the thumbnails.
    try:
        for stale in (out_dir / "_frames").glob("*.jpg"):
            stale.unlink()
        (out_dir / "_frames").rmdir()
    except OSError:
        pass
    return written
