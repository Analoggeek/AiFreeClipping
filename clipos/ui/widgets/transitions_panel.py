"""Real overlap-based transition recipes; never invents handles or scene edges."""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
)
from ...video.studio_transitions import transition_recipes


class TransitionsPanel(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        layout = QVBoxLayout(self)
        info = QLabel(
            "40 transition recipes (10 mask families × 4 curves). Arrange overlapping video layers, select the incoming item, then add. Preview using shared-graph playback or rendered snapshot."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.recipe = QComboBox()
        for key, name in transition_recipes().items():
            self.recipe.addItem(name, key)
        layout.addWidget(self.recipe)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0.05, 5.0)
        self.duration.setValue(0.4)
        self.duration.setSuffix(" seconds")
        layout.addWidget(self.duration)
        button = QPushButton("Add transition to selected incoming video")
        button.clicked.connect(lambda: studio.editing.run(self.add))
        layout.addWidget(button)

    def add(self):
        target = self.studio.target()
        if not target:
            raise ValueError("Select incoming video item on timeline")
        self.studio.project.add_dissolve(
            *target, self.duration.value(), mode=self.recipe.currentData()
        )
        self.studio.draw_timeline()
        self.studio.status.setText(
            "Transition added in real overlap. Undo removes it; select its track item to remove it manually."
        )
