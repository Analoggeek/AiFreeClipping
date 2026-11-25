"""The CLIPOS main window: macOS-style title bar, sidebar navigation, page stack."""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStyle, QSizePolicy, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from ..core.config import PATHS
from ..core.logging_setup import get_logger
from ..db.database import Database, get_db
from .theme import Metrics, PALETTES, apply_theme
from .widgets.common import Toast

log = get_logger(__name__)


class NavButton(QPushButton):
    """A sidebar navigation item with an icon and label."""

    def __init__(self, icon: str, label: str, key: str, parent=None) -> None:
        super().__init__(label, parent)
        icons = {
            "workflow": QStyle.StandardPixmap.SP_MediaPlay,
            "home": QStyle.StandardPixmap.SP_ComputerIcon,
            "new": QStyle.StandardPixmap.SP_FileDialogNewFolder,
            "studio": QStyle.StandardPixmap.SP_MediaPlay,
            "projects": QStyle.StandardPixmap.SP_DirIcon,
            "library": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "templates": QStyle.StandardPixmap.SP_FileDialogListView,
            "captions": QStyle.StandardPixmap.SP_FileDialogContentsView,
            "editor": QStyle.StandardPixmap.SP_MediaSeekForward,
            "export": QStyle.StandardPixmap.SP_DialogSaveButton,
            "models": QStyle.StandardPixmap.SP_DriveHDIcon,
            "settings": QStyle.StandardPixmap.SP_FileDialogInfoView,
        }
        from .widgets.icons import navigation_icon
        self.setIcon(navigation_icon(key))
        self.setIconSize(QSize(16, 16))
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(32)
        self.key = key
        self.setToolTip(label)


class TitleBar(QFrame):
    """The macOS-style traffic-light title bar."""

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(Metrics.titlebar_height)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 12, 0)
        lay.setSpacing(Metrics.sm)

        # Traffic lights
        self._lights = QHBoxLayout()
        self._lights.setSpacing(8)
        self.red = self._light("#ff5f57")
        self.yellow = self._light("#febc2e")
        self.green = self._light("#28c840")
        self._lights.addWidget(self.red)
        self._lights.addWidget(self.yellow)
        self._lights.addWidget(self.green)
        lay.addLayout(self._lights)

        lay.addStretch(1)

        self.title = QLabel("CLIPOS")
        self.title.setObjectName("TitleBarTitle")
        lay.addWidget(self.title)

        lay.addStretch(1)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("TitleBarSubtitle")
        lay.addWidget(self.subtitle)

        self._min_btn = self._square_button("–", self.minimize_requested.emit)
        self._max_btn = self._square_button("⤢", self.maximize_requested.emit)
        self._close_btn = self._square_button("✕", self.close_requested.emit)
        lay.addWidget(self._min_btn)
        lay.addWidget(self._max_btn)
        lay.addWidget(self._close_btn)

    def _light(self, color: str) -> QPushButton:
        b = QPushButton()
        b.setFixedSize(12, 12)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip("")
        b.setStyleSheet(
            f"QPushButton {{ background-color: {color}; border: none; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: {color}; }}"
        )
        return b

    def _square_button(self, glyph: str, handler) -> QPushButton:
        b = QPushButton(glyph)
        b.setFixedSize(28, 22)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #a8a8b0;"
            " font-size: 12px; border-radius: 5px; }"
            "QPushButton:hover { background: #33333a; color: #f2f2f5; }"
        )
        b.clicked.connect(handler)
        return b


class MainWindow(QMainWindow):
    """The application shell with shared project and preference events."""
    project_changed = Signal(int)
    settings_changed = Signal()
    data_changed = Signal()

    def __init__(self, db: Database | None = None) -> None:
        super().__init__()
        self.db = db or get_db()
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, NavButton] = {}
        self.current_key = "home"
        self._busy = False

        self.setWindowTitle("CLIPOS 3.1.1 — Video Clip Editor")
        self.setMinimumSize(1180, 760)
        self.resize(1440, 900)

        self._build_ui()
        self._build_shortcuts()
        self._apply_settings()
        self.navigate("workflow")

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready — everything stays on this device")

        self.toast = Toast(self)
        from .widgets.usage import UsageWorker
        self.usage_label = QLabel('Measuring real hardware usage…')
        self.status.addPermanentWidget(self.usage_label)
        self.usage_worker = UsageWorker(self)
        self.usage_worker.sample.connect(self.usage_label.setText)
        self.usage_worker.start()
        self.data_changed.connect(self._refresh_visible)

    # -- construction ------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar()
        self.titlebar.minimize_requested.connect(self.showMinimized)
        self.titlebar.maximize_requested.connect(self.toggleMaximized)
        self.titlebar.close_requested.connect(self.close)
        root.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        body.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.stack.setObjectName("Stack")
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self._register_pages()

    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(Metrics.sidebar_width)

        lay = QVBoxLayout(bar)
        lay.setContentsMargins(10, 12, 10, 12)
        lay.setSpacing(3)

        brand = QLabel("CLIPOS")
        brand.setObjectName("SidebarBrand")
        lay.addWidget(brand)

        tag = QLabel("AI Clipping Studio")
        tag.setObjectName("CardSubtitle")
        lay.addWidget(tag)
        lay.addSpacing(12)

        nav_defs = [
            ("workflow", "", "Create clips"),
            ("projects", "", "Projects"),
            ("library", "", "Clip library"),
            ("editor", "", "Advanced editor"),
            ("longform", "", "Automatic long-form"),
            ("templates", "", "Presets & captions"),
            ("models", "", "AI models"),
            ("settings", "", "Settings"),
        ]
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for key, icon, label in nav_defs:
            btn = NavButton(icon, label, key)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self._nav_group.addButton(btn)
            self.nav_buttons[key] = btn
            lay.addWidget(btn)

        lay.addStretch(1)

        self.privacy = QLabel("▣  Offline-first\nYour media never leaves\nthis device.")
        self.privacy.setObjectName("CardSubtitle")
        self.privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.privacy)

        self.storage_label = QLabel("")
        self.storage_label.setObjectName("CardSubtitle")
        self.storage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.storage_label)

        return bar

    def _register_pages(self) -> None:
        from .pages.auto_clip_studio import AutoClipStudioPage
        from .pages.ai_models import AiModelsPage
        from .pages.caption_studio import CaptionStudioPage
        from .pages.clip_library import ClipLibraryPage
        from .pages.editor import EditorPage
        from .pages.longform import LongformPage
        from .pages.export_center import ExportCenterPage
        from .pages.workflow import WorkflowPage
        from .pages.home import HomePage
        from .pages.my_projects import MyProjectsPage
        from .pages.new_project import NewProjectPage
        from .pages.settings_page import SettingsPage
        from .pages.templates import TemplatesPage

        page_classes = [
            ("workflow", WorkflowPage),
            ("projects", MyProjectsPage),
            ("library", ClipLibraryPage),
            ("templates", TemplatesPage),
            ("captions", CaptionStudioPage),
            ("editor", EditorPage),
            ("longform", LongformPage),
            ("export", ExportCenterPage),
            ("models", AiModelsPage),
            ("settings", SettingsPage),
        ]
        self._page_classes = dict(page_classes)
        # Build the main workflow only. Inactive editors/settings previously
        # probed devices, allocated previews and opened databases at startup.
        self._ensure_page('workflow')

    def _ensure_page(self,key):
        if key not in self.pages and key in self._page_classes:
            page=self._page_classes[key](self)
            self.pages[key]=page
            self.stack.addWidget(page)
            if hasattr(page,'navigated'):
                page.navigated.connect(self._on_page_navigated)
        return self.pages.get(key)

    def _build_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+N", lambda: self.navigate("new")),
            ("Ctrl+O", lambda: self.navigate("new")),
            ("Ctrl+1", lambda: self.navigate("home")),
            ("Ctrl+2", lambda: self.navigate("studio")),
            ("Ctrl+3", lambda: self.navigate("projects")),
            ("Ctrl+4", lambda: self.navigate("library")),
            ("Ctrl+E", lambda: self.navigate("export")),
            ("Ctrl+,", lambda: self.navigate("settings")),
            ("Ctrl+W", self.close),
            ("Ctrl+Q", self.close),
        ]
        for seq, fn in shortcuts:
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)

    # -- settings ----------------------------------------------------------------
    def _apply_settings(self) -> None:
        settings = self.db.get_settings()
        theme = settings.get("theme", "dark")
        apply_theme(self, theme)
        self._update_storage_label()

    def _update_storage_label(self) -> None:
        from .widgets.common import format_size

        stats = self.db.stats()
        self.storage_label.setText(f"Storage used · {format_size(stats['storage_bytes'])}")

    # -- navigation --------------------------------------------------------------
    def navigate(self, key: str) -> None:
        requested = key
        key = {"gaming":"workflow", "home":"workflow", "new":"workflow", "studio":"workflow", "export":"workflow"}.get(key,key)
        if self._ensure_page(key) is None:
            return
        self.current_key = key
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        if key == 'editor' and getattr(self,'active_project',None) and page.project_id != self.active_project:
            page.load_project(self.active_project)
        btn = self.nav_buttons.get(key)
        if btn:
            btn.setChecked(True)
        self.titlebar.subtitle.setText(getattr(page, "subtitle_text", ""))
        if key == "workflow" and requested in ("home", "new", "studio", "export"):
            page.go({"home":0,"new":0,"studio":2,"export":3}[requested])
        if hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception as exc:
                log.warning("page refresh failed for %s: %s", key, exc)
                self.db.log_error(f"refresh:{key}", str(exc))

    def _on_page_navigated(self, key: str) -> None:
        self.navigate(key)

    def toggleMaximized(self) -> None:  # noqa: N802
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # -- helpers for pages ---------------------------------------------------------
    def notify(self, message: str, msec: int = 3200) -> None:
        self.toast.show_message(message, msec)

    def set_busy(self, busy: bool, message: str = "") -> None:
        """Enable/disable navigation while a long task runs."""
        self._busy = busy
        for btn in self.nav_buttons.values():
            btn.setEnabled(not busy)
        if message:
            self.status.showMessage(message)
        elif not busy:
            self.status.showMessage("Ready — everything stays on this device")

    def open_project(self, project_id: int) -> None:
        """Open a project in the Auto Clip Studio page."""
        page = self.pages.get("workflow")
        if page is not None:
            page.load_project(project_id)
            self.navigate("workflow")
            page.go(1)

    def set_active_project(self, project_id):
        if getattr(self, 'active_project', None) == project_id:
            return
        self.active_project = project_id
        self.db.set_setting('active_project', project_id)
        self.project_changed.emit(project_id)

    def _refresh_visible(self):
        page = self.pages.get(self.current_key)
        if page and self.current_key != 'workflow':
            page.refresh()
        self._update_storage_label()

    def open_in_editor(self, project_id: int, clip_id: int | None = None) -> None:
        """Open a project (and optionally a clip) in the Preview Editor."""
        page = self.pages.get("editor")
        if page is None:
            return
        self.set_active_project(project_id)
        page.load_project(project_id)
        if clip_id is not None:
            page.load_clip(clip_id)
        self.navigate("editor")

    def refresh_all(self) -> None:
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                try:
                    page.refresh()
                except Exception:
                    pass
        self._update_storage_label()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy:
            reply = QMessageBox.question(
                self, "Processing in progress",
                "A task is still running. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        # Let every page stop its worker thread cleanly so a render is never
        # killed mid-write and no QThread is destroyed while still running.
        for page in self.pages.values():
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception as exc:
                    log.warning("page shutdown failed: %s", exc)
        if hasattr(self, 'usage_worker'):
            self.usage_worker.stop_event.set()
            self.usage_worker.wait(3000)
        event.accept()
