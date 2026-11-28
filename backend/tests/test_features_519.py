"""Regression tests for caption editing, seam-aware placement, and Auto Edit reuse."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.db import db
from app.schemas import AutoEditRequest
from app.services import asr, render


def test_caption_transcription_requires_installed_offline_whisper_weights(tmp_path, monkeypatch):
    models_root = tmp_path / "models"
    monkeypatch.setattr(db, "get_setting", lambda key, default="": {
        "models_folder": str(models_root), "whisper_model": "small", "WHISPER_MODEL_PATH": "",
    }.get(key, default))
    monkeypatch.setenv("WHISPER_MODEL", "small")
    monkeypatch.delenv("WHISPER_MODEL_PATH", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)

    with pytest.raises(RuntimeError, match="not installed locally"):
        asr._resolve_whisper_model()


def test_write_ass_honours_custom_caption_style_and_drag_position(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "CACHE", tmp_path)
    path = Path(render.write_ass(
        [{"text": "Hello world", "start": 1, "end": 2, "kind": "caption", "x": 0.4, "y": 0.6, "scale": 1.5}],
        {
            "preset": "minimal", "font_family": "Georgia", "font_size": 48,
            "primary_color": "#ffcc00", "outline_color": "#112233",
            "background_color": "#000000", "background_opacity": 0.4,
            "bold": False, "italic": True, "uppercase": True, "outline": 2, "shadow": 1,
            "spacing": 1.5, "position": "custom",
        },
    ))
    content = path.read_text(encoding="utf-8")

    assert "Style: Default,Georgia,48,&H0000CCFF" in content
    assert "&H00332211" in content
    assert "&H99000000" in content
    default_style = next(line for line in content.splitlines() if line.startswith("Style: Default,"))
    style_values = default_style.removeprefix("Style: Default,").split(",")
    assert style_values[6:8] == ["0", "-1"]
    assert style_values[12] == "1.5"
    assert ",&H99000000,0,-1,0,0,100,100,1.5,0,3,2.0,1.0,5," in content
    assert r"\an5\pos(432,1152)" in content
    assert r"\fscx150\fscy150" in content
    assert "HELLO WORLD" in content


def test_auto_caption_style_uses_split_seam_instead_of_stale_custom_coordinates():
    resolved = render._caption_style_for_layout(
        {"preset": "hype", "position": "auto", "x": 0.2, "y": 0.3},
        "top-game-bottom-player", 0.58,
    )
    assert resolved["preset"] == "hype" and resolved["position"] == "custom"
    assert resolved["x"] == pytest.approx(0.5) and resolved["y"] == pytest.approx(0.525)
    assert render._caption_style_for_layout(
        {"position": "auto", "x": 0.2, "y": 0.3}, "full",
    ) == {"position": "bottom"}


def test_auto_caption_position_tracks_player_gameplay_split_seam():
    assert render._split_caption_anchor("top-game-bottom-player") == pytest.approx((0.5, 0.525))
    assert render._split_caption_anchor("top-player-bottom-game") == pytest.approx((0.5, 0.365))
    assert render._split_caption_anchor("side-by-side") == pytest.approx((0.565, 0.5))
    assert render._split_caption_anchor("full") is None

    captions = render._timeline_caption_positions(
        [
            {"text": "seam caption", "start": 1, "end": 2},
            {"text": "manual caption", "start": 1, "end": 2, "x": 0.2, "y": 0.3},
        ],
        [{
            "clip_id": "short-1", "duration": 4,
            "region_layout": "top-game-bottom-player", "split_ratio": 0.58,
        }],
        {"position": "auto"},
    )
    assert captions[0]["x"] == pytest.approx(0.5) and captions[0]["y"] == pytest.approx(0.525)
    assert captions[1]["x"] == 0.2 and captions[1]["y"] == 0.3


def test_timeline_export_passes_seam_anchored_captions_to_ass(tmp_path, monkeypatch):
    source = tmp_path / "split-source.mp4"
    source.write_bytes(b"synthetic media")
    captured: dict = {}
    monkeypatch.setattr(render, "probe", lambda _path: {"width": 640, "height": 360, "audio_codec": None})

    def capture_ass(captions, *_args, **_kwargs):
        captured["captions"] = [dict(caption) for caption in captions]
        return str(tmp_path / "captions.ass")

    async def capture_encode(_args, _duration, on_progress=None):
        return None

    monkeypatch.setattr(render, "write_ass", capture_ass)
    monkeypatch.setattr(render, "encode", capture_encode)
    monkeypatch.setattr(render, "_validate_mp4", lambda _path: None)
    asyncio.run(render.render_timeline({
        "aspect": "9:16", "resolution": "720p",
        "caption_style": {"preset": "hype", "position": "auto"},
        "tracks": {
            "video": [{
                "clip_id": "split-short", "path": str(source), "sourceStart": 0,
                "duration": 3, "region_layout": "top-game-bottom-player", "split_ratio": 0.58,
            }],
            "captions": [{"text": "Keep it above the seam", "start": 0.2, "end": 1.1}],
            "stickers": [], "audio": [],
        },
    }, str(tmp_path / "split-export.mp4")))

    assert captured["captions"][0]["x"] == pytest.approx(0.5)
    assert captured["captions"][0]["y"] == pytest.approx(0.525)


def test_auto_edit_accepts_reused_caption_style_settings():
    request = AutoEditRequest(
        clip_ids=["clip-1"],
        style="hype",
        reuse_settings={
            "caption_style": {
                "preset": "minimal", "template_id": "editorial-italic-violet", "font_family": "Georgia", "font_size": 44,
                "position": "top", "primary_color": "#fefefe", "italic": True, "spacing": 1.25,
            },
        },
    )
    assert request.reuse_settings is not None
    assert request.reuse_settings.caption_style.font_family == "Georgia"
    assert request.reuse_settings.caption_style.font_size == 44
    assert request.reuse_settings.caption_style.template_id == "editorial-italic-violet"
    assert request.reuse_settings.caption_style.italic is True
    assert request.reuse_settings.caption_style.spacing == pytest.approx(1.25)
