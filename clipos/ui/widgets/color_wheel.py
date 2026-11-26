"""Native tonal-balance wheel driving actual RGB colorbalance parameters."""

import colorsys
import math
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QConicalGradient, QRadialGradient, QPen
from PySide6.QtWidgets import QWidget


class ColorWheel(QWidget):
    changed = Signal(float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.position = (0.0, 0.0)
        self.setMinimumSize(120, 120)
        self.setMaximumSize(180, 180)
        self.setToolTip(
            "Drag hue/distance for RGB tonal bias. Center resets chromatic bias; RGB numeric controls retain independent offsets."
        )

    def set_rgb(self, red, green, blue):
        values = (red, green, blue)
        lo = min(values)
        hi = max(values)
        if hi - lo < 0.000001:
            self.position = (0.0, 0.0)
        else:
            h, _, _ = colorsys.rgb_to_hsv(*[(v - lo) / (hi - lo) for v in values])
            radius = min(1, max(abs(v) for v in values))
            angle = h * 2 * math.pi
            self.position = (radius * math.cos(angle), -radius * math.sin(angle))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) / 2 - 8
        hue = QConicalGradient(center, 0)
        for i in range(7):
            hue.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1, 1, 1))
        painter.setBrush(hue)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius, radius)
        white = QRadialGradient(center, radius)
        white.setColorAt(0, QColor("white"))
        white.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(white)
        painter.drawEllipse(center, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("black"), 2))
        painter.drawEllipse(
            QPointF(
                center.x() + self.position[0] * radius,
                center.y() + self.position[1] * radius,
            ),
            5,
            5,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.choose(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.choose(event.position())

    def choose(self, point):
        radius = min(self.width(), self.height()) / 2 - 8
        x = (point.x() - self.width() / 2) / radius
        y = (point.y() - self.height() / 2) / radius
        length = math.hypot(x, y)
        if length > 1:
            x /= length
            y /= length
        amount = min(1, length)
        hue = math.atan2(-y, x) / (2 * math.pi) % 1
        values = colorsys.hsv_to_rgb(hue, 1, 1)
        mean = sum(values) / 3
        values = [v - mean for v in values]
        limit = max(abs(v) for v in values) or 1
        red, green, blue = [v / limit * amount for v in values]
        self.position = (x, y)
        self.update()
        self.changed.emit(red, green, blue)
