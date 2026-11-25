"""Caption Studio: preview and customise every caption style."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QInputDialog, QLineEdit, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ...captions.caption_engine import CAPTION_STYLES, get_style, list_styles
from ...core.logging_setup import get_logger
from ..theme import Metrics
from ..widgets.common import Card, SectionHeader
from .base import BasePage

log = get_logger(__name__)


class CaptionRenderWorker(QThread):
    ready=Signal(bytes)
    failed=Signal(str)

    def __init__(self,key,options,parent=None):
        super().__init__(parent);self.key=key;self.options=dict(options)
        self.text=self.options.pop("sample_text", "HERE IS THE TRUTH ABOUT THE SKY")

    def run(self):
        import tempfile,subprocess
        from ...captions.caption_engine import CaptionCue,write_ass,get_style
        from ...core.ffmpeg import require_ffmpeg
        try:
            with tempfile.TemporaryDirectory(prefix='clipos-caption-') as folder:
                ass=Path(folder)/'sample.ass'
                write_ass(ass,[CaptionCue(0,3,self.text)],get_style(self.key),**self.options)
                # Use a relative subtitle path so drive-letter/FFmpeg filter quoting
                # is identical across Windows and Unix.
                result=subprocess.run([require_ffmpeg(),'-v','error','-f','lavfi','-i','color=c=0x111827:s=1080x1920:r=1:d=2','-vf','ass=sample.ass,scale=324:576','-ss','1','-frames:v','1','-threads','1','-f','image2pipe','-vcodec','png','-'],cwd=folder,capture_output=True,timeout=45)
                if result.returncode or not result.stdout:raise RuntimeError(result.stderr.decode(errors='replace')[-1500:] or 'No rendered frame')
                self.ready.emit(result.stdout)
        except Exception as exc:self.failed.emit(str(exc))


class CaptionPreview(QWidget):
    """Renders a live preview of the caption style on a mock video frame."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Tall enough to show a 9:16 frame, short enough that the caption
        # label underneath is not pushed out of the card.
        self.setMinimumSize(300, 480)
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
        preview_card.add(SectionHeader("Typography Sample", "Illustrative background; export renders actual ASS motion"))
        self.preview = CaptionPreview()
        preview_card.add(self.preview)
        self.rendered_frame=QLabel('Render a frame to verify actual ASS typography and motion at one second.');self.rendered_frame.setWordWrap(True);preview_card.add(self.rendered_frame)
        self.render_button=QPushButton('Render actual caption frame');self.render_button.clicked.connect(self._render_actual);preview_card.add(self.render_button)
        self._render_worker=None
        self._render_generation=0
        self._active_render_generation=0
        self._render_timer=QTimer(self);self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(450);self._render_timer.timeout.connect(self._render_actual)
        self.sample_text=QLineEdit(self.preview.text);self.sample_text.setMaxLength(240)
        self.sample_text.setPlaceholderText('Your sample caption text');self.sample_text.textChanged.connect(self._sample_changed)
        preview_card.add(self.sample_text)
        self.preview_text = QLabel("Preview text")
        self.preview_text.setObjectName("CardSubtitle")
        preview_card.add(self.preview_text)
        splitter.addWidget(preview_card, 1)

        # --- controls ---
        controls = Card()
        controls.add(SectionHeader("Style", f"{len(CAPTION_STYLES)} styles · 30 animated combinations"))
        from ...captions.customization import CATEGORIES
        self.category=QComboBox();self.category.addItems(CATEGORIES)
        self.category.currentTextChanged.connect(self._filter_category);controls.add(self.category)
        custom_row=QHBoxLayout()
        self.custom_profiles=QComboBox();self.custom_profiles.setToolTip('Locally saved custom caption profiles')
        self.custom_profiles.activated.connect(self._load_custom)
        custom_row.addWidget(self.custom_profiles,1)
        save_custom=QPushButton('Save custom…');save_custom.clicked.connect(self._save_custom);custom_row.addWidget(save_custom)
        controls.add_layout(custom_row)
        self._refresh_custom()
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

        self.color_buttons={}
        self.colors={'primary':'','highlight':'','outline':''}
        for key,label in [('primary','Text color'),('highlight','Highlight color'),('outline','Outline color')]:
            button=QPushButton('Preset color');button.clicked.connect(lambda checked=False,k=key:self._choose_color(k))
            self.color_buttons[key]=button;form.addRow(label,button)
        self.animation_combo=QComboBox();self.animation_combo.addItem('Use preset','')
        from ...captions.customization import ANIMATIONS
        for motion in ANIMATIONS:self.animation_combo.addItem(motion.replace('_',' ').title(),motion)
        self.animation_combo.currentIndexChanged.connect(self._queue_render);form.addRow('Animation',self.animation_combo)
        self.alignment_combo=QComboBox();self.alignment_combo.addItem('Use preset','')
        for alignment in ('left','center','right'):self.alignment_combo.addItem(alignment.title(),alignment)
        self.alignment_combo.currentIndexChanged.connect(self._queue_render);form.addRow('Alignment',self.alignment_combo)
        self.offset_spin=QDoubleSpinBox();self.offset_spin.setRange(-10,10);self.offset_spin.setDecimals(2);self.offset_spin.setSingleStep(.05);self.offset_spin.setSuffix(' s')
        self.offset_spin.setToolTip('Shift real caption cues and their word timestamps; negative values show captions earlier.')
        self.offset_spin.valueChanged.connect(self._queue_render);form.addRow('Timing offset',self.offset_spin)
        controls.add_layout(form)

        self.desc = QLabel("")
        self.desc.setObjectName("CardSubtitle")
        self.desc.setWordWrap(True)
        controls.add(self.desc)

        save = QPushButton("Save as Default")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_default)
        controls.add(save)

        apply_btn = QPushButton("Apply style to pending clips")
        apply_btn.clicked.connect(self._apply_all)
        controls.add(apply_btn)

        splitter.addWidget(controls, 1)
        self.content_layout.addLayout(splitter)

        self._select_style("bold_viral")

    # -- handlers ------------------------------------------------------------------
    def _queue_render(self,*_):
        if not hasattr(self,'_render_timer'):return
        self._render_generation+=1
        self._render_timer.start()

    def _sample_changed(self,text):
        self.preview.text=text;self.preview.update();self._queue_render()

    def _filter_category(self,category):
        from ...captions.customization import categories_for
        for key,button in self.style_buttons.items():
            button.setVisible(category in categories_for(key))
        self.custom_profiles.setToolTip('Select a saved profile below' if category=='Custom' else 'Locally saved custom caption profiles')

    def _choose_color(self,key):
        color=QColorDialog.getColor(QColor(self.colors[key] or '#FFFFFF'),self,'Caption '+key+' color')
        if color.isValid():
            self.colors[key]=color.name();self.color_buttons[key].setText(color.name());self._queue_render()

    def _extra_options(self):
        return dict(primary_override=self.colors['primary'],highlight_override=self.colors['highlight'],
                    outline_override=self.colors['outline'],animation_override=self.animation_combo.currentData(),
                    alignment_override=self.alignment_combo.currentData(),timing_offset=self.offset_spin.value())

    def _render_actual(self):
        if self._render_worker and self._render_worker.isRunning():return
        self.render_button.setEnabled(False);self.rendered_frame.setText('Rendering with local FFmpeg / libass…')
        options=dict(font_override=self.preview.font_family,size_override=self.preview.size,position_override=self.preview.position,stroke_override=self.preview.stroke,shadow_override=self.preview.shadow,background_override=self.preview.background)
        options.update(self._extra_options());options['sample_text']=self.sample_text.text()
        self._active_render_generation=self._render_generation
        self._render_worker=CaptionRenderWorker(self.preview.style_key,options,self)
        self._render_worker.ready.connect(self._show_render)
        self._render_worker.failed.connect(self._render_failed)
        self._render_worker.finished.connect(self._render_finished)
        self._render_worker.start()

    def _render_failed(self,error):
        if self._active_render_generation==self._render_generation:self.rendered_frame.setText('Render failed: '+error)

    def _render_finished(self):
        self.render_button.setEnabled(True)
        if self._active_render_generation!=self._render_generation:self._render_timer.start()

    def _show_render(self,data):
        if self._active_render_generation!=self._render_generation:return
        pixmap=QPixmap()
        if pixmap.loadFromData(data):self.rendered_frame.setPixmap(pixmap)
        else:self.rendered_frame.setText('Could not decode rendered frame')

    def shutdown(self):
        self._render_timer.stop()
        self.preview.stop()
        if self._render_worker and self._render_worker.isRunning():self._render_worker.wait(50000)

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
        self.stroke_spin.blockSignals(True);self.stroke_spin.setValue(self.preview.stroke);self.stroke_spin.blockSignals(False)
        self.shadow_check.blockSignals(True);self.shadow_check.setChecked(self.preview.shadow);self.shadow_check.blockSignals(False)
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(st.size)
        self.size_slider.blockSignals(False)
        self.preview.update()
        self._queue_render()

    def _on_font(self, family: str) -> None:
        self.preview.font_family = family
        self.preview.update()
        self._queue_render()

    def _on_size(self, value: int) -> None:
        self.preview.size = value
        self.preview.update()
        self._queue_render()

    def _on_position(self, value: str) -> None:
        self.preview.position = value
        self.preview.update()
        self._queue_render()

    def _on_stroke(self, value: int) -> None:
        self.preview.stroke = value
        self.preview.update()
        self._queue_render()

    def _on_shadow(self, value: bool) -> None:
        self.preview.shadow = value
        self.preview.update()
        self._queue_render()

    def _on_bg(self, value: bool) -> None:
        self.preview.background = value
        self.preview.update()
        self._queue_render()

    def _current_settings(self):
        return {
            'caption_style':self.preview.style_key,'caption_font':self.preview.font_family,
            'caption_size':self.preview.size,'caption_position':self.preview.position,
            'caption_stroke':self.preview.stroke,'caption_shadow':int(self.preview.shadow),
            'caption_background':int(self.preview.background),
            'caption_primary':self.colors['primary'],'caption_highlight':self.colors['highlight'],
            'caption_outline':self.colors['outline'],'caption_animation':self.animation_combo.currentData(),
            'caption_alignment':self.alignment_combo.currentData(),'caption_timing_offset':self.offset_spin.value(),
        }

    def _save_default(self):
        self.db.set_settings(self._current_settings())
        self.window.settings_changed.emit()
        self.window.notify('Caption defaults saved for subsequent exports')

    def _profiles(self):
        try:
            profiles=json.loads(self.db.get_setting('caption_custom_profiles','{}'))
            return profiles if isinstance(profiles,dict) else {}
        except (TypeError,ValueError):return {}

    def _refresh_custom(self):
        self.custom_profiles.clear();self.custom_profiles.addItem('Saved custom profiles…','')
        for name in sorted(self._profiles()):self.custom_profiles.addItem(name,name)

    def _save_custom(self):
        name,ok=QInputDialog.getText(self,'Save custom caption','Profile name (up to 60 characters)')
        name=name.strip()[:60]
        if not ok or not name:return
        profiles=self._profiles()
        if name not in profiles and len(profiles)>=30:
            self.window.notify('Maximum 30 custom profiles. Reuse an existing name to replace it.');return
        profiles[name]=self._current_settings()
        self.db.set_setting('caption_custom_profiles',json.dumps(profiles))
        self._refresh_custom();self.window.notify('Custom caption profile saved locally')

    def _load_custom(self,index):
        name=self.custom_profiles.itemData(index)
        profile=self._profiles().get(name)
        if isinstance(profile,dict):self._restore_settings(profile)

    def _apply_all(self) -> None:
        with self.db.transaction():
            cursor = self.db.conn.execute(
                "UPDATE clips SET caption_style=? WHERE status='pending'",
                (self.preview.style_key,),
            )
            n = cursor.rowcount
        self.window.data_changed.emit()
        self.window.notify(f"Caption style applied to {n} pending clips")

    def refresh(self) -> None:
        self._refresh_custom()
        self._restore_settings(self.db.get_settings())

    def _restore_settings(self,settings):
        key = settings.get("caption_style", "bold_viral")
        if key in self.style_buttons:
            self._select_style(key)
        self.font_combo.setCurrentText(settings.get('caption_font',self.preview.font_family))
        self.size_slider.setValue(int(settings.get('caption_size',58)))
        self.position_combo.setCurrentText(settings.get('caption_position','bottom'))
        self.stroke_spin.setValue(int(settings.get('caption_stroke',4)))
        self.shadow_check.setChecked(bool(settings.get('caption_shadow',True)))
        self.bg_check.setChecked(bool(settings.get('caption_background',False)))

        for key in self.colors:
            self.colors[key]=settings.get('caption_'+key,'')
            self.color_buttons[key].setText(self.colors[key] or 'Preset color')
        for key,combo in [('caption_animation',self.animation_combo),('caption_alignment',self.alignment_combo)]:
            combo.setCurrentIndex(max(0,combo.findData(settings.get(key,''))))
        self.offset_spin.setValue(float(settings.get('caption_timing_offset',0.)))
        self._queue_render()
