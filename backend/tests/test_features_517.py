"""v5.1.7–v5.1.8 regressions for source-quality rendering and editable Auto Edit."""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from types import ModuleType
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import ffmpeg_binary
from app.db import db, dumps, now, uid
import app.main as main_module
from app.main import app
from app.schemas import AutoEditRequest, ExportAllRequest, ExportRequest, RenderRequest
from app.services import asr, llm, render, scoring, tts, vision
from app.services.utils import probe

client = TestClient(app)
HEADERS = {"X-AI-Clipper-Token": "aifreeclip-test-token"}


def _wait_for_job(job_id: str) -> dict:
    job = None
    for _ in range(200):
        response = client.get(f"/api/jobs/{job_id}", headers=HEADERS)
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"done", "error", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Job did not finish: {job}")


def test_render_request_defaults_to_source_quality_and_preserves_even_source_size():
    assert AutoEditRequest(clip_ids=["clip"]).resolution == "source"
    assert RenderRequest().resolution == "source"
    assert ExportRequest().resolution == "source"
    assert ExportAllRequest(clip_ids=["clip"]).resolution == "source"
    assert render.resolution_for("source", "source", (1920, 1080)) == (1920, 1080)
    assert render.resolution_for("16:9", "source", (640, 360)) == (640, 360)
    assert render.resolution_for("9:16", "source", (3840, 2160)) == (1214, 2160)


def test_composition_filter_graph_covers_stacks_and_picture_in_picture():
    regions = [
        {"x": 0, "y": 0, "w": 1, "h": 0.58},
        {"x": 0, "y": 0.58, "w": 1, "h": 0.42},
    ]
    stacked = render.build_clip_args(
        "/tmp/source.mp4", 1, 4, "/tmp/stacked.mp4", {
            "aspect": "9:16", "resolution": "720p", "regions": regions,
            "region_layout": "top-game-bottom-player", "sfx": [],
            "caption_style": {"preset": "none"},
        },
    )
    graph = stacked[stacked.index("-filter_complex") + 1]
    assert "split=2[clip_src0][clip_src1]" in graph
    assert "vstack=inputs=2[clip_composite]" in graph
    assert "scale=720:742" in graph and "scale=720:538" in graph

    for layout, operator in (
        ("top-player-bottom-game", "vstack=inputs=2[clip_composite]"),
        ("side-by-side", "hstack=inputs=2[clip_composite]"),
    ):
        args = render.build_clip_args(
            "/tmp/source.mp4", 1, 4, "/tmp/layout.mp4", {
                "aspect": "9:16", "resolution": "720p", "regions": regions,
                "region_layout": layout, "sfx": [],
                "caption_style": {"preset": "none"},
            },
        )
        assert operator in args[args.index("-filter_complex") + 1]

    pip = render.build_clip_args(
        "/tmp/source.mp4", 1, 4, "/tmp/pip.mp4", {
            "aspect": "9:16", "resolution": "720p", "regions": [
                {"x": 0, "y": 0, "w": 1, "h": 1},
                {"x": 0.05, "y": 0.05, "w": 0.35, "h": 0.35},
            ],
            "region_layout": "square-player-full-game", "sfx": [],
            "caption_style": {"preset": "none"},
        },
    )
    pip_graph = pip[pip.index("-filter_complex") + 1]
    assert "split=3" in pip_graph
    assert "overlay=x=28:y=28" in pip_graph
    assert "drawbox=x=28:y=28" in pip_graph


def test_scoring_preserves_the_explicitly_selected_focus_and_layout():
    first = {"x": 0.05, "y": 0.08, "w": 0.7, "h": 0.45}
    selected = {"x": 0.18, "y": 0.25, "w": 0.46, "h": 0.62}
    candidate = scoring.propose(
        [{"id": "media", "title": "Gameplay", "duration": 40}],
        {"media": {"segments": []}}, {"media": {"timeline": []}},
        count=1, min_duration=5, max_duration=10,
        regions={"media": [first, selected]},
        layouts={"media": "top-player-bottom-game"},
        focus_regions={"media": selected},
    )[0]
    assert candidate.region == selected
    assert candidate.regions == [first, selected]
    assert candidate.region_layout == "top-player-bottom-game"


def test_title_card_is_kept_when_speech_captions_are_disabled(tmp_path):
    args = render.build_clip_args(
        "/tmp/source.mp4", 2, 8, "/tmp/title.mp4", {
            "aspect": "9:16", "resolution": "720p", "title": "The final moment",
            "captions": [{"text": "speech should be hidden", "start": 2.2, "end": 2.8}],
            "caption_style": {"preset": "none"}, "sfx": [],
        },
    )
    graph = args[args.index("-filter_complex") + 1]
    assert "subtitles=" in graph
    ass_path = render.write_ass(
        [{"text": "The final moment", "start": 0, "end": 2, "kind": "title"}],
        {"preset": "none"},
    )
    ass = Path(ass_path).read_text(encoding="utf-8")
    assert "Style: Title," in ass
    assert "Dialogue: 0,00:00:00.0,00:00:02.0,Title,," in ass
    assert "The final moment" in ass
    assert "\\an8" in ass


def test_multi_region_render_is_a_playable_h264_mp4(tmp_path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "stacked.mp4"
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
    asyncio.run(render.render_clip(
        str(source), 0, 1, str(output), {
            "aspect": "9:16", "resolution": "720p",
            "regions": [
                {"x": 0, "y": 0, "w": 1, "h": 0.58},
                {"x": 0, "y": 0.58, "w": 1, "h": 0.42},
            ],
            "region_layout": "top-game-bottom-player", "sfx": [],
            "caption_style": {"preset": "none"},
        },
    ))
    info = probe(output)
    assert (info["video_codec"], info["audio_codec"]) == ("h264", "aac")
    assert (info["width"], info["height"]) == (720, 1280)

    pip_output = tmp_path / "picture-in-picture.mp4"
    asyncio.run(render.render_clip(
        str(source), 0, 1, str(pip_output), {
            "aspect": "9:16", "resolution": "720p",
            "regions": [
                {"x": 0, "y": 0, "w": 1, "h": 1},
                {"x": 0.05, "y": 0.05, "w": 0.35, "h": 0.35},
            ],
            "region_layout": "square-player-full-game", "sfx": [],
            "caption_style": {"preset": "none"},
        },
    ))
    pip_info = probe(pip_output)
    assert (pip_info["video_codec"], pip_info["audio_codec"]) == ("h264", "aac")
    assert (pip_info["width"], pip_info["height"]) == (720, 1280)


def test_timeline_export_uses_source_quality_and_renders_title_cards(tmp_path):
    source = tmp_path / "timeline-source.mp4"
    output = tmp_path / "timeline.mp4"
    command = [
        ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ]
    encoders = subprocess.run([ffmpeg_binary(), "-hide_banner", "-encoders"], capture_output=True, text=True)
    if "libx264" not in encoders.stdout:
        pytest.skip("Local FFmpeg does not include the libx264 encoder")
    subprocess.run(command, check=True, capture_output=True)

    asyncio.run(render.render_timeline({
        "aspect": "9:16", "resolution": "source", "caption_style": {"preset": "none"},
        "tracks": {
            "video": [{
                "clip_id": "synthetic-clip", "path": str(source), "sourceStart": 0,
                "duration": 1, "label": "A test title card",
                "regions": [
                    {"x": 0, "y": 0, "w": 1, "h": 0.58},
                    {"x": 0, "y": 0.58, "w": 1, "h": 0.42},
                ],
                "region_layout": "top-game-bottom-player",
            }],
            "captions": [{
                "text": "A test title card", "start": 0, "end": 1, "kind": "title",
            }], "stickers": [], "audio": [],
        },
    }, str(output)))

    info = probe(output)
    assert (info["video_codec"], info["audio_codec"]) == ("h264", "aac")
    # 9:16 source-quality output fits inside the 640x360 source without upscaling.
    assert (info["width"], info["height"]) == (202, 360)


def test_batch_export_respects_per_clip_settings_and_requested_quality(tmp_path, monkeypatch):
    source = tmp_path / "batch-source.mp4"
    source.write_bytes(b"synthetic source")
    media_id, clip_id = uid("m517_batch_"), uid("c517_batch_")
    db.insert("media", {
        "id": media_id, "title": "Batch source", "path": str(source), "source_url": None,
        "duration": 10, "width": 640, "height": 360, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": media_id,
        "start": 1, "end": 3, "score": 80, "title": "Batch quality", "reason": "",
        "status": "proposed", "output": None, "metadata": dumps({}), "created_at": now(),
    })
    captured: dict = {}
    async def fake_render(_media, _start, _end, output, options, on_progress=None):
        captured.update(options)
        return output

    monkeypatch.setattr(render, "render_clip", fake_render)
    monkeypatch.setattr(render, "export_path", lambda name: str(tmp_path / f"{name}.mp4"))
    monkeypatch.setattr(main_module, "configured_watermark_path", lambda: None)
    monkeypatch.setattr(main_module, "hardware_info", lambda: {"workers": 1, "encoder": "test"})
    job_id = None
    try:
        custom_regions = [
            {"x": 0, "y": 0, "w": 1, "h": 0.6},
            {"x": 0, "y": 0.6, "w": 1, "h": 0.4},
        ]
        response = client.post("/api/exports/batch", headers=HEADERS, json={
            "clip_ids": [clip_id], "aspect": "16:9", "resolution": "720p",
            "effects_by_clip": {clip_id: {
                "caption_style": {"preset": "premium", "position": "top"},
                "captions": [{"word": "brilliant", "start": 1.1, "end": 1.8}],
                "regions": custom_regions, "region_layout": "top-game-bottom-player",
                "split_ratio": 0.7, "outline_style": "neon", "title": "Edited title",
            }},
        })
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        job = _wait_for_job(job_id)
        assert job["status"] == "done", job
        assert captured["aspect"] == "16:9"
        assert captured["resolution"] == "720p"
        assert captured["caption_style"] == {"preset": "premium", "position": "top"}
        assert captured["captions"] == [{"word": "brilliant", "start": 1.1, "end": 1.8}]
        assert captured["regions"] == custom_regions
        assert captured["region_layout"] == "top-game-bottom-player"
        assert captured["split_ratio"] == 0.7
        assert captured["outline_style"] == "neon"
        assert captured["title"] == "Edited title"
        saved_clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
        assert saved_clip["metadata"]["effects"]["resolution"] == "720p"
        assert saved_clip["metadata"]["effects"]["watermark"] is True
    finally:
        if job_id:
            db.delete("jobs", "id", job_id)
        db.delete("clips", "id", clip_id)
        db.delete("media", "id", media_id)


def test_project_export_passes_selected_format_and_quality_to_timeline_renderer(tmp_path, monkeypatch):
    project_id = uid("p517_")
    source = tmp_path / "project-source.mp4"
    source.write_bytes(b"synthetic source")
    timeline = {
        "tracks": {"video": [{"path": str(source), "sourceStart": 0, "duration": 1}],
                   "captions": [], "stickers": [], "audio": []},
        "aspect": "9:16", "resolution": "source",
    }
    db.insert("projects", {
        "id": project_id, "name": "Project export", "data": dumps({"timeline": timeline}),
        "created_at": now(), "updated_at": now(),
    })
    captured: dict = {}

    async def fake_timeline(render_timeline, output, on_progress=None, watermark_path=None):
        captured["timeline"] = render_timeline
        captured["output"] = output
        captured["watermark_path"] = watermark_path
        return output

    monkeypatch.setattr(render, "render_timeline", fake_timeline)
    monkeypatch.setattr(render, "export_path", lambda name: str(tmp_path / f"{name}.mp4"))
    monkeypatch.setattr(main_module, "configured_watermark_path", lambda: None)
    job_id = None
    try:
        response = client.post(
            f"/api/projects/{project_id}/export", headers=HEADERS,
            json={"aspect": "16:9", "resolution": "720p"},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        job = _wait_for_job(job_id)
        assert job["status"] == "done", job
        assert captured["timeline"]["aspect"] == "16:9"
        assert captured["timeline"]["resolution"] == "720p"
        assert captured["watermark_path"] is None
    finally:
        if job_id:
            db.delete("jobs", "id", job_id)
        db.delete("projects", "id", project_id)


def test_export_path_uses_configured_root_and_local_date_subfolder(tmp_path):
    previous = db.get_setting("exports_folder", "")
    root = tmp_path / "my-exports"
    db.set_setting("exports_folder", str(root))
    try:
        output = Path(render.export_path("date folder probe", date(2026, 11, 26)))
        assert output.parent == root / "2026-11-26"
        assert output.name.endswith(".mp4")
        assert output.parent.is_dir()
    finally:
        db.set_setting("exports_folder", previous)


def test_model_services_use_persisted_local_preferences(tmp_path, monkeypatch):
    previous = {key: db.get_setting(key, "") for key in (
        "models_folder", "whisper_model", "WHISPER_MODEL_PATH", "active_llm", "ollama_model", "vision_engine",
    )}
    weights = tmp_path / "models" / "huggingface" / "whisper-medium"
    weights.mkdir(parents=True)
    (weights / "model.bin").write_bytes(b"weights")
    vision_weights = tmp_path / "models" / "yolo" / "yolo11n.pt"
    vision_weights.parent.mkdir(parents=True)
    vision_weights.write_bytes(b"weights")
    loaded_vision_weights: list[str] = []

    class FakeYOLO:
        def __init__(self, model_path: str):
            loaded_vision_weights.append(model_path)

    ultralytics = ModuleType("ultralytics")
    ultralytics.YOLO = FakeYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    try:
        db.set_setting("models_folder", str(tmp_path / "models"))
        db.set_setting("whisper_model", "medium")
        db.set_setting("WHISPER_MODEL_PATH", "")
        db.set_setting("active_llm", "gemma2:7b")
        db.set_setting("ollama_model", "llama3.2:3b")
        db.set_setting("vision_engine", "ultralytics")
        for key in ("WHISPER_MODEL", "WHISPER_MODEL_PATH", "HF_HOME", "OLLAMA_MODEL"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("OLLAMA_MODEL", "gemma2:7b")  # stale runtime activation must not override Settings

        assert asr._resolve_whisper_model() == str(weights)
        assert llm.selected_model() == "llama3.2:3b"
        assert vision._selected_engine("auto") == "ultralytics"
        assert vision._selected_engine("motion") == "motion"
        assert vision._detector("auto") is not None
        assert loaded_vision_weights == [str(vision_weights)]
    finally:
        for key, value in previous.items():
            db.set_setting(key, value)


def test_tts_uses_the_persisted_voice_and_custom_model_folder(tmp_path, monkeypatch):
    voice_id = "en_US-test-medium"
    model_path = tmp_path / "models" / "piper" / f"{voice_id}.onnx"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"synthetic voice weights")
    output = tmp_path / "spoken.wav"
    loaded_paths: list[str] = []

    class FakeVoice:
        @classmethod
        def load(cls, path: str):
            loaded_paths.append(path)
            return cls()

        def synthesize_wav(self, text: str, handle):
            handle.write(text.encode("utf-8"))

    piper = ModuleType("piper")
    piper.__path__ = []
    piper.PiperVoice = FakeVoice
    piper_download = ModuleType("piper.download")
    piper_download.get_voices = lambda _folder: {}
    monkeypatch.setitem(sys.modules, "piper", piper)
    monkeypatch.setitem(sys.modules, "piper.download", piper_download)
    monkeypatch.delenv("PIPER_VOICE", raising=False)
    old_models_folder = db.get_setting("models_folder", "")
    old_voice = db.get_setting("tts_voice", "")
    db.set_setting("models_folder", str(tmp_path / "models"))
    db.set_setting("tts_voice", voice_id)
    try:
        result = asyncio.run(tts.synthesize("Persisted voice test", out=output))
        assert result == str(output)
        assert loaded_paths == [str(model_path)]
        assert output.read_bytes() == b"Persisted voice test"
    finally:
        db.set_setting("models_folder", old_models_folder)
        db.set_setting("tts_voice", old_voice)


def test_auto_edit_transcription_fallback_and_batch_keep_caption_tracks_and_title_fallbacks(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    music = tmp_path / "music.wav"
    source.write_bytes(b"synthetic source")
    music.write_bytes(b"synthetic music")
    media_id, clip_id = uid("m517_"), uid("c517_")
    region_a = {"x": 0, "y": 0, "w": 1, "h": 0.62}
    region_b = {"x": 0, "y": 0.62, "w": 1, "h": 0.38}
    db.insert("media", {
        "id": media_id, "title": "Source", "path": str(source), "source_url": None,
        "duration": 10, "width": 640, "height": 360, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": media_id,
        "start": 2.0, "end": 8.0, "score": 88, "title": "Creator's winning moment",
        "reason": "high engagement", "status": "proposed", "output": None,
        "metadata": dumps({
            "transcript": "The creator lands an incredible final move.",
            "region": region_a, "regions": [region_a, region_b],
            "region_layout": "top-game-bottom-player",
            "crop_path": [[2.0, 0.4], [4.0, 0.6], [8.0, 0.5]],
            "effects": {"music": str(music), "music_volume": 0.16},
        }),
        "created_at": now(),
    })
    previous_watermark = db.get_setting("watermark_path", "")
    jobs_to_delete: list[str] = []
    auto_options: dict = {}
    batch_options: dict = {}

    async def fail_transcription(*_args, **_kwargs):
        raise RuntimeError("Whisper weights are not installed")

    async def fake_render(_media, _start, _end, output, options, on_progress=None):
        if "auto_edited" in output:
            auto_options.update(options)
        else:
            batch_options.update(options)
        return output

    monkeypatch.setattr(main_module, "transcribe", fail_transcription)
    monkeypatch.setattr(main_module, "configured_watermark_path", lambda: None)
    monkeypatch.setattr(main_module, "hardware_info", lambda: {"workers": 1, "encoder": "test"})
    monkeypatch.setattr(render, "render_clip", fake_render)
    monkeypatch.setattr(render, "export_path", lambda name: str(tmp_path / f"{name}.mp4"))
    db.set_setting("watermark_path", "")
    try:
        response = client.post("/api/auto-edit", headers=HEADERS, json={
            "clip_ids": [clip_id], "style": "premium", "aspect": "9:16", "resolution": "source",
        })
        assert response.status_code == 200
        auto_job_id = response.json()["job_id"]
        jobs_to_delete.append(auto_job_id)
        auto_job = _wait_for_job(auto_job_id)
        assert auto_job["status"] == "done", auto_job
        assert auto_job["result"]["count"] == 1
        assert any("captions unavailable" in warning for warning in auto_job["result"]["warnings"])
        recipe = auto_job["result"]["edits"][0]
        assert recipe["source_start"] == 2.0 and recipe["source_duration"] == 6.0
        assert recipe["duration"] == 6.0 and recipe["region_layout"] == "top-game-bottom-player"
        assert recipe["regions"] == [region_a, region_b]
        assert recipe["crop_path"] == [[2.0, 0.4], [4.0, 0.6], [8.0, 0.5]]
        assert recipe["captions"][0]["text"] == "The creator lands an incredible final move."
        assert [track["kind"] for track in recipe["audio"]] == ["music", "sfx", "sfx"]
        assert auto_options["resolution"] == "source"
        assert auto_options["title"] is None  # Speech captions replace the generated clip-name overlay.
        assert auto_options["region_layout"] == "top-game-bottom-player"
        assert auto_options["crop_path"] == [[2.0, 0.4], [4.0, 0.6], [8.0, 0.5]]
        assert auto_options["regions"] == [region_a, region_b]
        assert auto_options["captions"][0]["text"] == "The creator lands an incredible final move."
        assert auto_options["music"] == str(music)
        assert auto_options["watermark"] is False
        assert auto_options["watermark_path"] is None
        assert auto_options["sfx"][0]["name"] == "whoosh"

        stored_clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
        assert stored_clip["output"] == auto_job["result"]["outputs"][0]["output"]
        assert stored_clip["metadata"]["effects"]["captions"] == auto_options["captions"]
        assert stored_clip["metadata"]["effects"]["title"] is None
        assert stored_clip["metadata"]["effects"]["region_layout"] == "top-game-bottom-player"

        batch_response = client.post("/api/exports/batch", headers=HEADERS, json={"clip_ids": [clip_id]})
        assert batch_response.status_code == 200
        batch_job_id = batch_response.json()["job_id"]
        jobs_to_delete.append(batch_job_id)
        batch_job = _wait_for_job(batch_job_id)
        assert batch_job["status"] == "done", batch_job
        assert batch_options["captions"] == auto_options["captions"]
        assert batch_options["region"] == region_a
        assert batch_options["regions"] == [region_a, region_b]
        assert batch_options["region_layout"] == "top-game-bottom-player"
        assert batch_options["crop_path"] == [[2.0, 0.4], [4.0, 0.6], [8.0, 0.5]]
        assert batch_options["title"] is None
        assert batch_options["music"] == str(music)
        assert batch_options["watermark_path"] is None

        auto_options.clear()
        no_music_response = client.post("/api/auto-edit", headers=HEADERS, json={
            "clip_ids": [clip_id], "music": "", "captions": False, "sound_effects": False,
        })
        assert no_music_response.status_code == 200
        no_music_job_id = no_music_response.json()["job_id"]
        jobs_to_delete.append(no_music_job_id)
        no_music_job = _wait_for_job(no_music_job_id)
        assert no_music_job["status"] == "done", no_music_job
        assert auto_options["music"] is None and auto_options["captions"] == [] and auto_options["sfx"] == []
        assert auto_options["title"] == "Creator's winning moment"
        fallback_title = no_music_job["result"]["edits"][0]["captions"]
        assert fallback_title == [{
            "text": "Creator's winning moment", "start": 2.0, "end": 3.4, "kind": "title",
        }]
        assert no_music_job["result"]["edits"][0]["audio"] == []

        auto_options.clear()
        reuse_response = client.post("/api/auto-edit", headers=HEADERS, json={
            "clip_ids": [clip_id], "style": "hype", "captions": True,
            "reuse_settings": {
                "caption_style": {
                    "preset": "minimal", "font_family": "Georgia", "font_size": 44,
                    "primary_color": "#fefefe", "outline_color": "#112233",
                    "position": "top", "bold": False,
                },
            },
        })
        assert reuse_response.status_code == 200
        reuse_job_id = reuse_response.json()["job_id"]
        jobs_to_delete.append(reuse_job_id)
        reuse_job = _wait_for_job(reuse_job_id)
        assert reuse_job["status"] == "done", reuse_job
        reused_recipe = reuse_job["result"]["edits"][0]
        assert reused_recipe["aspect"] == "9:16" and reused_recipe["resolution"] == "source"
        assert auto_options["aspect"] == "9:16" and auto_options["resolution"] == "source"
        assert auto_options["caption_style"]["preset"] == "minimal"
        assert auto_options["caption_style"]["font_family"] == "Georgia"
        assert auto_options["caption_style"]["font_size"] == 44
        assert auto_options["caption_style"]["position"] == "top"
        assert auto_options["speed"] == pytest.approx(1.04)
        assert auto_options["sfx"]  # Auto Edit still contributes non-caption edits.
    finally:
        for job_id in jobs_to_delete:
            db.delete("jobs", "id", job_id)
        db.delete("clips", "id", clip_id)
        db.delete("media", "id", media_id)
        db.set_setting("watermark_path", previous_watermark)
