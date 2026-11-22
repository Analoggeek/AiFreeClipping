"""Drive the real CLIPOS GUI and capture every page with real content.

This is a documentation tool: it runs the actual application, imports a real
video, analyses it, generates clips, exports one and screenshots each page so
the interface can be shown with genuine data rather than placeholders.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from clipos.db.database import Database  # noqa: E402
from clipos.ui.fonts import ensure_fonts  # noqa: E402
from clipos.ui.main_window import MainWindow  # noqa: E402
from clipos.ui.theme import apply_theme  # noqa: E402

SHOTS = Path("/tmp/clipos_gui")
DB_PATH = Path("/tmp/clipos_gui.db")
SOURCE = ROOT / "testdata" / "demo_long.mp4"


def pump(app, n=40, dt=0.02):
    for _ in range(n):
        app.processEvents()
        time.sleep(dt)


def shot(window, name):
    path = SHOTS / f"{name}.png"
    window.grab().save(str(path))
    print(f"  captured {name}.png", flush=True)


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    for stale in DB_PATH.parent.glob("clipos_gui.db*"):
        stale.unlink()

    app = QApplication([])
    ensure_fonts()
    db = Database(DB_PATH)
    window = MainWindow(db)
    apply_theme(window, "dark")
    window.resize(1440, 900)
    window.show()
    pump(app)

    # ---------------------------------------------------------- 1. Home
    print("[1] Home")
    window.navigate("home")
    pump(app, 40)
    shot(window, "01_home")

    # ------------------------------------------------- 2. New Project
    print("[2] New Project")
    window.navigate("new")
    pump(app, 30)
    page = window.pages["new"]
    print("    new-page widgets:",
          [n for n in dir(page) if "path" in n.lower() or "edit" in n.lower()][:12])
    shot(window, "02_new_project")

    # ---------------------------------------------- 3. Import + analyse
    print("[3] Importing and analysing a real video")
    from clipos.video.pipeline import run_full_analysis

    from clipos.video.importer import import_local
    imported = import_local(SOURCE)
    project_id = db.create_project(
        name="Demo Podcast Episode",
        source_path=imported.path,
        duration=imported.duration,
        width=imported.width,
        height=imported.height,
        fps=imported.fps,
        has_audio=imported.has_audio,
        size_bytes=imported.size_bytes,
        thumbnail=imported.thumbnail,
        status="ready",
    )
    print(f"    imported {imported.path} ({imported.duration:.1f}s, "
          f"{imported.width}x{imported.height})")
    analysis = run_full_analysis(
        db, project_id,
        clip_count=10,
        duration_range="30-45",
        aspect="9:16",
        stt_model="base",
    )
    clips = db.list_clips(project_id)
    print(f"    project {project_id}: {len(clips)} clips generated")
    for c in clips[:3]:
        print(f"      #{c['id']} {c['title'][:40]!r} "
              f"engagement={c['engagement_score']} virality={c['virality_score']}")

    window.navigate("home")
    pump(app, 60, 0.05)
    shot(window, "03_home_with_data")

    # ------------------------------------------- 4. Auto Clip Studio
    print("[4] Auto Clip Studio")
    window.navigate("studio")
    pump(app, 30)
    studio = window.pages["studio"]
    studio.load_project(project_id)
    pump(app, 60)
    shot(window, "04_auto_clip_studio")

    # ------------------------------------------------ 5. My Projects
    print("[5] My Projects")
    window.navigate("projects")
    pump(app, 40)
    shot(window, "05_my_projects")

    # ------------------------------------------------ 6. Clip Library
    print("[6] Clip Library")
    window.navigate("library")
    pump(app, 40)
    shot(window, "06_clip_library")

    # -------------------------------------------------- 7. Templates
    print("[7] Templates")
    window.navigate("templates")
    pump(app, 30)
    shot(window, "07_templates")

    # ----------------------------------------------- 8. Caption Studio
    print("[8] Caption Studio")
    window.navigate("captions")
    pump(app, 40)
    shot(window, "08_caption_studio")

    # ------------------------------------------------ 9. Preview Editor
    print("[9] Preview Editor")
    window.navigate("editor")
    pump(app, 30)
    editor = window.pages["editor"]
    editor.load_project(project_id)
    pump(app, 60)
    if clips:
        editor.load_clip(clips[0]["id"])
        pump(app, 80)
    print(f"    editor segments: {len(editor.timeline.segments)}")
    shot(window, "09_preview_editor")

    # ------------------------------------------------ 10. Export Center
    print("[10] Export Center")
    window.navigate("export")
    pump(app, 40)
    shot(window, "10_export_center")

    # ---------------------------------------------------- 11. AI Models
    print("[11] AI Models")
    window.navigate("models")
    pump(app, 40)
    shot(window, "11_ai_models")

    # ---------------------------------------------------- 12. Settings
    print("[12] Settings")
    window.navigate("settings")
    pump(app, 40)
    shot(window, "12_settings")

    # ---------------------------------------------- 13. Light theme
    print("[13] Light theme")
    apply_theme(window, "light")
    window.navigate("home")
    pump(app, 40)
    shot(window, "13_home_light")
    window.navigate("studio")
    pump(app, 40)
    shot(window, "14_studio_light")
    apply_theme(window, "dark")
    pump(app, 30)

    print("\nDONE")
    print(json.dumps({"project": project_id, "clips": len(clips)}))


if __name__ == "__main__":
    main()
