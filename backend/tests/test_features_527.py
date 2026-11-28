"""v5.2.7 regression checks for safe download cleanup and Ollama/model setup."""
from __future__ import annotations

import asyncio
import io
import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import zstandard
from fastapi.testclient import TestClient

from app.db import db, now, dumps
from app.main import app, folder_map
from app.services import models

client = TestClient(app)
HEADERS = {"X-AI-Clipper-Token": "aifreeclip-test-token"}


def _add_media(media_id: str, path: Path, source_url: str | None) -> None:
    db.insert("media", {
        "id": media_id, "title": media_id, "path": str(path), "source_url": source_url,
        "duration": 1, "width": 16, "height": 9, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })


def _save_setting(key: str) -> tuple[bool, str]:
    row = db.one("SELECT value FROM settings WHERE key=?", (key,))
    return (row is not None, row["value"] if row else "")


def _restore_setting(key: str, previous: tuple[bool, str]) -> None:
    existed, value = previous
    if existed:
        db.set_setting(key, value)
    else:
        db.execute("DELETE FROM settings WHERE key=?", (key,))


def test_download_folder_map_uses_the_folder_the_downloader_really_uses(tmp_path):
    previous_download = _save_setting("download_folder")
    previous_legacy = _save_setting("downloads_folder")
    actual = tmp_path / "actual-downloads"
    stale = tmp_path / "stale-setting"
    db.set_setting("download_folder", str(actual))
    db.set_setting("downloads_folder", str(stale))
    try:
        assert folder_map()["downloads"] == str(actual)
    finally:
        _restore_setting("download_folder", previous_download)
        _restore_setting("downloads_folder", previous_legacy)


def test_download_storage_requires_explicit_confirmation(tmp_path):
    previous = _save_setting("download_folder")
    folder = tmp_path / "downloads"
    folder.mkdir()
    source = folder / "keep.mp4"
    source.write_bytes(b"download")
    media_id = "test527confirm"
    db.set_setting("download_folder", str(folder))
    _add_media(media_id, source, "https://example.test/keep")
    try:
        response = client.request(
            "DELETE", "/api/downloads/storage", headers=HEADERS,
            json={"folder": str(folder), "confirmed": False},
        )
        assert response.status_code == 400
        assert source.exists()
        assert db.one("SELECT id FROM media WHERE id=?", (media_id,)) is not None
    finally:
        db.delete("media", "id", media_id)
        _restore_setting("download_folder", previous)


def test_clear_download_storage_only_removes_owned_unreferenced_downloads(tmp_path):
    previous = _save_setting("download_folder")
    folder = tmp_path / "downloads"
    outside = tmp_path / "outside.mp4"
    folder.mkdir()
    removable = folder / "removable.mp4"
    referenced = folder / "project-source.mp4"
    imported = folder / "imported-original.mp4"
    shared_import = folder / "shared-imported-original.mp4"
    unregistered = folder / "not-in-library.mp4"
    for path in (removable, referenced, imported, shared_import, unregistered, outside):
        path.write_bytes(b"video")

    ids = {
        "remove": "test527remove", "referenced": "test527referenced",
        "imported": "test527imported", "shared_download": "test527sharedownload",
        "shared_import": "test527sharedimport", "outside": "test527outside",
    }
    project_id = "test527project"
    clip_id = "test527renderedclip"
    rendered = tmp_path / "rendered.mp4"
    rendered.write_bytes(b"rendered clip")
    db.set_setting("download_folder", str(folder))
    _add_media(ids["remove"], removable, "https://example.test/remove")
    _add_media(ids["referenced"], referenced, "https://example.test/project")
    _add_media(ids["imported"], imported, None)
    _add_media(ids["shared_download"], shared_import, "https://example.test/shared")
    _add_media(ids["shared_import"], shared_import, None)
    _add_media(ids["outside"], outside, "https://example.test/outside")
    db.insert("projects", {
        "id": project_id, "name": "Keep source", "data": dumps({"timeline": {"tracks": {
            "video": [{"path": str(referenced)}],
        }}}), "created_at": now(), "updated_at": now(),
    })
    db.insert("clips", {
        "id": clip_id, "project_id": None, "media_id": ids["referenced"], "start": 0, "end": 1,
        "score": 0, "title": "Rendered source", "reason": "", "status": "rendered",
        "output": str(rendered), "metadata": "{}", "created_at": now(),
    })

    try:
        response = client.request(
            "DELETE", "/api/downloads/storage", headers=HEADERS,
            json={"folder": str(folder), "confirmed": True},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["folder"] == str(folder)
        assert result["media_removed"] == 1
        assert result["media_kept_shared"] == 2
        assert result["media_kept_error"] == 0
        assert result["files_deleted"] == 1
        assert result["files_kept_shared"] == 2
        assert result["files_missing"] == 0
        assert not removable.exists()
        assert referenced.exists()
        assert imported.exists()
        assert shared_import.exists()
        assert outside.exists()
        assert unregistered.exists()
        assert db.one("SELECT id FROM media WHERE id=?", (ids["remove"],)) is None
        assert db.one("SELECT id FROM media WHERE id=?", (ids["referenced"],)) is not None
        assert db.one("SELECT id FROM media WHERE id=?", (ids["imported"],)) is not None
        assert db.one("SELECT id FROM media WHERE id=?", (ids["shared_download"],)) is not None
        assert db.one("SELECT id FROM media WHERE id=?", (ids["shared_import"],)) is not None
        assert db.one("SELECT id FROM media WHERE id=?", (ids["outside"],)) is not None
        assert db.one("SELECT id FROM projects WHERE id=?", (project_id,)) is not None
        assert db.one("SELECT id FROM clips WHERE id=?", (clip_id,)) is not None
    finally:
        for media_id in ids.values():
            db.delete("media", "id", media_id)
        db.delete("projects", "id", project_id)
        db.delete("clips", "id", clip_id)
        _restore_setting("download_folder", previous)


def test_clear_download_storage_rejects_a_folder_that_changed_after_confirmation(tmp_path):
    previous = _save_setting("download_folder")
    actual = tmp_path / "actual"
    different = tmp_path / "different"
    actual.mkdir()
    different.mkdir()
    source = actual / "keep.mp4"
    source.write_bytes(b"download")
    media_id = "test527stale"
    db.set_setting("download_folder", str(actual))
    _add_media(media_id, source, "https://example.test/stale")
    try:
        response = client.request(
            "DELETE", "/api/downloads/storage", headers=HEADERS,
            json={"folder": str(different), "confirmed": True},
        )
        assert response.status_code == 409
        assert source.exists()
        assert db.one("SELECT id FROM media WHERE id=?", (media_id,)) is not None
    finally:
        db.delete("media", "id", media_id)
        _restore_setting("download_folder", previous)


def test_clear_download_storage_keeps_library_entry_when_file_cannot_be_deleted(tmp_path, monkeypatch):
    previous = _save_setting("download_folder")
    folder = tmp_path / "downloads"
    folder.mkdir()
    source = folder / "protected.mp4"
    source.write_bytes(b"download")
    media_id = "test527permission"
    db.set_setting("download_folder", str(folder))
    _add_media(media_id, source, "https://example.test/protected")
    original_unlink = Path.unlink

    def deny_source_delete(path: Path, *args, **kwargs):
        if path.resolve() == source.resolve():
            raise PermissionError("permission denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_source_delete)
    try:
        response = client.request(
            "DELETE", "/api/downloads/storage", headers=HEADERS,
            json={"folder": str(folder), "confirmed": True},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["media_removed"] == 0
        assert result["media_kept_error"] == 1
        assert result["files_deleted"] == 0
        assert result["file_errors"]
        assert source.exists()
        assert db.one("SELECT id FROM media WHERE id=?", (media_id,)) is not None
    finally:
        db.delete("media", "id", media_id)
        _restore_setting("download_folder", previous)


def test_ollama_archive_selection_matches_official_release_assets():
    version = models.OLLAMA_VERSION
    assert version == "v0.40.19"
    assert models._ollama_archive("darwin", "arm64") == (
        f"https://github.com/ollama/ollama/releases/download/{version}/ollama-darwin.tgz", "ollama.tgz",
    )
    assert models._ollama_archive("windows", "aarch64")[0].endswith("/ollama-windows-arm64.zip")
    assert models._ollama_archive("windows", "x86_64")[0].endswith("/ollama-windows-amd64.zip")
    assert models._ollama_archive("linux", "aarch64")[0].endswith("/ollama-linux-arm64.tar.zst")
    assert models._ollama_archive("linux", "x86_64")[0].endswith("/ollama-linux-amd64.tar.zst")
    with pytest.raises(RuntimeError, match="not supported"):
        models._ollama_archive("freebsd", "x86_64")


def test_model_catalog_marks_only_the_installed_ollama_tag(monkeypatch):
    async def fake_tags():
        return [{"name": "gemma3:4b"}]

    monkeypatch.setattr(models, "tags", fake_tags)
    monkeypatch.setattr(models, "_installed_ids", lambda: set())
    monkeypatch.setattr(models, "hardware_info", lambda: {"ram_total_gb": 8, "gpu": {}})
    catalog = asyncio.run(models.status())
    by_id = {model["id"]: model for model in catalog}
    assert by_id["gemma3:4b"]["installed"] is True
    assert by_id["gemma3:12b"]["installed"] is False
    assert by_id["gemma2:7b"]["installed"] is False
    assert by_id["gemma3:4b"]["recommended"] is True


def test_ollama_pull_requests_and_reports_the_selected_model(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def __iter__(self):
            return iter((
                b'{"status":"pulling manifest"}\n',
                b'{"completed":50,"total":100}\n',
                b'{"status":"success"}\n',
            ))

    captured = {}
    monkeypatch.setattr(models, "ollama_host", lambda: "http://127.0.0.1:11434")

    def fake_open(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(models, "https_open", fake_open)
    progress = []
    models._ollama_pull("gemma3:4b", lambda percent, message: progress.append((percent, message)))
    request = captured["request"]
    assert request.full_url == "http://127.0.0.1:11434/api/pull"
    assert json.loads(request.data) == {"name": "gemma3:4b", "stream": True}
    assert captured["timeout"] == 30
    assert progress == [(5, "pulling manifest"), (50, "Pulling gemma3:4b…"), (5, "success")]


def test_ollama_binary_is_reused_from_a_custom_models_folder(tmp_path):
    previous_folder = _save_setting("models_folder")
    previous_binary = _save_setting("ollama_binary")
    root = tmp_path / "custom-models"
    executable = root / "ollama" / "ollama"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"runtime")
    db.set_setting("models_folder", str(root))
    db.set_setting("ollama_binary", "")
    try:
        assert models._ollama_binary() == executable
    finally:
        _restore_setting("models_folder", previous_folder)
        _restore_setting("ollama_binary", previous_binary)


def _zstd_tar_bytes(filename: str, content: bytes) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        info = tarfile.TarInfo(filename)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return zstandard.ZstdCompressor().compress(raw.getvalue())


def test_ollama_linux_zstd_archive_stream_extracts_safely(tmp_path):
    archive = tmp_path / "runtime.tar.zst"
    root = tmp_path / "ollama"
    archive.write_bytes(_zstd_tar_bytes("bin/ollama", b"official runtime"))
    models._extract_zstd_tar(archive, root)
    assert (root / "bin" / "ollama").read_bytes() == b"official runtime"

    unsafe = tmp_path / "unsafe.tar.zst"
    unsafe.write_bytes(_zstd_tar_bytes("../outside.txt", b"do not write"))
    models._extract_zstd_tar(unsafe, root)
    assert not (tmp_path / "outside.txt").exists()


def test_ollama_zstd_cli_fallback_streams_without_a_plain_tar(tmp_path, monkeypatch):
    downloaded = tmp_path / "runtime.tar.zst"
    root = tmp_path / "ollama"
    downloaded.write_bytes(_zstd_tar_bytes("bin/ollama", b"streamed runtime"))
    tar_stream = zstandard.ZstdDecompressor().decompress(downloaded.read_bytes())

    class Process:
        def __init__(self):
            self.stdout = io.BytesIO(tar_stream)
            self.returncode = None
            self.terminated = False

        def wait(self):
            self.returncode = -15 if self.terminated else 0
            return self.returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True

    process = Process()
    commands = []

    def fake_popen(command, **kwargs):
        commands.append((command, kwargs))
        return process

    monkeypatch.setitem(sys.modules, "zstandard", None)
    monkeypatch.setattr(models.shutil, "which", lambda name: "/usr/bin/zstd" if name == "zstd" else None)
    monkeypatch.setattr(models.subprocess, "Popen", fake_popen)
    models._extract_zstd_tar(downloaded, root)

    assert commands[0][0] == ["/usr/bin/zstd", "-d", "-c", str(downloaded)]
    assert commands[0][1]["stdout"] is models.subprocess.PIPE
    assert (root / "bin" / "ollama").read_bytes() == b"streamed runtime"
    assert not downloaded.with_suffix(".tar").exists()


def test_ensure_ollama_downloads_current_linux_runtime_and_starts_it(tmp_path, monkeypatch):
    root = tmp_path / "models"
    archive_bytes = _zstd_tar_bytes("ollama", b"fake executable")
    downloaded: list[tuple[str, Path]] = []
    started: list[list[str]] = []
    progress: list[tuple[float, str]] = []
    previous_binary = _save_setting("ollama_binary")

    def fake_download(url, target, _progress, _label):
        downloaded.append((url, target))
        target.write_bytes(archive_bytes)

    monkeypatch.setattr(models, "_models_root", lambda: root)
    monkeypatch.setattr(models, "_ollama_binary", lambda: None)
    monkeypatch.setattr(models.platform, "system", lambda: "Linux")
    monkeypatch.setattr(models.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(models, "_download", fake_download)
    alive_responses = iter((False, False, True))
    monkeypatch.setattr(models, "_ollama_alive", lambda: next(alive_responses, True))
    monkeypatch.setattr(models.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(models.subprocess, "Popen", lambda args, **_kwargs: started.append(args))
    try:
        models._ensure_ollama(lambda percent, message: progress.append((percent, message)))
        expected_url = f"https://github.com/ollama/ollama/releases/download/{models.OLLAMA_VERSION}/ollama-linux-amd64.tar.zst"
        assert downloaded == [(expected_url, root / "ollama" / "ollama.tar.zst")]
        executable = root / "ollama" / "ollama"
        assert executable.read_bytes() == b"fake executable"
        assert db.get_setting("ollama_binary") == str(executable)
        assert started == [[str(executable), "serve"]]
        assert not (root / "ollama" / "ollama.tar.zst").exists()
    finally:
        _restore_setting("ollama_binary", previous_binary)


def test_local_model_install_paths_are_exercised_with_mocked_downloads(tmp_path, monkeypatch):
    root = tmp_path / "models"
    checkpoint_dir = tmp_path / "checkpoints"
    activated: list[str] = []
    pulled: list[str] = []
    download_urls: list[str] = []

    def fake_download(url, target, _progress, _label):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mocked model payload")
        download_urls.append(url)

    def fake_snapshot_download(*, repo_id, local_dir):
        destination = Path(local_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "model.bin").write_bytes(b"whisper weights")
        return str(destination)

    monkeypatch.setattr(models, "_models_root", lambda: root)
    monkeypatch.setattr(models, "_whisper_dir", lambda model_id: root / model_id)
    monkeypatch.setattr(models, "_comfy_checkpoints_dir", lambda: checkpoint_dir)
    monkeypatch.setattr(models, "_download", fake_download)
    monkeypatch.setattr(models, "_ensure_ollama", lambda _progress: None)
    monkeypatch.setattr(models, "_ollama_pull", lambda model_id, _progress: pulled.append(model_id))
    monkeypatch.setattr(models, "_activate", lambda model: activated.append(model["id"]))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=fake_snapshot_download))

    local_model_ids = (
        "gemma2:7b", "gemma3:4b", "gemma3:12b",
        "whisper-small", "whisper-medium", "whisper-large-v3",
        "yolox-nano", "yolo11n", "piper-en_US-lessac-medium", "sdxl-1.0",
    )
    previous_checkpoint = _save_setting("comfy_checkpoint")
    previous_checkpoint_path = _save_setting("comfy_checkpoint_path")
    try:
        results = [
            asyncio.run(models.install(model_id, lambda _percent, _message: None))
            for model_id in local_model_ids
        ]

        assert all(result["installed"] and result["activated"] for result in results)
        assert activated == list(local_model_ids)
        assert pulled == list(local_model_ids[:3])
        assert (root / "whisper-small" / "model.bin").is_file()
        assert (root / "whisper-medium" / "model.bin").is_file()
        assert (root / "whisper-large-v3" / "model.bin").is_file()
        assert (root / "yolo" / "yolox_nano.onnx").is_file()
        assert (root / "yolo" / "yolo11n.pt").is_file()
        assert (root / "piper" / "en_US-lessac-medium.onnx").is_file()
        assert (root / "piper" / "en_US-lessac-medium.json").is_file()
        assert (checkpoint_dir / "sd_xl_base_1.0.safetensors").is_file()
        assert all("gemma3" not in url for url in download_urls)  # Ollama pulls via its local API.
    finally:
        _restore_setting("comfy_checkpoint", previous_checkpoint)
        _restore_setting("comfy_checkpoint_path", previous_checkpoint_path)


def test_cloud_model_install_explains_api_key_setup():
    for model_id in ("nano-banana", "youtube-api", "pexels-api", "pixabay-api"):
        with pytest.raises(RuntimeError, match="create your API key"):
            asyncio.run(models.install(model_id, lambda _percent, _message: None))
