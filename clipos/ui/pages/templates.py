"""Templates: ready-made caption and export presets."""
from __future__ import annotations

from PySide6.QtGui import QPixmap
from ..widgets.preset_preview import preset_thumbnail
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...captions.caption_engine import CAPTION_STYLES, get_style
from ...core.logging_setup import get_logger
from ..theme import Metrics
from ..widgets.common import Card, SectionHeader
from .base import BasePage

log = get_logger(__name__)

# Export presets: (name, aspect, fps, codec, bitrate, caption style)
EXPORT_TEMPLATES = [
    ("YouTube Shorts", "9:16", 30, "h264", 8000, "bold_viral",
     "1080×1920 · 30 fps · H.264 · ready for Shorts"),
    ("Instagram Reels", "9:16", 30, "h264", 9000, "modern_podcast",
     "1080×1920 · 30 fps · clean, readable captions"),
    ("TikTok", "9:16", 30, "h264", 10000, "neon_gaming",
     "1080×1920 · high bitrate for TikTok's encoder"),
    ("Square Feed", "1:1", 30, "h264", 7000, "minimal_white",
     "1080×1080 · for the Instagram and LinkedIn feed"),
    ("YouTube Landscape", "16:9", 30, "h264", 8000, "cinematic",
     "1920×1080 · cinematic subtitles for long-form"),
    ("Podcast Clip", "9:16", 30, "h264", 8000, "modern_podcast",
     "1080×1920 · speaker-friendly framing"),
    ("Shorts (H.265)", "9:16", 60, "h265", 6000, "mrbeast",
     "1080×1920 · 60 fps · smaller files, newer platforms"),
    ("Vertical Highlight", "9:16", 30, "h264", 8000, "karaoke",
     "1080×1920 · word-by-word karaoke captions"),
]


class TemplatesPage(BasePage):
    page_title = "Templates"
    page_subtitle = "Presets for each platform — apply one and export."

    def build(self) -> None:
        card = Card()
        card.add(SectionHeader("Platform Presets", "Apply a preset to the export settings"))
        grid = QGridLayout()
        grid.setSpacing(Metrics.md)
        for i, preset in enumerate(EXPORT_TEMPLATES):
            grid.addWidget(self._template_card(preset), i // 3, i % 3)
        card.add_layout(grid)
        self.content_layout.addWidget(card)

        cap_card = Card()
        cap_card.add(SectionHeader("Caption Styles", "38 working styles · typography and motion"))
        cgrid = QGridLayout()
        cgrid.setSpacing(Metrics.sm)
        for i, (key, st) in enumerate(CAPTION_STYLES.items()):
            widget = self._caption_card(key, st)
            cgrid.addWidget(widget, i // 2, i % 2)
        cap_card.add_layout(cgrid)
        self.content_layout.addWidget(cap_card)

    def _template_card(self, preset) -> QWidget:
        name, aspect, fps, codec, bitrate, cap_style, detail = preset
        card = Card()
        preview = QLabel()
        preview.setPixmap(preset_thumbnail("podcast" if "Podcast" in name else "clean", name))
        card.add(preview)
        title = QLabel(name)
        title.setObjectName("CardTitle")
        card.add(title)

        desc = QLabel(detail)
        desc.setObjectName("CardSubtitle")
        desc.setWordWrap(True)
        card.add(desc)

        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(
            lambda _=False, a=aspect, f=fps, c=codec, b=bitrate, cs=cap_style, n=name:
            self._apply(a, f, c, b, cs, n)
        )
        card.add(apply_btn)
        card.setMinimumWidth(250)
        return card

    def _caption_card(self, key: str, st) -> QWidget:
        card = Card()
        preview = QLabel()
        preview.setPixmap(preset_thumbnail(key, st.name))
        card.add(preview)
        title = QLabel(st.name)
        title.setObjectName("CardTitle")
        card.add(title)
        desc = QLabel(st.description)
        desc.setObjectName("CardSubtitle")
        desc.setWordWrap(True)
        card.add(desc)

        btn = QPushButton("Preview")
        btn.setObjectName("Ghost")
        btn.clicked.connect(lambda _=False, k=key: self._preview_caption(k))
        card.add(btn)
        card.setMinimumWidth(250)
        return card

    def _apply(self, aspect: str, fps: int, codec: str, bitrate: int,
               cap_style: str, name: str) -> None:
        recipe = "podcast" if "Podcast" in name else "clean"
        self.db.set_settings({
            "editing_preset": recipe,
            "aspect_ratio": aspect,
            "caption_style": cap_style,
            "default_aspect": aspect, "fps": fps, "codec": codec,
            "bitrate_kbps": bitrate, "default_clip_duration": "30-45",
        })
        self.window.settings_changed.emit()
        self.window.notify(f"Applied the '{name}' preset")
        # Reflect the preset in the export page if it is open
        export_page = self.window.pages.get("export")
        if export_page is not None:
            export_page.recipe_combo.setCurrentIndex(max(0, export_page.recipe_combo.findData(recipe)))
            idx = export_page.aspect_combo.findData(aspect)
            if idx >= 0:
                export_page.aspect_combo.setCurrentIndex(idx)
            export_page.fps_combo.setCurrentIndex(
                export_page.fps_combo.findData(fps)
            )
            export_page.codec_combo.setCurrentIndex(
                export_page.codec_combo.findData(codec)
            )
            export_page.bitrate_spin.setValue(bitrate)

    def _preview_caption(self, key: str) -> None:
        page = self.window.pages.get("captions")
        if page is not None:
            page._select_style(key)
        self.window.navigate("captions")
