"""End-to-end checks for accurate, fast source seeking and playable MP4 output."""
from __future__ import annotations

import asyncio
import math
import re
import struct
import subprocess
from pathlib import Path

import pytest

from app.config import ffmpeg_binary
from app.services import render
from app.services.utils import _probe_from_text, probe


def _frame_rgb_means(ffmpeg: str, path: Path, at: float = 0) -> tuple[float, float, float]:
    frame = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{at:.3f}", "-i", str(path),
        "-frames:v", "1", "-vf", "scale=8:8", "-pix_fmt", "rgb24",
        "-f", "rawvideo", "pipe:1",
    ], check=True, capture_output=True).stdout
    assert len(frame) == 8 * 8 * 3
    return tuple(sum(frame[channel::3]) / 64 for channel in range(3))


def _dominant_frequency(ffmpeg: str, path: Path, at: float = 0) -> int:
    pcm = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1",
    ], check=True, capture_output=True).stdout
    samples = struct.unpack(f"<{len(pcm) // 4}f", pcm)
    start = int((at + 0.15) * 48000)
    segment = samples[start:start + int(0.6 * 48000)]
    powers = {}
    for frequency in (440, 660, 880):
        real = sum(sample * math.cos(2 * math.pi * frequency * index / 48000)
                   for index, sample in enumerate(segment))
        imag = sum(sample * math.sin(2 * math.pi * frequency * index / 48000)
                   for index, sample in enumerate(segment))
        powers[frequency] = real * real + imag * imag
    return max(powers, key=powers.get)


def _assert_full_decode(ffmpeg: str, path: Path) -> None:
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "null", "-",
    ], check=True, capture_output=True)


def test_source_resolution_h264_signals_a_valid_level_and_decodes(tmp_path: Path, monkeypatch):
    ffmpeg = ffmpeg_binary()
    available = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
    bitstream_filters = subprocess.run([ffmpeg, "-hide_banner", "-bsfs"], capture_output=True, text=True)
    if "libx264" not in available.stdout or "trace_headers" not in bitstream_filters.stdout:
        pytest.skip("Local FFmpeg needs libx264 and trace_headers for H.264 level verification")

    source, output = tmp_path / "uhd-source.mp4", tmp_path / "uhd-render.mp4"
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=3840x2160:r=30:d=0.6",
        "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True)
    monkeypatch.setattr(render, "_ENCODER", "libx264")
    monkeypatch.setenv("AIFREECLIP_ENCODER", "libx264")
    asyncio.run(render.render_clip(str(source), 0, 0.5, str(output), {
        "aspect": "source", "resolution": "source", "sfx": [],
    }))

    info = probe(output)
    assert info["video_codec"] == "h264" and info["audio_codec"] == "aac"
    assert (info["width"], info["height"]) == (3840, 2160)
    _assert_full_decode(ffmpeg, output)
    trace = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "trace", "-i", str(output),
        "-c:v", "copy", "-bsf:v", "trace_headers", "-f", "null", "-",
    ], check=True, capture_output=True, text=True).stderr
    level = re.search(r"level_idc\s+[01]+\s*=\s*(\d+)", trace)
    assert level is not None, "H.264 sequence parameter set should include level_idc"
    assert int(level.group(1)) >= 51, "3840x2160 at 30 fps needs H.264 level 5.1 or higher"


def test_seeked_clip_and_timeline_exports_play_selected_video_and_aac_audio(tmp_path: Path, monkeypatch):
    ffmpeg = ffmpeg_binary()
    available = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
    if "libx264" not in available.stdout:
        pytest.skip("Local FFmpeg does not include the libx264 encoder")

    source = tmp_path / "color-segments.mp4"
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=320x180:r=10:d=2",
        "-f", "lavfi", "-i", "color=c=green:s=320x180:r=10:d=2",
        "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=10:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=2",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v];[3:a][4:a][5:a]concat=n=3:v=0:a=1[a]",
        "-map", "[v]", "-map", "[a]", "-t", "6", "-output_ts_offset", "2",
        "-c:v", "libx264", "-preset", "ultrafast", "-g", "100", "-keyint_min", "100",
        "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ], check=True, capture_output=True)
    monkeypatch.setattr(render, "_ENCODER", "libx264")
    monkeypatch.setenv("AIFREECLIP_ENCODER", "libx264")

    clip_output = tmp_path / "seeked-clip.mp4"
    asyncio.run(render.render_clip(str(source), 4.35, 5.35, str(clip_output), {
        "aspect": "source", "resolution": "source", "blur_background": False, "sfx": [],
    }))

    timeline_output = tmp_path / "seeked-timeline.mp4"
    asyncio.run(render.render_timeline({
        "aspect": "source", "resolution": "source",
        "tracks": {
            "video": [
                {
                    "path": str(source), "sourceStart": 0.35, "sourceDuration": 1,
                    "duration": 1, "effects": {"speed": 1},
                },
                {
                    "path": str(source), "sourceStart": 4.35, "sourceDuration": 1,
                    "duration": 1, "effects": {"speed": 1},
                },
            ],
            "audio": [], "stickers": [],
        },
    }, str(timeline_output)))

    for output, duration in ((clip_output, 1.0), (timeline_output, 2.0)):
        _assert_full_decode(ffmpeg, output)
        info = probe(output)
        assert info["video_codec"] == "h264"
        assert info["audio_codec"] == "aac"
        assert "mp4" in info["format"].split(",")
        assert (info["width"], info["height"]) == (320, 180)
        assert info["duration"] == pytest.approx(duration, abs=0.15)

    red, green, blue = _frame_rgb_means(ffmpeg, clip_output)
    assert blue > red + 80 and blue > green + 60, (red, green, blue)
    assert _dominant_frequency(ffmpeg, clip_output) == 880

    red, _green, blue = _frame_rgb_means(ffmpeg, timeline_output, 0.2)
    assert red > blue + 80, (red, blue)
    assert _dominant_frequency(ffmpeg, timeline_output, 0) == 440
    red, _green, blue = _frame_rgb_means(ffmpeg, timeline_output, 1.2)
    assert blue > red + 80, (red, blue)
    assert _dominant_frequency(ffmpeg, timeline_output, 1) == 880


def test_seeked_clip_and_timeline_preserve_absolute_moving_crop_timestamps(tmp_path: Path, monkeypatch):
    ffmpeg = ffmpeg_binary()
    available = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
    if "libx264" not in available.stdout:
        pytest.skip("Local FFmpeg does not include the libx264 encoder")

    source = tmp_path / "red-blue-halves.mp4"
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=320x180:r=10:d=6",
        "-vf", "drawbox=x=160:y=0:w=160:h=180:color=blue:t=fill",
        "-an", "-c:v", "libx264", "-preset", "ultrafast", "-g", "100",
        "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True)
    monkeypatch.setattr(render, "_ENCODER", "libx264")
    monkeypatch.setenv("AIFREECLIP_ENCODER", "libx264")
    crop_path = [[0, 0.25], [4.5, 0.25], [4.6, 0.75], [6, 0.75]]

    clip_output = tmp_path / "moving-crop-clip.mp4"
    asyncio.run(render.render_clip(str(source), 4.35, 5.35, str(clip_output), {
        "aspect": "9:16", "resolution": "source", "crop_path": crop_path, "sfx": [],
    }))
    timeline_output = tmp_path / "moving-crop-timeline.mp4"
    asyncio.run(render.render_timeline({
        "aspect": "9:16", "resolution": "source",
        "tracks": {"video": [{
            "path": str(source), "sourceStart": 4.35, "sourceDuration": 1,
            "duration": 1, "crop_path": crop_path, "effects": {"speed": 1},
        }], "audio": [], "stickers": []},
    }, str(timeline_output)))

    for output in (clip_output, timeline_output):
        _assert_full_decode(ffmpeg, output)
        first_red, _first_green, first_blue = _frame_rgb_means(ffmpeg, output, 0)
        last_red, _last_green, last_blue = _frame_rgb_means(ffmpeg, output, 0.8)
        assert first_red > first_blue + 80, (first_red, first_blue)
        assert last_blue > last_red + 80, (last_red, last_blue)


def test_auto_hardware_encoder_failure_retries_software_for_playable_output(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"synthetic input")
    output = tmp_path / "fallback.mp4"
    calls: list[str] = []
    monkeypatch.setattr(render, "_ENCODER", "h264_videotoolbox")
    monkeypatch.delenv("AIFREECLIP_ENCODER", raising=False)
    monkeypatch.delenv("FORCE_SOFTWARE_ENCODER", raising=False)
    monkeypatch.setattr(render, "probe", lambda _path: {
        "video_codec": "h264", "audio_codec": "aac", "width": 640, "height": 360,
        "duration": 1.0, "format": "mov,mp4,m4a,3gp,3g2,mj2",
    })
    monkeypatch.setattr(render, "_validate_mp4", lambda _path: None)

    async def fake_encode(args, _duration, _on_progress=None):
        encoder = args[args.index("-c:v") + 1]
        calls.append(encoder)
        if encoder == "h264_videotoolbox":
            raise RuntimeError("ffmpeg failed: simulated VideoToolbox device failure")
        Path(args[-1]).write_bytes(b"software output")

    monkeypatch.setattr(render, "encode", fake_encode)
    rendered = asyncio.run(render.render_clip(str(source), 0, 1, str(output), {"sfx": []}))

    assert rendered == str(output)
    assert calls == ["h264_videotoolbox", "libx264"]
    assert output.read_bytes() == b"software output"
    assert render._ENCODER == "libx264"


def test_automatic_hardware_output_validation_failure_retries_software(tmp_path: Path, monkeypatch):
    output = tmp_path / "bad-hardware.mp4"
    calls: list[str] = []
    validation_calls = 0
    monkeypatch.setattr(render, "_ENCODER", "h264_nvenc")
    monkeypatch.delenv("AIFREECLIP_ENCODER", raising=False)
    monkeypatch.delenv("FORCE_SOFTWARE_ENCODER", raising=False)

    async def fake_encode(args, _duration, _on_progress=None):
        calls.append(args[args.index("-c:v") + 1])
        Path(args[-1]).write_bytes(b"encoded output")

    def validate(_path):
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 1:
            raise render._HardwareCompatibilityError("simulated incompatible hardware stream")

    monkeypatch.setattr(render, "encode", fake_encode)
    monkeypatch.setattr(render, "_validate_mp4", validate)
    asyncio.run(render._encode_validated_mp4(
        ["ffmpeg", "-c:v", "h264_nvenc", "-c:a", "aac", str(output)],
        1.0, encoder="h264_nvenc",
    ))

    assert calls == ["h264_nvenc", "libx264"]
    assert validation_calls == 2
    assert output.read_bytes() == b"encoded output"
    assert render._ENCODER == "libx264"


def test_explicit_hardware_encoder_choice_is_not_silently_overridden(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"synthetic input")
    output = tmp_path / "explicit-failure.mp4"
    calls: list[str] = []
    monkeypatch.setattr(render, "_ENCODER", "h264_videotoolbox")
    monkeypatch.setenv("AIFREECLIP_ENCODER", "h264_videotoolbox")
    monkeypatch.delenv("FORCE_SOFTWARE_ENCODER", raising=False)
    monkeypatch.setattr(render, "probe", lambda _path: {"audio_codec": "aac", "width": 640, "height": 360})

    async def fail_encode(args, _duration, _on_progress=None):
        calls.append(args[args.index("-c:v") + 1])
        raise RuntimeError("forced encoder failure")

    monkeypatch.setattr(render, "encode", fail_encode)
    with pytest.raises(RuntimeError, match="forced encoder failure"):
        asyncio.run(render.render_clip(str(source), 0, 1, str(output), {"sfx": []}))
    assert calls == ["h264_videotoolbox"]
    assert not output.exists()


def test_ffmpeg_text_probe_reports_mp4_container():
    info = _probe_from_text(
        """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'rendered.mp4':
  Duration: 00:00:01.00, start: 0.000000, bitrate: 500 kb/s
  Stream #0:0: Video: h264 (High), yuv420p, 640x360, 30 fps
  Stream #0:1: Audio: aac (LC), 48000 Hz, stereo
"""
    )
    assert info["video_codec"] == "h264"
    assert info["audio_codec"] == "aac"
    assert "mp4" in info["format"].split(",")


def test_mp4_validation_requires_video_audio_and_nonzero_duration(tmp_path: Path, monkeypatch):
    output = tmp_path / "unplayable.mp4"
    output.write_bytes(b"x" * 256)
    base = {
        "video_codec": "h264", "audio_codec": "aac", "width": 640, "height": 360,
        "duration": 1.0, "format": "mov,mp4,m4a,3gp,3g2,mj2",
    }
    monkeypatch.setattr(render, "probe", lambda _path: dict(base))
    render._validate_mp4(output)

    base["audio_codec"] = ""
    with pytest.raises(RuntimeError, match="AAC audio"):
        render._validate_mp4(output)
    base["audio_codec"] = "aac"
    base["duration"] = 0
    with pytest.raises(RuntimeError, match="duration"):
        render._validate_mp4(output)
    base["duration"] = 1.0
    base["format"] = "matroska,webm"
    with pytest.raises(render._HardwareCompatibilityError, match="not a verified MP4"):
        render._validate_mp4(output)
