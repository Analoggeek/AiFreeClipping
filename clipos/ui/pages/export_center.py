"""Export Center: batch render every clip to finished videos."""
from __future__ import annotations

import json
import shutil
import threading
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QProgressBar, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from ...core.config import ASPECT_RATIOS
from ...core.logging_setup import get_logger
from ...video.pipeline import ClipOSPipeline
from ...video.renderer import RenderSettings
from ..theme import Metrics
from ..widgets.common import Card, SectionHeader, format_duration, format_size
from .base import BasePage

log = get_logger(__name__)


class ExportWorker(QThread):
    """Renders a list of clips sequentially with real progress."""

    progress = Signal(int, str, float)     # index, message, percent
    clip_done = Signal(int, str, int)      # index, output path, size
    failed = Signal(int, str)
    all_done = Signal(int, int)            # succeeded, failed

    def __init__(self, db, project_id: int, clip_ids: list[int], settings: RenderSettings,
                 out_dir: Path) -> None:
        super().__init__()
        self.db = db
        self.project_id = project_id
        self.clip_ids = clip_ids
        self.settings = settings
        self.out_dir = out_dir
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True
        pipe = getattr(self, "_pipe", None)
        if pipe:
            pipe.cancel()

    def run(self) -> None:
        ok = 0
        failed = 0
        try:
            analysis = self._analysis()
        except Exception as exc:
            log.exception("could not prepare the analysis for export")
            self.failed.emit(0, str(exc))
            self.all_done.emit(0, 1)
            return

        pipe = self._pipe = ClipOSPipeline(self.db, self.project_id)

        def on_progress(index: int, total: int, message: str, pct: float) -> None:
            self.progress.emit(index, message, pct)

        try:
            results = pipe.export_clips(
                self.clip_ids, self.out_dir, self.settings, analysis,
                progress_cb=on_progress, cancel_cb=lambda: self._cancel,
            )
        except Exception as exc:
            log.exception("batch export failed")
            self.failed.emit(0, str(exc))
            self.all_done.emit(0, 1)
            return
        for i, info in enumerate(results):
            if info.get("error"):
                failed += 1
                self.failed.emit(i, str(info["error"]))
                continue
            ok += 1
            self.clip_done.emit(i, info.get("output_path", ""),
                                int(info.get("size_bytes", 0)))
        self.all_done.emit(ok, failed)

    def _analysis(self):
        from .auto_clip_studio import AutoClipStudioPage  # noqa: F401
        from ...video.pipeline import AnalysisResult
        from ...ai.audio_analysis import analyze_audio
        from ...ai.speaker_tracking import analyze_speakers
        from ...ai.transcription import Segment, Transcript, Word
        from ...ai.visual_analysis import analyze_visual
        from ...core.config import PATHS
        from ...core.ffmpeg import extract_audio_wav

        result = AnalysisResult()
        project = self.db.get_project(self.project_id)
        source = Path(project["source_path"])
        result.duration = project["duration"]

        wav = PATHS.cache / f"audio_{self.project_id}.wav"
        if project["has_audio"] and not wav.exists():
            extract_audio_wav(source, wav)
        if wav.exists():
            result.audio = analyze_audio(wav)
            if self.settings.smart_reframe:
                try:
                    result.visual = analyze_visual(source, fps_sample=0.25)
                    result.speaker = analyze_speakers(result.visual, result.audio)
                except Exception as exc:
                    log.warning("Tracking unavailable; exporting with centre framing: %s", exc)

        tr = self.db.get_transcript(self.project_id)
        if tr:
            segs = []
            for s in json.loads(tr["segments"] or "[]"):
                words = [Word(w["w"], w["s"], w["e"], w.get("p", 1.0))
                         for w in s.get("words", [])]
                segs.append(Segment(s["start"], s["end"], s["text"], words))
            result.transcript = Transcript(
                language=tr["language"], duration=tr["duration"],
                text=tr["full_text"], segments=segs, model=tr["model"],
            )
        return result


class RecipePreviewWorker(QThread):
    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, source, start, end, settings, parent=None):
        super().__init__(parent)
        self.source, self.start_time, self.end_time = source, start, end
        self.settings = settings
        self.cancelled = False

    def run(self):
        try:
            import uuid
            from ...core.config import PATHS
            from ...video.renderer import ClipRenderer
            folder = PATHS.cache / "recipe-previews" / uuid.uuid4().hex
            folder.mkdir(parents=True, exist_ok=True)
            result = ClipRenderer(folder).render(self.source, folder / "preview.mp4",
                self.start_time, min(self.end_time, self.start_time + 4), self.settings,
                cancel_cb=lambda: self.cancelled)
            if not result.cancelled:
                self.ready.emit(result.output_path)
        except Exception as exc:
            self.failed.emit(str(exc))


class ExportCenterPage(BasePage):
    page_title = "Export Center"
    page_subtitle = "Render every clip and ship them as a batch."

    def __init__(self, window) -> None:
        self.project_id: int | None = None
        self._worker: ExportWorker | None = None
        self._results: dict[int, tuple[str, int]] = {}
        super().__init__(window)

    def build(self) -> None:
        # --- project + settings ---
        top = QHBoxLayout()
        top.setSpacing(Metrics.md)

        proj_card = Card()
        proj_card.add(SectionHeader("Project", ""))
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        proj_card.add(self.project_combo)

        self.project_info = QLabel("Select a project")
        self.project_info.setObjectName("CardSubtitle")
        self.project_info.setWordWrap(True)
        proj_card.add(self.project_info)
        top.addWidget(proj_card, 1)

        settings_card = Card()
        settings_card.add(SectionHeader("Export Settings", ""))
        from ...video.presets import PRESETS
        self.recipe_combo = QComboBox()
        for key, (name, detail) in PRESETS.items():
            self.recipe_combo.addItem(name, key)
        self.recipe_combo.setToolTip("Gaming uses the upper-left facecam region by default. Adjust your source before export if needed.")
        settings_card.add(self.recipe_combo)
        self.preview_recipe_btn = QPushButton("Preview recipe · 4 seconds")
        self.preview_recipe_btn.setToolTip("Renders your first clip at draft resolution with the selected layout and colour. Caption preview is in Caption Studio.")
        self.preview_recipe_btn.clicked.connect(self._preview_recipe)
        settings_card.add(self.preview_recipe_btn)
        self.facecam_controls = []
        facecam_form = QFormLayout()
        for label, value in (("Facecam X %", 0), ("Facecam Y %", 0), ("Facecam width %", 25), ("Facecam height %", 30)):
            spin = QSpinBox()
            spin.setRange(0 if "X" in label or "Y" in label else 1, 100)
            spin.setValue(value)
            facecam_form.addRow(label, spin)
            self.facecam_controls.append(spin)
        settings_card.add_layout(facecam_form)

        form = QFormLayout()
        form.setSpacing(Metrics.sm)

        self.aspect_combo = QComboBox()
        for ratio in ASPECT_RATIOS:
            w, h = ASPECT_RATIOS[ratio]
            self.aspect_combo.addItem(f"{ratio} ({w}×{h})", ratio)
        form.addRow("Resolution", self.aspect_combo)

        self.codec_combo = QComboBox()
        self.codec_combo.addItem("H.264 (MP4, most compatible)", "h264")
        self.codec_combo.addItem("H.265 (smaller file)", "h265")
        form.addRow("Codec", self.codec_combo)

        self.fps_combo = QComboBox()
        self.fps_combo.addItem("30 fps", 30)
        self.fps_combo.addItem("60 fps", 60)
        form.addRow("Frame rate", self.fps_combo)

        self.bitrate_spin = QSpinBox()
        self.bitrate_spin.setRange(1000, 50000)
        self.bitrate_spin.setValue(8000)
        self.bitrate_spin.setSuffix(" kbps")
        form.addRow("Bitrate", self.bitrate_spin)

        self.captions_check = QCheckBox("Burn in captions")
        self.captions_check.setChecked(True)
        form.addRow("", self.captions_check)

        self.gpu_combo = QComboBox()
        self.gpu_combo.addItem("Auto (best available)", "auto")
        self.gpu_combo.addItem("CPU (always works)", "cpu")
        self.gpu_combo.addItem("NVIDIA NVENC", "nvidia")
        self.gpu_combo.addItem("Apple VideoToolbox", "apple")
        self.gpu_combo.addItem("Intel Quick Sync", "intel")
        form.addRow("Encoder", self.gpu_combo)

        settings_card.add_layout(form)

        out_row = QHBoxLayout()
        self.out_label = QLabel("")
        self.out_label.setObjectName("CardSubtitle")
        out_row.addWidget(self.out_label, 1)
        browse = QPushButton("Change…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._choose_output)
        out_row.addWidget(browse)
        settings_card.add_layout(out_row)
        top.addWidget(settings_card, 1)

        self.content_layout.addLayout(top)

        # --- queue ---
        queue_card = Card()
        queue_card.add(SectionHeader("Export Queue", "Clips ready to render"))
        self.queue = QListWidget()
        self.queue.setMinimumHeight(190)
        queue_card.add(self.queue)
        self.content_layout.addWidget(queue_card)

        # --- progress ---
        prog_card = Card()
        prog_card.add(SectionHeader("Progress", ""))
        self.progress = QProgressBar()
        prog_card.add(self.progress)
        self.progress_label = QLabel("Idle")
        self.progress_label.setObjectName("CardSubtitle")
        prog_card.add(self.progress_label)

        btn_row = QHBoxLayout()
        self.export_btn = QPushButton("↓  Export All Clips")
        self.export_btn.setObjectName("BigAction")
        self.export_btn.clicked.connect(self._start_export)
        btn_row.addWidget(self.export_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("Danger")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_export)
        btn_row.addWidget(self.cancel_btn)

        self.zip_btn = QPushButton("Export as ZIP")
        self.zip_btn.setObjectName("Primary")
        self.zip_btn.clicked.connect(self._export_zip)
        btn_row.addWidget(self.zip_btn)
        btn_row.addStretch(1)
        prog_card.add_layout(btn_row)
        self.content_layout.addWidget(prog_card)

        # --- history ---
        hist_card = Card()
        hist_card.add(SectionHeader("Export History", ""))
        self.history = QListWidget()
        self.history.setMaximumHeight(150)
        hist_card.add(self.history)
        self.content_layout.addWidget(hist_card)

    # -- data ----------------------------------------------------------------------
    def refresh(self) -> None:
        current = self.project_combo.currentData()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for p in self.db.list_projects():
            self.project_combo.addItem(p["name"], p["id"])
        if current:
            idx = self.project_combo.findData(current)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        self.project_combo.blockSignals(False)

        settings = self.db.get_settings()
        self.out_label.setText(f"Output: {settings.get('output_dir', '')}")
        idx = self.aspect_combo.findData(settings.get("aspect_ratio", "9:16"))
        if idx >= 0:
            self.aspect_combo.setCurrentIndex(idx)

        self._on_project_changed()
        self._load_history()

    def _on_project_changed(self) -> None:
        pid = self.project_combo.currentData()
        self.project_id = pid
        self.queue.clear()
        self._results = {}
        if not pid:
            self.project_info.setText("Select a project")
            return
        p = self.db.get_project(pid)
        clips = self.db.list_clips(pid)
        self.project_info.setText(
            f"<b>{p['name']}</b><br>{len(clips)} clips · "
            f"{format_duration(p['duration'])} source"
        )
        for c in clips:
            item = QListWidgetItem(
                f"{c['title']}    [{format_duration(c['start_time'])} → "
                f"{format_duration(c['end_time'])}]   viral {c['virality_score']:.0f}"
            )
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.queue.addItem(item)

    # -- export ---------------------------------------------------------------------
    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if path:
            self.db.set_setting("output_dir", path)
            self.out_label.setText(f"Output: {path}")

    def _render_settings(self) -> RenderSettings:
        from ...core.editing import render_settings
        overrides = {
            "aspect_ratio": self.aspect_combo.currentData(),
            "editing_preset": self.recipe_combo.currentData(),
            "fps": self.fps_combo.currentData(), "codec": self.codec_combo.currentData(),
            "bitrate_kbps": self.bitrate_spin.value(),
            "auto_caption": self.captions_check.isChecked(),
            "encoder": self.gpu_combo.currentData(),
        }
        rs = render_settings(self.db, overrides)
        x,y,w,h = [spin.value()/100 for spin in self.facecam_controls]
        rs.auto_facecam = False
        rs.facecam_rect = (min(x,.99),min(y,.99),min(w,1-min(x,.99)),min(h,1-min(y,.99)))
        return rs

    def _preview_recipe(self):
        if not self.project_id or not self.queue.count():
            self.window.notify("Select a project with clips first")
            return
        project = self.db.get_project(self.project_id)
        clip = self.db.get_clip(self.queue.item(0).data(Qt.ItemDataRole.UserRole))
        settings = self._render_settings()
        ratio = settings.width / settings.height
        settings.height = 480
        settings.width = int(480 * ratio / 2) * 2
        settings.encoder_preference = "cpu"
        settings.show_captions = False
        worker = RecipePreviewWorker(project["source_path"], clip["start_time"], clip["end_time"], settings, self)
        self._recipe_worker = worker
        self.preview_recipe_btn.setEnabled(False)
        worker.ready.connect(lambda path: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        worker.failed.connect(lambda message: self.window.notify("Preview failed: " + message, 6000))
        worker.finished.connect(lambda: self.preview_recipe_btn.setEnabled(True))
        worker.start()

    def _start_export(self) -> None:
        if not self.project_id:
            self.window.notify("Select a project first")
            return
        clip_ids = [
            self.queue.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.queue.count())
        ]
        if not clip_ids:
            self.window.notify("No clips to export")
            return

        out_dir = Path(self.db.get_setting("output_dir") or "./exports")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.export_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.progress.setValue(0)
        self.progress_label.setText("Starting export…")

        self._worker = ExportWorker(
            self.db, self.project_id, clip_ids, self._render_settings(), out_dir,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.clip_done.connect(self._on_clip_done)
        self._worker.failed.connect(self._on_clip_failed)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _cancel_export(self) -> None:
        if self._worker:
            self._worker.cancel()
        self.progress_label.setText("Cancelling…")

    def _on_progress(self, index: int, message: str, pct: float) -> None:
        total = max(1, self.queue.count())
        overall = ((index + pct / 100.0) / total) * 100.0
        self.progress.setValue(int(overall))
        self.progress_label.setText(message)

    def _on_clip_done(self, index: int, path: str, size: int) -> None:
        self._results[index] = (path, size)
        self.progress_label.setText(f"Finished {Path(path).name} ({format_size(size)})")

    def _on_clip_failed(self, index: int, message: str) -> None:
        self.progress_label.setText(f"Clip {index + 1} failed: {message}")
        self.progress_label.setToolTip(message)
        self._last_export_error = message

    def _on_all_done(self, ok: int, failed: int) -> None:
        self.export_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.progress.setValue(100 if ok else 0)
        self.progress_label.setText(
            f"Export complete — {ok} succeeded" + (f", {failed} failed. {getattr(self, '_last_export_error', '')}" if failed else "")
        )
        self.window.notify(f"Exported {ok} clips")
        self._load_history()

    def shutdown(self) -> None:
        """Cancel a running export and wait for its thread to stop."""
        preview = getattr(self, "_recipe_worker", None)
        if preview and preview.isRunning():
            preview.cancelled = True
            preview.wait()
        worker = self._worker
        if worker is not None:
            try:
                worker.cancel()
            except Exception:
                pass
            if worker.isRunning():
                if not worker.wait(5000):
                    worker.terminate()
                    worker.wait(1000)
        self._worker = None

    def _load_history(self) -> None:
        self.history.clear()
        for e in self.db.list_exports(limit=40):
            name = Path(e["output_path"]).name or f"Export #{e['id']}"
            item = QListWidgetItem(
                f"{name}   ·  {e['status']}  ·  {format_size(e['size_bytes'])}"
            )
            item.setToolTip(e["error"] or e["output_path"])
            self.history.addItem(item)

    def _export_zip(self) -> None:
        if not self._results:
            self.window.notify("Export the clips first, then package them")
            return
        out_dir = Path(self.db.get_setting("output_dir") or "./exports")
        zip_path = out_dir / "clipos_export.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for path, _size in self._results.values():
                    p = Path(path)
                    if p.exists():
                        zf.write(p, p.name)
            self.window.notify(f"Packaged {len(self._results)} clips into {zip_path.name}")
        except Exception as exc:
            self.window.notify(f"ZIP failed: {exc}", 6000)
