"""v5.1.8 regression coverage for timeline edit recipes and explicit image failures."""
from __future__ import annotations

import asyncio
import subprocess

import pytest

from app.config import ffmpeg_binary
from app.services import images, render
from app.services.utils import probe


def test_audio_speed_filter_handles_browser_speed_range():
    assert render._atempo_filter(0.25) == "atempo=0.500,atempo=0.500"
    assert render._atempo_filter(1.25) == "atempo=1.250"
    assert render._atempo_filter(4.0) == "atempo=2.000,atempo=2.000"


def test_speed_treated_multi_region_timeline_export_is_playable(tmp_path):
    source = tmp_path / "source-speed.mp4"
    output = tmp_path / "speed-export.mp4"
    command = [
        ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000",
        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ]
    encoders = subprocess.run([ffmpeg_binary(), "-hide_banner", "-encoders"], capture_output=True, text=True)
    if "libx264" not in encoders.stdout:
        pytest.skip("Local FFmpeg does not include the libx264 encoder")
    subprocess.run(command, check=True, capture_output=True)

    asyncio.run(render.render_timeline({
        "aspect": "9:16", "resolution": "720p", "caption_style": {"preset": "none"},
        "tracks": {
            "video": [{
                "clip_id": "speed-edit", "path": str(source), "sourceStart": 0,
                "sourceDuration": 1, "duration": 0.8, "label": "Speed test",
                "regions": [
                    {"x": 0, "y": 0, "w": 1, "h": 0.42},
                    {"x": 0, "y": 0.42, "w": 1, "h": 0.58},
                ],
                "region_layout": "top-player-bottom-game",
                "effects": {"speed": 1.25, "brightness": 0.02, "contrast": 1.05, "saturation": 1.08},
            }],
            "captions": [], "stickers": [], "audio": [],
        },
    }, str(output)))

    info = probe(output)
    assert (info["video_codec"], info["audio_codec"]) == ("h264", "aac")
    assert (info["width"], info["height"]) == (720, 1280)
    assert info["duration"] == pytest.approx(0.8, abs=0.16)


def test_timeline_export_preserves_short_source_duration(tmp_path, monkeypatch):
    source = tmp_path / "short-source.mp4"
    source.write_bytes(b"synthetic media")
    captured: dict = {}
    monkeypatch.setattr(render, "probe", lambda _path: {"width": 640, "height": 360, "audio_codec": None})

    async def capture_encode(args, duration, on_progress=None):
        captured["args"] = args
        captured["duration"] = duration

    monkeypatch.setattr(render, "encode", capture_encode)
    monkeypatch.setattr(render, "_validate_mp4", lambda _path: None)
    asyncio.run(render.render_timeline({
        "aspect": "9:16", "resolution": "720p",
        "tracks": {
            "video": [{
                "path": str(source), "sourceStart": 0, "sourceDuration": 0.05,
                "duration": 0.2, "crop_path": [[0.0, 0.2], [0.05, 0.8]],
                "effects": {"speed": 0.25},
            }],
            "captions": [], "stickers": [], "audio": [],
        },
    }, str(tmp_path / "short-export.mp4")))

    graph = captured["args"][captured["args"].index("-filter_complex") + 1]
    assert captured["duration"] == pytest.approx(0.2)
    assert "trim=start=0.000:duration=0.050" in graph
    assert "if(lt(t,0.050000)" in graph
    assert "setpts=(PTS-STARTPTS)/0.250" in graph


def test_timeline_export_uses_explicit_caption_tracks_not_video_labels(tmp_path, monkeypatch):
    source = tmp_path / "caption-source.mp4"
    source.write_bytes(b"synthetic media")
    captured: dict = {}
    monkeypatch.setattr(render, "probe", lambda _path: {"width": 640, "height": 360, "audio_codec": None})

    def capture_write_ass(captions, *_args, **_kwargs):
        captured["captions"] = [dict(caption) for caption in captions]
        return str(tmp_path / "captions.ass")

    async def capture_encode(args, duration, on_progress=None):
        captured["args"] = args
        captured["duration"] = duration

    monkeypatch.setattr(render, "write_ass", capture_write_ass)
    monkeypatch.setattr(render, "encode", capture_encode)
    monkeypatch.setattr(render, "_validate_mp4", lambda _path: None)
    asyncio.run(render.render_timeline({
        "aspect": "9:16", "resolution": "720p", "caption_style": {"preset": "hype"},
        "tracks": {
            "video": [{
                "clip_id": "auto-edit-clip", "path": str(source), "sourceStart": 0,
                "duration": 2, "label": "Generated clip name must not appear",
            }],
            "captions": [
                {"text": "Spoken caption stays", "start": 0.2, "end": 0.8, "kind": "caption"},
                {"text": "Intentional title track stays", "start": 0, "end": 1, "kind": "title"},
            ],
            "stickers": [], "audio": [],
        },
    }, str(tmp_path / "caption-export.mp4")))

    assert [caption["text"] for caption in captured["captions"]] == [
        "Spoken caption stays", "Intentional title track stays",
    ]
    assert captured["captions"][1]["kind"] == "title"
    graph = captured["args"][captured["args"].index("-filter_complex") + 1]
    assert "subtitles=" in graph


def test_timeline_export_preserves_composition_speed_effects_and_timed_tracks(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    music = tmp_path / "music.wav"
    sfx = tmp_path / "whoosh.wav"
    sticker = tmp_path / "sticker.png"
    for path in (source, music, sfx, sticker):
        path.write_bytes(b"synthetic media")

    captured: dict = {}
    info = {"width": 640, "height": 360, "audio_codec": "aac"}
    monkeypatch.setattr(render, "probe", lambda _path: dict(info))

    async def capture_encode(args, duration, on_progress=None):
        captured["args"] = args
        captured["duration"] = duration

    monkeypatch.setattr(render, "encode", capture_encode)
    monkeypatch.setattr(render, "_validate_mp4", lambda _path: None)

    timeline = {
        "aspect": "9:16", "resolution": "720p", "caption_style": {"preset": "none"},
        "tracks": {
            "video": [{
                "clip_id": "edit-clip", "path": str(source), "sourceStart": 1.0,
                "sourceDuration": 2.0, "duration": 1.6, "label": "Player above gameplay",
                "regions": [
                    {"x": 0, "y": 0, "w": 1, "h": 0.42},
                    {"x": 0, "y": 0.42, "w": 1, "h": 0.58},
                ],
                "region_layout": "top-player-bottom-game",
                "effects": {"speed": 1.25, "brightness": 0.02, "contrast": 1.1, "saturation": 1.2},
            }],
            "captions": [], "stickers": [{
                "path": str(sticker), "start": 0.1, "end": 0.8,
                "x": 0.7, "y": 0.15, "scale": 0.2,
            }],
            "audio": [
                {"path": str(music), "start": 0, "end": 1.6, "volume": 0.18, "kind": "music"},
                {"path": str(sfx), "start": 0.3, "end": 0.7, "volume": 0.5, "kind": "sfx"},
            ],
        },
    }
    asyncio.run(render.render_timeline(timeline, str(tmp_path / "export.mp4")))

    args = captured["args"]
    graph = args[args.index("-filter_complex") + 1]
    assert captured["duration"] == pytest.approx(1.6)
    assert "trim=start=1.000:duration=2.000" in graph
    assert "setpts=(PTS-STARTPTS)/1.250" in graph
    assert "vstack=inputs=2" in graph
    assert "scale=720:538" in graph and "scale=720:742" in graph
    assert "eq=brightness=0.020:contrast=1.100:saturation=1.200" in graph
    assert "atempo=1.250" in graph
    assert "adelay=300|300" in graph
    assert "scale=144:-1" in graph
    assert "x='0.700*(W-w)':y='0.150*(H-h)'" in graph

    music_index = args.index(str(music))
    sfx_index = args.index(str(sfx))
    assert args[music_index - 3:music_index] == ["-stream_loop", "-1", "-i"]
    assert args[sfx_index - 1] == "-i"


def test_auto_image_generation_reports_missing_models_instead_of_fallback(monkeypatch):
    monkeypatch.setattr(images.db, "get_setting", lambda _key, default="": default)

    def fake_env(key, default=""):
        return "1" if key == "DISABLE_CLOUD_FEATURES" else default

    monkeypatch.setattr(images, "env", fake_env)
    monkeypatch.setattr(images, "comfy_reachable", lambda: False)
    monkeypatch.setattr(images, "local_art", lambda *_args, **_kwargs: pytest.fail("auto must not use decorative art"))

    with pytest.raises(RuntimeError, match="No AI image model is ready"):
        images.generate_variations("a detailed prompt", provider="auto", count=3)


def test_image_variations_return_partial_success_and_explain_failed_options(monkeypatch):
    calls: list[int] = []

    def fake_generate(_prompt, provider, _aspect, _reference, _negative, *, variation, variation_count):
        calls.append(variation)
        if variation == 1:
            raise RuntimeError("temporary provider failure")
        path = f"/tmp/generated-{variation}.png"
        return {"path": path, "url": path, "provider": provider}

    monkeypatch.setattr(images, "generate", fake_generate)
    result = images.generate_variations("subject", provider="nano-banana", count=3)
    assert calls == [0, 1, 2]
    assert [image["path"] for image in result["images"]] == ["/tmp/generated-0.png", "/tmp/generated-2.png"]
    assert result["warnings"] == ["Option 2 failed: temporary provider failure"]


def test_image_generation_reports_provider_reason_when_all_options_fail(monkeypatch):
    def fail_generate(*_args, **_kwargs):
        raise RuntimeError("provider rejected the request")

    monkeypatch.setattr(images, "generate", fail_generate)
    with pytest.raises(RuntimeError, match="Option 1 failed: provider rejected the request"):
        images.generate_variations("subject", provider="nano-banana", count=2)
