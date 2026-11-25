"""One model manager surface. No duplicate Director/experimental model panels."""

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
)
from .base import BasePage
from .video_clipper import BackgroundJob
from ..widgets.common import Card, SectionHeader
from ..widgets.flow_layout import FlowLayout
from ...ai.model_manager import ModelManager, OLLAMA_MODELS, preflight
from ...ai.transcription import WHISPER_SIZES, download_whisper_model, local_model_path
from ...core.config import PATHS
from ...db.database import Database


class ModelsPage(BasePage):
    page_title = "AI Models"
    page_subtitle = "Explicit downloads. Integrity checks. Actual runtime tests before verified registration."

    def build(self):
        self.worker = None
        self.buttons = []
        runtime = Card()
        runtime.add(
            SectionHeader(
                "Ollama runtime",
                "Install the official runtime once, then download local weights separately. OS confirmation is required.",
            )
        )
        self._buttons(
            runtime,
            [
                ("Install Ollama…", self._install_ollama),
                ("Start / verify local service", self._start_ollama),
                ("Refresh installed models", self._check_ollama),
            ],
        )
        self.runtime_status = QLabel(
            "Not checked. No runtime or model readiness assumed."
        )
        self.runtime_status.setWordWrap(True)
        runtime.add(self.runtime_status)
        self.content_layout.addWidget(runtime)
        language = Card()
        language.add(
            SectionHeader(
                "Local language models",
                "Used only when local Ollama ranking is explicitly selected. Gemma terms / Llama terms apply; Qwen 0.5B uses Apache-2.0.",
            )
        )
        self.model = QComboBox()
        self.model.setMinimumContentsLength(24)
        self.model.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        for tag, (label, disk, ram) in OLLAMA_MODELS.items():
            self.model.addItem(
                f"{label} · {disk} GiB disk / {ram} GiB RAM estimate", tag
            )
        self.model.setCurrentIndex(
            max(0, self.model.findData(self.db.get_setting("llm_model", "gemma:7b")))
        )
        language.add(self.model)
        self._buttons(
            language,
            [
                ("Download / retry…", self._pull),
                ("Test and select", self._select_model),
                ("Unload", self._unload),
                (
                    "Disable language ranking",
                    lambda: self._run(
                        lambda m, j: (
                            m.db.set_setting("ollama_model_enabled", False)
                            or "Language ranking disabled"
                        )
                    ),
                ),
                ("Delete model…", self._delete_model),
            ],
        )
        language.add(
            QLabel(
                "Actual quantization and local GGUF format are verified by Ollama /api/show, not guessed from a filename."
            )
        )
        self.content_layout.addWidget(language)
        speech = Card()
        speech.add(
            SectionHeader(
                "Whisper speech analysis",
                "Downloaded from Systran faster-whisper repositories. CPU loading and inference are tested before registration.",
            )
        )
        self.speech = QComboBox()
        for size, (_, approx) in WHISPER_SIZES.items():
            self.speech.addItem(f"{size} · {approx}", size)
        self.speech.setCurrentIndex(
            max(0, self.speech.findData(self.db.get_setting("stt_model", "base")))
        )
        speech.add(self.speech)
        self._buttons(
            speech,
            [
                ("Download / retry speech…", self._download_speech),
                ("Verify and enable speech", self._test_speech),
                (
                    "Disable speech",
                    lambda: self._run(
                        lambda m, j: (
                            m.db.set_setting("stt_enabled", False)
                            or "Speech analysis disabled"
                        )
                    ),
                ),
                ("Delete speech…", self._delete_speech),
            ],
        )
        self.content_layout.addWidget(speech)
        vision = Card()
        vision.add(
            SectionHeader(
                "YOLOX + ByteTrack",
                "Official YOLOX nano ONNX · 3.49 MiB · Apache-2.0. CPU ONNX detector + supervision 0.27.0 tracking. No CUDA required.",
            )
        )
        self._buttons(
            vision,
            [
                ("Download and test YOLOX…", self._download_yolox),
                (
                    "Verify weights + inference",
                    lambda: self._run(lambda m, j: m.verify_yolox()),
                ),
                (
                    "Test ByteTrack runtime",
                    lambda: self._run(lambda m, j: m.test_bytetrack()),
                ),
            ],
        )
        self._buttons(
            vision,
            [
                (
                    "Enable tracking",
                    lambda: self._run(
                        lambda m, j: (
                            m.enable_tracking(True)
                            or "Tracking enabled for analysis; saved crop remains authoritative."
                        )
                    ),
                ),
                (
                    "Disable tracking",
                    lambda: self._run(
                        lambda m, j: m.enable_tracking(False) or "Tracking disabled."
                    ),
                ),
                ("Delete YOLOX…", self._delete_yolox),
            ],
        )
        self.content_layout.addWidget(vision)
        self.registry = QLabel()
        self.registry.setWordWrap(True)
        self.content_layout.addWidget(self.registry)
        self.progress = QProgressBar()
        self.progress.hide()
        self.content_layout.addWidget(self.progress)
        self.status = QLabel(
            "Download is not the same as verified inference. Failed operations remain retryable."
        )
        self.status.setWordWrap(True)
        self.content_layout.addWidget(self.status)
        cancel = QPushButton("Cancel current download / operation")
        cancel.clicked.connect(self._cancel)
        self.content_layout.addWidget(cancel)
        for label in self.findChildren(QLabel):
            label.setWordWrap(True)
        self.refresh()

    def _buttons(self, card, actions):
        row = FlowLayout()
        for text, callback in actions:
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.buttons.append(button)
        card.add_layout(row)

    def _confirm(self, title, message):
        return (
            QMessageBox.question(self, title, message) == QMessageBox.StandardButton.Yes
        )

    def _run(self, fn):
        if self.worker and self.worker.isRunning():
            return
        dbpath = self.db.path

        def job(task):
            db = Database(dbpath)
            try:
                return fn(ModelManager(db), task)
            finally:
                db.close()

        self.worker = BackgroundJob(job, self)
        self.worker.result.connect(lambda value: self.status.setText(str(value)))
        self.worker.error.connect(
            lambda error: self.status.setText(
                "Failed: "
                + error
                + " Retry the same operation after correcting the cause."
            )
        )
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._finished)
        for b in self.buttons:
            b.setEnabled(False)
        self.model.setEnabled(False)
        self.speech.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText("Checking prerequisites / running the requested operation…")
        self.window.set_busy(True, "Managing local models…")
        self.worker.start()

    def _progress(self, pct, message):
        self.progress.setRange(0, 100)
        self.progress.setValue(int(pct))
        self.status.setText(message)

    def _finished(self):
        for b in self.buttons:
            b.setEnabled(True)
        self.model.setEnabled(True)
        self.speech.setEnabled(True)
        self.progress.hide()
        self.refresh()
        self.window.set_busy(False)
        self.window.settings_changed.emit()

    def _cancel(self):
        if self.worker:
            self.worker.cancelled.set()
            self.status.setText(
                "Cancellation requested. Partial downloads are retained where the upstream runtime supports resume."
            )

    def _install_ollama(self):
        if not self._confirm(
            "Install official Ollama runtime?",
            "Download the SHA256-pinned official Ollama installer (up to 2 GB), then run the normal OS installation? Windows may request permission; macOS signature/notarization checks remain enforced. This does not download a language model.",
        ):
            return
        from ...core.ollama_install import install

        self._run(
            lambda m, j: install(
                consent=True, progress=j.progress.emit, cancelled=j.cancelled.is_set
            )
        )

    def _start_ollama(self):
        from ...core.ollama_install import start_service

        self._run(lambda m, j: start_service(cancelled=j.cancelled.is_set))

    def _check_ollama(self):
        from ...ai.gemma_runtime import GemmaRuntime

        self._run(
            lambda m, j: (
                "Installed local Ollama models: " + str(GemmaRuntime().status())
            )
        )

    def _pull(self):
        model = self.model.currentData()
        if not self._confirm(
            "Download model weights?",
            f"Download {model} through the local Ollama API? This requires several GB. Review the official model license/terms before continuing. Gemma/Llama have their own terms. After download, a real inference test will run. No recording is uploaded.",
        ):
            return

        def progress(job, state):
            total = state.get("total", 0)
            completed = state.get("completed", 0)
            if total:
                job.progress.emit(
                    100 * completed / total,
                    str(state.get("status")) + f" · {completed:,}/{total:,} bytes",
                )
            else:
                job.progress.emit(0, str(state.get("status", "Verifying model")))

        self._run(
            lambda m, j: m.pull_ollama(
                model,
                consent=True,
                progress=lambda state: progress(j, state),
                cancelled=j.cancelled.is_set,
            )
        )

    def _select_model(self):
        model = self.model.currentData()
        self._run(lambda m, j: m.use_ollama(model))

    def _unload(self):
        from ...ai.gemma_runtime import GemmaRuntime

        model = self.model.currentData()
        self._run(lambda m, j: GemmaRuntime().unload(model) or "Model unloaded")

    def _delete_model(self):
        model = self.model.currentData()
        if self._confirm(
            "Delete language weights?",
            f"Delete {model} from local Ollama? Other applications using that model will also lose access until it is downloaded again.",
        ):
            self._run(lambda m, j: m.delete_ollama(model) or "Model removed")

    def _download_speech(self):
        size = self.speech.currentData()
        if not self._confirm(
            "Download speech weights?",
            f"Download the official faster-whisper {size} weights? Uses Hugging Face with upstream resumable downloads, then a real CPU inference test. No audio upload.",
        ):
            return
        self._run(
            lambda m, j: m.download_whisper(
                size,
                consent=True,
                progress=j.progress.emit,
                cancelled=j.cancelled.is_set,
            )
        )

    def _test_speech(self):
        size = self.speech.currentData()

        def verify(m, j):
            result = m.verify_whisper(size)
            m.db.set_setting("stt_model", size)
            return result

        self._run(verify)

    def _delete_speech(self):
        size = self.speech.currentData()
        if not self._confirm(
            "Delete speech weights?", f"Delete the managed Whisper {size} model?"
        ):
            return

        def remove(m, j):
            import shutil
            from ...ai.transcription import WHISPER_SIZES

            root = (
                PATHS.models / "whisper" / WHISPER_SIZES[size][0].replace("/", "--")
            ).resolve()
            if not root.is_relative_to((PATHS.models / "whisper").resolve()):
                raise ValueError("Invalid model path")
            if root.exists():
                shutil.rmtree(root)
            m.forget("whisper:" + size)
            return "Managed speech weights removed; externally cached weights are not deleted."

        self._run(remove)

    def _download_yolox(self):
        if self._confirm(
            "Download official YOLOX weights?",
            "Download 3.49 MiB from the official Apache-2.0 YOLOX release? SHA256, model input/output compatibility, real CPU inference and ByteTrack association are checked before registration.",
        ):
            self._run(
                lambda m, j: m.install_yolox(
                    consent=True, progress=j.progress.emit, cancelled=j.cancelled.is_set
                )
            )

    def _delete_yolox(self):
        if self._confirm(
            "Delete YOLOX weights?",
            "Remove managed YOLOX weights and disable tracking?",
        ):
            self._run(
                lambda m, j: m.delete_yolox() or "YOLOX removed; tracking disabled."
            )

    def refresh(self):
        rows = ModelManager(self.db).registry()
        details = []
        for key, value in rows.items():
            path = value.get("path")
            state = "Verified by previous runtime test"
            if path and not Path(path).is_file() and not Path(path).is_dir():
                state = "Files missing — verify/download again"
            details.append(f"{key}: {state}. {value.get('test', '')}")
        self.registry.setText(
            "Verified model registry (persisted across restarts):\n"
            + ("\n".join(details) or "No verified models registered.")
        )

    def shutdown(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancelled.set()
            self.worker.wait()
