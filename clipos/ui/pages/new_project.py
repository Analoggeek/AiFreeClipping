"""New Project: import a local video or paste a URL."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ...core.config import ASPECT_RATIOS, CLIP_DURATION_PRESETS, SUPPORTED_VIDEO_EXTENSIONS
from ...core.logging_setup import get_logger
from ...video.importer import (
    ImportError_, find_adapter, import_local, import_url, validate_url,
)
from ..theme import Metrics
from ..widgets.common import Card, DropZone, SectionHeader
from .base import BasePage

log = get_logger(__name__)


class ImportWorker(QObject):
    """Runs the import on a background thread with real progress."""

    progress = Signal(float, str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str = "", path: str = "") -> None:
        super().__init__()
        self.url = url
        self.path = path
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """Ask the import to stop at the next progress checkpoint."""
        self._cancelled.set()

    def run(self) -> None:
        try:
            if self.path:
                result = import_local(
                    self.path, copy_to_media=True,
                    progress_cb=lambda p, m: self.progress.emit(p, m),
                )
            else:
                result = import_url(
                    self.url,
                    progress_cb=lambda p, m: self.progress.emit(p, m),
                )
            if self._cancelled.is_set():
                return
            self.finished.emit(result.to_dict())
        except ImportError_ as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            log.exception("import failed")
            self.failed.emit(f"Import failed: {exc}")


class NewProjectPage(BasePage):
    page_title = "New Project"
    page_subtitle = "Import a video and choose how the clips should be generated."

    def __init__(self, window) -> None:
        self._thread: QThread | None = None
        self._worker: ImportWorker | None = None
        self._last_result: dict | None = None
        super().__init__(window)

    def build(self) -> None:
        # ---- import options ----------------------------------------------------
        tabs = Card()
        tabs.add(SectionHeader("Source", "Bring in a video to analyse"))

        self.drop = DropZone()
        self.drop.file_dropped.connect(self._on_file_dropped)
        tabs.add(self.drop)

        link_box = QWidget()
        link_layout = QHBoxLayout(link_box)
        link_layout.setContentsMargins(0, Metrics.sm, 0, 0)
        link_layout.setSpacing(Metrics.sm)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "Paste a direct video URL (https://…/video.mp4) — YouTube/Vimeo/TikTok "
            "links are detected and explained"
        )
        self.url_input.returnPressed.connect(self._start_url_import)
        link_layout.addWidget(self.url_input, 1)
        self.analyze_btn = QPushButton("Analyze Link")
        self.analyze_btn.setObjectName("Primary")
        self.analyze_btn.clicked.connect(self._start_url_import)
        link_layout.addWidget(self.analyze_btn)
        tabs.add(link_box)

        self.adapter_hint = QLabel("")
        self.adapter_hint.setObjectName("CardSubtitle")
        self.adapter_hint.setWordWrap(True)
        self.adapter_hint.setVisible(False)
        tabs.add(self.adapter_hint)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        tabs.add(self.progress)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("CardSubtitle")
        self.progress_label.setVisible(False)
        tabs.add(self.progress_label)

        self.content_layout.addWidget(tabs)

        # ---- detected media -----------------------------------------------------
        self.media_card = Card()
        self.media_card.add(SectionHeader("Detected Media", "Real metadata read from the file"))
        self.media_body = QLabel("Nothing imported yet.")
        self.media_body.setObjectName("CardSubtitle")
        self.media_body.setWordWrap(True)
        self.media_card.add(self.media_body)
        self.media_card.setVisible(False)
        self.content_layout.addWidget(self.media_card)

        # ---- project settings -----------------------------------------------------
        settings = Card()
        settings.add(SectionHeader("Clip Settings", "How many shorts, how long, which format"))

        form = QFormLayout()
        form.setSpacing(Metrics.md)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Project name (auto-filled from the file)")
        form.addRow("Name", self.name_input)

        self.aspect_combo = QComboBox()
        for ratio in ASPECT_RATIOS:
            w, h = ASPECT_RATIOS[ratio]
            self.aspect_combo.addItem(f"{ratio}   ({w}×{h})", ratio)
        form.addRow("Aspect ratio", self.aspect_combo)

        self.duration_combo = QComboBox()
        for label in ("15-30", "30-45", "45-60", "60-90", "custom"):
            self.duration_combo.addItem(label.replace("-", "–") + " seconds", label)
        self.duration_combo.setCurrentIndex(1)
        form.addRow("Clip length", self.duration_combo)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(10)
        self.count_spin.setToolTip(
            "How many shorts to generate. CLIPOS will not pad the list with "
            "repetitive clips — you may get fewer if the source is short."
        )
        form.addRow("Number of shorts", self.count_spin)

        settings.add_layout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.create_btn = QPushButton("Create Project")
        self.create_btn.setObjectName("Primary")
        self.create_btn.setEnabled(False)
        self.create_btn.clicked.connect(self._create_project)
        btn_row.addWidget(self.create_btn)
        settings.add_layout(btn_row)

        self.content_layout.addWidget(settings)

        self.url_input.textChanged.connect(self._on_url_changed)

    # -- import -------------------------------------------------------------------
    def _on_url_changed(self, text: str) -> None:
        ok, msg = validate_url(text)
        if not text.strip():
            self.adapter_hint.setVisible(False)
            return
        if not ok:
            self.adapter_hint.setText(msg)
            self.adapter_hint.setStyleSheet("color: #ff9f0a;")
            self.adapter_hint.setVisible(True)
            return
        adapter = find_adapter(text.strip())
        if adapter.allows_download:
            self.adapter_hint.setText(
                f"Source: {adapter.name} — the file will be downloaded directly."
            )
            self.adapter_hint.setStyleSheet("color: #32d74b;")
        else:
            self.adapter_hint.setText(
                f"Source: {adapter.name} — {adapter.limitation()}"
            )
            self.adapter_hint.setStyleSheet("color: #ff9f0a;")
        self.adapter_hint.setVisible(True)

    def _on_file_dropped(self, path: str) -> None:
        ext = Path(path).suffix.lower()
        if ext not in SUPPORTED_VIDEO_EXTENSIONS:
            self.window.notify(f"Unsupported format: {ext}")
            return
        self._start_import(path=path)

    def _start_url_import(self) -> None:
        url = self.url_input.text().strip()
        ok, msg = validate_url(url)
        if not ok:
            self.window.notify(msg)
            return
        adapter = find_adapter(url)
        if not adapter.allows_download:
            self.window.notify(f"{adapter.name} does not allow direct downloads")
            self._on_url_changed(url)
            return
        self._start_import(url=url)

    def _start_import(self, url: str = "", path: str = "") -> None:
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Starting import…")
        self.create_btn.setEnabled(False)
        self.analyze_btn.setEnabled(False)

        self._thread = QThread(self)
        self._worker = ImportWorker(url=url, path=path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _retire_thread(self) -> None:
        """Release the finished worker thread so it is never destroyed while running."""
        thread = self._thread
        if thread is not None:
            thread.quit()
            if not thread.wait(3000):
                thread.terminate()
                thread.wait(500)
        self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        """Stop a running import and wait for its thread to finish."""
        if self._worker is not None:
            try:
                self._worker.cancel()
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            if not thread.wait(5000):
                thread.terminate()
                thread.wait(1000)
        self._thread = None
        self._worker = None

    def _on_progress(self, pct: float, message: str) -> None:
        self.progress.setValue(int(pct))
        self.progress_label.setText(message)

    def _on_finished(self, result: dict) -> None:
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self._retire_thread()
        self._last_result = result
        self.create_btn.setEnabled(True)

        if not self.name_input.text().strip():
            self.name_input.setText(result.get("title", ""))

        from ...core.ffmpeg import extract_thumbnail

        thumb = result.get("thumbnail", "")
        lines = [
            f"<b>{result.get('title','')}</b>",
            f"Duration: {result.get('duration', 0):.1f}s · "
            f"Resolution: {result.get('width', 0)}×{result.get('height', 0)} · "
            f"FPS: {result.get('fps', 0):.2f}",
            f"Audio: {'yes' if result.get('has_audio') else 'none'} · "
            f"Size: {result.get('size_bytes', 0) / 1024 / 1024:.1f} MB",
        ]
        if result.get("adapter"):
            lines.append(f"Imported via {result['adapter']}")
        self.media_body.setText("<br>".join(lines))
        self.media_card.setVisible(True)
        self.window.notify("Import complete — configure the clips and create the project")

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self._retire_thread()
        self.create_btn.setEnabled(False)
        self.window.notify(message, 7000)
        self.media_body.setText(message.replace("\n", "<br>"))
        self.media_card.setVisible(True)
        log.warning("import failed: %s", message)

    # -- project creation -----------------------------------------------------------
    def _create_project(self) -> None:
        if not self._last_result:
            return
        name = self.name_input.text().strip() or self._last_result.get("title", "Untitled")
        pid = self.db.create_project(
            name=name,
            source_path=self._last_result["path"],
            source_type=self._last_result.get("source_type", "local"),
            source_url=self._last_result.get("source_url", ""),
            duration=self._last_result.get("duration", 0),
            width=self._last_result.get("width", 0),
            height=self._last_result.get("height", 0),
            fps=self._last_result.get("fps", 0),
            has_audio=int(bool(self._last_result.get("has_audio"))),
            size_bytes=self._last_result.get("size_bytes", 0),
            thumbnail=self._last_result.get("thumbnail", ""),
            aspect_ratio=self.aspect_combo.currentData(),
            clip_count=self.count_spin.value(),
            duration_range=self.duration_combo.currentData(),
        )
        self.db.log_activity(pid, "project", f"Created project '{name}'")
        self.window.notify(f"Project '{name}' created")
        self.window.open_project(pid)
