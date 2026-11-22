"""Caption Studio: preview and customise every caption style."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ...captions.caption_engine import CAPTION_STYLES, get_style, list_styles
from ...core.logging_setup import get_logger
from ..theme import Metrics
from ..widgets.common import Card, SectionHeader
from .base import BasePage

log = get_logger(__name__)


class CaptionPreview(QWidget):
    """Renders a live preview of the caption style on a mock video frame."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, 533)
        self.style_key = "bold_viral"
        self.text = "HERE IS THE TRUTH ABOUT THE SKY"
        self.highlight = {"TRUTH", "SKY"}
        self.size = 58
        self.position = "bottom"
        self.stroke = 4
        self.shadow = True
        self.background = False
        self.uppercase = True
        self.font_family = "DejaVu Sans"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(90)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.02) % 1.0
        self.update()

    def stop(self) -> None:
        self._timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802
        from ...ui.theme import PALETTES

        p = PALETTES.get("dark")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # --- mock video background (gradient + subtle shapes) ---
        grad_top = QColor("#2b2b35")
        grad_bot = QColor("#15151b")
        for y in range(h):
            t = y / max(1, h)
            c = QColor(
                int(grad_top.red() * (1 - t) + grad_bot.red() * t),
                int(grad_top.green() * (1 - t) + grad_bot.green() * t),
                int(grad_top.blue() * (1 - t) + grad_bot.blue() * t),
            )
            painter.setPen(c)
            painter.drawLine(0, y, w, y)

        # Moving "subject" so the preview feels alive
        import math

        cx = w * (0.5 + 0.22 * math.sin(self._phase * 2 * math.pi))
        cy = h * 0.36
        painter.setPen(QColor(90, 96, 120))
        painter.setBrush(QColor(120, 128, 156))
        painter.drawEllipse(int(cx - w * 0.16), int(cy - h * 0.10),
                           int(w * 0.32), int(h * 0.20))
        painter.setPen(QColor(0, 0, 0, 90))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(cx - w * 0.16), int(cy - h * 0.10),
                           int(w * 0.32), int(h * 0.20))

        # --- caption ---
        st = get_style(self.style_key)
        text = self.text.upper() if self.uppercase else self.text
        words = text.split()

        # Scale the font so the caption fits the preview width, mirroring how the
        # renderer scales a 1080-wide caption onto the preview canvas.
        scale = w / 405.0
        font = QFont(self.font_family)
        font.setBold(st.bold)
        font.setPixelSize(max(8, int(self.size * scale)))
        painter.setFont(font)
        fm = painter.fontMetrics()

        # Wrap based on the real metrics so lines always fit.  Allow up to three
        # lines, matching the renderer's MAX_LINES behaviour.
        lines = self._wrap_metrics(words, fm, int(w * 0.86), max_lines=3)
        gap = max(2, int(4 * scale))

        line_h = fm.height() * 1.2
        total_h = line_h * len(lines)
        if self.position == "top":
            base_y = fm.ascent() + int(h * 0.10)
        elif self.position == "middle":
            base_y = int(h * 0.5 - total_h / 2) + fm.ascent()
        else:
            base_y = int(h * 0.80 - total_h) + fm.ascent()

        for li, line in enumerate(lines):
            widths = [fm.horizontalAdvance(x) for x in line]
            total_w = sum(widths) + gap * (len(line) - 1)
            x = int((w - total_w) / 2)
            y = base_y + li * int(line_h)

            if self.background:
                rect_w = int(total_w + 24 * scale)
                rect_h = int(line_h + 6)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 140))
                painter.drawRoundedRect(
                    int(x - 12 * scale), int(y - fm.ascent() - 3), rect_w, rect_h, 8, 8
                )

            stroke = max(0, int(round(self.stroke * scale)))
            for word, ww in zip(line, widths):
                colour = QColor("#FFE000" if word.strip(".,!?").upper() in
                                 {h.upper() for h in self.highlight} else "#FFFFFF")
                if self.shadow:
                    painter.setPen(QColor(0, 0, 0, 220))
                    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                        painter.drawText(int(x + dx), int(y + dy), word)
                if stroke > 0:
                    painter.setPen(QColor(0, 0, 0))
                    for dx in range(-stroke, stroke + 1):
                        for dy in range(-stroke, stroke + 1):
                            if dx * dx + dy * dy <= stroke * stroke:
                                painter.drawText(int(x + dx), int(y + dy), word)
                painter.setPen(colour)
                painter.drawText(int(x), int(y), word)
                x += ww + gap

        painter.setPen(QColor("#6e6e78"))
        painter.setFont(QFont("DejaVu Sans", 9))
        painter.drawText(12, h - 14, f"{st.name} · {self.size}px")

    @staticmethod
    def _wrap_metrics(words: list[str], fm, max_px: int, max_lines: int = 3) -> list[list[str]]:
        """Greedy wrap using real font metrics so lines never overflow."""
        lines: list[list[str]] = []
        cur: list[str] = []
        cur_w = 0
        for w in words:
            ww = fm.horizontalAdvance(w)
            add = ww if not cur else ww + fm.horizontalAdvance(" ")
            if cur and cur_w + add > max_px:
                lines.append(cur)
                cur = []
                cur_w = 0
                if len(lines) >= max_lines:
                    break
                add = ww
            cur.append(w)
            cur_w += add
        if cur and len(lines) < max_lines:
            lines.append(cur)
        return lines or [[""]]


class CaptionStudioPage(BasePage):
    page_title = "Caption Studio"
    page_subtitle = "Preview every style, tune the typography, and burn it into your clips."

    def __init__(self, window) -> None:
        super().__init__(window)

    def build(self) -> None:
        splitter = QHBoxLayout()

        # --- preview ---
        preview_card = Card()
        preview_card.add(SectionHeader("Live Preview", "Word-by-word highlighting"))
        self.preview = CaptionPreview()
        preview_card.add(self.preview)
        self.preview_text = QLabel("Preview text")
        self.preview_text.setObjectName("CardSubtitle")
        preview_card.add(self.preview_text)
        splitter.addWidget(preview_card, 1)

        # --- controls ---
        controls = Card()
        controls.add(SectionHeader("Style", "8 built-in caption styles"))
        self.style_grid = QGridLayout()
        self.style_grid.setSpacing(Metrics.sm)
        self.style_buttons: dict[str, QPushButton] = {}
        for i, (key, st) in enumerate(CAPTION_STYLES.items()):
            btn = QPushButton(st.name)
            btn.setCheckable(True)
            btn.setToolTip(st.description)
            btn.clicked.connect(lambda _=False, k=key: self._select_style(k))
            self.style_buttons[key] = btn
            self.style_grid.addWidget(btn, i // 2, i % 2)
        controls.add_layout(self.style_grid)

        controls.add(SectionHeader("Typography", ""))

        form = QFormLayout()
        form.setSpacing(Metrics.sm)

        self.font_combo = QComboBox()
        from ..fonts import available_families

        for fam in available_families():
            self.font_combo.addItem(fam)
        self.font_combo.currentTextChanged.connect(self._on_font)
        form.addRow("Font", self.font_combo)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(24, 110)
        self.size_slider.setValue(58)
        self.size_slider.valueChanged.connect(self._on_size)
        form.addRow("Size", self.size_slider)

        self.position_combo = QComboBox()
        self.position_combo.addItems(["bottom", "middle", "top"])
        self.position_combo.currentTextChanged.connect(self._on_position)
        form.addRow("Position", self.position_combo)

        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(0, 12)
        self.stroke_spin.setValue(4)
        self.stroke_spin.valueChanged.connect(self._on_stroke)
        form.addRow("Stroke", self.stroke_spin)

        self.shadow_check = QCheckBox("Drop shadow")
        self.shadow_check.setChecked(True)
        self.shadow_check.toggled.connect(self._on_shadow)
        form.addRow("", self.shadow_check)

        self.bg_check = QCheckBox("Caption background")
        self.bg_check.toggled.connect(self._on_bg)
        form.addRow("", self.bg_check)

        controls.add_layout(form)

        self.desc = QLabel("")
        self.desc.setObjectName("CardSubtitle")
        self.desc.setWordWrap(True)
        controls.add(self.desc)

        save = QPushButton("Save as Default")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_default)
        controls.add(save)

        apply_btn = QPushButton("Apply to All Clips")
        apply_btn.clicked.connect(self._apply_all)
        controls.add(apply_btn)

        splitter.addWidget(controls, 1)
        self.content_layout.addLayout(splitter)

        self._select_style("bold_viral")

    # -- handlers ------------------------------------------------------------------
    def _select_style(self, key: str) -> None:
        self.preview.style_key = key
        for k, b in self.style_buttons.items():
            b.setChecked(k == key)
        st = get_style(key)
        self.desc.setText(st.description)
        self.preview.uppercase = st.uppercase
        self.preview.size = st.size
        self.preview.stroke = int(st.stroke_width)
        self.preview.shadow = st.shadow > 0
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(st.size)
        self.size_slider.blockSignals(False)
        self.preview.update()

    def _on_font(self, family: str) -> None:
        self.preview.font_family = family
        self.preview.update()

    def _on_size(self, value: int) -> None:
        self.preview.size = value
        self.preview.update()

    def _on_position(self, value: str) -> None:
        self.preview.position = value
        self.preview.update()

    def _on_stroke(self, value: int) -> None:
        self.preview.stroke = value
        self.preview.update()

    def _on_shadow(self, value: bool) -> None:
        self.preview.shadow = value
        self.preview.update()

    def _on_bg(self, value: bool) -> None:
        self.preview.background = value
        self.preview.update()

    def _save_default(self) -> None:
        key = self.preview.style_key
        self.db.set_settings({
            "caption_style": key,
            "caption_font": self.preview.font_family,
            "caption_size": self.preview.size,
            "caption_position": self.preview.position,
            "caption_stroke": self.preview.stroke,
            "caption_shadow": int(self.preview.shadow),
            "caption_background": int(self.preview.background),
        })
        self.window.notify(f"'{get_style(key).name}' saved as the default caption style")

    def _apply_all(self) -> None:
        n = self.db.execute(
            "UPDATE clips SET caption_style=? WHERE status='pending'",
            (self.preview.style_key,),
        )
        self.window.notify(f"Caption style applied to {n} pending clips")

    def refresh(self) -> None:
        settings = self.db.get_settings()
        key = settings.get("caption_style", "bold_viral")
        if key in self.style_buttons:
            self._select_style(key)
