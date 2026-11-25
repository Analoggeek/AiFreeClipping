"""Wrapping native toolbar layout for narrow desktop workspaces."""
from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def addStretch(self, stretch=0):
        # Wrapping rows naturally leave their trailing space empty.
        pass

    def addWidget(self, widget, stretch=0):
        super().addWidget(widget)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect, apply):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, height = area.x(), area.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            width = min(hint.width(), max(1, area.width()))
            if x > area.x() and x + width > area.x() + area.width():
                x, y, height = area.x(), y + height + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(x, y, width, hint.height()))
            x += width + self.spacing()
            height = max(height, hint.height())
        return y - rect.y() + height + margins.bottom()
