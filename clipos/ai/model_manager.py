"""Central model lifecycle: explicit download -> integrity -> real inference -> registry.

A Python import is never evidence that model weights have loaded. Registry entries
are written only after inference/test completion. Failed installs remain retryable.
"""

import importlib.metadata
import json
from pathlib import Path
import shutil
import time

from ..core.config import PATHS
from ..core.verified_download import download, sha256
from .gemma_runtime import GemmaRuntime

YOLOX = {
    "url": "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx",
    "sha256": "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d",
    "size": 3659407,
    "license": "Apache-2.0",
}
# Explicit local model tags; no arbitrary registry URLs or cloud variants.
OLLAMA_MODELS = {
    "gemma:7b": ("Gemma 7B · Ollama default quantization", 6, 8),
    "gemma:7b-instruct-v1.1-q4_K_S": ("Gemma 1.1 7B · Q4_K_S", 6, 8),
    "gemma:2b": ("Gemma 2B", 3, 4),
    "qwen2.5:0.5b": ("Qwen 2.5 0.5B", 2, 2),
    "llama3.2:1b": ("Llama 3.2 1B", 3, 4),
}


def preflight(folder, disk_gib, ram_gib=0):
    import psutil

    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path).free < disk_gib * 1024**3:
        raise RuntimeError(f"At least {disk_gib} GiB free disk is required")
    if ram_gib and psutil.virtual_memory().total < ram_gib * 1024**3:
        raise RuntimeError(
            f"Model requires at least {ram_gib} GiB system RAM; choose a smaller model"
        )
    test = path / ".write-test"
    try:
        test.write_bytes(b"")
        test.unlink()
    except OSError as exc:
        raise RuntimeError("Model storage is not writable") from exc


class ModelManager:
    def __init__(self, db):
        self.db = db

    def registry(self):
        return json.loads(self.db.get_setting("verified_model_registry", "{}"))

    def record(self, key, **values):
        data = self.registry()
        data[key] = {**values, "verified_at": time.time()}
        self.db.set_setting("verified_model_registry", json.dumps(data, sort_keys=True))

    def forget(self, key):
        data = self.registry()
        data.pop(key, None)
        self.db.set_setting("verified_model_registry", json.dumps(data))

    def install_yolox(self, *, consent=False, progress=None, cancelled=None):
        if not consent:
            raise PermissionError(
                "Confirm the official Apache-2.0 weight download first"
            )
        preflight(PATHS.models, 0.1)
        # Frozen builds must include these dependencies; never invoke pip inside
        # an end-user EXE/APP or install an unrelated legacy bytetrack package.
        for package in ("onnxruntime", "supervision"):
            try:
                importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError as exc:
                raise RuntimeError(
                    f"{package} runtime missing; install a build with tracking support. Weights have not been marked installed."
                ) from exc
        path = download(
            YOLOX["url"],
            PATHS.models / "yolox" / "yolox_nano.onnx",
            YOLOX["sha256"],
            YOLOX["size"],
            progress=progress,
            cancelled=cancelled,
        )
        return self.verify_yolox(path)

    def verify_yolox(self, path=None):
        import numpy as np
        from .person_tracking import LocalYOLOX

        path = Path(path or PATHS.models / "yolox" / "yolox_nano.onnx")
        if not path.is_file() or sha256(path) != YOLOX["sha256"]:
            raise RuntimeError(
                "YOLOX weights missing or integrity check failed; Download / retry from this page"
            )
        detector = LocalYOLOX(path)
        detector.detect(np.zeros((416, 416, 3), np.uint8))
        del detector
        self.test_bytetrack()
        self.record(
            "yolox",
            path=str(path),
            sha256=YOLOX["sha256"],
            test="Actual CPU ONNX inference completed; accuracy not certified",
        )
        return "YOLOX weights verified and actual CPU inference completed; ByteTrack runtime tested. Enable tracking explicitly."

    def test_bytetrack(self):
        import numpy as np
        import os

        os.environ.setdefault("MPLBACKEND", "Agg")
        import supervision as sv

        tracker = sv.ByteTrack(minimum_consecutive_frames=1)
        ids = []
        for frame in range(8):
            observed = sv.Detections(
                xyxy=np.array([[20 + frame, 30, 100 + frame, 180]], np.float32),
                confidence=np.array([0.95]),
                class_id=np.array([0]),
            )
            tracked = tracker.update_with_detections(observed)
            if len(tracked):
                ids.append(int(tracked.tracker_id[0]))
        if not ids or len(set(ids)) != 1:
            raise RuntimeError("ByteTrack CPU association test failed")
        self.record(
            "bytetrack",
            version=importlib.metadata.version("supervision"),
            test="Actual tracker on synthetic detections; no real-person quality claim",
        )
        return "ByteTrack CPU runtime test passed on synthetic detections (not a detector-quality test)."

    def enable_tracking(self, enabled):
        if enabled:
            self.verify_yolox()
            self.db.set_setting(
                "person_model_path", str(PATHS.models / "yolox" / "yolox_nano.onnx")
            )
        else:
            self.db.set_setting("person_model_path", "")
        self.db.set_setting("tracking_enabled", bool(enabled))

    def delete_yolox(self):
        self.enable_tracking(False)
        (PATHS.models / "yolox" / "yolox_nano.onnx").unlink(missing_ok=True)
        self.forget("yolox")

    def pull_ollama(self, model, *, consent=False, progress=None, cancelled=None):
        if not consent:
            raise PermissionError(
                "Confirm model license and download before continuing"
            )
        if model not in OLLAMA_MODELS:
            raise ValueError("Select a supported official local model")
        _, disk, ram = OLLAMA_MODELS[model]
        import os

        preflight(
            Path(os.environ.get("OLLAMA_MODELS", str(Path.home() / ".ollama"))),
            disk,
            ram,
        )
        runtime = GemmaRuntime(
            self.db.get_setting("ollama_host", "http://127.0.0.1:11434")
        )
        runtime.pull(model, consent=True, progress=progress, cancelled=cancelled)
        if cancelled and cancelled():
            raise RuntimeError("Download cancelled before inference verification")
        if progress:
            progress({"status": "Testing downloaded local GGUF inference"})
        response = runtime.verify_offline(model)
        details = runtime.client.require_local_model(model)
        self.record(model, test=response, details=details.get("details", {}))
        self.db.set_settings({"llm_model": model, "ollama_model_enabled": True})
        return response

    def use_ollama(self, model):
        runtime = GemmaRuntime(
            self.db.get_setting("ollama_host", "http://127.0.0.1:11434")
        )
        result = runtime.verify_offline(model)
        self.record(model, test=result)
        self.db.set_settings({"llm_model": model, "ollama_model_enabled": True})
        return result

    def delete_ollama(self, model):
        if model not in OLLAMA_MODELS:
            raise ValueError("Unsupported managed model")
        runtime = GemmaRuntime(
            self.db.get_setting("ollama_host", "http://127.0.0.1:11434")
        )
        runtime.client.request("/api/delete", {"model": model}, method="DELETE")
        self.forget(model)

    def download_whisper(self, size, *, consent=False, progress=None, cancelled=None):
        if not consent:
            raise PermissionError("Explicit model download consent required")
        from huggingface_hub import HfApi
        from .transcription import (
            WHISPER_SIZES,
            download_whisper_model,
            local_model_path,
        )
        import hashlib

        if size not in WHISPER_SIZES:
            raise ValueError("Unsupported speech model")
        preflight(PATHS.models, 4 if size in ("medium", "large-v3", "large-v2") else 1)
        repo = WHISPER_SIZES[size][0]
        metadata = HfApi().model_info(repo, files_metadata=True)
        if not metadata.sha:
            raise RuntimeError(
                "Official speech repository did not supply an immutable revision"
            )
        if not download_whisper_model(
            size, progress_cb=progress, revision=metadata.sha, cancelled=cancelled
        ):
            raise RuntimeError("Speech download failed; see download status and retry")
        root = local_model_path(size)
        if root is None:
            raise RuntimeError("Speech download lacks required files")
        for name in ("model.bin", "config.json", "tokenizer.json"):
            entry = next(
                (file for file in metadata.siblings if file.rfilename == name), None
            )
            if entry is None:
                raise RuntimeError("Official speech revision lacks " + name)
            file = root / name
            if entry.size is not None and file.stat().st_size != entry.size:
                raise RuntimeError("Speech file size mismatch: " + name)
            lfs = entry.lfs
            expected = lfs.sha256 if lfs else entry.blob_id
            if not expected:
                raise RuntimeError("Missing upstream file integrity metadata: " + name)
            if lfs:
                actual = sha256(file)
            else:
                digest = hashlib.sha1()
                digest.update(f"blob {file.stat().st_size}\0".encode())
                with file.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                actual = digest.hexdigest()
            if actual != expected:
                raise RuntimeError("Speech checksum mismatch: " + name)
        return self.verify_whisper(size)

    def verify_whisper(self, size):
        import wave
        from .transcription import local_model_path
        from faster_whisper import WhisperModel

        path = local_model_path(size)
        if path is None:
            raise RuntimeError("Speech weights not present")
        sample = PATHS.cache / "model-test-silence.wav"
        sample.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(sample), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b"\0\0" * 16000)
        try:
            model = WhisperModel(
                str(path),
                device="cpu",
                compute_type="int8",
                cpu_threads=2,
                local_files_only=True,
            )
            segments, _ = model.transcribe(str(sample), beam_size=1)
            list(segments)
            del model
        finally:
            sample.unlink(missing_ok=True)
        self.record(
            "whisper:" + size,
            path=str(path),
            test="Real CPU inference on silence; speech accuracy not certified",
        )
        self.db.set_settings({"stt_model": size, "stt_enabled": True})
        return "Whisper CPU loading and inference completed (silence input, not speech-quality acceptance)."
