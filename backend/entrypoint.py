"""PyInstaller entry point for the bundled local engine."""
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Make the bundled ffmpeg/ffprobe discoverable by imageio-ffmpeg and our own resolver.
bundle_dir = Path(getattr(sys, "_MEIPASS", str(backend_dir)))
for candidate in (bundle_dir, Path(sys.executable).parent):
    if str(candidate) not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")

from app.main import main  # noqa: E402

if __name__ == "__main__":
    main()
