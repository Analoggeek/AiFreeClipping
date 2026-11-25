"""Settings: appearance, defaults, hardware, storage and privacy."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QSpinBox, QDoubleSpinBox, QVBoxLayout, QWidget,
)

from ...core.editing import enabled
from ...core.config import ASPECT_RATIOS, CLIP_DURATION_PRESETS, PATHS
from ...core.hardware import detect_hardware, choose_encoder, suggest_worker_threads
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
            ("AMD AMF", "amd"),
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

        self.music_path_label = QLabel(settings.get("background_music", "") or "No background music")
        self.music_path_label.setWordWrap(True)
        music_row = QHBoxLayout()
        music_row.addWidget(self.music_path_label, 1)
        choose_music = QPushButton("Choose local audio…")
        choose_music.clicked.connect(self._choose_music)
        music_row.addWidget(choose_music)
        clear_music = QPushButton("Clear")
        clear_music.clicked.connect(lambda: self._set_music(""))
        music_row.addWidget(clear_music)
        form3.addRow("Background music", music_row)
        self.music_volume_spin = QDoubleSpinBox()
        self.music_volume_spin.setRange(0., 1.)
        self.music_volume_spin.setSingleStep(.02)
        self.music_volume_spin.setValue(float(settings.get("bgm_volume", .12)))
        self.music_volume_spin.valueChanged.connect(lambda v: self._save("bgm_volume", v))
        form3.addRow("Music level (0–1)", self.music_volume_spin)
        self.music_duck_check = QCheckBox("Lower music when source audio is loud")
        self.music_duck_check.setToolTip("Signal-driven ducking; loud game sounds also lower music. Not speaker identification.")
        self.music_duck_check.setChecked(enabled(settings.get("bgm_ducking", True)))
        self.music_duck_check.toggled.connect(lambda v: self._save("bgm_ducking", int(v)))
        form3.addRow("Music ducking", self.music_duck_check)

        caps.add_layout(form3)
        self.content_layout.addWidget(caps)

        tracking = Card()
        tracking.add(SectionHeader("Continuous person tracking (optional)",
            "Local YOLOX raw-head COCO ONNX + ByteTrack · CPU · body evidence, not speaker identity"))
        self.person_model_label = QLabel(settings.get("person_model_path", "") or "Disabled — select installed local YOLOX ONNX weights")
        self.person_model_label.setWordWrap(True)
        tracking.add(self.person_model_label)
        tracking_row = QHBoxLayout()
        select_model = QPushButton("Select installed model…")
        select_model.clicked.connect(self._choose_person_model)
        tracking_row.addWidget(select_model)
        clear_model = QPushButton("Disable")
        clear_model.clicked.connect(lambda:self._set_person_model(""))
        tracking_row.addWidget(clear_model)
        tracking.add_layout(tracking_row)
        self.body_reframe_check = QCheckBox("Follow body evidence in non-gaming auto framing")
        self.body_reframe_check.setChecked(enabled(settings.get("body_reframe",True)))
        self.body_reframe_check.toggled.connect(lambda value:self._save("body_reframe",int(value)))
        tracking.add(self.body_reframe_check)
        self.shot_reframe_check=QCheckBox('Hold one face crop per shot; reset at scene cuts (heuristic)')
        self.shot_reframe_check.setChecked(enabled(settings.get('shot_aware_reframe','1')))
        self.shot_reframe_check.toggled.connect(lambda v:self._save('shot_aware_reframe',int(v)))
        tracking.add(self.shot_reframe_check)
        self.body_track_spin = QSpinBox()
        self.body_track_spin.setRange(0,2147483647)
        self.body_track_spin.setValue(int(settings.get("body_track_id",0)))
        self.body_track_spin.setSpecialValueText("Auto: longest-supported person")
        self.body_track_spin.setToolTip("Person ID from this project's tracking artifact; not a speaker label")
        self.body_track_spin.valueChanged.connect(lambda value:self._save("body_track_id",value))
        tracking.add(self.body_track_spin)
        tracking.add(SectionHeader("Anonymous neural diarization (optional)",
            "Installed sherpa-compatible segmentation + embedding ONNX · CPU · no named identity"))
        self.diarization_label = QLabel()
        self.diarization_label.setWordWrap(True)
        tracking.add(self.diarization_label)
        self._update_diarization_label()
        diarization_row=QHBoxLayout()
        for text,key in [("Select segmentation…","diarization_segmentation"),("Select embedding…","diarization_embedding")]:
            button=QPushButton(text);button.clicked.connect(lambda checked=False,k=key:self._choose_diarization_model(k))
            diarization_row.addWidget(button)
        disable=QPushButton("Disable diarization");disable.clicked.connect(self._disable_diarization)
        diarization_row.addWidget(disable);tracking.add_layout(diarization_row)
        self.content_layout.addWidget(tracking)

        # ---------------- local LLM ----------------
        llm = Card()
        llm.add(SectionHeader("Local LLM (optional)", "Local Ollama — metadata and bounded edit plans; loopback only"))
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

        self.learn_preferences_check=QCheckBox('Learn bounded local selection preferences from successful exports')
        self.learn_preferences_check.setChecked(enabled(settings.get('learn_selection_preferences','0')))
        self.learn_preferences_check.toggled.connect(lambda v:self._save('learn_selection_preferences',int(v)))
        form4.addRow('',self.learn_preferences_check)
        reset_preferences=QPushButton('Delete learned selection feature snapshots')
        reset_preferences.clicked.connect(self._reset_preferences)
        form4.addRow('',reset_preferences)
        self.automatic_selection_check=QCheckBox('Strict automatic clip selection (no duplicate-count padding)')
        self.automatic_selection_check.setChecked(enabled(settings.get('automatic_selection','1')))
        self.automatic_selection_check.toggled.connect(lambda v:self._save('automatic_selection',int(v)))
        form4.addRow('',self.automatic_selection_check)
        self.selection_intent_check=QCheckBox('Compile direction into grounded phrases / explicit clock ranges locally')
        self.selection_intent_check.setChecked(enabled(settings.get('selection_compile_intent','0')))
        self.selection_intent_check.toggled.connect(lambda v:self._save('selection_compile_intent',int(v)))
        form4.addRow('',self.selection_intent_check)
        self.talknet_check=QCheckBox('Use local TalkNet audiovisual face association (CPU, explicit checkpoint)')
        self.talknet_check.setChecked(enabled(settings.get('talknet_enabled','0')))
        self.talknet_check.toggled.connect(lambda v:self._save('talknet_enabled',int(v)))
        form4.addRow('',self.talknet_check)
        self.talknet_checkpoint_field=QLineEdit(str(settings.get('talknet_checkpoint','')))
        self.talknet_checkpoint_field.editingFinished.connect(lambda:self._save('talknet_checkpoint',self.talknet_checkpoint_field.text()))
        form4.addRow('Trusted local TalkNet checkpoint',self.talknet_checkpoint_field)
        self.selection_sound_check=QCheckBox('Local AST sound classification (explicitly installed runtime and model)')
        self.selection_sound_check.setChecked(enabled(settings.get('selection_sound_review','0')))
        self.selection_sound_check.toggled.connect(lambda v:self._save('selection_sound_review',int(v)))
        form4.addRow('',self.selection_sound_check)
        self.selection_sound_model_field=QLineEdit(str(settings.get('selection_sound_model','')))
        self.selection_sound_model_field.editingFinished.connect(lambda:self._save('selection_sound_model',self.selection_sound_model_field.text()))
        form4.addRow('Local AST model directory',self.selection_sound_model_field)
        self.selection_ocr_check=QCheckBox('Read finalist on-screen text with explicitly installed local OCR models')
        self.selection_ocr_check.setChecked(enabled(settings.get('selection_ocr_review','0')))
        self.selection_ocr_check.toggled.connect(lambda v:self._save('selection_ocr_review',int(v)))
        form4.addRow('',self.selection_ocr_check)
        self.selection_vision_check=QCheckBox('Local visual-model review of up to four finalists (three source frames each)')
        self.selection_vision_check.setChecked(enabled(settings.get('selection_visual_review','0')))
        self.selection_vision_check.toggled.connect(lambda v:self._save('selection_visual_review',int(v)))
        form4.addRow('',self.selection_vision_check)
        self.selection_vision_model_field=QLineEdit(str(settings.get('selection_vision_model','')))
        self.selection_vision_model_field.setMaxLength(160)
        self.selection_vision_model_field.editingFinished.connect(lambda:self._save('selection_vision_model',self.selection_vision_model_field.text()))
        form4.addRow('Installed local vision model',self.selection_vision_model_field)
        self.selection_rerank_check=QCheckBox('Rerank up to 24 finalists with installed local model')
        self.selection_rerank_check.setChecked(enabled(settings.get('selection_local_rerank','0')))
        self.selection_rerank_check.toggled.connect(lambda v:self._save('selection_local_rerank',int(v)))
        form4.addRow('',self.selection_rerank_check)
        for label,key,limit in [('Prefer transcript phrases (comma-separated)','selection_include',2000),
                                ('Exclude transcript phrases (comma-separated)','selection_exclude',2000),
                                ('Selection direction (local compilation / reranking)','selection_direction',1000)]:
            field=QLineEdit(str(settings.get(key,'')));field.setMaxLength(limit)
            field.editingFinished.connect(lambda k=key,f=field:self._save(k,f.text()))
            setattr(self,key+'_field',field);form4.addRow(label,field)
        llm.add(QLabel('Phrases match transcript words, not unseen visuals. Missing local model keeps measured ranking.'))
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

    def _reset_preferences(self):
        from ...ai.preferences import reset
        reset(self.db)
        self.window.notify('Local selection feature snapshots deleted; preferences reset',5000)

    def _update_diarization_label(self):
        values=self.db.get_settings()
        self.diarization_label.setText("Segmentation: "+(values.get("diarization_segmentation") or "not installed/selected")+
            "\nEmbedding: "+(values.get("diarization_embedding") or "not installed/selected"))

    def _choose_diarization_model(self,key):
        path,_=QFileDialog.getOpenFileName(self,"Select trusted sherpa-compatible local "+key,"","ONNX (*.onnx)")
        if path:self._save(key,path);self._update_diarization_label()

    def _disable_diarization(self):
        self.db.set_settings({"diarization_segmentation":"","diarization_embedding":""})
        self._update_diarization_label()
        self.window.settings_changed.emit()

    def _set_person_model(self, path: str) -> None:
        self._save("person_model_path", path)
        self.person_model_label.setText(path or "Disabled — select installed local YOLOX ONNX weights")

    def _choose_person_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select trusted local raw-head YOLOX COCO model", "", "ONNX weights (*.onnx)")
        if path:
            self._set_person_model(path)

    def _set_music(self, path: str) -> None:
        self._save("background_music", path)
        self.music_path_label.setText(path or "No background music")

    def _choose_music(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose local background audio", "",
                                             "Audio (*.wav *.mp3 *.m4a *.aac *.flac *.ogg);;All files (*)")
        if path:
            self._set_music(path)

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if path:
            self.db.set_setting("output_dir", path)
            self.out_path_label.setText(path)

    def _check_ollama(self) -> None:
        from ...ai.title_generator import ollama_available, ollama_models

        host = self.ollama_host.currentText()
        from ...core.local_ai import local_endpoint,LocalAIError
        try:local_endpoint(host)
        except LocalAIError as exc:
            self.llm_status.setText(str(exc));return
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
        for name,key in [('count_spin','default_clip_count'),('threads_spin','processing_threads'),('cap_size_spin','caption_size'),('silence_spin','silence_threshold_db'),('min_sil_spin','min_silence_duration'),('music_volume_spin','bgm_volume'),('body_track_spin','body_track_id')]:
            widget=getattr(self,name,None)
            if widget is not None:
                widget.blockSignals(True);widget.setValue(values[key]);widget.blockSignals(False)
        for name,key in [('offline_check','offline_mode'),('restore_check','restore_on_launch'),('low_mem_check','low_memory_mode'),('music_duck_check','bgm_ducking'),('body_reframe_check','body_reframe'),('automatic_selection_check','automatic_selection'),('selection_rerank_check','selection_local_rerank'),('learn_preferences_check','learn_selection_preferences'),('speaker_colors_check','speaker_caption_colors'),('selection_vision_check','selection_visual_review'),('selection_intent_check','selection_compile_intent'),('shot_reframe_check','shot_aware_reframe'),('selection_ocr_check','selection_ocr_review'),('selection_sound_check','selection_sound_review'),('talknet_check','talknet_enabled')]:
            widget=getattr(self,name,None)
            if widget is not None:
                widget.blockSignals(True);widget.setChecked(enabled(values[key]));widget.blockSignals(False)
        for key in ('selection_include','selection_exclude','selection_direction','selection_vision_model','selection_sound_model','talknet_checkpoint'):
            widget=getattr(self,key+'_field',None)
            if widget is not None:
                widget.blockSignals(True);widget.setText(str(values.get(key,'')));widget.blockSignals(False)
        self._update_diarization_label()
        self.person_model_label.setText(values.get('person_model_path','') or 'Disabled — select installed local YOLOX ONNX weights')
        self.music_path_label.setText(values.get('background_music','') or 'No background music')
        self.out_path_label.setText(values.get('output_dir',''))
        stats = self.db.stats()
        self.storage_label.setText(
            f"{stats['projects']} projects · {stats['clips']} clips · "
            f"{stats['exports']} exports · {format_size(stats['storage_bytes'])} used\n"
            f"Data folder: {PATHS.root}"
        )

        if not hasattr(self,'_hardware_worker'):
            self.hw_label.setText('Detecting hardware in the background…')
            self._hardware_worker=HardwareSummary(self)
            self._hardware_worker.result.connect(self.hw_label.setText)
            self._hardware_worker.start()

    def shutdown(self):
        for name in ('_hardware_worker','_update_worker'):
            worker=getattr(self,name,None)
            if worker and worker.isRunning():worker.wait()


class HardwareSummary(QThread):
    result=Signal(str)

    def run(self):
        try:self.result.emit(self.summary())
        except Exception as exc:self.result.emit("Hardware diagnostics unavailable: "+str(exc))

    def summary(self):
        prof = detect_hardware()
        enc = ", ".join(sorted(prof.ffmpeg_encoders.keys())) or "none detected"
        return (
            f"OS: {prof.os_name} {prof.os_version} ({prof.arch})\n"
            f"CPU: {prof.cpu_name} — {prof.cpu_cores} cores / {prof.cpu_threads} threads\n"
            f"RAM: {prof.ram_total_mb} MB total, {prof.ram_available_mb} MB available\n"
            f"GPU: {prof.gpu.label} (vendor: {prof.gpu.vendor or 'none'})\n"
            f"Encoder candidate: {choose_encoder(verify=False).description} (unverified; tested at export, CPU fallback)\n"
            f"Automatic worker budget now: {suggest_worker_threads()} threads\n"
            f"Torch: {'available' if prof.torch_available else 'not installed'}"
            f"{' (CUDA)' if prof.torch_cuda else ''}{' (Metal)' if prof.torch_mps else ''}\n"
            f"FFmpeg encoders: {enc}"
        )
