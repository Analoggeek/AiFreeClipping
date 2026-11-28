"""Packaging helpers must use the platform names consumed by the Electron shell."""
from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "package-backend.py"
SPEC = importlib.util.spec_from_file_location("package_backend", SCRIPT)
assert SPEC and SPEC.loader
package_backend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_backend)


def test_release_platform_labels_map_to_electron_runtime_names(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg-source"
    ffmpeg.write_bytes(b"test ffmpeg")
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(package_backend, "RUNTIME", runtime)
    monkeypatch.setattr(package_backend, "ffmpeg_candidates", lambda: [ffmpeg])

    windows = package_backend.build("win", "x64", skip_pyinstaller=True)
    macos = package_backend.build("mac", "arm64", skip_pyinstaller=True)

    assert windows == runtime / "windows-x64"
    assert (windows / "ffmpeg.exe").read_bytes() == b"test ffmpeg"
    assert macos == runtime / "macos-arm64"
    assert (macos / "ffmpeg").read_bytes() == b"test ffmpeg"
