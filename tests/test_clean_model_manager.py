"""Contract tests are not live Gemma/OS-installer acceptance evidence."""

import hashlib
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from clipos.core.verified_download import download, DownloadCancelled
from clipos.core import ollama_install
from clipos.ai.model_manager import ModelManager
from clipos.db.database import Database


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}

    def getcode(self):
        return self.status


def test_verified_download_checks_real_bytes_and_resume_range(tmp_path):
    body = b"official fixture data"
    digest = hashlib.sha256(body).hexdigest()
    path = tmp_path / "model.onnx"
    path.with_suffix(".onnx.part").write_bytes(body[:5])

    def server(request, timeout):
        assert request.headers["Range"] == "bytes=5-"
        return Response(
            body[5:], 206, {"Content-Range": f"bytes 5-{len(body) - 1}/{len(body)}"}
        )

    with patch("urllib.request.urlopen", side_effect=server):
        assert (
            download("https://github.com/official/asset", path, digest, len(body))
            == path
        )
    assert path.read_bytes() == body
    with patch("urllib.request.urlopen") as network:
        download("https://github.com/official/asset", path, digest, len(body))
        network.assert_not_called()


def test_hash_mismatch_deletes_untrusted_partial_and_does_not_replace_completed_file(
    tmp_path,
):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"previous verified model")
    with patch("urllib.request.urlopen", return_value=Response(b"BAD")):
        with pytest.raises(RuntimeError, match="SHA256 mismatch"):
            download("https://github.com/official/asset", path, "0" * 64, 3)
    assert path.read_bytes() == b"previous verified model"
    assert not path.with_suffix(".onnx.part").exists()


def test_cancelled_download_is_not_registered_as_installed(tmp_path):
    path = tmp_path / "model.onnx"
    with patch("urllib.request.urlopen", return_value=Response(b"data")):
        with pytest.raises(DownloadCancelled):
            download(
                "https://github.com/official/asset",
                path,
                "0" * 64,
                4,
                cancelled=lambda: True,
            )
    assert not path.exists()


def test_runtime_requires_consent_and_never_reinstalls_an_existing_service():
    with patch.object(ollama_install, "download") as network:
        with pytest.raises(PermissionError):
            ollama_install.install()
        network.assert_not_called()
        with patch.object(
            ollama_install, "api_status", return_value={"version": "fixture"}
        ):
            assert ollama_install.install(consent=True) == {"version": "fixture"}
        network.assert_not_called()


def test_stopped_installed_runtime_starts_without_duplicate_download(tmp_path):
    with (
        patch.object(ollama_install, "api_status", side_effect=RuntimeError("stopped")),
        patch.object(ollama_install, "find_binary", return_value=tmp_path / "ollama"),
        patch.object(
            ollama_install, "start_service", return_value={"version": "fixture"}
        ) as start,
        patch.object(ollama_install, "download") as network,
    ):
        assert ollama_install.install(consent=True) == {"version": "fixture"}
        start.assert_called_once()
        network.assert_not_called()


def test_yolox_invalid_weights_never_enter_registry_or_enable_tracking(tmp_path):
    db = Database(tmp_path / "models.db")
    manager = ModelManager(db)
    try:
        bad = tmp_path / "bad.onnx"
        bad.write_bytes(b"not a model")
        with pytest.raises(RuntimeError, match="integrity"):
            manager.verify_yolox(bad)
        assert manager.registry() == {}
        with patch.object(
            manager, "verify_yolox", side_effect=RuntimeError("inference failed")
        ):
            with pytest.raises(RuntimeError):
                manager.enable_tracking(True)
        assert not db.get_setting("tracking_enabled", False)
    finally:
        db.close()


def test_actual_bytetrack_cpu_test_and_registry_survive_restart(tmp_path):
    path = tmp_path / "models.db"
    db = Database(path)
    try:
        result = ModelManager(db).test_bytetrack()
        assert "synthetic" in result and "bytetrack" in ModelManager(db).registry()
        db.close()
        db = Database(path)
        assert ModelManager(db).registry()["bytetrack"]["version"] == "0.27.0"
    finally:
        db.close()


def test_ollama_pull_registers_only_after_inference_succeeds(tmp_path):
    db = Database(tmp_path / "models.db")
    manager = ModelManager(db)
    try:
        with (
            patch("clipos.ai.model_manager.preflight"),
            patch("clipos.ai.model_manager.GemmaRuntime") as runtime,
        ):
            runtime.return_value.verify_offline.side_effect = RuntimeError(
                "inference failed"
            )
            with pytest.raises(RuntimeError):
                manager.pull_ollama("gemma:7b", consent=True)
            assert manager.registry() == {}
        with pytest.raises(PermissionError):
            manager.pull_ollama("gemma:7b")
    finally:
        db.close()


def test_additional_manifest_host_requires_explicit_allowlist_and_exact_hostname(
    tmp_path,
):
    payload = b"verified official speech model"
    digest = hashlib.sha256(payload).hexdigest()
    with patch("urllib.request.urlopen", return_value=Response(payload)) as request:
        with pytest.raises(ValueError):
            download(
                "https://huggingface.co/repo/file",
                tmp_path / "blocked",
                digest,
                len(payload),
            )
        with pytest.raises(ValueError):
            download(
                "https://huggingface.co.evil.invalid/repo/file",
                tmp_path / "blocked",
                digest,
                len(payload),
                allowed_hosts=("huggingface.co",),
            )
        request.assert_not_called()
        download(
            "https://huggingface.co/repo/file",
            tmp_path / "verified",
            digest,
            len(payload),
            allowed_hosts=("huggingface.co",),
        )
    assert (tmp_path / "verified").read_bytes() == payload


def test_windows_signature_uses_os_security_module_not_inherited_pwsh_modules(tmp_path):
    from types import SimpleNamespace

    with patch.dict(
        "os.environ",
        {"PSModulePath": "untrusted-pwsh-modules", "SystemRoot": r"C:\Windows"},
    ):
        with patch.object(
            ollama_install.subprocess, "run", return_value=SimpleNamespace(returncode=0)
        ) as run:
            ollama_install.verify_windows_signature(tmp_path / "OllamaSetup.exe")
            args = run.call_args.args[0]
            env = run.call_args.kwargs["env"]
            assert args[0].endswith("powershell.exe")
            assert "WindowsPowerShell" in args[0]
            assert not any(key.upper() == "PSMODULEPATH" for key in env)
            assert "Join-Path $PSHOME" in args[-1]
            assert '$ErrorActionPreference="Stop"' in args[-1]
            assert '$s.Status -ne "Valid"' in args[-1]


def test_windows_signature_failure_stays_fail_closed(tmp_path):
    from types import SimpleNamespace

    with patch.object(
        ollama_install.subprocess,
        "run",
        return_value=SimpleNamespace(returncode=1, stdout="HashMismatch", stderr=""),
    ):
        with pytest.raises(RuntimeError, match="HashMismatch"):
            ollama_install.verify_windows_signature(tmp_path / "OllamaSetup.exe")
