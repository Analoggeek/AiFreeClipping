"""Home dashboard: statistics, quick actions, recent projects, system status."""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ...core.hardware import detect_hardware, memory_pressure
from ...core.logging_setup import get_logger
from ..theme import Metrics
from ..widgets.common import Card, SectionHeader, StatTile, format_duration, format_size
from .base import BasePage

log = get_logger(__name__)


class HomePage(BasePage):
    page_title = "Home"
    page_subtitle = "Turn long videos into ready-to-post shorts — entirely on your device."

    def __init__(self, window) -> None:
        self._sys_thread: threading.Thread | None = None
        self._sys_data: dict = {}
        self._recent_container: QVBoxLayout | None = None
        super().__init__(window)

    # -- layout ------------------------------------------------------------------
    def build(self) -> None:
        welcome=Card();welcome.setObjectName('DashboardHero')
        title=QLabel('Your next great edit starts here.');title.setObjectName('HeroTitle');title.setWordWrap(True);welcome.add(title)
        welcome.add(QLabel('Ai clipping PRO 3.5 · Local intelligence. Real timelines. Your media stays yours.'))
        self.content_layout.addWidget(welcome)
        director=Card();director.add(SectionHeader('AI Director','Uses your selected local Gemma/Ollama weights and the active project. Review every proposed change.'))
        self.instruction=QLineEdit();self.instruction.setPlaceholderText('Create 10 gaming shorts; gameplay above and facecam below…');self.instruction.setMaxLength(2000);director.add(self.instruction)
        propose=QPushButton('Open director & propose edits');propose.setObjectName('Primary');propose.clicked.connect(self._director);director.add(propose)
        self.content_layout.addWidget(director)
        # --- quick actions -------------------------------------------------------
        actions = Card()
        row = QHBoxLayout()
        row.setSpacing(Metrics.md)

        self.btn_new = QPushButton("✦   Create New Project")
        self.btn_new.setObjectName("BigAction")
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.clicked.connect(lambda: self.navigate("new"))
        row.addWidget(self.btn_new, 2)

        self.btn_import = QPushButton("↓   Import Video")
        self.btn_import.setObjectName("Primary")
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(lambda: self.navigate("new"))
        row.addWidget(self.btn_import, 1)

        self.btn_link = QPushButton("↗   Paste Video Link")
        self.btn_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_link.clicked.connect(lambda: self.navigate("new"))
        row.addWidget(self.btn_link, 1)

        actions.add_layout(row)
        self.content_layout.addWidget(actions)

        # --- statistics ----------------------------------------------------------
        stats_row = QHBoxLayout()
        stats_row.setSpacing(Metrics.md)
        self.tiles: dict[str, StatTile] = {}

        def add_tile(key: str, icon: str, label: str, accent: str) -> None:
            tile = StatTile(icon, label, "0", accent)
            self.tiles[key] = tile
            stats_row.addWidget(tile)

        add_tile("projects", "◧", "Local Projects", "#0a84ff")
        add_tile("clips", "✂", "Shorts Generated", "#5e5ce6")
        add_tile("exports", "↓", "Exported Clips", "#32d74b")
        add_tile("storage", "▤", "Storage Used", "#ff9f0a")
        self.content_layout.addLayout(stats_row)

        # --- recent projects + system status --------------------------------------
        grid = QGridLayout()
        grid.setSpacing(Metrics.md)

        recent = Card()
        recent_header = SectionHeader("Recent Projects", "Pick up where you left off")
        self.btn_all_projects = QPushButton("View All")
        self.btn_all_projects.setObjectName("Ghost")
        self.btn_all_projects.clicked.connect(lambda: self.navigate("projects"))
        recent_header.add_action(self.btn_all_projects)
        recent.add(recent_header)

        self.recent_list = QWidget()
        self._recent_container = QVBoxLayout(self.recent_list)
        self._recent_container.setSpacing(Metrics.sm)
        self._recent_container.setContentsMargins(0, Metrics.sm, 0, 0)
        recent.add(self.recent_list)
        grid.addWidget(recent, 0, 0, 1, 2)

        status = Card()
        status.add(SectionHeader("System Status", "Detected on this machine"))
        self.status_body = QWidget()
        self._status_layout = QVBoxLayout(self.status_body)
        self._status_layout.setSpacing(Metrics.sm)
        self._status_layout.setContentsMargins(0, Metrics.sm, 0, 0)
        status.add(self.status_body)
        grid.addWidget(status, 0, 2)

        self.content_layout.addLayout(grid)

        # --- processing queue ------------------------------------------------------
        queue_card = Card()
        queue_card.add(SectionHeader("Processing Queue", "Active and queued work"))
        self.queue_body = QWidget()
        self._queue_layout = QVBoxLayout(self.queue_body)
        self._queue_layout.setSpacing(Metrics.xs)
        self._queue_layout.setContentsMargins(0, Metrics.sm, 0, 0)
        queue_card.add(self.queue_body)
        self.content_layout.addWidget(queue_card)

        # --- AI model status --------------------------------------------------------
        model_card = Card()
        model_card.add(SectionHeader("AI Models", "Offline model availability"))
        self.model_body = QWidget()
        self._model_layout = QVBoxLayout(self.model_body)
        self._model_layout.setSpacing(Metrics.xs)
        self._model_layout.setContentsMargins(0, Metrics.sm, 0, 0)
        model_card.add(self.model_body)
        self.content_layout.addWidget(model_card)

        self._start_system_monitor()

    # -- data --------------------------------------------------------------------
    def _director(self):
        workflow=self.window._ensure_page('workflow')
        workflow.agent_instruction.setText(self.instruction.text())
        self.window.navigate('workflow');workflow.go(0)
        workflow._propose_agent_plan()

    def refresh(self) -> None:
        stats = self.db.stats()
        self.tiles["projects"].set_value(str(stats["projects"]))
        self.tiles["clips"].set_value(str(stats["clips"]))
        self.tiles["exports"].set_value(str(stats["exports"]))
        self.tiles["storage"].set_value(format_size(stats["storage_bytes"]))
        self._refresh_recent()
        self._refresh_models()
        self._refresh_queue()

    def _refresh_recent(self) -> None:
        if self._recent_container is None:
            return
        while self._recent_container.count():
            item = self._recent_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        projects = self.db.list_projects()[:4]
        if not projects:
            empty = QLabel("No projects yet — import a video to get started.")
            empty.setObjectName("CardSubtitle")
            self._recent_container.addWidget(empty)
            return

        for p in projects:
            row = QWidget()
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(Metrics.sm, Metrics.xs, Metrics.sm, Metrics.xs)
            rl.setSpacing(Metrics.md)

            name = QLabel(p["name"])
            name.setObjectName("CardTitle")
            rl.addWidget(name)

            meta = QLabel(
                f"{format_duration(p['duration'] or 0)} · "
                f"{p['width']}×{p['height']} · {p['status']}"
            )
            meta.setObjectName("CardSubtitle")
            rl.addWidget(meta)
            rl.addStretch(1)

            open_btn = QPushButton("Open")
            open_btn.setObjectName("Ghost")
            open_btn.clicked.connect(lambda _=False, pid=p["id"]: self.window.open_project(pid))
            rl.addWidget(open_btn)

            self._recent_container.addWidget(row)

    def _refresh_models(self) -> None:
        while self._model_layout.count():
            item = self._model_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        from ...ai.transcription import WHISPER_SIZES, model_installed

        rows: list[tuple[str, str, bool]] = []
        for size, (repo, approx) in WHISPER_SIZES.items():
            installed = model_installed(size)
            rows.append((f"Whisper {size}", approx, installed))
        from ...core.resources import resource_file
        rows.append(("YuNet face detector", "bundled weights", resource_file('models','face_detection_yunet_2023mar.onnx').is_file()))

        for name, size, ok in rows:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(Metrics.sm)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {'#32d74b' if ok else '#6e6e78'}; font-size: 11px;")
            rl.addWidget(dot)
            lbl = QLabel(name)
            rl.addWidget(lbl)
            rl.addStretch(1)
            state = QLabel("Installed" if ok else f"Not downloaded · {size}")
            state.setObjectName("CardSubtitle")
            rl.addWidget(state)
            self._model_layout.addWidget(row)

        manage = QPushButton("Manage Models")
        manage.setObjectName("Ghost")
        manage.clicked.connect(lambda: self.navigate("models"))
        self._model_layout.addWidget(manage)

    def _refresh_queue(self) -> None:
        while self._queue_layout.count():
            item = self._queue_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        pending = self.db.query(
            "SELECT id, project_id, output_path, status FROM exports "
            "WHERE status IN ('pending','rendering') ORDER BY id DESC LIMIT 5"
        )
        if not pending:
            lbl = QLabel("Queue is empty — nothing running.")
            lbl.setObjectName("CardSubtitle")
            self._queue_layout.addWidget(lbl)
            return
        for e in pending:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            name = QLabel(Path(e["output_path"]).name or f"Export #{e['id']}")
            rl.addWidget(name)
            rl.addStretch(1)
            st = QLabel(e["status"])
            st.setObjectName("CardSubtitle")
            rl.addWidget(st)
            self._queue_layout.addWidget(row)

    # -- system monitor ----------------------------------------------------------
    def _start_system_monitor(self) -> None:
        def worker() -> None:
            while True:
                try:
                    prof = detect_hardware()
                    self._sys_data = {
                        "cpu": prof.cpu_name,
                        "threads": prof.cpu_threads,
                        "ram_total": prof.ram_total_mb,
                        "ram_used": prof.ram_available_mb,
                        "gpu": prof.gpu.label,
                        "vendor": prof.gpu.vendor,
                        "encoders": list(prof.ffmpeg_encoders.keys()),
                        "pressure": memory_pressure(),
                    }
                except Exception:
                    pass
                time.sleep(3.0)

        self._sys_thread = threading.Thread(target=worker, daemon=True)
        self._sys_thread.start()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._render_status)
        self._status_timer.start(1500)
        self._render_status()

    def _render_status(self) -> None:
        while self._status_layout.count():
            item = self._status_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        d = self._sys_data
        if not d:
            lbl = QLabel("Detecting hardware…")
            lbl.setObjectName("CardSubtitle")
            self._status_layout.addWidget(lbl)
            return

        def row(icon: str, name: str, value: str, color: str = "#a8a8b0") -> None:
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 2, 0, 2)
            hl.setSpacing(Metrics.sm)
            ic = QLabel(icon)
            hl.addWidget(ic)
            nm = QLabel(name)
            nm.setObjectName("CardSubtitle")
            hl.addWidget(nm)
            hl.addStretch(1)
            vl = QLabel(value)
            vl.setStyleSheet(f"color: {color}; font-size: 11px;")
            hl.addWidget(vl)
            self._status_layout.addWidget(w)

        row("▣", "CPU", f"{d['threads']} threads")
        row("◍", "RAM", f"{d['ram_total'] // 1024} GB total · "
                        f"{int(d['pressure'] * 100)}% used",
            "#ff9f0a" if d.get("pressure", 0) > 0.85 else "#32d74b")
        row("◆", "GPU", d.get("gpu", "unknown"))
        accel = []
        for e in d.get("encoders", []):
            if e.endswith("nvenc"):
                accel.append("NVENC")
            elif "videotoolbox" in e:
                accel.append("VideoToolbox")
            elif "qsv" in e:
                accel.append("QuickSync")
        row("◈", "Acceleration", ", ".join(accel) if accel else "CPU only", "#32d74b")
