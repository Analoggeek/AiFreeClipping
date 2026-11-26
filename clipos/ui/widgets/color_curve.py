"""Normalized draggable control points with natural-cubic curve visualization."""

from copy import deepcopy
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QWidget


def spline_samples(points, count=128):
    n = len(points)
    x = [p[0] for p in points]
    y = [p[1] for p in points]
    widths = [x[i + 1] - x[i] for i in range(n - 1)]
    lower = [0.0] * n
    diag = [1.0] * n
    upper = [0.0] * n
    rhs = [0.0] * n
    for i in range(1, n - 1):
        lower[i] = widths[i - 1]
        diag[i] = 2 * (widths[i - 1] + widths[i])
        upper[i] = widths[i]
        rhs[i] = 6 * ((y[i + 1] - y[i]) / widths[i] - (y[i] - y[i - 1]) / widths[i - 1])
    for i in range(1, n):
        factor = lower[i] / diag[i - 1]
        diag[i] -= factor * upper[i - 1]
        rhs[i] -= factor * rhs[i - 1]
    second = [0.0] * n
    second[-1] = rhs[-1] / diag[-1]
    for i in range(n - 2, -1, -1):
        second[i] = (rhs[i] - upper[i] * second[i + 1]) / diag[i]
    result = []
    segment = 0
    for index in range(count + 1):
        value = index / count
        while segment < n - 2 and value > x[segment + 1]:
            segment += 1
        h = widths[segment]
        a = (x[segment + 1] - value) / h
        b = (value - x[segment]) / h
        output = (
            a * y[segment]
            + b * y[segment + 1]
            + ((a**3 - a) * second[segment] + (b**3 - b) * second[segment + 1])
            * h
            * h
            / 6
        )
        result.append((value, max(0.0, min(1.0, output))))
    return result


class ColorCurve(QWidget):
    changed = Signal(object)
    MARGIN = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = [[0.0, 0.0], [1.0, 1.0]]
        self.drag = None
        self.setMinimumSize(240, 180)
        self.setToolTip(
            "Double-click to add a point; drag to adjust; right-click interior points to remove. Endpoints keep input 0 and 1. Natural cubic interpolation."
        )

    def set_points(self, points):
        from ...video.studio_color import validate_curves

        validate_curves({"master": points})
        self.points = deepcopy(points)
        self.drag = None
        self.update()

    def display(self, x, y):
        m = self.MARGIN
        return QPointF(
            m + x * (self.width() - 2 * m),
            self.height() - m - y * (self.height() - 2 * m),
        )

    def normalized(self, point):
        m = self.MARGIN
        return [
            max(0.0, min(1.0, (point.x() - m) / (self.width() - 2 * m))),
            max(
                0.0, min(1.0, (self.height() - m - point.y()) / (self.height() - 2 * m))
            ),
        ]

    def hit(self, position):
        for index, (x, y) in enumerate(self.points):
            if (self.display(x, y) - position).manhattanLength() < 12:
                return index
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#151923"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#3b4252"), 1))
        for i in range(5):
            painter.drawLine(self.display(i / 4, 0), self.display(i / 4, 1))
            painter.drawLine(self.display(0, i / 4), self.display(1, i / 4))
        path = QPainterPath()
        for index, (x, y) in enumerate(spline_samples(self.points)):
            path.moveTo(self.display(x, y)) if index == 0 else path.lineTo(
                self.display(x, y)
            )
        painter.setPen(QPen(QColor("#a5b4fc"), 2))
        painter.drawPath(path)
        painter.setBrush(QColor("#f1f5f9"))
        for x, y in self.points:
            painter.drawEllipse(self.display(x, y), 4, 4)

    def commit(self):
        self.update()
        self.changed.emit(deepcopy(self.points))

    def mousePressEvent(self, event):
        index = self.hit(event.position())
        if event.button() == Qt.MouseButton.RightButton and index not in (
            None,
            0,
            len(self.points) - 1,
        ):
            self.points.pop(index)
            self.commit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.drag = index

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or len(self.points) >= 16:
            return
        x, y = self.normalized(event.position())
        if any(abs(x - p[0]) < 0.005 for p in self.points):
            return
        self.points.append([x, y])
        self.points.sort(key=lambda p: p[0])
        self.drag = next(i for i, p in enumerate(self.points) if p[0] == x)
        self.commit()

    def mouseMoveEvent(self, event):
        if self.drag is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        x, y = self.normalized(event.position())
        index = self.drag
        if index == 0:
            x = 0.0
        elif index == len(self.points) - 1:
            x = 1.0
        else:
            x = max(
                self.points[index - 1][0] + 0.001,
                min(self.points[index + 1][0] - 0.001, x),
            )
        self.points[index] = [x, y]
        self.commit()

    def mouseReleaseEvent(self, event):
        self.drag = None
