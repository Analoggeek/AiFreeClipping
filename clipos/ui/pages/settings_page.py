"""Settings: appearance, defaults, hardware, storage and privacy."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QSpinBox, QDoubleSpinBox, QVBoxLayout, QWidget,
)

from ...core.editing import enabled
from ...core.config import ASPECT_RATIOS, CLIP_DURATION_PRESETS, PATHS
from ...core.hardware import detect_hardware
from ...core.logging_setup import get_logger
from ..theme import Metrics, PALETTES, apply_theme
from ..widgets.common import Card, SectionHeader, format_size
from .base import BasePage

log = get_logger(__name__)


class UpdateCheck(QThread):
    result = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            from ... import __version__
            from ...core.updates import check_update
            self.result.emit(check_update(__version__))
        except Exception as exc:
            self.failed.emit(str(exc))


class SettingsPage(BasePage):
    page_title = "Settings"
    page_subtitle = "Everything is stored on this device. Nothing is uploaded."

    def build(self) -> None:
        settings = self.db.get_settings()

        updates = Card()
        updates.add(SectionHeader("Software updates", "By Analoggeek · checks GitHub only when requested"))
        self.update_button = QPushButton("Check for updates")
        self.update_button.clicked.connect(self._check_update)
        updates.add(self.update_button)
        updates.add(QLabel("Downloads the matching installer. Quit CLIPOS before installation. Your project library stays separate."))
        self.content_layout.addWidget(updates)

        from ...video.presets import PRESETS
        recipes = Card()
        recipes.add(SectionHeader("One-click editing recipe", "Original offline presets, not engagement guarantees"))
        recipe = self.recipe_combo = QComboBox()
        for key, (name, detail) in PRESETS.items():
            recipe.addItem(name + " — " + detail, key)
        recipe.setCurrentIndex(max(0, recipe.findData(settings.get("editing_preset", "clean"))))
        recipe.currentIndexChanged.connect(lambda _: self._save("editing_preset", recipe.currentData()))
        recipes.add(recipe)
        self.content_layout.addWidget(recipes)

        # ---------------- appearance ----------------
        appear = Card()
        appear.add(SectionHeader("Appearance", "Theme and language"))
        form = QFormLayout()
        form.setSpacing(Metrics.md)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.setCurrentIndex(0 if settings.get("theme") == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)
        form.addRow("Theme", self.theme_combo)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Auto-detect", "")
        for code, label in (
            ("en", "English"), ("es", "Español"), ("fr", "Français"),
            ("de", "Deutsch"), ("pt", "Português"), ("hi", "हिन्दी"),
            ("zh", "中文"), ("ja", "日本語"),
        ):
            self.lang_combo.addItem(label, code)
        idx = self.lang_combo.findData(settings.get("stt_language", ""))
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(
            lambda i: self._save("stt_language", self.lang_combo.currentData())
        )
        form.addRow("Speech language", self.lang_combo)

        appear.add_layout(form)
        self.content_layout.addWidget(appear)

        # ---------------- defaults ----------------
        defaults = Card()
        defaults.add(SectionHeader("Defaults", "Used for new projects and exports"))

        form2 = QFormLayout()
        form2.setSpacing(Metrics.md)

        self.aspect_combo = QComboBox()
        for ratio in ASPECT_RATIOS:
            w, h = ASPECT_RATIOS[ratio]
            self.aspect_combo.addItem(f"{ratio} ({w}×{h})", ratio)
        idx = self.aspect_combo.findData(settings.get("aspect_ratio", "9:16"))
        if idx >= 0:
            self.aspect_combo.setCurrentIndex(idx)
        self.aspect_combo.currentIndexChanged.connect(
            lambda i: self._save("aspect_ratio", self.aspect_combo.currentData())
        )
        form2.addRow("Default aspect ratio", self.aspect_combo)

        self.duration_combo = QComboBox()
        for label in ("15-30", "30-45", "45-60", "60-90"):
            self.duration_combo.addItem(label.replace("-", "–") + " s", label)
        idx = self.duration_combo.findData(settings.get("default_clip_duration", "30-45"))
        if idx >= 0:
            self.duration_combo.setCurrentIndex(idx)
        self.duration_combo.currentIndexChanged.connect(
            lambda i: self._save("default_clip_duration", self.duration_combo.currentData())
        )
        form2.addRow("Default clip length", self.duration_combo)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(int(settings.get("default_clip_count", 10)))
        self.count_spin.valueChanged.connect(
            lambda v: self._save("default_clip_count", v)
        )
        form2.addRow("Default number of shorts", self.count_spin)

        self.stt_combo = QComboBox()
        from ...ai.transcription import WHISPER_SIZES

        for size, (repo, approx) in WHISPER_SIZES.items():
            self.stt_combo.addItem(f"Whisper {size} ({approx})", size)
        idx = self.stt_combo.findData(settings.get("stt_model", "base"))
        if idx >= 0:
            self.stt_combo.setCurrentIndex(idx)
        self.stt_combo.currentIndexChanged.connect(
            lambda i: self._save("stt_model", self.stt_combo.currentData())
        )
        form2.addRow("Transcription model", self.stt_combo)

        self.gpu_combo = QComboBox()
        for label, value in (
            ("Auto — use the best available", "auto"),
            ("CPU only", "cpu"),
            ("NVIDIA NVENC", "nvidia"),
            ("Apple VideoToolbox", "apple"),
            ("Intel Quick Sync", "intel"),
        ):
            self.gpu_combo.addItem(label, value)
        idx = self.gpu_combo.findData(settings.get("use_gpu", "auto"))
        if idx >= 0:
            self.gpu_combo.setCurrentIndex(idx)
        self.gpu_combo.currentIndexChanged.connect(
            lambda i: self._save("use_gpu", self.gpu_combo.currentData())
        )
        form2.addRow("Hardware acceleration", self.gpu_combo)

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(0, 64)
        self.threads_spin.setSpecialValueText("Auto")
        self.threads_spin.setValue(int(settings.get("processing_threads", 0)))
        self.threads_spin.valueChanged.connect(
            lambda v: self._save("processing_threads", v)
        )
        form2.addRow("Processing threads", self.threads_spin)

        defaults.add_layout(form2)
        self.content_layout.addWidget(defaults)

        # ---------------- captions ----------------
        caps = Card()
        caps.add(SectionHeader("Captions", ""))
        form3 = QFormLayout()
        form3.setSpacing(Metrics.md)

        from ...captions.caption_engine import CAPTION_STYLES

        self.cap_style_combo = QComboBox()
        for key, st in CAPTION_STYLES.items():
            self.cap_style_combo.addItem(st.name, key)
        idx = self.cap_style_combo.findData(settings.get("caption_style", "bold_viral"))
        if idx >= 0:
            self.cap_style_combo.setCurrentIndex(idx)
        self.cap_style_combo.currentIndexChanged.connect(
            lambda i: self._save("caption_style", self.cap_style_combo.currentData())
        )
        form3.addRow("Default style", self.cap_style_combo)

        self.cap_size_spin = QSpinBox()
        self.cap_size_spin.setRange(20, 120)
        self.cap_size_spin.setValue(int(settings.get("caption_size", 58)))
        self.cap_size_spin.valueChanged.connect(
            lambda v: self._save("caption_size", v)
        )
        form3.addRow("Font size", self.cap_size_spin)

        self.silence_spin = QSpinBox()
        self.silence_spin.setRange(-60, 0)
        self.silence_spin.setSuffix(" dB")
        self.silence_spin.setValue(int(float(settings.get("silence_threshold_db", -32))))
        self.silence_spin.valueChanged.connect(
            lambda v: self._save("silence_threshold_db", v)
        )
        form3.addRow("Silence threshold", self.silence_spin)

        self.min_sil_spin = QDoubleSpinBox()
        self.min_sil_spin.setRange(0.1, 3.0)
        self.min_sil_spin.setSingleStep(0.05)
        self.min_sil_spin.setSuffix(" s")
        self.min_sil_spin.setValue(float(settings.get("min_silence_duration", 0.35)))
        self.min_sil_spin.valueChanged.connect(
            lambda v: self._save("min_silence_duration", v)
        )
        form3.addRow("Minimum silence", self.min_sil_spin)

        caps.add_layout(form3)
        self.content_layout.addWidget(caps)

        # ---------------- local LLM ----------------
        llm = Card()
        llm.add(SectionHeader("Local LLM (optional)", "Ollama — used for title ideas"))
        form4 = QFormLayout()
        form4.setSpacing(Metrics.md)

        self.llm_model_combo = QComboBox()
        self.llm_model_combo.setEditable(True)
        for m in ("llama3.1:8b", "llama3.2:3b", "qwen2.5:7b", "mistral:7b", "gemma2:9b"):
            self.llm_model_combo.addItem(m)
        self.llm_model_combo.setCurrentText(settings.get("llm_model", "llama3.1:8b"))
        self.llm_model_combo.currentTextChanged.connect(
            lambda t: self._save("llm_model", t)
        )
        form4.addRow("Model", self.llm_model_combo)

        self.ollama_host = QComboBox()
        self.ollama_host.setEditable(True)
        self.ollama_host.addItem("http://127.0.0.1:11434")
        self.ollama_host.setCurrentText(settings.get("ollama_host", "http://127.0.0.1:11434"))
        self.ollama_host.currentTextChanged.connect(
            lambda t: self._save("ollama_host", t)
        )
        form4.addRow("Ollama host", self.ollama_host)

        self.use_llm_check = QCheckBox("Use the local LLM for titles and descriptions")
        self.use_llm_check.setChecked(enabled(settings.get("use_llm", "0")))
        self.use_llm_check.toggled.connect(
            lambda v: self._save("use_llm", int(v))
        )
        form4.addRow("", self.use_llm_check)

        llm.add_layout(form4)
        self.llm_status = QLabel("")
        self.llm_status.setObjectName("CardSubtitle")
        llm.add(self.llm_status)
        check = QPushButton("Check Ollama connection")
        check.setObjectName("Ghost")
        check.clicked.connect(self._check_ollama)
        llm.add(check)
        self.content_layout.addWidget(llm)

        # ---------------- storage & privacy ----------------
        storage = Card()
        storage.add(SectionHeader("Storage & Privacy", ""))
        self.storage_label = QLabel("")
        self.storage_label.setObjectName("CardSubtitle")
        self.storage_label.setWordWrap(True)
        storage.add(self.storage_label)

        out_row = QHBoxLayout()
        self.out_path_label = QLabel(settings.get("output_dir", ""))
        self.out_path_label.setObjectName("CardSubtitle")
        self.out_path_label.setWordWrap(True)
        out_row.addWidget(self.out_path_label, 1)
        browse = QPushButton("Change…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._choose_output)
        out_row.addWidget(browse)
        storage.add_layout(out_row)

        self.offline_check = QCheckBox("Offline mode — never contact the network")
        self.offline_check.setChecked(enabled(settings.get("offline_mode", "1")))
        self.offline_check.toggled.connect(lambda v: self._save("offline_mode", int(v)))
        storage.add(self.offline_check)

        self.restore_check = QCheckBox("Reopen the last project on launch")
        self.restore_check.setChecked(enabled(settings.get("restore_on_launch", "1")))
        self.restore_check.toggled.connect(
            lambda v: self._save("restore_on_launch", int(v))
        )
        storage.add(self.restore_check)

        self.low_mem_check = QCheckBox("Low-memory mode (slower, smaller footprint)")
        self.low_mem_check.setChecked(enabled(settings.get("low_memory_mode", "0")))
        self.low_mem_check.toggled.connect(
            lambda v: self._save("low_memory_mode", int(v))
        )
        storage.add(self.low_mem_check)

        clear = QPushButton("Clear temporary files")
        clear.setObjectName("Ghost")
        clear.clicked.connect(self._clear_cache)
        storage.add(clear)

        settings_row = QHBoxLayout()
        export_btn = QPushButton("Export settings…")
        export_btn.setObjectName("Ghost")
        export_btn.setToolTip("Save every preference to a JSON file you can back up")
        export_btn.clicked.connect(self._export_settings)
        settings_row.addWidget(export_btn)
        import_btn = QPushButton("Import settings…")
        import_btn.setObjectName("Ghost")
        import_btn.setToolTip("Load preferences from a JSON file")
        import_btn.clicked.connect(self._import_settings)
        settings_row.addWidget(import_btn)
        settings_row.addStretch(1)
        storage.add_layout(settings_row)

        privacy = QLabel(
            "▣  CLIPOS never uploads your video, audio, transcripts or generated clips. "
            "There is no account, no subscription, and no analytics."
        )
        privacy.setWordWrap(True)
        privacy.setObjectName("CardSubtitle")
        storage.add(privacy)
        self.content_layout.addWidget(storage)

        # ---------------- recovery ----------------
        rec = Card()
        rec.add(SectionHeader("Recovery", "Projects interrupted by a crash or a forced quit"))
        self.recovery_label = QLabel("")
        self.recovery_label.setWordWrap(True)
        self.recovery_label.setObjectName("CardSubtitle")
        rec.add(self.recovery_label)
        recover_btn = QPushButton("Check for interrupted projects")
        recover_btn.setObjectName("Ghost")
        recover_btn.clicked.connect(self._recover_projects)
        rec.add(recover_btn)
        self.content_layout.addWidget(rec)
        self._refresh_recovery()

        # ---------------- hardware ----------------
        hw = Card()
        hw.add(SectionHeader("Detected Hardware", "Read from this machine"))
        self.hw_label = QLabel("")
        self.hw_label.setWordWrap(True)
        self.hw_label.setObjectName("CardSubtitle")
        hw.add(self.hw_label)
        self.content_layout.addWidget(hw)

    def _check_update(self):
        self.update_button.setEnabled(False)
        self._update_worker = UpdateCheck(self)
        self._update_worker.result.connect(self._update_ready)
        self._update_worker.failed.connect(lambda message: self.window.notify("Update check failed: " + message, 6000))
        self._update_worker.finished.connect(lambda: self.update_button.setEnabled(True))
        self._update_worker.start()

    def _update_ready(self, release):
        if not release:
            self.window.notify("You have the latest published stable version")
            return
        if QMessageBox.question(self, "Update available", f"Download {release['version']} ({release['name']})? Install after quitting CLIPOS. Project files are not removed.") == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(release["url"]))

    def shutdown(self):
        worker = getattr(self, "_update_worker", None)
        if worker and worker.isRunning():
            worker.wait(25000)

    # -- handlers ------------------------------------------------------------------
    def _save(self, key: str, value) -> None:
        self.db.set_setting(key, value)
        if hasattr(self.window, 'settings_changed'):
            self.window.settings_changed.emit()

    def _export_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export settings", str(Path.home() / "clipos-settings.json"),
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            written = self.db.export_settings(path)
        except Exception as exc:
            self.window.notify(f"Could not export settings: {exc}", 6000)
            return
        self.window.notify(f"Settings exported to {written.name}")

    def _import_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import settings", str(Path.home()), "JSON files (*.json)",
        )
        if not path:
            return
        try:
            count = self.db.import_settings(path)
        except Exception as exc:
            self.window.notify(f"Could not import settings: {exc}", 6000)
            return
        self.refresh()
        self.window.notify(f"Imported {count} settings", 4000)

    def _refresh_recovery(self) -> None:
        try:
            interrupted = self.db.find_interrupted_projects()
        except Exception:
            interrupted = []
        if interrupted:
            names = ", ".join(p["name"] for p in interrupted[:3])
            extra = f" (+{len(interrupted) - 3} more)" if len(interrupted) > 3 else ""
            self.recovery_label.setText(
                f"{len(interrupted)} project(s) were interrupted: {names}{extra}. "
                "Run the recovery to make them available again."
            )
        else:
            self.recovery_label.setText("No interrupted projects — everything is in order.")

    def _recover_projects(self) -> None:
        recovered = self.db.recover_projects()
        self._refresh_recovery()
        if not recovered:
            self.window.notify("Nothing to recover")
            return
        missing = [p for p in recovered if p["status"] == "error"]
        if missing:
            self.window.notify(
                f"Recovered {len(recovered) - len(missing)} project(s); "
                f"{len(missing)} source file(s) are missing", 7000,
            )
        else:
            self.window.notify(f"Recovered {len(recovered)} project(s)", 5000)
        self.window.refresh_all()

    def _apply_theme(self) -> None:
        theme = self.theme_combo.currentData()
        self.db.set_setting("theme", theme)
        apply_theme(self.window, theme)

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if path:
            self.db.set_setting("output_dir", path)
            self.out_path_label.setText(path)

    def _check_ollama(self) -> None:
        from ...ai.title_generator import ollama_available, ollama_models

        host = self.ollama_host.currentText()
        if ollama_available(host):
            models = ollama_models(host)
            self.llm_status.setText(
                f"Connected. Installed models: {', '.join(models) if models else 'none'}"
            )
        else:
            self.llm_status.setText(
                "No Ollama server found. Titles fall back to the built-in rule-based "
                "generator, which works fully offline."
            )

    def _clear_cache(self) -> None:
        freed = 0
        if PATHS.cache.exists():
            for p in PATHS.cache.rglob("*"):
                try:
                    if p.is_file():
                        freed += p.stat().st_size
                        p.unlink()
                except OSError:
                    continue
        if PATHS.tmp.exists():
            shutil.rmtree(PATHS.tmp, ignore_errors=True)
            PATHS.tmp.mkdir(parents=True, exist_ok=True)
        self.window.notify(f"Cleared temporary files — freed {format_size(freed)}")
        self.refresh()

    def refresh(self) -> None:
        values=self.db.get_settings()
        for name,key in [('recipe_combo','editing_preset'),('aspect_combo','aspect_ratio'),('duration_combo','default_clip_duration'),('stt_combo','stt_model'),('gpu_combo','use_gpu'),('cap_style_combo','caption_style')]:
            widget=getattr(self,name,None)
            if widget is not None:
                idx=widget.findData(values.get(key, values.get('default_aspect','9:16') if key=='aspect_ratio' else None))
                if idx>=0:
                    widget.blockSignals(True);widget.setCurrentIndex(idx);widget.blockSignals(False)
        for name,key in [('count_spin','default_clip_count'),('threads_spin','processing_threads'),('cap_size_spin','caption_size'),('silence_spin','silence_threshold_db'),('min_sil_spin','min_silence_duration')]:
            widget=getattr(self,name,None)
            if widget is not None:
                widget.blockSignals(True);widget.setValue(values[key]);widget.blockSignals(False)
        for name,key in [('offline_check','offline_mode'),('restore_check','restore_on_launch'),('low_mem_check','low_memory_mode')]:
            widget=getattr(self,name,None)
            if widget is not None:
                widget.blockSignals(True);widget.setChecked(enabled(values[key]));widget.blockSignals(False)
        self.out_path_label.setText(values.get('output_dir',''))
        stats = self.db.stats()
        self.storage_label.setText(
            f"{stats['projects']} projects · {stats['clips']} clips · "
            f"{stats['exports']} exports · {format_size(stats['storage_bytes'])} used\n"
            f"Data folder: {PATHS.root}"
        )

        prof = detect_hardware()
        enc = ", ".join(sorted(prof.ffmpeg_encoders.keys())) or "none detected"
        self.hw_label.setText(
            f"OS: {prof.os_name} {prof.os_version} ({prof.arch})\n"
            f"CPU: {prof.cpu_name} — {prof.cpu_cores} cores / {prof.cpu_threads} threads\n"
            f"RAM: {prof.ram_total_mb} MB total, {prof.ram_available_mb} MB available\n"
            f"GPU: {prof.gpu.label} (vendor: {prof.gpu.vendor or 'none'})\n"
            f"Hardware encode: {'yes' if prof.gpu.cuda_available or prof.is_apple_silicon else 'CPU only'}\n"
            f"Torch: {'available' if prof.torch_available else 'not installed'}"
            f"{' (CUDA)' if prof.torch_cuda else ''}{' (Metal)' if prof.torch_mps else ''}\n"
            f"FFmpeg encoders: {enc}"
        )
