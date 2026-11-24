"""CLIPOS — AI Automatic Video Clipping Studio.

Application entry point.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the bundled resources are importable when frozen with PyInstaller.
if getattr(sys, "frozen", False):
    _root = Path(sys._MEIPASS)
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))


def _prepare_environment() -> None:
    """Make bundled FFmpeg discoverable before anything imports it."""
    from clipos.core.resources import resource_dir

    ffmpeg = resource_dir("ffmpeg")
    if ffmpeg.exists():
        # Point at the directory that holds every bundled resource folder.
        os.environ.setdefault("CLIPOS_RESOURCES", str(ffmpeg.parent))


def main() -> int:
    _prepare_environment()
    if len(sys.argv)>1 and sys.argv[1]=='--diarize-worker':
        from clipos.ai.diarization import worker_main
        return worker_main(sys.argv[2:])

    from clipos.core.config import PATHS
    from clipos.core.logging_setup import setup_logging

    PATHS.ensure()
    log_file = setup_logging()
    log = __import__("logging").getLogger("clipos")

    log.info("CLIPOS starting — data dir: %s", PATHS.root)

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon, QPixmap
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        print(
            "CLIPOS could not start: the Qt interface could not be loaded.\n"
            f"  {exc}\n\n"
            "Install the GUI dependencies with:\n"
            "  pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    from clipos import APP_NAME, __version__
    from clipos.db.database import get_db
    from clipos.ui.fonts import ensure_fonts
    from clipos.ui.main_window import MainWindow
    from clipos.ui.theme import apply_theme

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("CLIPOS")

    ensure_fonts()

    # The caption styles are built before the application exists, so the
    # font they name is only a guess until now.
    try:
        from clipos.captions.caption_engine import resolve_style_fonts

        resolve_style_fonts()
    except Exception as exc:
        log.warning("could not settle the caption font: %s", exc)

    db = get_db()
    settings = db.get_settings()
    apply_theme(app, settings.get("theme", "dark"))

    from clipos.core.resources import resource_file

    for name in ("icons/app_icon.png", "icons/app.png"):
        candidate = resource_file(*name.split("/"))
        if candidate and candidate.exists():
            app.setWindowIcon(QIcon(str(candidate)))
            break

    window = MainWindow(db)
    window.show()

    # Reopen the last project when the user asked for it
    if settings.get("restore_on_launch", "1") == "1":
        projects = db.list_projects()
        if projects:
            try:
                window.open_project(projects[0]["id"])
                window.navigate("studio")
            except Exception as exc:
                log.warning("could not restore the last project: %s", exc)

    log.info("CLIPOS ready — logs at %s", log_file)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
