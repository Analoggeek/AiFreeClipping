"""Real original asset-based title/logo graphics, not a parameter-only recipe."""

from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QFileDialog,
)
from ...video.studio_graphics import graphic_catalog, render_graphic, inspect_logo
from ...video.multitrack import MultitrackProject


class GraphicsPanel(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.logo_path = ""
        self.logo_sha = ""
        layout = QVBoxLayout(self)
        label = QLabel(
            "Original asset-based graphics · three transparent plates with editable title/subtitle/logo and fade/slide animation. Generated alpha MOV media is preserved with project references. This is a small real pack, not 50 complete motion-graphics packs."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.template = QComboBox()
        for key, spec in graphic_catalog().items():
            self.template.addItem(spec["name"], key)
        layout.addWidget(self.template)
        self.title = QLineEdit("Your title")
        self.subtitle = QLineEdit("Your subtitle")
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0.2, 30)
        self.duration.setDecimals(4)
        self.duration.setValue(3)
        self.duration.setSuffix(" seconds")
        layout.addWidget(self.duration)
        self.animation = QComboBox()
        self.animation.addItems(["fade", "slide"])
        layout.addWidget(self.animation)
        self.logo = QLabel("No logo selected.")
        self.logo.setWordWrap(True)
        layout.addWidget(self.logo)
        for title, fn in [
            ("Choose local logo…", self.choose_logo),
            ("Clear logo", self.clear_logo),
            ("Add graphic at timeline cursor", self.add),
            ("Read selected graphic settings", self.read),
            ("Rebuild selected graphic from controls", lambda: self.add(True)),
        ]:
            button = QPushButton(title)
            button.clicked.connect(
                lambda checked=False, action=fn: studio.editing.run(action)
            )
            layout.addWidget(button)

    def clear_logo(self):
        self.logo_path = ""
        self.logo_sha = ""
        self.logo.setText("No logo selected.")

    def choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose authorized local logo",
            "",
            "Raster logo (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return

        def done(result):
            self.logo_path, self.logo_sha = result
            self.logo.setText(self.logo_path)

        self.studio._background(
            lambda worker: inspect_logo(path), done, "Verifying local logo…"
        )

    def read(self):
        target = self.studio.target()
        if not target:
            raise ValueError("Select an asset-based graphic item")
        _, item = self.studio.project.find(*target)
        media = next(m for m in self.studio.project.media if m.id == item.media_id)
        spec = media.graphic
        if not spec:
            raise ValueError("Selected item is not a generated graphic")
        self.template.setCurrentIndex(self.template.findData(spec["template"]))
        self.title.setText(spec["title"])
        self.subtitle.setText(spec["subtitle"])
        self.duration.setValue(spec["duration"])
        self.animation.setCurrentText(spec["animation"])
        self.logo_path = spec["logo_path"]
        self.logo_sha = spec["logo_sha256"]
        self.logo.setText(self.logo_path or "No logo selected.")

    def add(self, rebuild=False):
        from ...core.config import PATHS
        from ...core.ffmpeg import FFmpegCancelled

        snapshot = self.studio.project.to_dict()
        project = self.studio.project
        at = self.studio.split_time.value()
        media_id = None
        if rebuild:
            target = self.studio.target()
            if not target:
                raise ValueError("Select a generated graphic to rebuild")
            lane, item = project.find(*target)
            media = next(m for m in project.media if m.id == item.media_id)
            if lane.locked:
                raise ValueError("Track is locked")
            if not media.graphic:
                raise ValueError("Selected source is not an editable graphic")
            if sum(i.media_id == media.id for l in project.lanes for i in l.items) != 1:
                raise ValueError(
                    "Shared graphic has multiple instances; add a new graphic variant instead"
                )
            media_id = media.id
        spec = {
            "template": self.template.currentData(),
            "title": self.title.text(),
            "subtitle": self.subtitle.text(),
            "logo_path": self.logo_path,
            "logo_sha256": self.logo_sha,
            "duration": max(1, round(self.duration.value() * project.fps))
            / project.fps,
            "animation": self.animation.currentText(),
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
        }

        def job(worker):
            output = render_graphic(
                spec,
                PATHS.media / "graphics",
                cancelled=worker.cancelled.is_set,
                progress=lambda pct, message: worker.progress.emit(pct, message),
            )
            try:
                if worker.cancelled.is_set():
                    raise FFmpegCancelled()
                draft = MultitrackProject.from_dict(snapshot)
                if media_id:
                    media = next(m for m in draft.media if m.id == media_id)
                    media.path = str(output.resolve())
                    media.duration = spec["duration"]
                    media.graphic = deepcopy(spec)
                    item = next(
                        i
                        for l in draft.lanes
                        for i in l.items
                        if i.media_id == media_id
                    )
                    item.source_in = 0.0
                    item.length = spec["duration"]
                    item.speed = 1.0
                else:
                    new_id = draft.import_media(output, at=at)
                    next(m for m in draft.media if m.id == new_id).graphic = deepcopy(
                        spec
                    )
                draft.validate()
                return draft.to_dict(), str(output)
            except Exception:
                output.unlink(missing_ok=True)
                raise

        def done(result):
            data, output = result
            try:
                if self.studio.project.to_dict() != snapshot:
                    raise ValueError("Timeline changed during graphic rendering; retry")
                incoming = MultitrackProject.from_dict(data)

                def replace(draft):
                    draft.media, draft.lanes = incoming.media, incoming.lanes

                self.studio.project.edit(replace)
                self.studio.draw_timeline()
                self.studio.status.setText(
                    "Asset-based graphic committed. Preview through shared graph; save assembly to retain editable title/logo settings. Older generated assets are retained for undo."
                )
            except Exception as exc:
                Path(output).unlink(missing_ok=True)
                self.studio.status.setText("Graphic commit failed: " + str(exc))

        self.studio._background(job, done, "Rendering original alpha graphic…")
