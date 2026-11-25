"""Explicit official validation asset download for native/frozen CI checks."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from clipos.ai.model_manager import YOLOX
    from clipos.core.verified_download import download

    path = download(
        YOLOX["url"],
        ROOT / "build" / "yolox-validation.onnx",
        YOLOX["sha256"],
        YOLOX["size"],
    )
    print(path)
