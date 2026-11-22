"""AI Models: download, enable and remove offline models."""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ...ai.transcription import WHISPER_SIZES, download_whisper_model, model_installed
from ...core.config import PATHS
from ...core.logging_setup import get_logger
from ..theme import Metrics
from ..widgets.common import Card, SectionHeader, format_size
from .base import BasePage

log = get_logger(__name__)


class DownloadWorker(QThread):
    """Downloads a model with real progress."""

    progress = Signal(float, str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, size: str) -> None:
        super().__init__()
        self.size = size
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """Ask the download to stop at the next progress checkpoint."""
        self._cancelled.set()

    def run(self) -> None:
        ok = download_whisper_model(
            self.size,
            progress_cb=lambda p, m: (
                None if self._cancelled.is_set() else self.progress.emit(p, m)
            ),
        )
        if self._cancelled.is_set():
            return
        if ok:
            self.finished_ok.emit(self.size)
        else:
            self.failed.emit(f"Could not download the {self.size} model")


class AiModelsPage(BasePage):
    page_title = "AI Models"
    page_subtitle = "Models run entirely on this device. Download once, then work offline."

    def __init__(self, window) -> None:
        self._worker: DownloadWorker | None = None
        self._rows: dict[str, dict] = {}
        super().__init__(window)

    def build(self) -> None:
        card = Card()
        card.add(SectionHeader(
            "Speech Recognition (Whisper)",
            "Transcribes your audio locally — no audio ever leaves the machine",
        ))
        self.models_body = QWidget()
        self._layout = QVBoxLayout(self.models_body)
        self._layout.setSpacing(Metrics.sm)
        self._layout.setContentsMargins(0, Metrics.sm, 0, 0)
        card.add(self.models_body)
        self.content_layout.addWidget(card)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.content_layout.addWidget(self.progress)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("CardSubtitle")
        self.progress_label.setVisible(False)
        self.content_layout.addWidget(self.progress_label)

        other = Card()
        other.add(SectionHeader("Bundled Models", "Ship with the application"))
        yunet = QLabel(
            "●  YuNet face detector  ·  230 KB  ·  Installed\n"
            "    Used for speaker tracking and automatic reframing."
        )
        yunet.setWordWrap(True)
        other.add(yunet)

        cascade = QLabel(
            "●  Haar cascades  ·  3.2 MB  ·  Installed\n"
            "    Fallback face detector when the DNN model is unavailable."
        )
        cascade.setWordWrap(True)
        other.add(cascade)

        ffmpeg = QLabel("●  FFmpeg / FFprobe  ·  bundled\n    Video decoding, encoding and rendering.")
        ffmpeg.setWordWrap(True)
        other.add(ffmpeg)
        self.content_layout.addWidget(other)

        storage = Card()
        storage.add(SectionHeader("Model Storage", ""))
        self.storage_label = QLabel("")
        self.storage_label.setObjectName("CardSubtitle")
        storage.add(self.storage_label)
        clean = QPushButton("Clean up download cache")
        clean.setObjectName("Ghost")
        clean.clicked.connect(self._clean_cache)
        storage.add(clean)
        self.content_layout.addWidget(storage)

    def refresh(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        settings = self.db.get_settings()
        default_model = settings.get("stt_model", "base")
        self._rows = {}

        for size, (repo, approx) in WHISPER_SIZES.items():
            installed = model_installed(size)
            self._layout.addWidget(
                self._model_row(size, approx, installed, size == default_model)
            )

        self._update_storage()

    def _model_row(self, size: str, approx: str, installed: bool, is_default: bool) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, Metrics.xs, 0, Metrics.xs)
        lay.setSpacing(Metrics.md)

        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {'#32d74b' if installed else '#6e6e78'}; font-size: 12px;"
        )
        dot.setFixedWidth(16)
        lay.addWidget(dot)

        info = QVBoxLayout()
        info.setSpacing(0)
        name = QLabel(f"Whisper {size}")
        name.setStyleSheet("font-weight: 600;")
        if is_default:
            badge = QLabel("  (default)")
            badge.setObjectName("Badge")
            row_title = QWidget()
            rl = QHBoxLayout(row_title)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            rl.addWidget(name)
            rl.addWidget(badge)
            rl.addStretch(1)
            info.addWidget(row_title)
        else:
            info.addWidget(name)

        detail = QLabel(
            f"{approx} · {'installed, works offline' if installed else 'not downloaded'}"
        )
        detail.setObjectName("CardSubtitle")
        info.addWidget(detail)
        lay.addLayout(info, 1)

        if installed:
            use = QPushButton("Set as default")
            use.setObjectName("Ghost")
            use.clicked.connect(lambda _=False, s=size: self._set_default(s))
            lay.addWidget(use)

            remove = QPushButton("Remove")
            remove.setObjectName("Ghost")
            remove.setStyleSheet("QPushButton { color: #ff453a; }")
            remove.clicked.connect(lambda _=False, s=size: self._remove(s))
            lay.addWidget(remove)
        else:
            dl = QPushButton("Download")
            dl.setObjectName("Primary")
            dl.clicked.connect(lambda _=False, s=size: self._download(s))
            lay.addWidget(dl)
        return row

    def _set_default(self, size: str) -> None:
        self.db.set_setting("stt_model", size)
        self.window.notify(f"Whisper {size} is now the default transcription model")
        self.refresh()

    def _remove(self, size: str) -> None:
        repo, _ = WHISPER_SIZES[size]
        folder = PATHS.models / "whisper" / repo.replace("/", "--")
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        self.window.notify(f"Whisper {size} removed")
        self.refresh()

    def shutdown(self) -> None:
        """Stop a running model download and wait for it to finish."""
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

    def _download(self, size: str) -> None:
        if self._worker and self._worker.isRunning():
            self.window.notify("A download is already running")
            return
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText(f"Downloading Whisper {size}…")
        self._worker = DownloadWorker(size)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, pct: float, message: str) -> None:
        self.progress.setValue(int(pct))
        self.progress_label.setText(message)

    def _on_done(self, size: str) -> None:
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self.window.notify(f"Whisper {size} is ready — it now works offline")
        self.refresh()

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self.window.notify(message, 7000)

    def _update_storage(self) -> None:
        total = 0
        if PATHS.models.exists():
            for p in PATHS.models.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        self.storage_label.setText(f"Models use {format_size(total)} in {PATHS.models}")

    def _clean_cache(self) -> None:
        freed = 0
        for folder in (PATHS.cache,):
            if folder.exists():
                for p in folder.glob("*"):
                    try:
                        if p.is_file():
                            freed += p.stat().st_size
                            p.unlink()
                    except OSError:
                        continue
        self.window.notify(f"Cache cleared — freed {format_size(freed)}")
        self._update_storage()
