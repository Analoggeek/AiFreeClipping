"""Integrated phase-one queue and non-destructive multitrack assembly.

Source playback is explicitly not a composited timeline preview.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QLabel,
    QScrollArea,
    QSpinBox,
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
        from ...video.clip_queue import ClipQueue

        self.queue_manager = ClipQueue(self.db)
        self.project = MultitrackProject()
        self.worker = None
        self.project_path = None
        self.status = QLabel("Select generated clips, then add them to the timeline.")
        self.status.setWordWrap(True)
        self.content_layout.addWidget(self.status)
        self.queue = QTableWidget(0, 8)
        self.queue.setHorizontalHeaderLabels(
            [
                "Clip",
                "Duration",
                "Aspect",
                "File size",
                "Media",
                "Timeline",
                "Resolution",
                "Group",
            ]
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
        self._buttons(
            [
                ("Rename", self.rename_clip),
                ("Duplicate selected", self.duplicate_clips),
                ("Remove from library…", self.delete_clips),
                ("Move up", lambda: self.move_clips(-1)),
                ("Move down", lambda: self.move_clips(1)),
                ("Group selected…", self.group_clips),
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
        self._buttons(
            [
                ("Lock / unlock track", lambda: self.toggle_track("locked")),
                ("Show / hide track", lambda: self.toggle_track("enabled")),
                ("Build source waveforms", self.waveforms),
                ("Render timeline preview (with audio)", self.render_preview),
                ("Cancel background work", self.cancel_work),
            ]
        )
        canvas_row = QHBoxLayout()
        self.canvas_fields = {}
        for key, minimum, maximum in [
            ("width", 16, 7680),
            ("height", 16, 7680),
            ("fps", 1, 120),
        ]:
            canvas_row.addWidget(QLabel("Canvas " + key))
            field = QSpinBox()
            field.setRange(minimum, maximum)
            field.setValue(getattr(self.project, key))
            if key != "fps":
                field.setSingleStep(2)
            self.canvas_fields[key] = field
            canvas_row.addWidget(field)
        self.content_layout.addLayout(canvas_row)
        self._buttons(
            [
                ("Apply canvas", self.apply_canvas),
                (
                    "Timeline zoom in",
                    lambda: self.graph.set_scale(self.graph.scale * 1.25),
                ),
                (
                    "Timeline zoom out",
                    lambda: self.graph.set_scale(self.graph.scale / 1.25),
                ),
            ]
        )
        from ..widgets.editing_panel import EditingPanel

        self.editing = EditingPanel(self)
        self.content_layout.addWidget(self.editing)
        from ..widgets.caption_panel import CaptionPanel

        self.captions = CaptionPanel(self)
        self.content_layout.addWidget(self.captions)
        from ..widgets.batch_panel import BatchPanel

        self.batch = BatchPanel(self)
        self.content_layout.addWidget(self.batch)
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
        self.clips = self.queue_manager.entries()
        exports = {}
        for export in self.db.list_exports(limit=10000):
            exports.setdefault(export["clip_id"], dict(export))
        self.queue.setRowCount(len(self.clips))
        paths = {m.path for m in self.project.media}
        for row, clip in enumerate(self.clips):
            path = Path(clip["output_path"])
            exists = path.is_file()
            export = exports.get(clip["id"], {})
            values = [
                clip["title"],
                f"{clip['duration']:.2f}s",
                clip["aspect_ratio"],
                f"{path.stat().st_size / 1024**2:.2f} MiB" if exists else "—",
                "Available" if exists else "Missing",
                "Added" if str(path.resolve()) in paths else "Not added",
                f"{export['width']}×{export['height']}"
                if export.get("width") and export.get("height")
                else "Not recorded",
                clip["queue_group"],
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if (
                    col == 0
                    and clip["thumbnail_path"]
                    and Path(clip["thumbnail_path"]).is_file()
                ):
                    cell.setIcon(QIcon(clip["thumbnail_path"]))
                self.queue.setItem(row, col, cell)
            if clip["id"] in selected:
                for col in range(8):
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
                draft.import_media(
                    clip["output_path"], at=draft.duration, queue_clip_id=clip["id"]
                )
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
            new_ids = {m.id for m in incoming.media} - {m.id for m in draft.media}
            self.editing.apply_future(incoming, new_ids)
            draft.media, draft.lanes = incoming.media, incoming.lanes

        try:
            self.project.edit(replace)
        except Exception as exc:
            self.status.setText(
                "Import settings failed; timeline unchanged: " + str(exc)
            )
            return
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
        current = self.timeline.currentItem()
        selected_item = self.target()
        selected_lane = (
            current.data(0, Qt.ItemDataRole.UserRole + 1) if current else None
        )
        self.graph.set_project(self.project)
        for key, field in self.canvas_fields.items():
            field.setValue(getattr(self.project, key))
        self.timeline.clear()
        for lane in self.project.lanes:
            track = QTreeWidgetItem(
                [
                    lane.name
                    + (" [locked]" if lane.locked else "")
                    + (" [hidden]" if not lane.enabled else "")
                ]
            )
            track.setData(0, Qt.ItemDataRole.UserRole + 1, lane.id)
            self.timeline.addTopLevelItem(track)
            if selected_lane == lane.id:
                self.timeline.setCurrentItem(track)
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
                if selected_item == (lane.id, item.id):
                    self.timeline.setCurrentItem(node)
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

    def rename_clip(self):
        clips = self.selected_clips()
        if len(clips) != 1:
            self.status.setText("Select exactly one clip to rename.")
            return
        title, ok = QInputDialog.getText(
            self, "Rename clip", "Name", text=clips[0]["title"]
        )
        if ok:
            self.action(lambda: self.queue_manager.rename(clips[0]["id"], title))
            self.window.data_changed.emit()

    def duplicate_clips(self):
        for clip in self.selected_clips():
            self.queue_manager.duplicate(clip["id"])
        self.window.data_changed.emit()

    def delete_clips(self):
        clips = self.selected_clips()
        if (
            clips
            and QMessageBox.question(
                self,
                "Remove clips",
                "Remove selected library entries? Media files and existing timeline items are kept.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            for clip in clips:
                self.db.delete_clip(clip["id"])
            self.window.data_changed.emit()

    def move_clips(self, delta):
        self.queue_manager.move([c["id"] for c in self.selected_clips()], delta)
        self.refresh()

    def group_clips(self):
        ids = [c["id"] for c in self.selected_clips()]
        if not ids:
            return
        name, ok = QInputDialog.getText(
            self, "Group clips", "Group name (empty removes group)"
        )
        if ok:
            self.action(lambda: self.queue_manager.group(ids, name))
            self.refresh()

    def toggle_track(self, property_name):
        node = self.timeline.currentItem()
        if not node:
            return
        target = self.target()
        lane_id = target[0] if target else node.data(0, Qt.ItemDataRole.UserRole + 1)
        lane = next(lane for lane in self.project.lanes if lane.id == lane_id)
        self.action(
            lambda: self.project.lane_state(
                lane_id, **{property_name: not getattr(lane, property_name)}
            )
        )

    def cancel_work(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancelled.set()
            self.status.setText("Cancellation requested…")

    def _background(self, fn, done, label, on_progress=None):
        if self.worker and self.worker.isRunning():
            self.status.setText("Background work is already running.")
            return
        self.worker = BackgroundJob(fn, self)
        self.worker.result.connect(done)
        self.worker.error.connect(
            lambda message: self.status.setText("Failed: " + message)
        )
        self.worker.progress.connect(
            on_progress
            or (lambda pct, message: self.status.setText(f"{pct:.0f}% · {message}"))
        )
        self.worker.finished.connect(lambda: self.window.set_busy(False))
        self.window.set_busy(True, label)
        self.status.setText(label)
        self.worker.start()

    def waveforms(self):
        from ...core.config import PATHS
        from ...video.waveform import build_waveform

        media = [m for m in self.project.media if m.has_audio]

        def job(worker):
            result = {}
            cached = {}
            for source in media:
                if source.path not in cached:
                    cached[source.path] = build_waveform(
                        source.path,
                        PATHS.cache / "studio-waveforms",
                        cancel_cb=worker.cancelled.is_set,
                    )
                result[source.id] = cached[source.path]
            return result

        def done(result):
            self.graph.waveforms = result
            self.graph.update()
            self.status.setText(
                "Source-amplitude waveforms ready (not final mixed audio)."
            )

        self._background(job, done, "Decoding source audio waveforms…")

    def render_preview(self):
        from ...core.config import PATHS
        from ...video.multitrack_render import export_project
        import tempfile

        if self.project.duration <= 0:
            self.status.setText("Add media before rendering a preview.")
            return
        snapshot = self.project.to_dict()

        def job(worker):
            draft = MultitrackProject.from_dict(snapshot)
            # Use the same graph/canvas as export, never an unrelated source preview.
            with tempfile.TemporaryDirectory(
                prefix="studio-preview-", dir=PATHS.cache
            ) as folder:
                import uuid

                output = PATHS.cache / ("studio-preview-" + uuid.uuid4().hex + ".mp4")
                return export_project(
                    draft,
                    output,
                    folder,
                    encoder="cpu",
                    cancel_cb=worker.cancelled.is_set,
                    progress_cb=lambda pct, message: worker.progress.emit(pct, message),
                ).output_path

        def done(path):
            self.status.setText(
                "Rendered timeline snapshot with mixed audio; re-render after edits."
            )
            url = QUrl.fromLocalFile(str(path))
            if self.player:
                self.player.setSource(url)
                self.player.play()
            else:
                from PySide6.QtGui import QDesktopServices

                QDesktopServices.openUrl(url)

        self._background(job, done, "Rendering timeline snapshot with audio…")

    def apply_canvas(self):
        values = {key: field.value() for key, field in self.canvas_fields.items()}

        def operation(draft):
            for key, value in values.items():
                setattr(draft, key, value)

        self.action(lambda: self.project.edit(operation))
