"""Non-destructive RGB balance/exposure/gamma and verified .cube asset import."""

from copy import deepcopy
import json

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
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
        layout = QVBoxLayout(self)
        info = QLabel(
            "Color grading · exposure, gamma and RGB shadows/midtones/highlights. Verified normalized 3D .cube LUTs support strength mixing. This is not a full curves/wheels/HSL grading suite."
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
        grade.update(lut_path=self.lut_path, lut_sha256=self.lut_sha)
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
