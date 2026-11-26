"""Implemented effects and original combinations loaded into selective inspector."""

from copy import deepcopy
import json

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
)
from ...video.studio_effects import EFFECTS, effect_recipes


class EffectsPanel(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.recipes = effect_recipes()
        layout = QVBoxLayout(self)
        text = QLabel(
            "Video effects · eight implemented filters / twenty original combinations. Load into inspector, choose target scope, Apply, then preview the shared graph."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        self.effect = QComboBox()
        for key, (name, *_) in EFFECTS.items():
            self.effect.addItem(name, key)
        layout.addWidget(self.effect)
        self.amount = QDoubleSpinBox()
        self.amount.setDecimals(3)
        self.amount.setSingleStep(0.1)
        layout.addWidget(self.amount)
        self.effect.currentIndexChanged.connect(self.changed)
        self.changed()
        self.recipe = QComboBox()
        self.recipe.addItems(list(self.recipes))
        layout.addWidget(self.recipe)
        for title, fn in [
            ("Load single effect into inspector", self.load_single),
            ("Load effect recipe into inspector", self.load_recipe),
            ("Load empty effects (clear on Apply)", lambda: self.populate([])),
        ]:
            button = QPushButton(title)
            button.clicked.connect(
                lambda checked=False, action=fn: studio.editing.run(action)
            )
            layout.addWidget(button)

    def changed(self, *args):
        _, lo, hi, value = EFFECTS[self.effect.currentData()]
        self.amount.setRange(lo, hi)
        self.amount.setValue(value)

    def populate(self, effects):
        panel = self.studio.editing
        for key, check in panel.checks.items():
            check.setChecked(key == "effects")
        panel.fields["effects"].setText(json.dumps(effects))
        self.studio.status.setText(
            "Only Effects checked. Review targets and Apply to commit; source files remain unchanged."
        )

    def load_single(self):
        self.populate(
            [{"kind": self.effect.currentData(), "amount": self.amount.value()}]
        )

    def load_recipe(self):
        self.populate(deepcopy(self.recipes[self.recipe.currentText()]))
