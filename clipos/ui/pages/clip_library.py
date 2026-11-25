"""Generated local media library with an integrated assembly queue route."""

from pathlib import Path
import shutil

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)
from .base import BasePage
from ..widgets.common import Card, SectionHeader, VideoThumbnail, format_duration


class ClipLibraryPage(BasePage):
    page_title = "Clip Library"
    page_subtitle = (
        "Preview, save or remove generated clips. Files stay on this device."
    )

    def build(self):
        card = Card()
        header = SectionHeader("Generated clips", "")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search clips…")
        self.search.textChanged.connect(self.refresh)
        header.add_action(self.search)
        editor = QPushButton("Open Clip Queue & Editor")
        editor.clicked.connect(lambda: self.navigate("studio"))
        header.add_action(editor)
        card.add(header)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        card.add(self.grid_host)
        self.content_layout.addWidget(card)

    def refresh(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        query = self.search.text().strip().lower()
        clips = [
            dict(c)
            for c in self.db.list_clips()
            if c["output_path"] and query in (c["title"] or "").lower()
        ]
        exports = {}
        for e in self.db.list_exports(limit=10000):
            exports.setdefault(e["clip_id"], dict(e))
        if not clips:
            empty = QLabel(
                "No generated clips yet. Choose Video Clipper to create some."
            )
            empty.setWordWrap(True)
            self.grid.addWidget(empty, 0, 0)
            return
        for index, clip in enumerate(clips):
            self.grid.addWidget(
                self._card(clip, exports.get(clip["id"], {})),
                index // (2 if self.width() >= 1000 else 1),
                index % (2 if self.width() >= 1000 else 1),
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "grid"):
            widgets = []
            while self.grid.count():
                item = self.grid.takeAt(0)
                if item.widget():
                    widgets.append(item.widget())
            columns = 2 if self.width() >= 1000 else 1
            for index, widget in enumerate(widgets):
                self.grid.addWidget(widget, index // columns, index % columns)

    def _card(self, clip, export):
        card = Card()
        thumb = VideoThumbnail(width=320)
        thumb.setMaximumHeight(180)
        thumb.set_video(clip["thumbnail_path"], clip["duration"])
        card.add(thumb)
        title = QLabel(clip["title"] or "Untitled clip")
        title.setWordWrap(True)
        card.add(title)
        width, height = export.get("width"), export.get("height")
        resolution = (
            f"{width}×{height}"
            if width and height
            else "Resolution unavailable for legacy output"
        )
        card.add(
            QLabel(
                f"{format_duration(export.get('duration') or clip['duration'])} · {resolution} · {clip['aspect_ratio']}"
            )
        )
        path = Path(clip["output_path"])
        exists = path.is_file()
        if not exists:
            card.add(
                QLabel("Output file missing. Re-generate from the original recording.")
            )
        row = QHBoxLayout()
        for text, action in [
            (
                "Preview",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))),
            ),
            ("Save clip…", lambda: self._save(path)),
            (
                "Open output folder",
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))),
            ),
        ]:
            button = QPushButton(text)
            button.setEnabled(exists)
            button.clicked.connect(action)
            row.addWidget(button)
        card.add_layout(row)
        delete = QPushButton("Delete clip…")
        delete.clicked.connect(lambda: self._delete(clip))
        card.add(delete)
        return card

    def _save(self, path):
        target, _ = QFileDialog.getSaveFileName(
            self, "Save generated clip", path.name, "MP4 video (*.mp4)"
        )
        if not target:
            return
        destination = Path(target)
        if destination.resolve() == path.resolve():
            return
        try:
            shutil.copy2(path, destination)
            self.window.notify("Clip saved to " + str(destination))
        except OSError as exc:
            self.window.notify("Could not save clip: " + str(exc), 7000)

    def _delete(self, clip):
        if (
            QMessageBox.question(
                self,
                "Delete generated clip?",
                "Delete this generated output and its library record? The original source recording and copies saved elsewhere are preserved.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        source = self.db.get_project(clip["project_id"])
        output = Path(clip["output_path"])
        if source and output.resolve() == Path(source["source_path"]).resolve():
            self.window.notify("Refusing to delete original source media")
            return
        shared = self.db.query(
            "SELECT id FROM clips WHERE output_path=? AND id<>?",
            (str(output), clip["id"]),
        )
        try:
            if output.is_file() and not shared:
                output.unlink()
            self.db.execute("DELETE FROM exports WHERE clip_id=?", (clip["id"],))
            self.db.execute("DELETE FROM clips WHERE id=?", (clip["id"],))
            self.refresh()
        except OSError as exc:
            self.window.notify("Deletion failed: " + str(exc), 7000)
