"""Reusable UI widgets for CLIPOS."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ..theme import Metrics


class Card(QFrame):
    """A rounded elevated panel used throughout the app."""

    def __init__(self, parent: QWidget | None = None, padding: int = Metrics.lg) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(Metrics.sm)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class StatTile(QFrame):
    """A single animated statistic tile used on the dashboard."""

    def __init__(
        self,
        icon: str = "",
        label: str = "",
        value: str = "0",
        accent: str = "#0a84ff",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._value = value
        self._accent = accent

        lay = QVBoxLayout(self)
        lay.setContentsMargins(Metrics.lg, Metrics.md, Metrics.lg, Metrics.md)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(Metrics.sm)
        self._icon = QLabel(icon)
        self._icon.setObjectName("StatIcon")
        top.addWidget(self._icon)
        top.addStretch(1)
        lay.addLayout(top)

        self._value_label = QLabel(value)
        self._value_label.setObjectName("StatValue")
        lay.addWidget(self._value_label)

        self._label = QLabel(label)
        self._label.setObjectName("StatLabel")
        self._label.setWordWrap(True)
        lay.addWidget(self._label)

        self.setMinimumHeight(104)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_value(self, value: str, animate: bool = True) -> None:
        """Update the displayed value, optionally counting up to it."""
        if not animate:
            self._value = value
            self._value_label.setText(value)
            return
        self._value = value
        try:
            target = float(value.replace(",", "").strip())
        except ValueError:
            self._value_label.setText(value)
            return
        self._animate_number(target, value)

    def _animate_number(self, target: float, suffix_fmt: str) -> None:
        self._anim = getattr(self, "_anim", None)
        if self._anim:
            self._anim.stop()
        # QLabel has no "opacity" property -- use a graphics effect for the fade.
        effect = self._value_label.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(self._value_label)
            self._value_label.setGraphicsEffect(effect)
        self._anim = QPropertyAnimation(effect, b"opacity", self)
        self._anim.setDuration(420)
        self._anim.setStartValue(0.35)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()
        self._value_label.setText("0")

        def step() -> None:
            pct = min(1.0, self._anim.currentValue() / 1.0)
            # The opacity animation drives a simple count-up
            current = target * pct
            if target >= 1000:
                self._value_label.setText(f"{int(current):,}")
            elif target != int(target):
                self._value_label.setText(f"{current:.1f}")
            else:
                self._value_label.setText(f"{int(current)}")

        self._timer = QTimer(self)
        self._timer.timeout.connect(step)
        self._timer.start(30)

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._icon.setStyleSheet(f"color: {color};")


class ScoreBadge(QLabel):
    """A coloured 0-100 score badge (engagement / virality)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(46, 24)
        self.set_value(0)

    def set_value(self, score: float, kind: str = "viral") -> None:
        score = max(0.0, min(100.0, float(score)))
        self.setText(f"{score:.0f}")
        if kind == "viral":
            if score >= 75:
                bg, fg = "#32d74b", "#052e16"
            elif score >= 50:
                bg, fg = "#0a84ff", "#ffffff"
            elif score >= 30:
                bg, fg = "#ff9f0a", "#3a1c00"
            else:
                bg, fg = "#6e6e78", "#ffffff"
        else:
            bg, fg = "#5e5ce6", "#ffffff"
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 11px;"
            f"font-weight: 700; font-size: 11px;"
        )
        self.setToolTip(
            "Virality score — predicted shareability of this clip" if kind == "viral"
            else "Engagement score — how strong the moment is"
        )


class SectionHeader(QWidget):
    """A title + optional subtitle + optional right-hand action."""

    def __init__(
        self, title: str, subtitle: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Metrics.md)

        left = QVBoxLayout()
        left.setSpacing(1)
        self.title = QLabel(title)
        self.title.setObjectName("SectionTitle")
        left.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("CardSubtitle")
        self.subtitle.setVisible(bool(subtitle))
        left.addWidget(self.subtitle)
        lay.addLayout(left)
        lay.addStretch(1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(Metrics.sm)
        lay.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget)
        return widget


class DropZone(QFrame):
    """Drag-and-drop target for video files."""

    file_dropped = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        self._hover = False

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(Metrics.sm)

        icon = QLabel("↓")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 30px; color: #0a84ff;")
        lay.addWidget(icon)

        title = QLabel("Drop a video file here")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("CardTitle")
        lay.addWidget(title)

        hint = QLabel("MP4 · MOV · MKV · AVI · WEBM · M4V")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName("CardSubtitle")
        lay.addWidget(hint)

        browse = QPushButton("Browse Files…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(browse)
        row.addStretch(1)
        lay.addLayout(row)

    def _browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a video", "",
            "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mpg *.mpeg *.wmv *.flv);;"
            "All files (*)",
        )
        if path:
            self.file_dropped.emit(path)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._hover = True
            self.setStyleSheet(
                "QFrame#Card { border: 2px solid #0a84ff; border-radius: 14px; }"
            )

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.setStyleSheet("")

    def dropEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.setStyleSheet("")
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.file_dropped.emit(path)
                event.acceptProposedAction()


class VideoThumbnail(QLabel):
    """Displays a video thumbnail with a rounded frame and duration badge."""

    def __init__(self, parent: QWidget | None = None, width: int = 120) -> None:
        super().__init__(parent)
        self._path = ""
        self._duration = 0.0
        self.setFixedSize(width, int(width * 9 / 16))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background: #1c1c1e; border-radius: 8px; color: #6e6e78; font-size: 10px;"
        )

    def set_video(self, thumb_path: str, duration: float = 0.0) -> None:
        self._path = thumb_path or ""
        self._duration = duration
        self._refresh()

    def _refresh(self) -> None:
        if self._path and Path(self._path).exists():
            pm = QPixmap(self._path)
            if not pm.isNull():
                scaled = pm.scaled(
                    self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Centre-crop
                x = max(0, (scaled.width() - self.width()) // 2)
                y = max(0, (scaled.height() - self.height()) // 2)
                cropped = scaled.copy(x, y, self.width(), self.height())
                self.setPixmap(cropped)
                return
        self.setPixmap(QPixmap())
        self.setText("No preview")


def format_duration(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_size(num_bytes: int | float) -> str:
    """Human readable byte size."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class Toast(QLabel):
    """A transient notification shown in the corner of the window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVisible(False)
        self.setWordWrap(True)
        self.setMaximumWidth(360)
        self.setStyleSheet(
            "background-color: #2a2a2e; color: #f2f2f5; border: 1px solid #45454f;"
            "border-radius: 10px; padding: 12px 14px; font-size: 12px;"
        )
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, msec: int = 3200) -> None:
        self.setText(text)
        self.adjustSize()
        self.raise_()
        parent = self.parentWidget()
        if parent:
            self.move(
                parent.width() - self.width() - 24,
                parent.height() - self.height() - 24,
            )
        self.show()
        self._timer.start(msec)
