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
            return result
        finally:
            db.close()
