"""The CLIPOS preview editor: timeline, waveform and editing tools.

This page lets the user load a clip, play it frame by frame, trim/split/merge
segments, change speed and zoom, move the crop centre, and render the result.
Everything it shows is real: the waveform comes from the actual audio track and
the preview frames are extracted from the actual source video with FFmpeg.
"""
from __future__ import annotations

import json
import math
import subprocess
import threading
import time
import wave
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygon,
)
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ...core.config import ASPECT_RATIOS
from ...core.ffmpeg import extract_audio_wav, extract_frames, probe
from ...core.logging_setup import get_logger
from ...video.renderer import ClipRenderer, RenderSettings
from ...video.timeline import Timeline
from ..theme import Metrics, palette
from ..widgets.common import Card, SectionHeader, format_duration, format_size
from .base import BasePage

log = get_logger(__name__)


class TimelineWidget(QWidget):
    """Custom-painted timeline: ruler, waveform, video and effects tracks."""

    position_changed = Signal(float)
    seek_requested = Signal(float)

    TRACK_TOP = 34          # ruler height
    WAVE_TOP = 34
    WAVE_H = 46
    VIDEO_TOP = 84
    VIDEO_H = 34
    FX_TOP = 122
    FX_H = 26
    TOTAL_H = 154

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(self.TOTAL_H)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._duration = 1.0
        self._position = 0.0
        self._waveform: list[float] = []
        self._segments: list[dict] = []
        self._selected = 0
        self._hover_px = -1.0
        self._dragging = False

    # -- data -----------------------------------------------------------------
    def set_duration(self, duration: float) -> None:
        self._duration = max(0.1, duration)
        self.update()

    def set_waveform(self, samples: list[float]) -> None:
        self._waveform = samples
        self.update()

    def set_segments(self, segments: list[dict]) -> None:
        self._segments = segments
        self.update()

    def set_position(self, position: float) -> None:
        self._position = max(0.0, min(self._duration, position))
        self.update()

    def position(self) -> float:
        return self._position

    def select(self, index: int) -> None:
        self._selected = index
        self.update()

    def selected(self) -> int:
        return self._selected

    # -- geometry -------------------------------------------------------------
    def _x(self, t: float) -> float:
        if self._duration <= 0:
            return 0.0
        return (t / self._duration) * self.width()

    def _t(self, x: float) -> float:
        if self.width() <= 0:
            return 0.0
        return max(0.0, min(self._duration, (x / self.width()) * self._duration))

    def _segment_rect(self, seg: dict) -> QRect:
        x0 = self._x(seg["out_start"])
        x1 = self._x(seg["out_end"])
        return QRect(int(x0), self.VIDEO_TOP, max(3, int(x1 - x0)), self.VIDEO_H)

    # -- painting -------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(pal.bg))

        # -- ruler --------------------------------------------------------------
        p.setPen(QPen(QColor(pal.border), 1))
        p.drawLine(0, self.TRACK_TOP - 1, w, self.TRACK_TOP - 1)
        step = self._ruler_step()
        t = 0.0
        while t <= self._duration + 0.001:
            x = self._x(t)
            p.setPen(QPen(QColor(pal.border), 1))
            p.drawLine(int(x), self.TRACK_TOP - 7, int(x), self.TRACK_TOP - 1)
            p.setPen(QPen(QColor(pal.text_dim)))
            p.drawText(int(x) + 3, self.TRACK_TOP - 10, format_duration(t))
            t += step

        # -- waveform -----------------------------------------------------------
        wave_rect = QRect(0, self.WAVE_TOP, w, self.WAVE_H)
        p.fillRect(wave_rect, QColor(pal.bg_panel))
        if self._waveform:
            mid = self.WAVE_TOP + self.WAVE_H / 2
            amp = (self.WAVE_H / 2) - 2
            path = QPainterPath()
            n = len(self._waveform)
            for i, v in enumerate(self._waveform):
                x = (i / max(1, n - 1)) * w
                y = mid - max(-1.0, min(1.0, v)) * amp
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(pal.accent)))
            p.drawPath(path)
        else:
            p.setPen(QPen(QColor(pal.text_dim)))
            p.drawText(8, self.WAVE_TOP + self.WAVE_H // 2 + 4, "No audio waveform")

        # -- video track --------------------------------------------------------
        p.fillRect(0, self.VIDEO_TOP, w, self.VIDEO_H, QColor(pal.bg_panel))
        for i, seg in enumerate(self._segments):
            r = self._segment_rect(seg)
            selected = (i == self._selected)
            fill = QColor(pal.accent) if selected else QColor(pal.accent)
            p.setPen(QPen(QColor(pal.accent if selected else pal.border), 2 if selected else 1))
            p.setBrush(QBrush(fill))
            p.drawRoundedRect(r, 5, 5)
            # speed badge
            sp = seg.get("speed", 1.0)
            label = f"{sp:.2f}x" if abs(sp - 1.0) > 0.001 else ""
            if label:
                p.setPen(QPen(QColor(pal.bg)))
                p.drawText(r.adjusted(5, 3, 0, 0), Qt.AlignmentFlag.AlignTop, label)
            if r.width() > 60:
                p.setPen(QPen(QColor(pal.text if selected else pal.text_dim)))
                p.drawText(r.adjusted(4, 0, -4, -3),
                           Qt.AlignmentFlag.AlignBottom,
                           f"{seg.get('source_start', 0):.1f}s–{seg.get('source_end', 0):.1f}s")

        # -- effects track ------------------------------------------------------
        p.fillRect(0, self.FX_TOP, w, self.FX_H, QColor(pal.bg_panel))
        p.setPen(QPen(QColor(pal.text_dim)))
        p.drawText(8, self.FX_TOP + self.FX_H // 2 + 4, "Effects / captions")

        # -- playhead -----------------------------------------------------------
        px = self._x(self._position)
        p.setPen(QPen(QColor(pal.danger), 2))
        p.drawLine(int(px), 0, int(px), h)
        p.setBrush(QBrush(QColor(pal.danger)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygon([QPoint(int(px) - 6, 0), QPoint(int(px) + 6, 0),
                                QPoint(int(px), 9)]))
        p.end()

    def _ruler_step(self) -> float:
        d = self._duration
        for step in (0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300):
            if d / step <= 12:
                return step
        return 600.0

    # -- interaction ----------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        t = self._t(event.position().x())
        for index, segment in enumerate(self._segments):
            if segment["out_start"] <= t <= segment["out_end"]:
                self.select(index)
                break
        self._dragging = True
        self.seek_requested.emit(t)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self.seek_requested.emit(self._t(event.position().x()))
        else:
            self._hover_px = event.position().x()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._dragging = False

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_px = -1.0
        self.update()


class PreviewWidget(QWidget):
    """Shows the current video frame with the caption overlay."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(240, 426)
        self._pixmap: QPixmap | None = None
        self._text = ""
        self._highlight = ""

    def set_frame(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def set_caption(self, text: str, highlight: str = "") -> None:
        self._text = text
        self._highlight = highlight
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        p.fillRect(self.rect(), QColor(pal.bg))

        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
            if self._text:
                self._draw_caption(p, x, y, scaled.width(), scaled.height())
        else:
            p.setPen(QPen(QColor(pal.text_dim)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No preview")
        p.end()

    def _draw_caption(self, p: QPainter, x: int, y: int, w: int, h: int) -> None:
        pal = palette()
        font = QFont(self.font().family())
        font.setBold(True)
        font.setPixelSize(max(14, int(h * 0.052)))
        p.setFont(font)
        fm = p.fontMetrics()

        # Wrap to the frame width.
        words = self._text.split()
        lines: list[str] = []
        cur = ""
        limit = int(w * 0.86)
        for word in words:
            cand = f"{cur} {word}".strip()
            if cur and fm.horizontalAdvance(cand) > limit:
                lines.append(cur)
                cur = word
                if len(lines) >= 3:
                    break
            else:
                cur = cand
        if cur and len(lines) < 3:
            lines.append(cur)

        line_h = fm.height()
        block_h = line_h * len(lines)
        base_y = y + h - int(h * 0.16) - block_h
        for i, line in enumerate(lines):
            lw = fm.horizontalAdvance(line)
            lx = x + (w - lw) // 2
            ly = base_y + i * line_h
            # Stroke
            p.setPen(QPen(QColor("#000000"), 5))
            p.drawText(lx, ly + line_h * 0.78, line)
            # Fill, highlighting the emphasised words
            p.setPen(QPen(QColor("#FFFFFF")))
            if self._highlight and self._highlight.lower() in line.lower():
                hl = self._highlight.lower()
                pos = line.lower().find(hl)
                before = line[:pos]
                wbefore = fm.horizontalAdvance(before)
                whl = fm.horizontalAdvance(line[pos:pos + len(hl)])
                p.drawText(lx, ly + line_h * 0.78, before)
                p.setPen(QPen(QColor(pal.warning)))
                p.drawText(lx + wbefore, ly + line_h * 0.78, line[pos:pos + len(hl)])
            else:
                p.drawText(lx, ly + line_h * 0.78, line)


class PreviewWorker(QThread):
    """Extracts a single frame from the source video on a worker thread."""

    frame_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, source: str, timestamp: float, out_dir: Path,
                 parent=None, video_filter="") -> None:
        super().__init__(parent)
        self.video_filter = video_filter
        self.source = source
        self.timestamp = timestamp
        self.out_dir = out_dir
        self._seq = 0

    def run(self) -> None:
        try:
            import uuid
            from ...core.ffmpeg import run_ffmpeg
            out_dir = self.out_dir / uuid.uuid4().hex
            out_dir.mkdir(parents=True, exist_ok=True)
            frame = out_dir / "preview.jpg"
            run_ffmpeg(["-y", "-ss", str(self.timestamp), "-i", self.source,
                        "-frames:v", "1", "-vf", self.video_filter or "scale=540:-2", str(frame)])
            written = [str(frame)]
            if written and Path(written[0]).exists():
                self.frame_ready.emit(str(written[0]))
            else:
                self.failed.emit(f"Could not extract a frame at {self.timestamp:.2f}s")
        except Exception as exc:
            log.exception("frame extraction failed")
            self.failed.emit(str(exc))


class TimelineRenderWorker(QThread):
    """Renders the edited timeline on a worker thread so the UI stays live.

    The render itself is genuine FFmpeg work; the thread only keeps the
    window responsive and makes the operation cancellable.
    """

    progress = Signal(float, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, source: str, target: Path, timeline, settings,
                 work_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.source = source
        self.target = target
        self.timeline = timeline
        self.settings = settings
        self.work_dir = work_dir
        self._cancel = False
        self.cues = []

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            renderer = ClipRenderer(self.work_dir)
            result = renderer.render_timeline(
                self.source, self.target, self.timeline, self.settings,
                cues=getattr(self, 'cues', []),
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                cancel_cb=lambda: self._cancel,
            )
            self.finished_ok.emit(result)
        except Exception as exc:
            log.exception("timeline render failed")
            self.failed.emit(str(exc))


class EditorPage(BasePage):
    """The functional preview editor."""

    page_title = "Preview Editor"
    page_subtitle = "Advanced source timeline. Review the finished composition in Create clips."

    def __init__(self, window) -> None:
        self.project_id: int | None = None
        self.clip_id: int | None = None
        self.timeline = Timeline()
        self.source: Path | None = None
        self._worker: PreviewWorker | None = None
        self._render_worker: TimelineRenderWorker | None = None
        self._render_target: Path | None = None
        self._playing = False
        self._frame_cache: dict[float, str] = {}
        super().__init__(window)

    # -- construction ---------------------------------------------------------
    def build(self) -> None:
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(33)
        self._play_timer.timeout.connect(self._on_tick)

        root = self.content_layout
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Metrics.md)

        # -- header ------------------------------------------------------------
        header = QHBoxLayout()
        header.addStretch(1)
        self.btn_undo = QPushButton("Undo")
        self.btn_redo = QPushButton("Redo")
        self.btn_split = QPushButton("Split")
        self.btn_merge = QPushButton("Merge")
        self.btn_trim_in = QPushButton("Set In")
        self.btn_trim_out = QPushButton("Set Out")
        self.btn_render = QPushButton("Render Edit")
        self.btn_render.setObjectName("Primary")
        self.btn_cancel_render = QPushButton("Cancel")
        self.btn_cancel_render.setObjectName("Danger")
        self.btn_cancel_render.setVisible(False)
        for b in (self.btn_undo, self.btn_redo, self.btn_split, self.btn_merge,
                  self.btn_trim_in, self.btn_trim_out):
            b.setEnabled(False)
        header.addWidget(self.btn_undo)
        header.addWidget(self.btn_redo)
        header.addWidget(self.btn_split)
        header.addWidget(self.btn_merge)
        header.addWidget(self.btn_trim_in)
        header.addWidget(self.btn_trim_out)
        header.addWidget(self.btn_render)
        header.addWidget(self.btn_cancel_render)
        root.addLayout(header)

        # -- main split --------------------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(Metrics.md)

        # preview column
        left = QVBoxLayout()
        left.setSpacing(Metrics.md)
        preview_card = Card()
        self.preview = PreviewWidget()
        preview_card.add(self.preview, 1)
        left.addWidget(preview_card, 1)

        transport = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_play.setEnabled(False)
        self.btn_prev = QPushButton("◀ Frame")
        self.btn_prev.setEnabled(False)
        self.btn_next = QPushButton("Frame ▶")
        self.btn_next.setEnabled(False)
        transport.addWidget(self.btn_play)
        transport.addWidget(self.btn_prev)
        transport.addWidget(self.btn_next)
        transport.addStretch(1)
        self.time_label = QLabel("00:00.00 / 00:00.00")
        transport.addWidget(self.time_label)
        left.addLayout(transport)
        body.addLayout(left, 3)

        # inspector column
        right = QVBoxLayout()
        right.setSpacing(Metrics.md)
        insp = Card()
        insp.add(SectionHeader("Inspector", "Properties of the selected segment"))
        form = QVBoxLayout()
        form.setSpacing(Metrics.sm)

        self.lbl_segment = QLabel("No clip loaded")
        self.lbl_segment.setObjectName("StatLabel")
        self.lbl_segment.setWordWrap(True)
        form.addWidget(self.lbl_segment)

        row_speed = QHBoxLayout()
        row_speed.addWidget(QLabel("Speed"))
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.25, 4.0)
        self.spin_speed.setSingleStep(0.05)
        self.spin_speed.setValue(1.0)
        self.spin_speed.setSuffix("×")
        self.spin_speed.setEnabled(False)
        row_speed.addWidget(self.spin_speed)
        form.addLayout(row_speed)

        row_zoom = QHBoxLayout()
        row_zoom.addWidget(QLabel("Zoom"))
        self.spin_zoom = QDoubleSpinBox()
        self.spin_zoom.setRange(1.0, 3.0)
        self.spin_zoom.setSingleStep(0.05)
        self.spin_zoom.setValue(1.0)
        self.spin_zoom.setSuffix("×")
        self.spin_zoom.setEnabled(False)
        row_zoom.addWidget(self.spin_zoom)
        form.addLayout(row_zoom)

        row_crop = QHBoxLayout()
        row_crop.addWidget(QLabel("Crop X"))
        self.spin_crop_x = QDoubleSpinBox()
        self.spin_crop_x.setRange(0.0, 1.0)
        self.spin_crop_x.setSingleStep(0.02)
        self.spin_crop_x.setValue(0.5)
        self.spin_crop_x.setEnabled(False)
        row_crop.addWidget(self.spin_crop_x)
        row_crop.addWidget(QLabel("Y"))
        self.spin_crop_y = QDoubleSpinBox()
        self.spin_crop_y.setRange(0.0, 1.0)
        self.spin_crop_y.setSingleStep(0.02)
        self.spin_crop_y.setValue(0.5)
        self.spin_crop_y.setEnabled(False)
        row_crop.addWidget(self.spin_crop_y)
        form.addLayout(row_crop)

        row_mute = QHBoxLayout()
        self.check_mute = QPushButton("Mute")
        self.check_mute.setCheckable(True)
        self.check_mute.setEnabled(False)
        row_mute.addWidget(self.check_mute)
        row_mute.addStretch(1)
        form.addLayout(row_mute)

        row_move = QHBoxLayout()
        self.btn_up = QPushButton("Move Up")
        self.btn_down = QPushButton("Move Down")
        self.btn_up.setEnabled(False)
        self.btn_down.setEnabled(False)
        row_move.addWidget(self.btn_up)
        row_move.addWidget(self.btn_down)
        form.addLayout(row_move)

        insp.add_layout(form)
        right.addWidget(insp)

        # clip list
        clips_card = Card()
        clips_card.add(SectionHeader("Clips in project", "Pick a clip to edit"))
        self.clip_list = QWidget()
        self.clip_layout = QVBoxLayout(self.clip_list)
        self.clip_layout.setContentsMargins(0, 0, 0, 0)
        self.clip_layout.setSpacing(4)
        clips_card.add(self.clip_list)
        right.addWidget(clips_card, 1)

        body.addLayout(right, 2)
        root.addLayout(body, 1)

        # -- timeline ----------------------------------------------------------
        tl_card = Card()
        tl_card.add(SectionHeader("Timeline", "Click to seek · drag the playhead"))
        self.timeline_widget = TimelineWidget()
        tl_card.add(self.timeline_widget)
        root.addWidget(tl_card)

        # -- wiring -------------------------------------------------------------
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_prev.clicked.connect(lambda: self._step_frame(-1))
        self.btn_next.clicked.connect(lambda: self._step_frame(1))
        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo.clicked.connect(self._redo)
        self.btn_split.clicked.connect(self._split)
        self.btn_merge.clicked.connect(self._merge)
        self.btn_trim_in.clicked.connect(lambda: self._trim("in"))
        self.btn_trim_out.clicked.connect(lambda: self._trim("out"))
        self.btn_render.clicked.connect(self._render)
        self.btn_cancel_render.clicked.connect(self._cancel_render)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.check_mute.toggled.connect(self._toggle_mute)
        self.spin_speed.valueChanged.connect(self._on_speed)
        self.spin_zoom.valueChanged.connect(self._on_zoom)
        self.spin_crop_x.valueChanged.connect(self._on_crop)
        self.spin_crop_y.valueChanged.connect(self._on_crop)
        self.timeline_widget.seek_requested.connect(self._seek)
        self.timeline_widget.position_changed.connect(self._set_position)

    def refresh(self) -> None:
        if self.project_id:
            self._reload_clips()

    def shutdown(self) -> None:
        """Stop the workers so no thread outlives the window."""
        self._play_timer.stop()
        worker = self._worker
        if worker is not None and worker.isRunning():
            if not worker.wait(3000):
                worker.terminate()
                worker.wait(500)
        self._worker = None

        # A running render is cancelled and waited for, so FFmpeg is not
        # left writing into a half-closed window.
        render_worker = self._render_worker
        if render_worker is not None:
            render_worker.cancel()
            if render_worker.isRunning():
                if not render_worker.wait(5000):
                    render_worker.terminate()
                    render_worker.wait(500)
            self._render_worker = None


    # -- loading --------------------------------------------------------------
    def load_project(self, project_id: int) -> None:
        self.project_id = project_id
        self._reload_clips()

    def _reload_clips(self) -> None:
        while self.clip_layout.count():
            item = self.clip_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self.project_id:
            self.lbl_segment.setText("No clip loaded")
            return
        clips = self.window.db.list_clips(self.project_id)
        if not clips:
            self.lbl_segment.setText("This project has no clips yet")
            return
        for c in clips:
            btn = QPushButton(
                f"{c['title']}   [{format_duration(c['start_time'])}]   "
                f"viral {c['virality_score']:.0f}"
            )
            btn.setToolTip(f"Source {format_duration(c['start_time'])} "
                           f"→ {format_duration(c['end_time'])}")
            btn.clicked.connect(lambda _=False, cid=c["id"]: self.load_clip(cid))
            self.clip_layout.addWidget(btn)
        self.load_clip(clips[0]["id"])

    def load_clip(self, clip_id: int) -> None:
        self.clip_id = clip_id
        clip = self.window.db.get_clip(clip_id)
        if clip is None:
            return
        project = self.window.db.get_project(self.project_id)
        self.source = Path(project["source_path"])
        if not self.source.exists():
            self.lbl_segment.setText("Source video is missing")
            return

        self.timeline = Timeline.from_clip(
            clip["start_time"], clip["end_time"], project["duration"],
        )
        from ...core.config import PATHS
        saved = PATHS.projects / str(self.project_id) / "edits" / f"{clip_id}.json"
        if saved.exists():
            try:
                self.timeline = Timeline.load(saved)
            except (ValueError, OSError, KeyError) as exc:
                log.warning("Could not restore timeline: %s", exc)
        self._frame_cache.clear()
        self.timeline_widget.select(0)
        self.timeline_widget.set_duration(self.timeline.duration)
        self.timeline_widget.set_segments(self._segment_views())
        self._load_waveform()
        self._update_controls()
        self._set_position(0.0)

        self.btn_play.setEnabled(True)
        self.btn_prev.setEnabled(True)
        self.btn_next.setEnabled(True)
        self.btn_render.setEnabled(True)
        self.lbl_segment.setText(
            f"{clip['title']}\nSource {format_duration(clip['start_time'])} → "
            f"{format_duration(clip['end_time'])}"
        )

    def _segment_views(self) -> list[dict]:
        """Convert the model into the dicts the timeline widget paints."""
        views = []
        acc = 0.0
        for seg in self.timeline.segments:
            views.append({
                "id": seg.id,
                "source_start": seg.start,
                "source_end": seg.end,
                "out_start": acc,
                "out_end": acc + seg.duration,
                "speed": seg.speed,
                "zoom": seg.zoom,
            })
            acc += seg.duration
        return views

    def _load_waveform(self) -> None:
        """Read the real audio track and compute the waveform peaks."""
        if not self.source:
            return
        try:
            from ...core.config import PATHS

            wav = PATHS.cache / f"editor_{self.project_id}.wav"
            if not wav.exists():
                extract_audio_wav(self.source, wav)
            with wave.open(str(wav), "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                width = wf.getsampwidth()
                count = wf.getnframes()
                channels = wf.getnchannels()
            if width != 2 or count == 0:
                return
            import array

            samples = array.array("h")
            samples.frombytes(frames[: count * width * channels])
            buckets = 900
            step = max(1, len(samples) // buckets)
            peaks: list[float] = []
            for i in range(0, len(samples) - step, step):
                chunk = samples[i:i + step]
                if not chunk:
                    break
                peak = max(abs(v) for v in chunk) / 32768.0
                peaks.append(peak)
            self.timeline_widget.set_waveform(peaks)
        except Exception as exc:
            log.warning("waveform unavailable: %s", exc)
            self.timeline_widget.set_waveform([])

    # -- transport ------------------------------------------------------------
    def _toggle_play(self) -> None:
        self._playing = not self._playing
        self.btn_play.setText("Pause" if self._playing else "Play")
        if self._playing:
            self._play_timer.start()
        else:
            self._play_timer.stop()

    def _on_tick(self) -> None:
        pos = self.timeline_widget.position() + 0.033
        if pos >= self.timeline.duration:
            pos = 0.0
        self._set_position(pos)

    def _step_frame(self, direction: int) -> None:
        fps = 30.0
        pos = self.timeline_widget.position() + direction / fps
        self._set_position(max(0.0, min(self.timeline.duration, pos)))

    def _seek(self, t: float) -> None:
        self._set_position(t)

    def _set_position(self, t: float) -> None:
        self.timeline_widget.set_position(t)
        self.time_label.setText(
            f"{format_duration(t)} / {format_duration(self.timeline.duration)}"
        )
        self._request_frame(t)

    def _request_frame(self, t: float) -> None:
        key = round(t, 2)
        cached = self._frame_cache.get(key)
        if cached:
            self._show_frame(cached)
            return
        if self._worker and self._worker.isRunning():
            return
        from ...core.config import PATHS

        # The previous worker has finished, so it can be released safely.
        old = self._worker
        if old is not None:
            old.deleteLater()
        from ...video.renderer import segment_video_filter
        acc = 0.0
        active = None
        for segment in self.timeline.segments:
            if acc <= t <= acc + segment.duration:
                active = segment
                break
            acc += segment.duration
        vf = segment_video_filter(active, 270, 480) if active else "scale=540:-2"
        self._worker = PreviewWorker(
            str(self.source), self.timeline.source_time_at(t),
            PATHS.cache / "frames", parent=self, video_filter=vf,
        )
        self._worker.frame_ready.connect(self._show_frame)
        self._worker.failed.connect(lambda m: log.debug("frame: %s", m))
        self._worker.start()

    def _show_frame(self, path: str) -> None:
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.preview.set_frame(pixmap)
        # Caption text for the current position
        clip = self.window.db.get_clip(self.clip_id) if self.clip_id else None
        if clip:
            text = clip["transcript_text"] or ""
            self.preview.set_caption(text[:120])

    # -- editing --------------------------------------------------------------
    def _selected_segment(self):
        idx = self.timeline_widget.selected()
        if 0 <= idx < len(self.timeline.segments):
            return idx, self.timeline.segments[idx]
        return -1, None

    def _split(self) -> None:
        source_t = self.timeline.source_time_at(self.timeline_widget.position())
        if self.timeline.split_at(source_t):
            self._after_edit()
            self.window.notify(f"Split at {source_t:.2f}s")
        else:
            self.window.notify("The playhead is not inside a segment")

    def _merge(self) -> None:
        idx, _ = self._selected_segment()
        if idx < 0:
            return
        if self.timeline.merge_with_next(idx):
            self._after_edit()
            self.window.notify("Merged with the next segment")
        else:
            self.window.notify("Nothing to merge — segments must be adjacent")

    def _trim(self, which: str) -> None:
        idx, seg = self._selected_segment()
        if seg is None:
            return
        source_t = self.timeline.source_time_at(self.timeline_widget.position())
        if which == "in":
            if self.timeline.trim(seg.id, new_start=source_t):
                self._after_edit()
                self.window.notify(f"In point set to {source_t:.2f}s")
            else:
                self.window.notify("The in point must be before the out point")
        else:
            if self.timeline.trim(seg.id, new_end=source_t):
                self._after_edit()
                self.window.notify(f"Out point set to {source_t:.2f}s")
            else:
                self.window.notify("The out point must be after the in point")

    def _move(self, delta: int) -> None:
        idx, _ = self._selected_segment()
        if idx < 0:
            return
        if self.timeline.move_segment(idx, delta):
            self._after_edit()
        else:
            self.window.notify("Cannot move further in that direction")

    def _undo(self) -> None:
        label = self.timeline.undo()
        if label:
            self._after_edit()
            self.window.notify(f"Undo: {label}")

    def _redo(self) -> None:
        label = self.timeline.redo()
        if label:
            self._after_edit()
            self.window.notify(f"Redo: {label}")

    def _on_speed(self, value: float) -> None:
        idx, seg = self._selected_segment()
        if seg is None or abs(seg.speed - value) < 0.001:
            return
        self.timeline.set_speed(seg.id, value)
        self._after_edit()

    def _on_zoom(self, value: float) -> None:
        idx, seg = self._selected_segment()
        if seg is None or abs(seg.zoom - value) < 0.001:
            return
        self.timeline.set_zoom(seg.id, value)
        self._after_edit()

    def _on_crop(self) -> None:
        idx, seg = self._selected_segment()
        if seg is None:
            return
        if (abs(seg.crop_x - self.spin_crop_x.value()) < 0.005
                and abs(seg.crop_y - self.spin_crop_y.value()) < 0.005):
            return
        self.timeline.set_crop(seg.id, self.spin_crop_x.value(), self.spin_crop_y.value())
        self._after_edit()

    def _toggle_mute(self, checked: bool) -> None:
        idx, seg = self._selected_segment()
        if seg is None:
            return
        self.timeline.set_muted(seg.id, checked)
        self._after_edit()

    def _after_edit(self) -> None:
        from ...core.config import PATHS
        if self.clip_id:
            self.timeline.save(PATHS.projects / str(self.project_id) / "edits" / f"{self.clip_id}.json")
        self._frame_cache.clear()
        self.timeline_widget.set_segments(self._segment_views())
        self.timeline_widget.set_duration(self.timeline.duration)
        self._update_controls()
        self._request_frame(self.timeline_widget.position())

    def _update_controls(self) -> None:
        self.btn_undo.setEnabled(self.timeline.can_undo())
        self.btn_redo.setEnabled(self.timeline.can_redo())
        has = bool(self.timeline.segments)
        for b in (self.btn_split, self.btn_merge, self.btn_trim_in, self.btn_trim_out,
                  self.btn_up, self.btn_down):
            b.setEnabled(has)
        idx, seg = self._selected_segment()
        enabled = seg is not None
        self.spin_speed.setEnabled(enabled)
        self.spin_zoom.setEnabled(enabled)
        self.spin_crop_x.setEnabled(enabled)
        self.spin_crop_y.setEnabled(enabled)
        self.check_mute.setEnabled(enabled)
        if seg:
            self.spin_speed.blockSignals(True)
            self.spin_speed.setValue(seg.speed)
            self.spin_speed.blockSignals(False)
            self.spin_zoom.blockSignals(True)
            self.spin_zoom.setValue(seg.zoom)
            self.spin_zoom.blockSignals(False)
            self.spin_crop_x.blockSignals(True)
            self.spin_crop_x.setValue(seg.crop_x)
            self.spin_crop_x.blockSignals(False)
            self.spin_crop_y.blockSignals(True)
            self.spin_crop_y.setValue(seg.crop_y)
            self.spin_crop_y.blockSignals(False)
            self.check_mute.blockSignals(True)
            self.check_mute.setChecked(seg.muted)
            self.check_mute.blockSignals(False)

    # -- render ---------------------------------------------------------------
    def _render(self) -> None:
        if not self.source or self.timeline.is_empty:
            return
        if self._render_worker is not None and self._render_worker.isRunning():
            self.window.notify("A render is already running", 3000)
            return

        out_dir = Path(self.window.db.get_setting("output_dir") or "./exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"edited_{self.clip_id}_{int(time.time())}.mp4"

        from ...core.editing import render_settings
        state=json.loads(self.window.db.get_setting(f'workflow:{self.project_id}','{}') or '{}')
        overrides={}
        if state.get('facecam'):
            overrides={'facecam_rect':state['facecam'],'gameplay_rect':state.get('gameplay',(0.,0.,1.,1.)),'framing_mode':'manual'}
        settings=render_settings(self.window.db,overrides)

        from ...core.config import PATHS

        self._render_target = target
        worker = TimelineRenderWorker(
            str(self.source), target, self.timeline, settings,
            PATHS.cache / "work", parent=self,
        )
        if settings.show_captions:
            from ...ai.transcription import Transcript, Segment, Word
            from ...captions.caption_engine import build_cues, retime_cues
            saved=self.window.db.get_transcript(self.project_id)
            if saved:
                segments=[Segment(s['start'],s['end'],s['text'],[Word(w['w'],w['s'],w['e'],w.get('p',1.)) for w in s.get('words',[])]) for s in json.loads(saved['segments'] or '[]')]
                transcript=Transcript(language=saved['language'],duration=saved['duration'],text=saved['full_text'],segments=segments,model=saved['model'])
                worker.cues=retime_cues(build_cues(transcript,0,transcript.duration),[(s.start,s.end,s.speed) for s in self.timeline.segments])
        worker.progress.connect(self._on_render_progress)
        worker.finished_ok.connect(self._on_render_done)
        worker.failed.connect(self._on_render_failed)
        worker.finished.connect(self._on_render_finished)
        self._render_worker = worker
        self.btn_render.setEnabled(False)
        self.btn_cancel_render.setVisible(True)
        self.window.set_busy(True, "Rendering your edit…")
        worker.start()

    def _cancel_render(self) -> None:
        if self._render_worker is not None and self._render_worker.isRunning():
            self._render_worker.cancel()
            self.window.notify("Stopping the render…", 3000)

    def _on_render_progress(self, pct: float, message: str) -> None:
        self.window.set_busy(True, f"{message} · {pct:.0f}%")

    def _on_render_done(self, result) -> None:
        if getattr(result, "cancelled", False):
            self.window.notify("Render cancelled", 3000)
            return
        target = self._render_target
        if self.clip_id:
            self.window.db.update_clip(self.clip_id, output_path=str(target), status="rendered")
            self.window.db.create_export(
                project_id=self.project_id, clip_id=self.clip_id,
                output_path=str(target), status="done",
                size_bytes=result.size_bytes, duration=result.duration,
                width=result.width, height=result.height,
            )
        self.window.notify(
            f"Rendered {result.width}×{result.height} · {format_duration(result.duration)} "
            f"· {format_size(result.size_bytes)}"
        )

    def _on_render_failed(self, message: str) -> None:
        self.window.notify(f"Render failed: {message}", 6000)

    def _on_render_finished(self) -> None:
        worker = self._render_worker
        self._render_worker = None
        if worker is not None:
            worker.deleteLater()
        self.btn_render.setEnabled(True)
        self.btn_cancel_render.setVisible(False)
        self.window.set_busy(False)
        self.window.data_changed.emit()
