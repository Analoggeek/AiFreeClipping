"""v5.1.4: settings folders, HTTPS helpers and exact clip counts."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db import db
from app.main import app
from app.config import hardware_info
from app.services import images, models, net, render, scoring, vision

client = TestClient(app)
HEADERS = {"X-AI-Clipper-Token": "aifreeclip-test-token"}


def test_folders_endpoint_is_nested_so_settings_cannot_crash():
    response = client.get("/api/folders", headers=HEADERS)
    assert response.status_code == 200
    folders = response.json()["folders"]
    assert isinstance(folders, dict)
    for key in ("downloads", "exports", "models", "clips", "cache", "assets"):
        assert isinstance(folders[key], str)
        assert folders[key]


def test_folder_patch_returns_nested_map_and_is_readable(tmp_path):
    previous = db.get_setting("models_folder", "")
    target = tmp_path / "weights"
    response = client.put(
        "/api/folders", headers=HEADERS, json={"key": "models", "path": str(target)}
    )
    assert response.status_code == 200
    assert response.json()["folders"]["models"] == str(target)
    assert models._models_root() == target
    assert vision._weights_dir() == target / "yolo"
    db.set_setting("models_folder", previous)


def test_clips_folder_override_controls_render_output(tmp_path):
    previous = db.get_setting("clips_folder", "")
    response = client.put(
        "/api/folders", headers=HEADERS, json={"key": "clips", "path": str(tmp_path)}
    )
    assert response.status_code == 200
    assert render.export_path("sample").startswith(str(tmp_path))
    db.set_setting("clips_folder", previous)


def test_hardware_snapshot_includes_app_usage():
    info = hardware_info()
    assert "app_usage_gb" in info
    assert isinstance(info["app_usage_gb"], (int, float))


def test_ssl_context_is_available():
    context = net.ssl_context()
    assert context is not None
    assert hasattr(context, "verify_mode")


class FakeResponse:
    headers = {"Content-Length": "4"}

    def __init__(self, chunks=(b"ab", b"cd")):
        self.chunks = list(chunks)
        self.index = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=0):
        if self.index >= len(self.chunks):
            return b""
        chunk = self.chunks[self.index]
        self.index += 1
        return chunk

    def __iter__(self):
        return iter([b'{"total":10,"completed":10}', b"not json"])


def test_download_and_ollama_pull_build_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "https_open", lambda *a, **k: FakeResponse())
    target = tmp_path / "weights.bin"
    models._download("https://example.test/model.bin", target, lambda pct, msg: None, "model")
    assert target.read_bytes() == b"abcd"
    models._ollama_pull("gemma2:7b", lambda pct, msg: None)


def test_exact_clip_count_is_enforced_across_one_video():
    clips = scoring.propose(
        [{"id": "m1", "title": "Long gameplay", "duration": 120}],
        {"m1": {"segments": []}},
        {"m1": {"timeline": []}},
        count=5,
        min_duration=6,
        max_duration=20,
    )
    assert len(clips) == 5
    intervals = sorted((clip.start, clip.end) for clip in clips)
    for (_, end), (next_start, _) in zip(intervals, intervals[1:]):
        assert next_start >= end


def test_image_generation_has_an_offline_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "ASSETS", tmp_path)
    result = images.generate("neon trophy sticker", provider="local")
    assert result["provider"] == "local"
    assert Path(result["path"]).exists()
    assert Path(result["path"]).stat().st_size > 1000


def test_auto_edit_and_auto_setup_jobs_are_registered():
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/models/auto-setup" in paths
    assert "/api/auto-edit" in paths
