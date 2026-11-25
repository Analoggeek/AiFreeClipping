"""Essential settings only; legacy configuration remains stored, not exposed."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
)
from .base import BasePage
from .video_clipper import BackgroundJob
from ..widgets.common import Card, SectionHeader
from ...core.config import PATHS


class EssentialSettingsPage(BasePage):
    page_title = "Settings"
    page_subtitle = "Output, processing, model storage and updates."

    def build(self):
        self.worker = None
        card = Card()
        form = QFormLayout()
        self.output = QPushButton("Change output folder…")
        self.output.setToolTip(self.db.get_setting("output_dir", str(PATHS.exports)))
        self.output.clicked.connect(self._output)
        form.addRow("Output folder", self.output)
        self.compute = QComboBox()
        self.compute.addItem("Auto (GPU if supported)", "auto")
        self.compute.addItem("CPU only", "cpu")
        self.compute.setCurrentIndex(
            max(0, self.compute.findData(self.db.get_setting("use_gpu", "auto")))
        )
        self.compute.currentIndexChanged.connect(
            lambda _: self.db.set_setting("use_gpu", self.compute.currentData())
        )
        form.addRow("Processing", self.compute)
        self.models = QPushButton("Change model storage…")
        self.models.setToolTip(str(PATHS.models))
        self.models.clicked.connect(self._models)
        form.addRow("Model storage", self.models)
        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        self.theme.addItem("System", "system")
        self.theme.setCurrentIndex(
            max(0, self.theme.findData(self.db.get_setting("theme", "dark")))
        )
        self.theme.currentIndexChanged.connect(self._theme)
        form.addRow("Appearance", self.theme)
        from ... import __version__

        form.addRow("Application version", QLabel("Ai clipping PRO " + __version__))
        card.add_layout(form)
        self.content_layout.addWidget(card)
        downloads = Card()
        downloads.add(
            SectionHeader(
                "Downloads",
                "Ollama weights use Ollama storage. App-managed speech/YOLOX weights use the model folder above.",
            )
        )
        manage = QPushButton("Open AI Models / manage downloads")
        manage.clicked.connect(lambda: self.navigate("models"))
        downloads.add(manage)
        cache = QPushButton("Open resumable installer/download cache")
        cache.clicked.connect(self._open_cache)
        downloads.add(cache)
        self.content_layout.addWidget(downloads)
        updates = Card()
        updates.add(
            SectionHeader(
                "Software updates",
                "Checks GitHub only when requested; project data is separate from installers.",
            )
        )
        self.update = QPushButton("Check for updates")
        self.update.clicked.connect(self._updates)
        updates.add(self.update)
        logs = QPushButton("Open local logs")
        logs.clicked.connect(self._logs)
        updates.add(logs)
        self.status = QLabel("No update or hardware check has run.")
        self.status.setWordWrap(True)
        updates.add(self.status)
        self.content_layout.addWidget(updates)

    def _output(self):
        path = QFileDialog.getExistingDirectory(
            self, "Output folder", self.output.text()
        )
        if path:
            self.db.set_setting("output_dir", path)
            self.output.setToolTip(path)

    def _models(self):
        path = QFileDialog.getExistingDirectory(self, "Model folder", str(PATHS.models))
        if not path:
            return
        if (
            QMessageBox.question(
                self,
                "Change model folder?",
                "Use this folder after restarting the app? Existing weights are preserved in the old location, not silently moved or deleted. Ollama manages its own model store.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        folder = Path(path)
        probe = folder / ".clipos-write-test"
        try:
            probe.write_text("")
            probe.unlink()
        except OSError as exc:
            self.status.setText("Folder is not writable: " + str(exc))
            return
        self.db.set_setting("model_storage", str(folder))
        self.models.setToolTip(str(folder))
        self.status.setText(
            "Model storage change saved; restart required. Existing weights preserved."
        )

    def _theme(self):
        from ..theme import apply_theme

        self.db.set_setting("theme", self.theme.currentData())
        apply_theme(self.window, self.theme.currentData())

    def _open_cache(self):
        PATHS.cache.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(PATHS.cache)))

    def _logs(self):
        PATHS.logs.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(PATHS.logs)))

    def _updates(self):
        if self.worker and self.worker.isRunning():
            return
        from ...core.updates import check_update
        from ... import __version__

        self.update.setEnabled(False)
        self.worker = BackgroundJob(lambda _: check_update(__version__), self)

        def done(release):
            if not release:
                self.status.setText("No newer stable release was reported.")
                return
            self.status.setText("Available: " + release["version"])
            if (
                QMessageBox.question(
                    self,
                    "Update available",
                    f"Download {release['version']}? Quit this application before installing. Project data is preserved.",
                )
                == QMessageBox.StandardButton.Yes
            ):
                QDesktopServices.openUrl(QUrl(release["url"]))

        self.worker.result.connect(done)
        self.worker.error.connect(
            lambda error: self.status.setText("Update check failed: " + error)
        )
        self.worker.finished.connect(lambda: self.update.setEnabled(True))
        self.worker.start()

    def shutdown(self):
        if self.worker and self.worker.isRunning():
            self.worker.wait()
