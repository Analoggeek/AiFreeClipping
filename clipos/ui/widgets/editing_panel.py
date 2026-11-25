"""Functional selective batch inspector; no unsupported effects are advertised."""

import json
from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QPushButton,
    QLabel,
    QFileDialog,
)
from ...video.editing_preset import EditingPreset, DEFAULTS, apply_editing_preset
from ...captions.caption_engine import CAPTION_STYLES


class EditingPanel(QWidget):
    FUTURE_KEY = "studio_future_editing_preset_v1"

    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Selective batch editing · only checked categories are copied")
        )
        self.name = QLineEdit("Studio style")
        layout.addWidget(self.name)
        self.checks = {}
        self.fields = {}
        self.caption_options = {}
        ranges = {
            "brightness": (-1, 1),
            "contrast": (0, 3),
            "saturation": (0, 3),
            "x": (0, 1),
            "y": (0, 1),
            "w": (0.01, 1),
            "h": (0.01, 1),
            "opacity": (0, 1),
            "rotation": (-180, 180),
            "gain": (0, 4),
            "fade_in_fraction": (0, 1),
            "fade_out_fraction": (0, 1),
        }
        for category, values in DEFAULTS.items():
            check = QCheckBox(category.title())
            self.checks[category] = check
            check.setChecked(category == "color")
            layout.addWidget(check)
            form = QFormLayout()
            for key, value in values.items():
                if key == "caption_options":
                    continue
                if key == "caption_style":
                    field = QComboBox()
                    for style in CAPTION_STYLES.values():
                        field.addItem(style.name, style.key)
                    field.setCurrentIndex(field.findData(value))
                else:
                    field = QDoubleSpinBox()
                    field.setDecimals(4)
                    field.setRange(*ranges[key])
                    field.setSingleStep(0.05)
                    field.setValue(value)
                self.fields[key] = field
                form.addRow(key.replace("_", " ").title(), field)
            layout.addLayout(form)
        self.scope = QComboBox()
        for title, key in [
            ("Current timeline media", "current"),
            ("Selected queue clips on timeline", "selected"),
            ("All timeline media", "all"),
            ("Named queue group on timeline", "group"),
        ]:
            self.scope.addItem(title, key)
        layout.addWidget(self.scope)
        self.group = QLineEdit()
        self.group.setPlaceholderText("Exact queue group name")
        layout.addWidget(self.group)
        for title, fn in [
            ("Read current item settings", self.read_current),
            ("Apply checked categories", self.apply),
            ("Use checked categories for future imports", self.set_future),
            ("Clear future defaults", self.clear_future),
            ("Save preset…", self.save),
            ("Load preset…", self.load),
        ]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, action=fn: self.run(action))
            layout.addWidget(button)

    def run(self, fn):
        if self.studio.worker and self.studio.worker.isRunning():
            self.studio.status.setText("Wait for background work to finish.")
            return
        try:
            fn()
        except Exception as exc:
            self.studio.status.setText("Editing failed: " + str(exc))

    def preset(self):
        categories = {}
        for category, defaults in DEFAULTS.items():
            if not self.checks[category].isChecked():
                continue
            values = {}
            for key in defaults:
                if key == "caption_options":
                    values[key] = deepcopy(self.caption_options)
                elif key == "caption_style":
                    values[key] = self.fields[key].currentData()
                else:
                    values[key] = self.fields[key].value()
            categories[category] = values
        return EditingPreset(self.name.text(), categories).validate()

    def targets(self):
        project = self.studio.project
        scope = self.scope.currentData()
        if scope == "all":
            return {media.id for media in project.media}
        if scope == "current":
            target = self.studio.target()
            if not target:
                raise ValueError("Select a timeline media item")
            media_id = project.find(*target)[1].media_id
            if not media_id:
                raise ValueError("Select a video or audio item, not an overlay")
            return {media_id}
        entries = (
            self.studio.selected_clips()
            if scope == "selected"
            else [
                c
                for c in self.studio.queue_manager.entries()
                if c["queue_group"] == self.group.text().strip()
            ]
        )
        if scope == "group" and not self.group.text().strip():
            raise ValueError("Enter a non-empty group name")
        ids = {c["id"] for c in entries}
        paths = {str(Path(c["output_path"]).resolve()) for c in entries}
        return {
            media.id
            for media in project.media
            if media.queue_clip_id in ids
            or (
                media.queue_clip_id is None and str(Path(media.path).resolve()) in paths
            )
        }

    def apply(self):
        count = apply_editing_preset(self.studio.project, self.preset(), self.targets())
        self.studio.draw_timeline()
        self.studio.status.setText(
            f"Updated {count} timeline items in one undoable transaction. Caption text/timing and source trims preserved."
        )

    def read_current(self):
        target = self.studio.target()
        if not target:
            raise ValueError("Select a timeline item")
        lane, item = self.studio.project.find(*target)
        category = {
            "video": ("color", "transform"),
            "audio": ("audio",),
            "caption": ("captions",),
        }.get(lane.kind, ())
        if not category:
            raise ValueError("Select video, audio or caption item")
        for name in category:
            for key in DEFAULTS[name]:
                if key == "caption_options":
                    self.caption_options = deepcopy(item.caption_options)
                elif key == "caption_style":
                    self.fields[key].setCurrentIndex(
                        self.fields[key].findData(item.caption_style)
                    )
                elif key.endswith("_fraction"):
                    self.fields[key].setValue(
                        getattr(item, key.replace("_fraction", "")) / item.duration
                    )
                else:
                    self.fields[key].setValue(getattr(item, key))
        self.studio.status.setText(
            "Read "
            + ", ".join(category)
            + "; other inspector categories remain unchanged."
        )

    def set_future(self):
        preset = self.preset()
        if "captions" in preset.categories:
            raise ValueError(
                "Future caption style requires caption generation, which is not integrated yet"
            )
        self.studio.db.set_setting(self.FUTURE_KEY, json.dumps(preset.to_dict()))
        self.studio.status.setText(
            "Future-import defaults saved on this device. Existing timeline items are unchanged."
        )

    def clear_future(self):
        self.studio.db.set_setting(self.FUTURE_KEY, "")
        self.studio.status.setText("Future-import defaults cleared.")

    def apply_future(self, incoming, new_ids):
        raw = self.studio.db.get_setting(self.FUTURE_KEY, "")
        if raw and new_ids:
            apply_editing_preset(
                incoming, EditingPreset.from_dict(json.loads(raw)), new_ids
            )

    def save(self):
        preset = self.preset()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save editing preset", "", "Editing preset (*.json)"
        )
        if path:
            if Path(path).resolve() in {
                Path(m.path).resolve() for m in self.studio.project.media
            }:
                raise ValueError("Preset cannot overwrite media")
            preset.save(path)
            self.studio.status.setText("Editing preset saved locally.")

    def load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load editing preset", "", "Editing preset (*.json)"
        )
        if not path:
            return
        preset = EditingPreset.load(path)
        self.name.setText(preset.name)
        for category, check in self.checks.items():
            check.setChecked(category in preset.categories)
        for category, values in preset.categories.items():
            for key, value in values.items():
                if key == "caption_options":
                    self.caption_options = deepcopy(value)
                elif key == "caption_style":
                    self.fields[key].setCurrentIndex(self.fields[key].findData(value))
                else:
                    self.fields[key].setValue(value)
        self.studio.status.setText(
            "Preset loaded into inspector; click Apply to change timeline items."
        )
