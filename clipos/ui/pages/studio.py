"""Integrated phase-one queue and non-destructive multitrack assembly.

Source playback is explicitly not a composited timeline preview.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
)
from .base import BasePage
from .video_clipper import BackgroundJob
from ...video.multitrack import MultitrackProject


class StudioPage(BasePage):
    page_title = "Clip Queue & Editor"
    page_subtitle = "Phase 1 · Non-destructive assembly. Source player does not preview timeline composites."

    def build(self):
        self.project = MultitrackProject()
        self.worker = None
        self.project_path = None
        self.status = QLabel("Select generated clips, then add them to the timeline.")
        self.status.setWordWrap(True)
        self.content_layout.addWidget(self.status)
        self.queue = QTableWidget(0, 6)
        self.queue.setHorizontalHeaderLabels(
            ["Clip", "Duration", "Aspect", "File size", "Media", "Timeline"]
        )
        self.queue.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue.setMinimumHeight(180)
        self.queue.itemDoubleClicked.connect(lambda _: self.preview_source())
        self.content_layout.addWidget(self.queue)
        self._buttons(
            [
                ("Select all", self.queue.selectAll),
                ("Preview source", self.preview_source),
                ("Add selected to timeline", self.add_selected),
                ("Refresh queue", self.refresh),
            ]
        )
        self.player = None
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget

            self.video = QVideoWidget()
            self.video.setMinimumHeight(200)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video)
            self.player.errorOccurred.connect(
                lambda *_: self.status.setText(self.player.errorString())
            )
            self.content_layout.addWidget(self.video)
            self._buttons(
                [("Play source", self.player.play), ("Pause", self.player.pause)]
            )
        except ImportError as exc:
            self.content_layout.addWidget(
                QLabel(
                    "Embedded source player unavailable; Preview source opens the system player. "
                    + str(exc)
                )
            )
        from ..widgets.multitrack_timeline import MultitrackTimeline

        self.graph = MultitrackTimeline()
        viewport = QScrollArea()
        viewport.setWidgetResizable(True)
        viewport.setWidget(self.graph)
        viewport.setMinimumHeight(220)
        self.content_layout.addWidget(viewport)
        self.graph.editRequested.connect(
            lambda lane, item, values: self.action(
                lambda: self.project.change_item(lane, item, linked=True, **values)
            )
        )
        self.graph.seekRequested.connect(
            lambda seconds: self.split_time.setValue(seconds)
        )
        self.graph.selected.connect(self._graph_selected)
        self.graph.set_project(self.project)
        self.timeline = QTreeWidget()
        self.timeline.setHeaderLabels(
            ["Track / item", "Start (s)", "Source in (s)", "Length (s)"]
        )
        self.timeline.setMinimumHeight(200)
        self.timeline.itemSelectionChanged.connect(self._selection)
        self.content_layout.addWidget(self.timeline)
        row = QHBoxLayout()
        self.values = {}
        for key, label in [
            ("at", "Timeline start"),
            ("source_in", "Source in"),
            ("length", "Source length"),
        ]:
            row.addWidget(QLabel(label))
            field = QDoubleSpinBox()
            field.setRange(0, 864000)
            field.setDecimals(4)
            self.values[key] = field
            row.addWidget(field)
        self.content_layout.addLayout(row)
        self._buttons(
            [
                ("Apply trim / move (linked A/V)", self.change),
                ("Split at timeline time", self.split),
                ("Remove linked item", self.remove),
            ]
        )
        self.split_time = QDoubleSpinBox()
        self.split_time.setRange(0, 864000)
        self.split_time.setDecimals(4)
        self.split_time.setPrefix("Split time (seconds): ")
        self.content_layout.addWidget(self.split_time)
        self._buttons(
            [
                ("Undo", lambda: self.action(self.project.undo)),
                ("Redo", lambda: self.action(self.project.redo)),
                ("Save assembly…", self.save),
                ("Open assembly…", self.open),
            ]
        )
        self.window.data_changed.connect(self.refresh)
        self.refresh()

    def _buttons(self, actions):
        row = QHBoxLayout()
        for text, fn in actions:
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, action=fn: action())
            row.addWidget(button)
        self.content_layout.addLayout(row)

    def refresh(self):
        if not hasattr(self, "queue"):
            return
        selected = {c["id"] for c in self.selected_clips()}
        self.clips = [dict(c) for c in self.db.list_clips() if c["output_path"]]
        self.queue.setRowCount(len(self.clips))
        paths = {m.path for m in self.project.media}
        for row, clip in enumerate(self.clips):
            path = Path(clip["output_path"])
            exists = path.is_file()
            values = [
                clip["title"],
                f"{clip['duration']:.2f}s",
                clip["aspect_ratio"],
                f"{path.stat().st_size / 1024**2:.2f} MiB" if exists else "—",
                "Available" if exists else "Missing",
                "Added" if str(path.resolve()) in paths else "Not added",
            ]
            for col, value in enumerate(values):
                self.queue.setItem(row, col, QTableWidgetItem(str(value)))
            if clip["id"] in selected:
                for col in range(6):
                    self.queue.item(row, col).setSelected(True)
        self.queue.resizeColumnsToContents()

    def selected_clips(self):
        return [
            self.clips[index.row()]
            for index in self.queue.selectionModel().selectedRows()
        ]

    def preview_source(self):
        clips = self.selected_clips()
        if clips:
            url = QUrl.fromLocalFile(clips[0]["output_path"])
            if self.player:
                self.player.setSource(url)
                self.player.play()
            else:
                from PySide6.QtGui import QDesktopServices

                QDesktopServices.openUrl(url)

    def add_selected(self):
        if self.worker and self.worker.isRunning():
            return
        clips = self.selected_clips()
        if not clips:
            return
        snapshot = self.project.to_dict()

        def job(worker):
            draft = MultitrackProject.from_dict(snapshot)
            for clip in clips:
                if worker.cancelled.is_set():
                    raise RuntimeError("Import cancelled")
                draft.import_media(clip["output_path"], at=draft.duration)
            return draft.to_dict()

        self.worker = BackgroundJob(job, self)
        self.window.set_busy(True, "Inspecting source media…")
        self.worker.result.connect(self._imported)
        self.worker.error.connect(
            lambda message: self.status.setText("Import failed: " + message)
        )
        self.worker.finished.connect(lambda: self.window.set_busy(False))
        self.worker.start()

    def _imported(self, data):
        def replace(draft):
            incoming = MultitrackProject.from_dict(data)
            draft.media, draft.lanes = incoming.media, incoming.lanes

        self.project.edit(replace)
        self.status.setText(
            "Sources added. Originals are unchanged. Linked audio/video trims stay synchronized."
        )
        self.draw_timeline()
        self.refresh()

    def _graph_selected(self, lane, item):
        for row in range(self.timeline.topLevelItemCount()):
            track = self.timeline.topLevelItem(row)
            for index in range(track.childCount()):
                node = track.child(index)
                if node.data(0, Qt.ItemDataRole.UserRole) == (lane, item):
                    self.timeline.setCurrentItem(node)

    def draw_timeline(self):
        self.graph.set_project(self.project)
        self.timeline.clear()
        for lane in self.project.lanes:
            track = QTreeWidgetItem([lane.name])
            self.timeline.addTopLevelItem(track)
            for item in lane.items:
                node = QTreeWidgetItem(
                    [
                        item.id[:8],
                        f"{item.at:.4f}",
                        f"{item.source_in:.4f}",
                        f"{item.length:.4f}",
                    ]
                )
                node.setData(0, Qt.ItemDataRole.UserRole, (lane.id, item.id))
                track.addChild(node)
        self.timeline.expandAll()

    def target(self):
        node = self.timeline.currentItem()
        if node:
            return node.data(0, Qt.ItemDataRole.UserRole)

    def _selection(self):
        target = self.target()
        if target:
            item = self.project.find(*target)[1]
            for key, field in self.values.items():
                field.setValue(getattr(item, key))

    def action(self, fn):
        if self.worker and self.worker.isRunning():
            self.status.setText("Wait for source inspection to finish.")
            return
        try:
            fn()
            self.draw_timeline()
        except Exception as exc:
            self.status.setText(str(exc))

    def change(self):
        target = self.target()
        if target:
            self.action(
                lambda: self.project.change_item(
                    *target,
                    linked=True,
                    **{key: field.value() for key, field in self.values.items()},
                )
            )

    def split(self):
        target = self.target()
        if target:
            self.action(
                lambda: self.project.split(
                    *target, self.split_time.value(), linked=True
                )
            )

    def remove(self):
        target = self.target()
        if target:
            self.action(lambda: self.project.remove(*target, linked=True))

    def save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save assembly", "", "CLIPOS assembly (*.json)"
        )
        if path:
            self.action(lambda: self.project.save(path))

    def open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open assembly", "", "CLIPOS assembly (*.json)"
        )
        if path:

            def load():
                self.project = MultitrackProject.load(path)

            self.action(load)
