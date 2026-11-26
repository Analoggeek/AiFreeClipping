"""Non-destructive RGB balance/exposure/gamma and verified .cube asset import."""

from copy import deepcopy
import json

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QDoubleSpinBox,
    QPushButton,
    QFileDialog,
)
from ...video.studio_color import GRADE_DEFAULTS, read_cube, validate_grade


class ColorPanel(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.lut_path = ""
        self.lut_sha = ""
        self.curves = {}
        layout = QVBoxLayout(self)
        info = QLabel(
            "Color grading · exposure, gamma and RGB shadows/midtones/highlights. Verified normalized 3D .cube LUTs support strength mixing. RGB/master curves, tonal wheels and global HSL share the same export/preview graph. Six overlapping hue-range HSL qualifiers use original hue with gray protection."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.fields = {}
        form = QFormLayout()
        labels = {
            "rs": "Red shadows",
            "gs": "Green shadows",
            "bs": "Blue shadows",
            "rm": "Red midtones",
            "gm": "Green midtones",
            "bm": "Blue midtones",
            "rh": "Red highlights",
            "gh": "Green highlights",
            "bh": "Blue highlights",
            "lut_strength": "LUT strength",
            "exposure": "Exposure stops",
            "gamma": "Gamma",
        }
        for key, value in GRADE_DEFAULTS.items():
            if not isinstance(value, (float, int)):
                continue
            field = QDoubleSpinBox()
            field.setDecimals(3)
            field.setSingleStep(0.05)
            field.setRange(
                *(
                    (0.1, 4)
                    if key == "gamma"
                    else (-3, 3)
                    if key == "exposure"
                    else (0, 1)
                    if key == "lut_strength"
                    else (-1, 1)
                )
            )
            field.setValue(value)
            self.fields[key] = field
            form.addRow(labels[key], field)
        layout.addLayout(form)
        from .color_wheel import ColorWheel

        self.wheels = {}
        wheel_row = QHBoxLayout()
        for title, keys in [
            ("Shadows", ("rs", "gs", "bs")),
            ("Midtones", ("rm", "gm", "bm")),
            ("Highlights", ("rh", "gh", "bh")),
        ]:
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            wheel = ColorWheel()
            self.wheels[title] = (wheel, keys)
            wheel.changed.connect(
                lambda r, g, b, chosen=keys: self.wheel_changed(chosen, r, g, b)
            )
            for key in keys:
                self.fields[key].valueChanged.connect(lambda value: self.sync_wheels())
            column.addWidget(wheel)
            wheel_row.addLayout(column)
        layout.addLayout(wheel_row)
        self.secondary = {}
        self.hue_range = QComboBox()
        self.hue_range.addItems(
            ["Global", "red", "yellow", "green", "cyan", "blue", "magenta"]
        )
        layout.addWidget(self.hue_range)
        self.active_hue_range = "Global"
        self.hsl_fields = {}
        hsl_form = QFormLayout()
        for key in ("hue", "saturation", "lightness"):
            field = QDoubleSpinBox()
            field.setRange(-180 if key == "hue" else -1, 180 if key == "hue" else 1)
            field.setDecimals(3)
            field.setSingleStep(1 if key == "hue" else 0.05)
            self.hsl_fields[key] = field
            hsl_form.addRow("HSL " + key, field)
        layout.addLayout(hsl_form)
        self.hue_range.currentTextChanged.connect(self.switch_hue_range)
        self.channel = QComboBox()
        self.channel.addItems(["master", "red", "green", "blue"])
        layout.addWidget(self.channel)
        from .color_curve import ColorCurve

        self.curve = ColorCurve()
        layout.addWidget(self.curve)
        self.channel.currentTextChanged.connect(self.show_curve)
        self.curve.changed.connect(self.curve_changed)
        reset_curve = QPushButton("Reset current curve")
        reset_curve.clicked.connect(self.reset_curve)
        layout.addWidget(reset_curve)
        self.lut = QLabel("No LUT selected.")
        self.lut.setWordWrap(True)
        layout.addWidget(self.lut)
        for title, fn in [
            ("Read current video grade", self.read),
            ("Import verified .cube LUT…", self.choose_lut),
            ("Remove LUT from controls", self.clear_lut),
            ("Load grade into Batch inspector", self.load),
            ("Load neutral grade (clear on Apply)", lambda: self.populate({})),
        ]:
            button = QPushButton(title)
            button.clicked.connect(
                lambda checked=False, action=fn: studio.editing.run(action)
            )
            layout.addWidget(button)

    def populate(self, grade):
        validate_grade(grade)
        panel = self.studio.editing
        for key, check in panel.checks.items():
            check.setChecked(key == "color_grade")
        panel.fields["color_grade"].setText(json.dumps(grade))
        self.studio.status.setText(
            "Only Color Grade checked. Review scope and Apply; source files remain unchanged."
        )

    def load(self):
        grade = {key: field.value() for key, field in self.fields.items()}
        self.store_hue_range()
        hsl = self.secondary.get("Global", {})
        grade.update(
            lut_path=self.lut_path,
            lut_sha256=self.lut_sha,
            curves=deepcopy(self.curves),
            secondary={
                k: deepcopy(v)
                for k, v in self.secondary.items()
                if k != "Global" and any(v.values())
            },
            hsl=hsl if any(hsl.values()) else {},
        )
        self.populate(grade)

    def read(self):
        target = self.studio.target()
        if not target:
            raise ValueError("Select a timeline video item")
        lane, item = self.studio.project.find(*target)
        if lane.kind != "video":
            raise ValueError("Color grading requires video")
        grade = deepcopy(item.color_grade or GRADE_DEFAULTS)
        for key, field in self.fields.items():
            field.setValue(grade[key])
        self.curves = deepcopy(grade.get("curves", {}))
        self.show_curve()
        self.secondary = deepcopy(grade.get("secondary", {}))
        self.secondary["Global"] = deepcopy(grade.get("hsl", {}))
        self.active_hue_range = self.hue_range.currentText()
        self.restore_hue_range()
        self.sync_wheels()
        self.lut_path = grade["lut_path"]
        self.lut_sha = grade["lut_sha256"]
        self.lut.setText(self.lut_path or "No LUT selected.")

    def choose_lut(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import local 3D LUT", "", "3D LUT (*.cube)"
        )
        if path:
            self.import_lut(path)

    def import_lut(self, path):
        def job(worker):
            data = read_cube(path)
            return {key: data[key] for key in ("path", "sha256", "size")}

        def done(data):
            self.lut_path = data["path"]
            self.lut_sha = data["sha256"]
            self.lut.setText(f"Verified {data['size']}³ LUT: {data['path']}")
            self.studio.status.setText(
                "LUT bytes validated and checksum bound. Load grade and Apply explicitly. Keep the referenced LUT with your project assets."
            )

        self.studio._background(job, done, "Validating local 3D LUT…")

    def clear_lut(self):
        self.lut_path = ""
        self.lut_sha = ""
        self.lut.setText(
            "No LUT selected. Load grade and Apply to remove it from targets."
        )

    def wheel_changed(self, keys, red, green, blue):
        for key, value in zip(keys, (red, green, blue)):
            self.fields[key].setValue(value)

    def sync_wheels(self):
        for wheel, keys in self.wheels.values():
            wheel.set_rgb(*(self.fields[key].value() for key in keys))

    def show_curve(self, *args):
        self.curve.set_points(
            self.curves.get(self.channel.currentText(), [[0.0, 0.0], [1.0, 1.0]])
        )

    def curve_changed(self, points):
        self.curves[self.channel.currentText()] = deepcopy(points)

    def reset_curve(self):
        self.curves.pop(self.channel.currentText(), None)
        self.show_curve()

    def store_hue_range(self):
        self.secondary[self.active_hue_range] = {
            key: field.value() for key, field in self.hsl_fields.items()
        }

    def restore_hue_range(self):
        values = self.secondary.get(self.active_hue_range, {})
        for key, field in self.hsl_fields.items():
            field.setValue(values.get(key, 0.0))

    def switch_hue_range(self, name):
        self.store_hue_range()
        self.active_hue_range = name
        self.restore_hue_range()
