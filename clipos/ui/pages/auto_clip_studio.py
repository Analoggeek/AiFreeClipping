"""Auto Clip Studio: analyse a project, review AI clips, render and export."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from ...core.config import ASPECT_RATIOS, CLIP_DURATION_PRESETS
from ...core.logging_setup import get_logger
from ...video.pipeline import ClipOSPipeline, PipelineProgress
from ...video.renderer import RenderSettings
from ..theme import Metrics
from ..widgets.common import (
    Card, ScoreBadge, SectionHeader, VideoThumbnail, format_duration,
)
from .base import BasePage

log = get_logger(__name__)


class AnalysisWorker(QObject):
    """Runs the analysis + clip detection pipeline off the UI thread."""

    progress = Signal(object)          # PipelineProgress
    finished = Signal(int)             # number of clips
    failed = Signal(str)

    def __init__(self, db, project_id: int, clip_count: int, duration_range: str) -> None:
        super().__init__()
        self.db = db
        self.project_id = project_id
        self.clip_count = clip_count
        self.duration_range = duration_range
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        from ...video.pipeline import run_full_analysis

        try:
            settings = self.db.get_settings()
            analysis = run_full_analysis(
                self.db, self.project_id,
                clip_count=self.clip_count,
                duration_range=self.duration_range,
                aspect=settings.get("aspect_ratio", "9:16"),
                stt_model=settings.get("stt_model", "base"),
                language=settings.get("stt_language", "") or "",
                progress_cb=lambda p: self.progress.emit(p),
            )
            self.finished.emit(len(analysis.clips))
        except Exception as exc:
            log.exception("analysis failed")
            self.failed.emit(str(exc))


class OneClickWorker(QObject):
    """Runs the whole unattended chain: analyse -> cut -> caption -> export."""

    progress = Signal(object)          # PipelineProgress
    finished = Signal(dict)            # the run_one_click summary
    failed = Signal(str)

    def __init__(self, db, project_id: int, out_dir: str, clip_count: int,
                 duration_range: str) -> None:
        super().__init__()
        self.db = db
        self.project_id = project_id
        self.out_dir = out_dir
        self.clip_count = clip_count
        self.duration_range = duration_range
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        from ...video.pipeline import run_one_click

        try:
            settings = self.db.get_settings()
            summary = run_one_click(
                self.db, self.project_id, self.out_dir,
                clip_count=self.clip_count,
                duration_range=self.duration_range,
                aspect=settings.get("aspect_ratio", "9:16"),
                stt_model=settings.get("stt_model", "base"),
                language=settings.get("stt_language", "") or "",
                progress_cb=lambda p: self.progress.emit(p),
                cancel_cb=self._cancel.is_set,
            )
            self.finished.emit(summary)
        except Exception as exc:
            log.exception("one-click editing failed")
            self.failed.emit(str(exc))


class AutoClipStudioPage(BasePage):
    page_title = "Auto Clip Studio"
    page_subtitle = "Analyse the full video, then review, edit and export the AI-picked moments."

    def __init__(self, window) -> None:
        self.project_id: int | None = None
        self.project = None
        self._thread: QThread | None = None
        self._worker: AnalysisWorker | None = None
        self._clip_rows: dict[int, dict] = {}
        super().__init__(window)

    # -- layout --------------------------------------------------------------------
    def build(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---------------- left: project + controls ----------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(Metrics.md)

        proj = Card()
        proj.add(SectionHeader("Source Video", ""))
        self.thumb = VideoThumbnail(width=150)
        self.thumb.setMaximumHeight(90)
        proj.add(self.thumb)
        self.project_info = QLabel("No project selected")
        self.project_info.setObjectName("CardSubtitle")
        self.project_info.setWordWrap(True)
        proj.add(self.project_info)
        left_layout.addWidget(proj)

        run = Card()
        run.add(SectionHeader("Generate Clips", "One click, fully offline"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(10)
        self.duration_combo = QComboBox()
        for label in ("15-30", "30-45", "45-60", "60-90"):
            self.duration_combo.addItem(label.replace("-", "–") + " s", label)
        self.duration_combo.setCurrentIndex(1)

        form = QFormLayout()
        form.setSpacing(Metrics.sm)
        form.addRow("Shorts to create", self.count_spin)
        form.addRow("Clip length", self.duration_combo)
        run.add_layout(form)

        self.analyze_btn = QPushButton("✦  Generate Clips with AI")
        self.analyze_btn.setObjectName("BigAction")
        self.analyze_btn.clicked.connect(self._run_analysis)
        run.add(self.analyze_btn)

        self.one_click_btn = QPushButton("▶  One-Click Edit → Upload-Ready Clips")
        self.one_click_btn.setObjectName("Primary")
        self.one_click_btn.setToolTip(
            "Analyse, cut, caption, reframe and export finished videos — no manual editing"
        )
        self.one_click_btn.clicked.connect(self._run_one_click)
        run.add(self.one_click_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("Danger")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_analysis)
        run.add(self.cancel_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        run.add(self.progress)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("CardSubtitle")
        self.progress_label.setWordWrap(True)
        self.progress_label.setVisible(False)
        run.add(self.progress_label)
        left_layout.addWidget(run)

        left_layout.addStretch(1)
        splitter.addWidget(left)

        # ---------------- right: clip list ----------------
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(Metrics.md)

        clips_card = Card()
        clips_header = SectionHeader(
            "Detected Moments", "Ranked by virality score")
        self.export_all_btn = QPushButton("Export All")
        self.export_all_btn.setObjectName("Primary")
        self.export_all_btn.clicked.connect(self._export_all)
        clips_header.add_action(self.export_all_btn)
        clips_card.add(clips_header)

        self.clip_list = QListWidget()
        self.clip_list.setSpacing(4)
        self.clip_list.itemSelectionChanged.connect(self._on_clip_selected)
        self.clip_list.setMinimumHeight(280)
        clips_card.add(self.clip_list)
        right_layout.addWidget(clips_card, 2)

        detail_card = Card()
        detail_card.add(SectionHeader("Clip Details", "Why the AI picked this moment"))
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_body = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_body)
        self.detail_layout.setContentsMargins(0, Metrics.sm, 0, 0)
        self.detail_layout.setSpacing(Metrics.sm)
        self.detail_scroll.setWidget(self.detail_body)
        detail_card.add(self.detail_scroll)
        right_layout.addWidget(detail_card, 3)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([330, 900])

        self.content_layout.addWidget(splitter)

    # -- project -------------------------------------------------------------------
    def load_project(self, project_id: int) -> None:
        self.project_id = project_id
        self.project = self.db.get_project(project_id)
        self.refresh()
        self.window.notify(f"Opened '{self.project['name']}'" if self.project else "Project not found")

    def refresh(self) -> None:
        if self.project_id:
            self.project = self.db.get_project(self.project_id)
        if not self.project:
            self.project_info.setText("No project selected")
            self.thumb.set_video("")
            self._populate_clips([])
            return

        p = self.project
        self.thumb.set_video(p["thumbnail"], p["duration"])
        audio_note = "with audio" if p["has_audio"] else "no audio track"
        self.project_info.setText(
            f"<b>{p['name']}</b><br>"
            f"{format_duration(p['duration'])} · {p['width']}×{p['height']} · "
            f"{p['fps']:.2f} fps · {audio_note}<br>"
            f"Status: {p['status']}"
        )
        self.count_spin.setValue(p["clip_count"] or 10)
        idx = self.duration_combo.findData(p["duration_range"] or "30-45")
        if idx >= 0:
            self.duration_combo.setCurrentIndex(idx)
        self._populate_clips(self.db.list_clips(self.project_id))

    # -- clip list -------------------------------------------------------------------
    def _populate_clips(self, clips) -> None:
        self.clip_list.clear()
        self._clip_rows = {}
        if not clips:
            # Say why the list is empty rather than showing a blank panel.
            hint = QListWidgetItem()
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(Metrics.md, Metrics.lg, Metrics.md, Metrics.md)
            title = QLabel("No clips yet")
            title.setObjectName("CardSubtitle")
            title.setStyleSheet("font-weight: 650; font-size: 13px;")
            layout.addWidget(title)
            detail = QLabel(
                "Run the analysis to find engaging moments in this video."
            )
            detail.setObjectName("CardSubtitle")
            detail.setWordWrap(True)
            layout.addWidget(detail)
            self.clip_list.addItem(hint)
            self.clip_list.setItemWidget(hint, widget)
            return
        for position, c in enumerate(clips):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            hint = item.sizeHint()
            item.setSizeHint(QSize(hint.width(), 52))
            widget = self._clip_widget(c, position + 1)
            self.clip_list.addItem(item)
            self.clip_list.setItemWidget(item, widget)
            self._clip_rows[c["id"]] = dict(c)

    def _clip_widget(self, c, position: int = 1) -> QWidget:
        w = QWidget()
        # QListWidget sizes embedded widgets to the item rect, so the widget
        # needs its own minimum height or the text is squeezed and clipped.
        w.setMinimumHeight(48)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(Metrics.sm, Metrics.xs, Metrics.sm, Metrics.xs)
        lay.setSpacing(Metrics.md)

        idx = QLabel(str(position))
        idx.setFixedWidth(22)
        idx.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx.setStyleSheet(
            "background: #2f2f34; border-radius: 9px; color: #f2f2f5; font-size: 11px;"
            " font-weight: 700; padding: 2px;"
        )
        lay.addWidget(idx)

        texts = QVBoxLayout()
        texts.setSpacing(0)
        title = QLabel(c["title"] or "Untitled clip")
        title.setStyleSheet("font-weight: 600; font-size: 12px;")
        title.setToolTip(c["title"])
        texts.addWidget(title)

        meta = QLabel(
            f"{format_duration(c['start_time'])} → {format_duration(c['end_time'])}  "
            f"({c['duration']:.0f}s)"
        )
        meta.setObjectName("CardSubtitle")
        texts.addWidget(meta)
        lay.addLayout(texts, 1)

        eng = ScoreBadge()
        eng.set_value(c["engagement_score"] or 0, "engagement")
        lay.addWidget(eng)

        vir = ScoreBadge()
        vir.set_value(c["virality_score"] or 0, "viral")
        lay.addWidget(vir)

        return w

    def _on_clip_selected(self) -> None:
        items = self.clip_list.selectedItems()
        if not items:
            return
        clip_id = items[0].data(Qt.ItemDataRole.UserRole)
        clip = self.db.get_clip(clip_id)
        if clip:
            self._show_detail(clip)

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_detail(self, clip) -> None:
        self._clear_detail()

        # --- reason ---
        reason = QLabel(f"<b>Why it was picked</b><br>{clip['reason'] or '—'}")
        reason.setWordWrap(True)
        reason.setTextFormat(Qt.TextFormat.RichText)
        self.detail_layout.addWidget(reason)

        # --- scores ---
        score_row = QHBoxLayout()
        for label, value in (
            ("Virality", clip["virality_score"]),
            ("Engagement", clip["engagement_score"]),
        ):
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setSpacing(2)
            cap = QLabel(label)
            cap.setObjectName("StatLabel")
            bl.addWidget(cap)
            val = QLabel(f"{value:.0f} / 100")
            val.setStyleSheet("font-size: 17px; font-weight: 700;")
            bl.addWidget(val)
            score_row.addWidget(box)
        score_row.addStretch(1)
        self.detail_layout.addLayout(score_row)

        # --- hook suggestions ---
        try:
            hooks = json.loads(clip["hook_suggestions"] or "[]")
        except json.JSONDecodeError:
            hooks = []
        if hooks:
            hook_title = QLabel("<b>Auto Hook Suggestions</b>")
            self.detail_layout.addWidget(hook_title)
            for h in hooks:
                lbl = QLabel(f"→ {h}")
                lbl.setWordWrap(True)
                lbl.setObjectName("CardSubtitle")
                self.detail_layout.addWidget(lbl)

        # --- titles ---
        try:
            titles = json.loads(clip["titles"] or "[]")
        except json.JSONDecodeError:
            titles = []
        if titles:
            t_title = QLabel("<b>Suggested titles</b>")
            self.detail_layout.addWidget(t_title)
            for t in titles:
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                lbl = QLabel(t)
                lbl.setWordWrap(True)
                lbl.setStyleSheet("font-size: 12px;")
                rl.addWidget(lbl, 1)
                use = QPushButton("Use")
                use.setObjectName("Ghost")
                use.clicked.connect(lambda _=False, tt=t, cid=clip["id"]: self._use_title(cid, tt))
                rl.addWidget(use)
                self.detail_layout.addWidget(row)

        # --- hashtags ---
        try:
            tags = json.loads(clip["hashtags"] or "[]")
        except json.JSONDecodeError:
            tags = []
        if tags:
            hl = QLabel("<b>Hashtags</b>  " + "  ".join(f"#{t}" for t in tags))
            hl.setWordWrap(True)
            hl.setObjectName("CardSubtitle")
            self.detail_layout.addWidget(hl)

        # --- transcript ---
        if clip["transcript_text"]:
            tr_title = QLabel("<b>Transcript excerpt</b>")
            self.detail_layout.addWidget(tr_title)
            tr = QTextEdit()
            tr.setReadOnly(True)
            tr.setPlainText(clip["transcript_text"])
            tr.setMaximumHeight(130)
            tr.setStyleSheet("font-size: 11px;")
            self.detail_layout.addWidget(tr)

        # --- actions ---
        actions = QHBoxLayout()
        render = QPushButton("Render This Clip")
        render.setObjectName("Primary")
        render.clicked.connect(lambda: self._render_clip(clip["id"]))
        actions.addWidget(render)

        edit = QPushButton("Edit in Preview Editor")
        edit.setObjectName("Ghost")
        edit.clicked.connect(
            lambda _=False, cid=clip["id"], pid=clip["project_id"]:
                self.window.open_in_editor(pid, cid)
        )
        actions.addWidget(edit)

        open_out = QPushButton("Reveal Output")
        open_out.clicked.connect(lambda: self._reveal(clip["output_path"]))
        actions.addWidget(open_out)
        actions.addStretch(1)
        self.detail_layout.addLayout(actions)

    def _use_title(self, clip_id: int, title: str) -> None:
        self.db.update_clip(clip_id, title=title)
        self.window.notify("Title updated")
        self.refresh()

    def _reveal(self, path: str) -> None:
        if not path or not Path(path).exists():
            self.window.notify("Output file not found yet")
            return
        import subprocess
        import sys

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", path])
            else:
                subprocess.Popen(["xdg-open", str(Path(path).parent)])
        except Exception as exc:
            self.window.notify(f"Could not open file: {exc}")

    # -- analysis -------------------------------------------------------------------
    def _run_analysis(self) -> None:
        if not self.project_id:
            self.window.notify("Open a project first")
            return
        self.analyze_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Preparing…")

        self._thread = QThread(self)
        self._worker = AnalysisWorker(
            self.db, self.project_id,
            self.count_spin.value(), self.duration_combo.currentData(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _on_progress(self, p: PipelineProgress) -> None:
        self.progress.setValue(int(p.percent))
        self.progress_label.setText(f"{p.stage}: {p.message}")

    # -- one-click editing -------------------------------------------------------
    def _run_one_click(self) -> None:
        """Produce finished, upload-ready clips with no manual editing."""
        if not self.project_id:
            self.window.notify("Open a project first")
            return
        out_dir = Path(self.db.get_setting("output_dir") or "./exports")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.analyze_btn.setEnabled(False)
        self.one_click_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("One-click editing starting…")

        self._thread = QThread(self)
        self._worker = OneClickWorker(
            self.db, self.project_id, str(out_dir),
            self.count_spin.value(), self.duration_combo.currentData(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_one_click_done)
        self._worker.failed.connect(self._on_one_click_failed)
        self._thread.start()

    def _on_one_click_done(self, summary: dict) -> None:
        self.analyze_btn.setEnabled(True)
        self.one_click_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self._retire_thread()
        exports = summary.get("exports", [])
        errors = summary.get("errors", [])
        out_dir = summary.get("output_dir", "")
        ok = len(exports) - len(errors)
        if ok:
            self.window.notify(
                f"One-click editing done — {ok} upload-ready clip"
                f"{'s' if ok != 1 else ''} in {out_dir}", 6000,
            )
        else:
            self.window.notify("One-click editing produced no clips", 6000)
        self.refresh()

    def _on_one_click_failed(self, message: str) -> None:
        self.analyze_btn.setEnabled(True)
        self.one_click_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self._retire_thread()
        self.window.notify(f"One-click editing failed: {message}", 8000)

    def _on_done(self, count: int) -> None:
        self.analyze_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self.window.notify(f"Generated {count} clips")
        self._retire_thread()
        self.refresh()

    def _on_failed(self, message: str) -> None:
        self.analyze_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self._retire_thread()
        self.window.notify(f"Analysis failed: {message}", 8000)

    def _cancel_analysis(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _retire_thread(self) -> None:
        """Release the finished worker thread so it is never destroyed while running."""
        thread = self._thread
        if thread is not None:
            thread.quit()
            if not thread.wait(3000):
                thread.terminate()
                thread.wait(500)
        self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        """Stop any running worker and wait for its thread to finish.

        Called when the window closes so a long render is not killed
        mid-write and the QThread is never destroyed while still running.
        """
        if self._worker is not None:
            try:
                self._worker.cancel()
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            if not thread.wait(5000):
                thread.terminate()
                thread.wait(1000)
        self._thread = None
        self._worker = None
        self.window.notify("Cancelling…")

    # -- rendering -------------------------------------------------------------------
    def _render_clip(self, clip_id: int) -> None:
        """Render a single clip using the current settings."""
        if not self.project_id:
            return
        settings = self.db.get_settings()
        rs = RenderSettings.for_aspect(settings.get("aspect_ratio", "9:16"))
        rs.caption_style = settings.get("caption_style", "bold_viral")
        rs.caption_size = int(settings.get("caption_size", 58))
        rs.encoder_preference = settings.get("use_gpu", "auto")

        out_dir = Path(settings.get("output_dir") or self.window.db.path.parent / "exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        clip = self.db.get_clip(clip_id)
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in (clip["title"] or "clip"))
        out_path = out_dir / f"{safe[:50] or 'clip'}.mp4"

        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Rendering…")

        def worker() -> None:
            try:
                analysis = self._rebuild_analysis()
                pipe = ClipOSPipeline(self.db, self.project_id)
                pipe.set_progress_callback(
                    lambda p: self.progress_label.setText(f"{p.stage}: {p.message}")
                )
                pipe.render_clip(clip_id, out_path, rs, analysis)
                self.window.notify(f"Rendered {out_path.name}")
                self.refresh()
            except Exception as exc:
                log.exception("render failed")
                self.window.notify(f"Render failed: {exc}", 7000)
            finally:
                self.progress.setVisible(False)
                self.progress_label.setVisible(False)

        threading.Thread(target=worker, daemon=True).start()

    def _rebuild_analysis(self):
        """Rebuild the analysis context for rendering (cached per project)."""
        from ...ai.audio_analysis import analyze_audio
        from ...ai.speaker_tracking import analyze_speakers
        from ...ai.transcription import Transcript
        from ...ai.visual_analysis import analyze_visual
        from ...core.config import PATHS
        from ...core.ffmpeg import extract_audio_wav
        from ...video.pipeline import AnalysisResult

        result = AnalysisResult()
        project = self.db.get_project(self.project_id)
        source = Path(project["source_path"])
        result.duration = project["duration"]

        wav = PATHS.cache / f"audio_{self.project_id}.wav"
        if project["has_audio"] and not wav.exists():
            extract_audio_wav(source, wav)
        if wav.exists():
            result.audio = analyze_audio(wav)
            result.visual = analyze_visual(source, fps_sample=1.5)
            result.speaker = analyze_speakers(result.visual, result.audio)

        tr = self.db.get_transcript(self.project_id)
        if tr:
            import json as _json

            segs = []
            for s in _json.loads(tr["segments"] or "[]"):
                from ...ai.transcription import Segment, Word

                words = [
                    Word(w["w"], w["s"], w["e"], w.get("p", 1.0))
                    for w in s.get("words", [])
                ]
                segs.append(Segment(s["start"], s["end"], s["text"], words))
            result.transcript = Transcript(
                language=tr["language"], duration=tr["duration"],
                text=tr["full_text"], segments=segs, model=tr["model"],
            )
        return result

    def _export_all(self) -> None:
        self.window.navigate("export")
