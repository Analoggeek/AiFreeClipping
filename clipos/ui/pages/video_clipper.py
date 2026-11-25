"""Single automatic clipping surface; no manual editor or Director workflow."""

from pathlib import Path
import threading

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .base import BasePage
from ..widgets.common import Card, SectionHeader
from ..widgets.crop_selector import CropSelector
from ...core.config import PATHS
from ...db.database import Database
from ...video.crop_config import (
    ASPECTS,
    CropConfig,
    display_dimensions,
    load_crop,
    save_crop,
)
from ...video.renderer import RenderSettings, ClipRenderer


class BackgroundJob(QThread):
    progress = Signal(float, str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.cancelled = threading.Event()

    def run(self):
        try:
            self.result.emit(self.fn(self))
        except Exception as exc:
            self.error.emit(str(exc))


class SingleCropCanvas(CropSelector):
    COLORS = {"crop": "#a880ff"}

    def __init__(self):
        super().__init__()
        self.regions = {"crop": None}
        self.active = "crop"
        self.empty_text = "Choose a recording to select the exported crop region"

    def set_crop(self, config):
        self.regions = {"crop": config.normalized}
        self.rect = config.normalized
        self.update()


def clipping_settings(config, db):
    """Do not inherit retired editing presets, auto-captions or crop overrides."""
    return RenderSettings(
        crop_config=config.to_dict(),
        aspect=config.aspect_ratio,
        width=config.output_width,
        height=config.output_height,
        editing_preset="clean",
        show_captions=False,
        smart_reframe=False,
        auto_facecam=False,
        auto_zoom=False,
        remove_silence=False,
        color_correct=False,
        sound_effects=False,
        transitions=False,
        normalize_audio=False,
        noise_reduction=False,
        encoder_preference=db.get_setting("use_gpu", "auto"),
        threads=int(db.get_setting("processing_threads", 0)),
    )


class VideoClipperPage(BasePage):
    page_title = "Video Clipper"
    page_subtitle = "Choose a video, select its crop, then generate clips automatically. No media upload."

    def build(self):
        self.project_id = None
        self.config = None
        self.worker = None
        self.frame_path = None
        self._pending = False
        self._selection_bounds = None
        self.saved = QComboBox()
        self.saved.setMinimumContentsLength(24)
        self.saved.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.saved.setAccessibleName("Open saved recording")
        self.saved.activated.connect(self._open_saved)
        self.content_layout.addWidget(self.saved)
        source = Card()
        source.add(
            SectionHeader(
                "Video source", "Local recordings you are authorised to process"
            )
        )
        self.upload = QPushButton("Upload / choose video")
        self.upload.setObjectName("Primary")
        self.upload.clicked.connect(self._choose)
        source.add(self.upload)
        self.source_label = QLabel("No video selected")
        self.source_label.setWordWrap(True)
        source.add(self.source_label)
        self.content_layout.addWidget(source)
        crop = Card()
        crop.add(
            SectionHeader(
                "Select crop",
                "Drag on the decoded source. The highlighted rectangle is the exact exported region.",
            )
        )
        row = QHBoxLayout()
        self.canvas = SingleCropCanvas()
        self.canvas.selected.connect(self._selection)
        row.addWidget(self.canvas, 2)
        self.crop_preview = QLabel("Crop preview")
        self.crop_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_preview.setMinimumSize(160, 180)
        row.addWidget(self.crop_preview, 1)
        crop.add_layout(row)
        form = QFormLayout()
        self.aspect = QComboBox()
        self.aspect.addItems(ASPECTS)
        self.aspect.currentTextChanged.connect(self._aspect_changed)
        form.addRow("Output aspect ratio", self.aspect)
        self.resolution = QComboBox()
        self.resolution.addItems(["Standard", "Full HD"])
        self.resolution.currentIndexChanged.connect(self._aspect_changed)
        form.addRow("Output resolution", self.resolution)
        self.geometry = QLabel("Select a recording first.")
        self.geometry.setWordWrap(True)
        self.geometry.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form.addRow("Saved crop (source pixels)", self.geometry)
        crop.add_layout(form)
        self.preview_button = QPushButton("Render crop preview")
        self.preview_button.clicked.connect(self._preview)
        crop.add(self.preview_button)
        self.content_layout.addWidget(crop)
        options = Card()
        options.add(
            SectionHeader(
                "Automatic clipping",
                "AI chooses timestamps. It never changes your saved crop.",
            )
        )
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("Scenes + audio", "visual")
        self.mode.addItem("Whisper speech", "speech")
        self.mode.addItem("Whisper + Ollama", "ollama")
        form.addRow("Analysis mode", self.mode)
        self.count = QSpinBox()
        self.count.setRange(1, 30)
        self.count.setValue(5)
        form.addRow("Maximum clips", self.count)
        self.duration = QComboBox()
        self.duration.addItems(["15-30", "30-45", "45-60", "60-90"])
        form.addRow("Clip duration (seconds)", self.duration)
        options.add_layout(form)
        self.tracking = QCheckBox(
            "Use verified YOLOX + ByteTrack analysis (CPU compatible)"
        )
        self.tracking.setChecked(bool(self.db.get_setting("tracking_enabled", False)))
        options.add(self.tracking)
        self.generate = QPushButton("Generate clips")
        self.generate.setObjectName("Primary")
        self.generate.clicked.connect(self._generate)
        options.add(self.generate)
        self.content_layout.addWidget(options)
        self.progress = QProgressBar()
        self.progress.hide()
        self.content_layout.addWidget(self.progress)
        self.status = QLabel(
            "Choose a video to begin. Optional models are managed only in AI Models."
        )
        self.status.setWordWrap(True)
        self.content_layout.addWidget(self.status)
        self.cancel = QPushButton("Cancel current task")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self._cancel)
        self.content_layout.addWidget(self.cancel)
        library = QPushButton("Open generated clips")
        library.clicked.connect(lambda: self.navigate("library"))
        self.content_layout.addWidget(library)
        self.refresh()
        QTimer.singleShot(0, self._restore)

    def _restore(self):
        active = self.db.get_setting("active_project", "")
        if (
            self.db.get_setting("restore_on_launch", True)
            and str(active).isdigit()
            and self.db.get_project(int(active))
        ):
            self.load_project(int(active))

    def _start(self, fn, done):
        if self._pending or (self.worker and self.worker.isRunning()):
            return
        self._pending = True
        self.worker = BackgroundJob(fn, self)
        self.worker.progress.connect(self._progress)
        self.worker.result.connect(done)
        self.worker.error.connect(self._failed)
        self.worker.finished.connect(self._finished)
        for control in (
            self.upload,
            self.aspect,
            self.resolution,
            self.mode,
            self.tracking,
            self.generate,
            self.preview_button,
            self.saved,
            self.canvas,
        ):
            control.setEnabled(False)
        self.cancel.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.window.set_busy(True, "Processing local video…")
        self.worker.start()

    def _progress(self, pct, message):
        self.progress.setRange(0, 100)
        self.progress.setValue(max(0, min(100, int(pct))))
        self.status.setText(message)

    def _failed(self, message):
        self.status.setText("Failed: " + message)
        self.db.log_error("video-clipper", message)

    def _finished(self):
        self._pending = False
        self.progress.hide()
        self.cancel.setEnabled(False)
        for control in (
            self.upload,
            self.aspect,
            self.resolution,
            self.mode,
            self.tracking,
            self.generate,
            self.preview_button,
            self.saved,
            self.canvas,
        ):
            control.setEnabled(True)
        self.window.set_busy(False)
        self.refresh()

    def _cancel(self):
        if self.worker:
            self.worker.cancelled.set()
            self.status.setText(
                "Cancellation requested; waiting for the current bounded operation."
            )

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose authorised recording",
            "",
            "Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)",
        )
        if not path:
            return
        dbpath = self.db.path

        def job(task):
            from ...video.importer import import_local
            from ...core.ffmpeg import probe

            imported = import_local(
                path, copy_to_media=False, progress_cb=task.progress.emit
            )
            width, height = display_dimensions(probe(imported.path).video)
            if task.cancelled.is_set():
                raise RuntimeError("Import cancelled")
            db = Database(dbpath)
            try:
                return db.create_project(
                    name=imported.title,
                    source_path=imported.path,
                    width=width,
                    height=height,
                    duration=imported.duration,
                    has_audio=imported.has_audio,
                    fps=imported.fps,
                    thumbnail=imported.thumbnail,
                    status="imported",
                )
            finally:
                db.close()

        self._start(job, self.load_project)

    def load_project(self, pid):
        project = self.db.get_project(pid)
        if project is None:
            return
        self.project_id = pid
        self.frame_path = None
        self.canvas.image = QPixmap()
        self.canvas.regions = {"crop": None}
        self.canvas.update()
        self.crop_preview.clear()
        self.db.set_setting("active_project", pid)
        self.source_label.setText(project["source_path"])
        self._saved_crop_error = False
        # This check is intentionally strict: corrupt/stale saved config is not
        # silently replaced with a centered crop.
        try:
            self.config = load_crop(self.db, pid)
            if self.config:
                self._selection_bounds = self.config.normalized
                self.aspect.blockSignals(True)
                self.aspect.setCurrentText(self.config.aspect_ratio)
                self.aspect.blockSignals(False)
                self.resolution.blockSignals(True)
                self.resolution.setCurrentIndex(
                    1
                    if (self.config.output_width, self.config.output_height)
                    in ((1080, 1920), (1920, 1080))
                    else 0
                )
                self.resolution.blockSignals(False)
                self._show_crop()
        except Exception as exc:
            self.config = None
            self._saved_crop_error = True
            self._failed(str(exc))
        if self.worker and self.worker.isRunning():
            self.worker.finished.connect(self._load_frame)
        else:
            self._load_frame()

    def _load_frame(self):
        if not self.project_id:
            return
        pid = self.project_id
        source = self.db.get_project(pid)["source_path"]
        out = PATHS.cache / f"crop-source-{pid}.png"

        def job(task):
            from ...core.ffmpeg import extract_thumbnail, probe

            info = probe(source)
            dims = display_dimensions(info.video)
            out.parent.mkdir(parents=True, exist_ok=True)
            if not extract_thumbnail(source, out, min(0.5, info.duration / 2)):
                raise RuntimeError("Could not decode source preview")
            return str(out), dims

        def done(value):
            path, dims = value
            self.frame_path = path
            self.canvas.set_image(path)
            self.db.update_project(pid, width=dims[0], height=dims[1])
            try:
                if self.config:
                    self.config.filter(*dims)
                    self._show_crop()
                elif not self._saved_crop_error:
                    self._selection((0.0, 0.0, 1.0, 1.0), dims)
            except Exception as exc:
                self._failed(str(exc))

        self._start(job, done)

    def _selection(self, rect, dimensions=None, *, keep_bounds=False):
        if not self.project_id:
            return
        if not keep_bounds:
            self._selection_bounds = rect
        p = self.db.get_project(self.project_id)
        w, h = dimensions or (int(p["width"]), int(p["height"]))
        try:
            aspect = self.aspect.currentText()
            output = ASPECTS[aspect]
            if self.resolution.currentIndex() == 1:
                output = {
                    "9:16": (1080, 1920),
                    "1:1": (1080, 1080),
                    "16:9": (1920, 1080),
                }[aspect]
            self.config = CropConfig.from_selection(rect, w, h, aspect, output)
            save_crop(self.db, self.project_id, self.config)
            self._show_crop()
            self.status.setText(
                "Crop saved. This exact highlighted region is applied to every clip."
            )
        except Exception as exc:
            if self.config:
                self.canvas.set_crop(self.config)
            self._failed(str(exc))

    def _show_crop(self):
        c = self.config
        if not c:
            return
        self.canvas.set_crop(c)
        self.geometry.setText(
            f"X {c.x} · Y {c.y} · W {c.width} · H {c.height}\nSource {c.source_width}×{c.source_height} → Output {c.output_width}×{c.output_height} ({c.aspect_ratio})"
        )
        if self.frame_path:
            # extract_thumbnail may downscale the decoded source. Map the same
            # authoritative normalized rectangle, never widget letterboxing.
            image = QPixmap(self.frame_path)
            x, y, w, h = c.normalized
            part = image.copy(
                round(x * image.width()),
                round(y * image.height()),
                round(w * image.width()),
                round(h * image.height()),
            )
            self.crop_preview.setPixmap(
                part.scaled(
                    220,
                    240,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _aspect_changed(self, *_):
        if self.config:
            self._selection(
                self._selection_bounds or self.config.normalized, keep_bounds=True
            )

    def _preview(self):
        if not self.config or not self.project_id:
            self._failed("Choose a video and valid crop first")
            return
        config = self.config
        source = self.db.get_project(self.project_id)["source_path"]
        settings = clipping_settings(config, self.db)
        output = PATHS.cache / f"crop-preview-{self.project_id}.mp4"
        duration = self.db.get_project(self.project_id)["duration"]

        def job(task):
            result = ClipRenderer(PATHS.cache / "crop-preview-work").render(
                source,
                output,
                0,
                min(2, duration),
                settings,
                progress_cb=task.progress.emit,
                cancel_cb=task.cancelled.is_set,
            )
            if result.cancelled:
                raise RuntimeError("Preview cancelled")
            return result.output_path

        self._start(
            job, lambda path: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        )

    def _generate(self):
        if not self.config or not self.project_id:
            self._failed("Choose a video and save a valid crop first")
            return
        pid = self.project_id
        crop = self.config
        dbpath = self.db.path
        mode = self.mode.currentData()
        count = self.count.value()
        duration = self.duration.currentText()
        tracking = self.tracking.isChecked()
        self.db.set_setting("tracking_enabled", tracking)
        settings = clipping_settings(crop, self.db)
        output = self.db.get_setting("output_dir", str(PATHS.exports))

        def job(task):
            from ...video.clean_clipping import generate_clips

            db = Database(dbpath)
            try:
                if tracking:
                    from ...ai.model_manager import ModelManager

                    ModelManager(db).enable_tracking(True)
                return generate_clips(
                    db,
                    pid,
                    crop,
                    output,
                    count=count,
                    duration=duration,
                    speech=mode in ("speech", "ollama"),
                    rerank=mode == "ollama",
                    tracking=tracking,
                    progress=task.progress.emit,
                    cancelled=task.cancelled.is_set,
                    settings=settings,
                )
            finally:
                db.close()

        def done(result):
            errors = [x["error"] for x in result if x.get("error")]
            self.status.setText(
                f"{len(result) - len(errors)} clips generated; {len(errors)} failed. "
                + (
                    "; ".join(errors)
                    if errors
                    else "Open Clip Library to preview or save them."
                )
            )
            self.window.data_changed.emit()

        self._start(job, done)

    def _open_saved(self, index):
        pid = self.saved.itemData(index)
        if pid:
            self.load_project(pid)

    def refresh(self):
        if not hasattr(self, "saved"):
            return
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem("Open an existing recording…", None)
        for p in self.db.list_projects():
            self.saved.addItem(p["name"], p["id"])
        self.saved.blockSignals(False)

    def shutdown(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancelled.set()
            self.worker.wait()
