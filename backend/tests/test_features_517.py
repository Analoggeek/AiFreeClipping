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
        },
    ))
    pip_info = probe(pip_output)
    assert (pip_info["video_codec"], pip_info["audio_codec"]) == ("h264", "aac")
    assert (pip_info["width"], pip_info["height"]) == (720, 1280)


def test_timeline_export_uses_source_quality_without_text_overlays(tmp_path):
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
        "aspect": "9:16", "resolution": "source",
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
            "stickers": [], "audio": [],
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
        assert captured["regions"] == custom_regions
        assert captured["region_layout"] == "top-game-bottom-player"
        assert captured["split_ratio"] == 0.7
        assert captured["outline_style"] == "neon"
        assert "caption_style" not in captured and "captions" not in captured and "title" not in captured
        saved_clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
        assert saved_clip["metadata"]["effects"]["resolution"] == "720p"
        assert saved_clip["metadata"]["effects"]["watermark"] is True
        assert not ({"caption_style", "captions", "title"} & saved_clip["metadata"]["effects"].keys())
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
                   "stickers": [], "audio": []},
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



def test_auto_edit_keeps_transcript_internal_and_emits_only_editable_media_tracks(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic source")
    media_id, clip_id = uid("m517_v6_"), uid("c517_v6_")
    region = {"x": 0, "y": 0, "w": 1, "h": 1}
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
            "caption": "Legacy social copy",
            "transcript": "The creator lands an incredible final move.",
            "region": region, "regions": [region],
            "effects": {
                "caption_style": {"preset": "premium"},
                "captions": [{"text": "legacy overlay", "start": 0, "end": 2}],
                "title": "legacy title overlay",
                "music": "/missing/music.wav",
            },
        }),
        "created_at": now(),
    })
    jobs_to_delete: list[str] = []
    captured: dict[str, dict] = {}

    async def forbidden_transcription(*_args, **_kwargs):
        raise AssertionError("Auto Edit must not transcribe for captions")

    async def fake_render(_media, _start, _end, output, options, on_progress=None):
        captured["auto" if "auto_edited" in output else "batch"] = dict(options)
        return output

    monkeypatch.setattr(main_module, "transcribe", forbidden_transcription)
    monkeypatch.setattr(main_module, "configured_watermark_path", lambda: None)
    monkeypatch.setattr(main_module, "hardware_info", lambda: {"workers": 1, "cpu_count": 1, "encoder": "test"})
    monkeypatch.setattr(render, "render_clip", fake_render)
    monkeypatch.setattr(render, "export_path", lambda name: str(tmp_path / f"{name}.mp4"))
    try:
        response = client.post("/api/auto-edit", headers=HEADERS, json={
            "clip_ids": [clip_id], "style": "premium", "aspect": "9:16", "resolution": "source",
            "music": "", "sound_effects": False, "stickers": False,
            "captions": True, "caption_style": {"preset": "hype"},
        })
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        jobs_to_delete.append(job_id)
        job = _wait_for_job(job_id)
        assert job["status"] == "done", job
        assert job["result"]["count"] == 1 and job["result"]["warnings"] == []
        edit = job["result"]["edits"][0]
        assert edit["source_start"] == 2 and edit["source_duration"] == 6
        assert edit["region"] == region
        assert edit["audio"] == [] and edit["stickers"] == []
        assert "captions" not in edit and "caption_style" not in edit
        assert "captions" not in edit["effects"] and "caption_style" not in edit["effects"]
        assert "title" not in edit["effects"]
        assert "captions" not in captured["auto"] and "caption_style" not in captured["auto"]
        assert "title" not in captured["auto"] and captured["auto"]["sfx"] == []

        stored = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
        effects = stored["metadata"]["effects"]
        assert not ({"caption_style", "captions", "title"} & effects.keys())
        assert "caption" not in stored["metadata"]
        assert stored["metadata"]["auto_edited"] is True
        assert stored["metadata"]["hardware"]["encoder"] == "test"

        batch_response = client.post("/api/exports/batch", headers=HEADERS, json={"clip_ids": [clip_id]})
        assert batch_response.status_code == 200
        batch_job_id = batch_response.json()["job_id"]
        jobs_to_delete.append(batch_job_id)
        batch_job = _wait_for_job(batch_job_id)
        assert batch_job["status"] == "done", batch_job
        assert "captions" not in captured["batch"] and "caption_style" not in captured["batch"]
        assert "title" not in captured["batch"]
    finally:
        for job_id in jobs_to_delete:
            db.delete("jobs", "id", job_id)
        db.delete("clips", "id", clip_id)
        db.delete("media", "id", media_id)
