"""Working local EQ/dynamics/cleanup and background-audio import controls."""

import json

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QFileDialog,
)
from ...video.studio_audio import AUDIO_EFFECTS
from ...video.multitrack import MultitrackProject


class AudioPanel(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        layout = QVBoxLayout(self)
        label = QLabel(
            "Audio processing · fixed-band EQ, FFT noise reduction, compressor, limiter, echo and rumble filter. Load processors into Batch inspector, review targets and Apply. This is not AI voice reconstruction or automatic music ducking."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.processor = QComboBox()
        for key, (name, *_) in AUDIO_EFFECTS.items():
            self.processor.addItem(name, key)
        layout.addWidget(self.processor)
        self.amount = QDoubleSpinBox()
        self.amount.setDecimals(3)
        layout.addWidget(self.amount)
        self.processor.currentIndexChanged.connect(self.changed)
        self.changed()
        for title, fn in [
            ("Load processor into inspector", self.load),
            ("Append processor in inspector", lambda: self.load(True)),
            ("Clear processors on next Apply", lambda: self.populate([])),
            ("Add background audio at cursor…", self.import_audio),
        ]:
            button = QPushButton(title)
            button.clicked.connect(
                lambda checked=False, action=fn: studio.editing.run(action)
            )
            layout.addWidget(button)

    def changed(self, *args):
        _, lo, hi, value = AUDIO_EFFECTS[self.processor.currentData()]
        self.amount.setRange(lo, hi)
        self.amount.setValue(value)

    def populate(self, processors):
        from ...video.studio_audio import validate_audio_effects

        validate_audio_effects(processors)
        panel = self.studio.editing
        for key, check in panel.checks.items():
            check.setChecked(key == "audio_effects")
        panel.fields["audio_effects"].setText(json.dumps(processors))
        self.studio.status.setText(
            "Audio processors loaded, not applied yet. Choose target scope and Apply. Gain/fades remain separate unchecked settings."
        )

    def load(self, append=False):
        current = (
            json.loads(self.studio.editing.fields["audio_effects"].text())
            if append
            else []
        )
        self.populate(
            current
            + [{"kind": self.processor.currentData(), "amount": self.amount.value()}]
        )

    def import_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import local background audio",
            "",
            "Audio (*.wav *.mp3 *.m4a *.aac *.flac *.ogg);;All files (*)",
        )
        if path:
            self.import_path(path)

    def import_path(self, path):
        snapshot = self.studio.project.to_dict()
        at = self.studio.split_time.value()

        def job(worker):
            draft = MultitrackProject.from_dict(snapshot)
            media_id = draft.import_media(path, at=at)
            media = next(m for m in draft.media if m.id == media_id)
            if not media.has_audio:
                raise ValueError("Selected file has no audio stream")
            draft.lanes = [
                lane
                for lane in draft.lanes
                if not (
                    lane.kind == "video"
                    and any(item.media_id == media_id for item in lane.items)
                )
            ]
            draft.validate()
            return draft.to_dict()

        def done(data):
            try:
                if self.studio.project.to_dict() != snapshot:
                    raise ValueError("Timeline changed during import; retry")
                incoming = MultitrackProject.from_dict(data)

                def replace(draft):
                    draft.media, draft.lanes = incoming.media, incoming.lanes

                self.studio.project.edit(replace)
                self.studio.draw_timeline()
                self.studio.status.setText(
                    "Background audio added as independent track. Adjust gain/fades/processing and trim as needed; no automatic ducking applied."
                )
            except Exception as exc:
                self.studio.status.setText("Audio import failed: " + str(exc))

        self.studio._background(job, done, "Inspecting local background audio…")
