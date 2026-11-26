"""Integrated local caption generation and validated cue/word correction."""

from copy import deepcopy

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
)
from ...captions.caption_engine import CAPTION_STYLES
from ...captions.customization import ANIMATIONS
from ...ai.transcription import WHISPER_SIZES


class CaptionPanel(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Offline captions · uses batch inspector target scope · appends a new caption track"
            )
        )
        self.model = QComboBox()
        for size in WHISPER_SIZES:
            self.model.addItem(size, size)
        saved = studio.db.get_setting("stt_model", "base")
        self.model.setCurrentIndex(max(0, self.model.findData(saved)))
        self.language = QComboBox()
        for name, code in [
            ("Detect language", None),
            ("English", "en"),
            ("Hindi / Hinglish speech", "hi"),
        ]:
            self.language.addItem(name, code)
        self.style = QComboBox()
        for style in CAPTION_STYLES.values():
            self.style.addItem(style.name, style.key)
        for field in (self.model, self.language, self.style):
            layout.addWidget(field)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Selected caption text")
        layout.addWidget(self.text)
        self.start = QDoubleSpinBox()
        self.length = QDoubleSpinBox()
        for field in (self.start, self.length):
            field.setRange(0, 21600)
            field.setDecimals(4)
        self.start.setPrefix("Start seconds: ")
        self.length.setPrefix("Duration seconds: ")
        layout.addWidget(self.start)
        layout.addWidget(self.length)
        self.font = QLineEdit()
        self.font.setPlaceholderText("Font family override (empty uses preset)")
        layout.addWidget(self.font)
        self.color = QLineEdit()
        self.color.setPlaceholderText("Text color #RRGGBB (empty uses preset)")
        layout.addWidget(self.color)
        self.position = QComboBox()
        for value in ("", "top", "middle", "bottom"):
            self.position.addItem(value or "Preset position", value)
        layout.addWidget(self.position)
        self.animation = QComboBox()
        self.animation.addItem("Preset animation", "")
        for value in ANIMATIONS:
            self.animation.addItem(value, value)
        layout.addWidget(self.animation)
        self.words = QTableWidget(0, 3)
        self.words.setHorizontalHeaderLabels(
            ["Word", "Start in cue (s)", "End in cue (s)"]
        )
        self.words.setMinimumHeight(130)
        layout.addWidget(self.words)
        layout.addWidget(
            QLabel(
                "Word times are relative to the cue. After changing dialogue, clear stale word timing or correct every word."
            )
        )
        for title, fn in [
            ("Generate captions for target clips", self.generate),
            ("Read selected caption", self.read),
            ("Apply caption text / timing / style", self.apply),
            ("Clear word timings", lambda: self.words.setRowCount(0)),
            ("Add manual caption", self.add_manual),
        ]:
            button = QPushButton(title)
            button.clicked.connect(
                lambda checked=False, action=fn: studio.editing.run(action)
            )
            layout.addWidget(button)
        self.extra_options = {}

    def selected(self):
        target = self.studio.target()
        if not target:
            raise ValueError("Select a caption item in the timeline")
        lane, item = self.studio.project.find(*target)
        if lane.kind != "caption":
            raise ValueError("Select a caption item, not video/audio")
        return target, item

    def generate(self):
        from ...video.multitrack import MultitrackProject
        from ...video.studio_captions import (
            generate_timeline_captions,
            append_generated_captions,
        )

        snapshot = self.studio.project.to_dict()
        targets = self.studio.editing.targets()
        model = self.model.currentData()
        language = self.language.currentData()
        style = self.style.currentData()

        def job(worker):
            return generate_timeline_captions(
                MultitrackProject.from_dict(snapshot),
                targets,
                model_size=model,
                language=language,
                style=style,
                progress=lambda pct, message: worker.progress.emit(pct, message),
                cancelled=worker.cancelled.is_set,
            )

        def done(result):
            try:
                if self.studio.project.to_dict() != snapshot:
                    raise ValueError(
                        "Timeline changed during transcription; retry on current timeline"
                    )
                append_generated_captions(self.studio.project, result)
                self.studio.draw_timeline()
                self.studio.status.setText(
                    f"Added {result['count']} real speech cues. Detected languages: {', '.join(result['languages'])}. Review recognition accuracy before export."
                )
            except Exception as exc:
                self.studio.status.setText("Caption commit failed: " + str(exc))

        self.studio._background(job, done, "Transcribing local speech; no downloads…")

    def read(self):
        _, item = self.selected()
        self.text.setText(item.text)
        self.start.setValue(item.at)
        self.length.setValue(item.duration)
        self.style.setCurrentIndex(self.style.findData(item.caption_style))
        self.extra_options = deepcopy(item.caption_options)
        self.font.setText(item.caption_options.get("font_override", ""))
        self.color.setText(item.caption_options.get("primary_override", ""))
        self.position.setCurrentIndex(
            max(
                0,
                self.position.findData(
                    item.caption_options.get("position_override", "")
                ),
            )
        )
        self.animation.setCurrentIndex(
            max(
                0,
                self.animation.findData(
                    item.caption_options.get("animation_override", "")
                ),
            )
        )
        self.words.setRowCount(len(item.caption_words))
        for row, word in enumerate(item.caption_words):
            for col, key in enumerate(("w", "s", "e")):
                self.words.setItem(row, col, QTableWidgetItem(str(word[key])))

    def options(self):
        result = deepcopy(self.extra_options)
        for key, value in [
            ("font_override", self.font.text().strip()),
            ("primary_override", self.color.text().strip()),
            ("position_override", self.position.currentData()),
            ("animation_override", self.animation.currentData()),
        ]:
            if value:
                result[key] = value
            else:
                result.pop(key, None)
        return result

    def apply(self):
        target, item = self.selected()
        words = []
        for row in range(self.words.rowCount()):
            values = [
                self.words.item(row, col).text() if self.words.item(row, col) else ""
                for col in range(3)
            ]
            words.append({"w": values[0], "s": float(values[1]), "e": float(values[2])})
        if words and self.text.text().split() != [word["w"] for word in words]:
            raise ValueError(
                "Word text must match cue dialogue; correct words or clear timings"
            )
        self.studio.project.change_item(
            *target,
            at=self.start.value(),
            length=self.length.value(),
            text=self.text.text(),
            caption_style=self.style.currentData(),
            caption_options=self.options(),
            caption_words=words,
        )
        self.studio.draw_timeline()
        self.studio.status.setText(
            "Caption corrected. Changes are undoable and saved with the assembly."
        )

    def add_manual(self):
        self.studio.project.add_caption(
            self.text.text(),
            self.start.value(),
            self.length.value(),
            self.style.currentData(),
            self.options(),
        )
        self.studio.draw_timeline()
