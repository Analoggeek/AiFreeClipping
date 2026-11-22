"""My Projects: list, rename, duplicate, delete and reopen projects."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from ...core.logging_setup import get_logger
from ..theme import Metrics
from ..widgets.common import Card, SectionHeader, VideoThumbnail, format_duration, format_size
from .base import BasePage

log = get_logger(__name__)


class MyProjectsPage(BasePage):
    page_title = "My Projects"
    page_subtitle = "Every project is stored locally in your CLIPOS folder."

    def __init__(self, window) -> None:
        self._rows: list[tuple] = []
        super().__init__(window)

    def build(self) -> None:
        card = Card()
        header = SectionHeader("All Projects", "")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search projects…")
        self.search.setMaximumWidth(240)
        self.search.textChanged.connect(self.refresh)
        header.add_action(self.search)
        card.add(header)

        self.list_body = QWidget()
        self._list_layout = QVBoxLayout(self.list_body)
        self._list_layout.setSpacing(Metrics.sm)
        self._list_layout.setContentsMargins(0, Metrics.sm, 0, 0)
        card.add(self.list_body)
        self.content_layout.addWidget(card)

    def refresh(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows = []

        query = self.search.text().strip().lower()
        projects = self.db.list_projects(include_archived=True)
        if query:
            projects = [p for p in projects if query in p["name"].lower()]

        if not projects:
            lbl = QLabel("No projects yet." if not query else "No projects match your search.")
            lbl.setObjectName("CardSubtitle")
            self._list_layout.addWidget(lbl)
            return

        for p in projects:
            self._list_layout.addWidget(self._project_row(p))

    def _project_row(self, p) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(Metrics.sm, Metrics.sm, Metrics.sm, Metrics.sm)
        lay.setSpacing(Metrics.md)

        thumb = VideoThumbnail(width=110)
        thumb.set_video(p["thumbnail"], p["duration"])
        lay.addWidget(thumb)

        info = QVBoxLayout()
        info.setSpacing(1)
        name = QLabel(p["name"])
        name.setStyleSheet("font-weight: 650; font-size: 13px;")
        info.addWidget(name)

        meta = QLabel(
            f"{format_duration(p['duration'])} · {p['width']}×{p['height']} · "
            f"{format_size(p['size_bytes'])} · {p['status']} · "
            f"{p['aspect_ratio']} · {p['clip_count']} clips"
        )
        meta.setObjectName("CardSubtitle")
        info.addWidget(meta)
        lay.addLayout(info, 1)

        open_btn = QPushButton("Open")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(lambda _=False, pid=p["id"]: self.window.open_project(pid))
        lay.addWidget(open_btn)

        rename = QPushButton("Rename")
        rename.setObjectName("Ghost")
        rename.clicked.connect(lambda _=False, pid=p["id"]: self._rename(pid))
        lay.addWidget(rename)

        dup = QPushButton("Duplicate")
        dup.setObjectName("Ghost")
        dup.clicked.connect(lambda _=False, pid=p["id"]: self._duplicate(pid))
        lay.addWidget(dup)

        delete = QPushButton("Delete")
        delete.setObjectName("Ghost")
        delete.setStyleSheet("QPushButton { color: #ff453a; }")
        delete.clicked.connect(lambda _=False, pid=p["id"], nm=p["name"]: self._delete(pid, nm))
        lay.addWidget(delete)

        return row

    def _rename(self, project_id: int) -> None:
        p = self.db.get_project(project_id)
        if not p:
            return
        new_name, ok = QInputDialog.getText(self, "Rename project", "Name:", text=p["name"])
        if ok and new_name.strip():
            self.db.update_project(project_id, name=new_name.strip())
            self.window.notify("Project renamed")
            self.refresh()
            self.window.refresh_all()

    def _duplicate(self, project_id: int) -> None:
        new_id = self.db.duplicate_project(project_id)
        if new_id:
            self.window.notify("Project duplicated")
            self.refresh()

    def _delete(self, project_id: int, name: str) -> None:
        reply = QMessageBox.question(
            self, "Delete project",
            f"Delete '{name}' and all of its generated clips?\n\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        p = self.db.get_project(project_id)
        self.db.delete_project(project_id)
        # Remove the project's working folder
        if p and p["source_path"]:
            try:
                from ...core.config import PATHS

                folder = PATHS.projects / str(project_id)
                if folder.exists():
                    import shutil

                    shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass
        self.window.notify("Project deleted")
        self.refresh()
        self.window.refresh_all()
