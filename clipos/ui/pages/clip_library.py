"""Clip Library: every generated clip across all projects."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from ...core.logging_setup import get_logger
from ..theme import Metrics
from ..widgets.common import Card, ScoreBadge, SectionHeader, VideoThumbnail, format_duration
from .base import BasePage

log = get_logger(__name__)


class ClipLibraryPage(BasePage):
    page_title = "Clip Library"
    page_subtitle = "Every short CLIPOS has generated, ranked by virality."

    def __init__(self, window) -> None:
        super().__init__(window)

    def build(self) -> None:
        card = Card()
        header = SectionHeader("All Clips", "")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles and transcripts…")
        self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self.refresh)
        header.add_action(self.search)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Virality (high→low)", "Engagement (high→low)",
                                  "Newest first", "Longest first"])
        self.sort_combo.currentIndexChanged.connect(self.refresh)
        header.add_action(self.sort_combo)
        card.add(header)

        # The grid lives directly in the page (the base page already provides
        # a scroll area).  Nesting a second one inside the card would collapse
        # to zero height and the cards would not be visible.
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(Metrics.md)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        card.add(self.grid_host)
        self.content_layout.addWidget(card)

    def refresh(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        clips = self.db.list_clips()
        query = self.search.text().strip().lower()
        if query:
            clips = [
                c for c in clips
                if query in (c["title"] or "").lower()
                or query in (c["transcript_text"] or "").lower()
            ]

        mode = self.sort_combo.currentIndex()
        if mode == 0:
            clips.sort(key=lambda c: -(c["virality_score"] or 0))
        elif mode == 1:
            clips.sort(key=lambda c: -(c["engagement_score"] or 0))
        elif mode == 2:
            clips.sort(key=lambda c: -(c["id"] or 0))
        else:
            clips.sort(key=lambda c: -(c["duration"] or 0))

        if not clips:
            lbl = QLabel("No clips yet — generate some in the Auto Clip Studio.")
            lbl.setObjectName("CardSubtitle")
            self.grid.addWidget(lbl, 0, 0)
            return

        for i, c in enumerate(clips):
            self.grid.addWidget(self._clip_card(c), i // 3, i % 3)

    def _clip_card(self, c) -> QWidget:
        card = Card()
        thumb = VideoThumbnail(width=320)
        thumb.setMaximumHeight(180)
        thumb.set_video(c["thumbnail_path"], c["duration"])
        card.add(thumb)

        title = QLabel(c["title"] or "Untitled clip")
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 650; font-size: 13px;")
        title.setToolTip(c["title"])
        card.add(title)

        meta = QLabel(
            f"{format_duration(c['start_time'])} → {format_duration(c['end_time'])} "
            f"· {c['duration']:.0f}s · {c['aspect_ratio']}"
        )
        meta.setObjectName("CardSubtitle")
        card.add(meta)

        try:
            hooks = json.loads(c["hook_suggestions"] or "[]")
        except json.JSONDecodeError:
            hooks = []
        if hooks:
            hook = QLabel(f"Hook: {hooks[0]}")
            hook.setWordWrap(True)
            hook.setObjectName("CardSubtitle")
            card.add(hook)

        scores = QHBoxLayout()
        eng = ScoreBadge()
        eng.set_value(c["engagement_score"] or 0, "engagement")
        scores.addWidget(QLabel("Engagement"))
        scores.addWidget(eng)
        vir = ScoreBadge()
        vir.set_value(c["virality_score"] or 0, "viral")
        scores.addWidget(QLabel("Virality"))
        scores.addWidget(vir)
        scores.addStretch(1)
        card.add_layout(scores)

        row = QHBoxLayout()
        open_btn = QPushButton("Open in Studio")
        open_btn.setObjectName("Ghost")
        open_btn.clicked.connect(
            lambda _=False, pid=c["project_id"]: self.window.open_project(pid)
        )
        row.addWidget(open_btn)
        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("Ghost")
        edit_btn.clicked.connect(
            lambda _=False, pid=c["project_id"], cid=c["id"]:
                self.window.open_in_editor(pid, cid)
        )
        row.addWidget(edit_btn)
        card.add_layout(row)

        card.setMinimumWidth(300)
        return card
