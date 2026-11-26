"""Explicit verification entry point; never executed during normal app startup."""

import os
from pathlib import Path
import tempfile


def verify():
    import onnxruntime as ort
    from ..ai.visual_analysis import cv2_module
    from ..ai.model_manager import ModelManager
    from ..db.database import Database

    cv2 = cv2_module()
    if cv2 is None or not hasattr(cv2, "CascadeClassifier"):
        raise RuntimeError("Headless OpenCV decoder/detector APIs unavailable")
    if "CPUExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("ONNX Runtime CPU provider unavailable")
    with tempfile.TemporaryDirectory(prefix="clipos-runtime-check-") as folder:
        db = Database(Path(folder) / "runtime.db")
        try:
            manager = ModelManager(db)
            tracking = manager.test_bytetrack()
            weights = os.environ.get("CLIPOS_VERIFY_YOLOX_WEIGHTS", "")
            result = {"status": "ok", "bytetrack": tracking, "onnx_cpu": True}
            if weights:
                result["yolox"] = manager.verify_yolox(weights)
            else:
                result["yolox"] = (
                    "Not tested: no explicit validation weight path supplied"
                )
            import subprocess
            from .ffmpeg import require_ffmpeg
            from ..video.multitrack import MultitrackProject
            from ..video.live_playback import stream_frames
            from ..captions.original_styles import original_style_keys

            source = Path(folder) / "stream-check.mp4"
            subprocess.run(
                [
                    require_ffmpeg(),
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=160x90:r=10:d=0.3",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=0.3",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(source),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            project = MultitrackProject(width=160, height=90, fps=10)
            project.import_media(source)
            counts = {"video": 0, "audio": 0}
            for kind, _, payload in stream_frames(project, max_size=160):
                counts[kind] += 1
            if not counts["video"] or not counts["audio"]:
                raise RuntimeError(
                    "Packaged compositor did not produce video and audio"
                )
            result["composited_stream"] = counts
            result["original_caption_presets"] = len(original_style_keys())
            result["physical_audio_device"] = (
                "Not tested by this headless runtime check"
            )
            return result
        finally:
            db.close()
