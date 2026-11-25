"""Original offline caption/template recipes with actual FFmpeg thumbnail previews."""

from pathlib import Path
import hashlib
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QComboBox,
)

from ...captions.original_styles import original_style_keys
from ...captions.caption_engine import CAPTION_STYLES
from ...video.creative_templates import templates
from ...video.editing_preset import EditingPreset


class CreativeLibrary(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.catalog = templates()
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Original creative library · 50 caption compositions + 50 asset-free editing recipes"
            )
        )
        self.kind = QComboBox()
        self.kind.addItems(["Caption compositions", "Editing recipe templates"])
        self.kind.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.kind)
        self.list = QListWidget()
        self.list.setMinimumHeight(170)
        self.list.currentItemChanged.connect(self.describe)
        layout.addWidget(self.list)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.image = QLabel("Select a preset and render its actual style thumbnail.")
        self.image.setMinimumHeight(180)
        layout.addWidget(self.image)
        for title, fn in [
            ("Preview selected composition", self.preview),
            ("Load selected style / recipe into inspector", self.load_selected),
        ]:
            button = QPushButton(title)
            button.clicked.connect(
                lambda checked=False, action=fn: studio.editing.run(action)
            )
            layout.addWidget(button)
        self.refresh()

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        if self.kind.currentIndex() == 0:
            for key in original_style_keys():
                item = QListWidgetItem(CAPTION_STYLES[key].name)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.list.addItem(item)
        else:
            for key, template in self.catalog.items():
                item = QListWidgetItem(template["name"])
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.list.addItem(item)
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(0)

    def describe(self, *args):
        if not hasattr(self, "description"):
            return
        item = self.list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if self.kind.currentIndex() == 0:
            self.description.setText(
                CAPTION_STYLES[key].description
                + " Word motion requires actual caption word timings; preview uses labelled demo timing."
            )
        else:
            t = self.catalog[key]
            self.description.setText(
                t["description"]
                + " "
                + t["aspect_ratio"]
                + ". "
                + t["duration"]
                + ". Required external assets: none."
            )

    def load_selected(self):
        item = self.list.currentItem()
        if not item:
            raise ValueError("Select a composition")
        key = item.data(Qt.ItemDataRole.UserRole)
        if self.kind.currentIndex() == 0:
            for panel in (self.studio.captions, self.studio.editing):
                field = (
                    panel.style
                    if hasattr(panel, "style")
                    else panel.fields["caption_style"]
                )
                field.setCurrentIndex(field.findData(key))
            self.studio.status.setText(
                "Original caption style loaded. Generate captions or apply the checked Captions category to existing cues."
            )
        else:
            self.studio.editing.populate(
                EditingPreset.from_dict(self.catalog[key]["preset"])
            )
            self.studio.status.setText(
                "Recipe loaded into inspector. Review checked categories and target scope before Apply."
            )

    def preview(self):
        from ...core.config import PATHS
        from ...video.multitrack import MultitrackProject, Item, uid
        from ...video.caption_raster import CaptionRaster

        item = self.list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        style = (
            key
            if self.kind.currentIndex() == 0
            else self.catalog[key]["preset"]["categories"]["captions"]["caption_style"]
        )
        template = self.catalog[key] if self.kind.currentIndex() else None
        signature = hashlib.sha256(
            json.dumps(
                {"style": CAPTION_STYLES[style].to_dict(), "template": template},
                sort_keys=True,
            ).encode()
        ).hexdigest()

        def job(worker):
            import subprocess
            import tempfile
            from ...core.ffmpeg import require_ffmpeg
            from ...video.overlay_tracks import write_caption
            from ...video.renderer import _ass_filter

            path = PATHS.cache / ("original-preview-" + signature + ".png")
            project = MultitrackProject(width=360, height=640, fps=10)
            cue = Item(
                uid(),
                "",
                0,
                0,
                2,
                text="Build your next story",
                caption_style=style,
                caption_words=[
                    {"w": w, "s": i * 0.4, "e": (i + 1) * 0.4}
                    for i, w in enumerate(("Build", "your", "next", "story"))
                ],
            )
            with tempfile.TemporaryDirectory(prefix="clipos-style-") as directory:
                ass = Path(directory) / "demo.ass"
                write_caption(ass, cue, 360, 640)
                filters = []
                if template:
                    c = template["preset"]["categories"]["color"]
                    filters.append(
                        f"eq=brightness={c['brightness']}:contrast={c['contrast']}:saturation={c['saturation']}"
                    )
                filters.append(_ass_filter(ass))
                subprocess.run(
                    [
                        require_ffmpeg(),
                        "-v",
                        "error",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "testsrc2=s=360x640:r=10:d=2",
                        "-vf",
                        ",".join(filters),
                        "-ss",
                        "0.6",
                        "-frames:v",
                        "1",
                        "-threads",
                        "1",
                        str(path),
                    ],
                    capture_output=True,
                    check=True,
                    timeout=30,
                )
            return str(path)

        requested_kind = self.kind.currentIndex()

        def done(path):
            pixmap = QPixmap(path)
            self.image.setPixmap(
                pixmap.scaled(
                    180,
                    320,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            item = self.list.currentItem()
            if (
                item
                and self.kind.currentIndex() == requested_kind
                and item.data(Qt.ItemDataRole.UserRole) == key
            ):
                item.setIcon(QIcon(path))
            self.studio.status.setText(
                CAPTION_STYLES[style].name
                + ": actual FFmpeg style demo; illustrative timing, not recognized speech or a full template animation."
            )

        self.studio._background(job, done, "Rendering original style preview…")
