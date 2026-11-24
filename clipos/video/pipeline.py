"""The CLIPOS processing pipeline.

Orchestrates the complete workflow:

    import -> analyse (audio + visual + speech) -> detect clips -> generate metadata
           -> build captions -> render -> export

Runs on a worker thread so the UI never blocks.  Progress is reported with real
measurements taken from the underlying tools.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
from datetime import datetime
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..ai import audio_analysis, clip_detector, speaker_tracking, title_generator
from ..ai import visual_analysis
from ..ai.transcription import (
    Transcript,
    TranscriptionUnavailable,
    model_installed,
    transcribe,
)
from ..captions.caption_engine import build_cues_for_clip, get_style, list_styles
from ..core.config import ASPECT_RATIOS, CLIP_DURATION_PRESETS, PATHS
from ..core.ffmpeg import extract_audio_wav, probe
from ..core.logging_setup import get_logger
from ..db.database import Database
from ..video.renderer import ClipRenderer, RenderSettings, generate_thumbnails

log = get_logger(__name__)


@dataclass
class PipelineProgress:
    stage: str = ""
    percent: float = 0.0
    message: str = ""
    detail: str = ""


@dataclass
class AnalysisResult:
    """Everything the pipeline learned about one source video."""
    duration: float = 0.0
    audio: Optional[audio_analysis.AudioAnalysis] = None
    visual: Optional[visual_analysis.VisualAnalysis] = None
    speaker: Optional[speaker_tracking.SpeakerTrack] = None
    transcript: Optional[Transcript] = None
    transcription_available: bool = True
    transcription_error: str = ""
    clips: list = field(default_factory=list)
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "transcription_available": self.transcription_available,
            "transcription_error": self.transcription_error,
            "clips": len(self.clips),
            "elapsed": round(self.elapsed, 2),
        }


class PipelineCancelled(RuntimeError):
    pass


class ClipOSPipeline:
    """Runs analysis + clip generation + rendering for a project."""

    def __init__(self, db: Database, project_id: int) -> None:
        self.db = db
        self.project_id = project_id
        self._cancel = threading.Event()
        self.external_cancel = None
        self._progress: Optional[Callable[[PipelineProgress], None]] = None

    # -- control ---------------------------------------------------------------
    def set_progress_callback(self, cb: Callable[[PipelineProgress], None]) -> None:
        self._progress = cb

    def cancel(self) -> None:
        self._cancel.set()

    def _cancel_requested(self) -> bool:
        return self._cancel.is_set() or bool(self.external_cancel and self.external_cancel())

    def _check_cancel(self) -> None:
        if self._cancel_requested():
            self._cancel.set()
            raise PipelineCancelled("Processing cancelled")

    def _report(self, stage: str, pct: float, message: str = "") -> None:
        self._check_cancel()
        if self._progress:
            self._progress(PipelineProgress(stage=stage, percent=pct, message=message))

    # -- analysis ---------------------------------------------------------------
    def analyse(
        self,
        source: str | Path,
        stt_model: str = "base",
        language: str = "",
        sample_rate: float = 2.0,
    ) -> AnalysisResult:
        """Run the full analysis pass over a source video."""
        t0 = time.time()
        source = Path(source)
        result = AnalysisResult()

        self._report("probe", 2.0, "Reading media information")
        info = probe(source)
        result.duration = info.duration
        self._check_cancel()

        # -- audio --------------------------------------------------------------
        self._report("audio", 8.0, "Extracting and analysing audio")
        wav_path = PATHS.cache / f"audio_{self.project_id}.wav"
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        if info.has_audio:
            ok = extract_audio_wav(source, wav_path)
            if ok:
                result.audio = audio_analysis.analyze_audio(
                    wav_path,
                    silence_threshold_db=float(self.db.get_setting("silence_threshold_db",-32.)),
                    min_silence_duration=float(self.db.get_setting("min_silence_duration",.35)),
                )
        else:
            self._report("audio", 12.0, "No audio track — visual analysis only")
        self._check_cancel()

        # -- visual ------------------------------------------------------------
        self._report("visual", 18.0, "Analysing scenes and subjects")
        result.visual = visual_analysis.analyze_visual(
            source, fps_sample=sample_rate,
            progress_cb=lambda p, m: self._report("visual", 18.0 + p * 0.27, m),
        )
        self._check_cancel()

        # -- speech ------------------------------------------------------------
        self._report("speech", 48.0, "Transcribing speech (offline)")
        if info.has_audio and wav_path.exists():
            # Only try to transcribe when the model is actually on disk.
            # Asking Whisper to load a model it has to fetch would block the
            # whole analysis on a network download, and the app's contract is
            # that models come from the model manager, not the pipeline.
            if not model_installed(stt_model):
                result.transcription_available = False
                result.transcription_error = (
                    f"The speech-to-text model '{stt_model}' is not installed. "
                    "Open AI Models to download it."
                )
                self._report("speech", 78.0,
                             f"Speech model '{stt_model}' is not installed")
            else:
                try:
                    result.transcript = transcribe(
                        wav_path, model_size=stt_model, language=language or None,
                        device="cpu" if self.db.get_setting("use_gpu", "auto")=="cpu" else "auto",
                        threads=int(self.db.get_setting("processing_threads",0)),
                        progress_cb=lambda p, m: self._report(
                            "speech", 48.0 + p * 0.30, m),
                    )
                    result.transcription_available = True
                except TranscriptionUnavailable as exc:
                    result.transcription_available = False
                    result.transcription_error = str(exc)
                    self._report("speech", 78.0, f"Speech model unavailable: {exc}")
                except Exception as exc:
                    result.transcription_available = False
                    result.transcription_error = str(exc)
                    log.warning("transcription failed: %s", exc)
                    self._report("speech", 78.0, f"Transcription failed: {exc}")
        else:
            result.transcription_available = False
            result.transcription_error = "No audio track in source video"
        self._check_cancel()

        # -- speaker tracking ---------------------------------------------------
        self._report("speakers", 80.0, "Identifying the active speaker")
        if result.visual:
            result.speaker = speaker_tracking.analyze_speakers(
                result.visual, result.audio or audio_analysis.AudioAnalysis()
            )
        self._check_cancel()

        # -- clip detection -----------------------------------------------------
        self._report("clips", 84.0, "Scoring moments for engagement")
        result.elapsed = time.time() - t0
        return result

    def detect_clips(
        self,
        analysis: AnalysisResult,
        min_duration: float = 30.0,
        max_duration: float = 45.0,
        target_count: int = 10,
        selected_ranges=None,
    ) -> list:
        """Run clip detection over an analysis result."""
        self._report("clips", 86.0, "Scoring candidate moments")
        clips = clip_detector.detect_clips(
            duration=analysis.duration,
            selected_ranges=selected_ranges,
            audio=analysis.audio or audio_analysis.AudioAnalysis(),
            visual=analysis.visual or visual_analysis.VisualAnalysis(),
            transcript=analysis.transcript,
            speaker=analysis.speaker,
            min_duration=min_duration,
            max_duration=max_duration,
            target_count=target_count,
            progress_cb=lambda p, m: self._report("clips", 86.0 + p * 0.12, m),
        )
        analysis.clips = clips
        return clips

    # -- persistence ------------------------------------------------------------
    def save_clips(self, clips: list, aspect: str = "9:16") -> list[int]:
        """Persist detected clips, replacing any previous ones for this project."""
        self.db.execute("DELETE FROM clips WHERE project_id=?", (self.project_id,))
        ids: list[int] = []
        for c in clips:
            meta = title_generator.generate_metadata(
                text=c.transcript_text,
                keywords=c.keywords,
                title_hint=c.title,
                use_llm=str(self.db.get_setting("use_llm", "0")).lower() in ('1','true','on'),
                llm_model=self.db.get_setting("llm_model", "llama3.1:8b"),
                ollama_host=self.db.get_setting("ollama_host", "http://127.0.0.1:11434"),
            )
            clip_id = self.db.create_clip(
                project_id=self.project_id,
                title=c.title or (meta.titles[0] if meta.titles else "Untitled clip"),
                description=meta.description or c.description,
                start_time=c.start,
                end_time=c.end,
                duration=c.duration,
                engagement_score=c.engagement_score,
                virality_score=c.virality_score,
                reason=" · ".join(c.reasons[:4]),
                transcript_text=c.transcript_text,
                hook_suggestions=json.dumps(c.hook_suggestions),
                keywords=json.dumps(meta.keywords or c.keywords),
                hashtags=json.dumps(meta.hashtags),
                titles=json.dumps(meta.titles),
                aspect_ratio=aspect,
                caption_style=self.db.get_setting("caption_style", "bold_viral"),
            )
            ids.append(clip_id)
        self.db.log_activity(self.project_id, "clips", f"Generated {len(ids)} clips")
        return ids

    def save_transcript(self, analysis: AnalysisResult) -> None:
        tr = analysis.transcript
        if not tr:
            return
        self.db.save_transcript(
            self.project_id, tr.language, tr.model, tr.duration,
            tr.text, tr.segments_as_dicts(),
        )

    # -- rendering ---------------------------------------------------------------
    def render_clip(
        self,
        clip_id: int,
        output: str | Path,
        settings: RenderSettings,
        analysis: AnalysisResult,
        make_thumbnails: bool = True,
        progress_cb: Optional[Callable[[float, str], None]] = None,
    ) -> dict:
        """Render one clip to a finished video."""
        clip = self.db.get_clip(clip_id)
        if clip is None:
            raise ValueError(f"Clip {clip_id} not found")
        project = self.db.get_project(self.project_id)
        source = Path(project["source_path"])
        if not source.exists():
            raise FileNotFoundError(f"Source video missing: {source}")

        self._report("render", 5.0, "Preparing clip")

        # Build captions for the clip
        cues = []
        if settings.show_captions:
            cues = build_cues_for_clip(
                analysis.transcript, clip["transcript_text"],
                clip["start_time"], clip["end_time"],
                words_per_cue=3 if settings.caption_style == "clean_professional" else 6,
            )
        self._check_cancel()

        work_dir = PATHS.projects / str(self.project_id) / "work"
        renderer = ClipRenderer(work_dir)

        def prog(pct: float, msg: str) -> None:
            self._report("render", 5.0 + pct * 0.85, msg)
            if progress_cb:
                progress_cb(pct, msg)

        saved_edit = PATHS.projects / str(self.project_id) / "edits" / f"{clip_id}.json"
        from .timeline import Timeline
        if saved_edit.exists() or Timeline.backup_path(saved_edit).exists():
            timeline = Timeline.load(saved_edit)
            if timeline.recovered_from:
                self._report("render", 5., "Recovered previous timeline backup; latest edits may be missing")
            from ..captions.caption_engine import retime_cues, build_cues
            edited_cues = retime_cues(build_cues(analysis.transcript, 0, analysis.duration),
                [(seg.start, seg.end, seg.speed) for seg in timeline.segments]) if settings.show_captions and analysis.transcript else []
            result = renderer.render_timeline(
                source, output, timeline, settings, cues=edited_cues,
                progress_cb=prog, cancel_cb=self._cancel_requested,
            )
        else:
            result = renderer.render(
                source, output,
                clip["start_time"], clip["end_time"],
                settings, cues=cues,
                audio=analysis.audio, visual=analysis.visual, speaker=analysis.speaker,
                progress_cb=prog, cancel_cb=self._cancel_requested,
            )
        self._check_cancel()
        if result.cancelled:
            raise PipelineCancelled("Render cancelled")
        if not Path(output).is_file() or Path(output).stat().st_size == 0:
            raise RuntimeError("Renderer produced no playable output")

        # Thumbnails from the best frames in the clip
        thumb_paths: list[str] = []
        if make_thumbnails:
            self._report("render", 92.0, "Generating thumbnails")
            times = [
                result.duration * f for f in (0.3,)
            ]
            # One folder per clip so the files never overwrite each other
            # and every clip keeps its own set of thumbnail candidates.
            thumb_dir = (PATHS.projects / str(self.project_id)
                         / "thumbnails" / f"clip_{clip_id:03d}")
            try:
                titles = json.loads(clip["titles"] or "[]")
                text = titles[0] if titles else ""
                thumb_paths = generate_thumbnails(
                    output, thumb_dir, times,
                    settings.width, settings.height, text="",
                )
            except Exception as exc:
                log.warning("thumbnail generation failed: %s", exc)

        self.db.update_clip(
            clip_id,
            output_path=str(output),
            status="rendered",
            thumbnail_path=thumb_paths[0] if thumb_paths else "",
            settings=json.dumps(settings.to_dict()),
        )
        self.db.log_activity(
            self.project_id, "render",
            f"Rendered clip #{clip_id} -> {Path(output).name}", level="success",
        )
        self._report("render", 100.0, "Clip ready")
        return {
            "output_path": str(output),
            "duration": result.duration,
            "width": result.width,
            "height": result.height,
            "size_bytes": result.size_bytes,
            "thumbnails": thumb_paths,
            "encoder": result.encoder,
            "steps": result.steps,
            "warnings": result.warnings,
        }

    # -- batch export -----------------------------------------------------------
    def export_clips(
        self,
        clip_ids: list[int],
        out_dir: str | Path,
        settings: RenderSettings,
        analysis: AnalysisResult,
        progress_cb: Optional[Callable[[int, int, str, float], None]] = None,
        cancel_cb: Optional[Callable[[], bool]] = None,
    ) -> list[dict]:
        """Render and export several clips, recording every result in the database.

        ``progress_cb`` receives ``(index, total, message, percent)``.  Returns a
        list of result dicts — one per clip, in the order the clips were given.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        project = self.db.get_project(self.project_id)
        batch = out_dir / datetime.now().strftime("%Y-%m-%d") / _safe_folder(project["name"] or Path(project["source_path"]).stem)
        batch.mkdir(parents=True, exist_ok=True)
        manifest_path = batch / "export-results.json"
        total = len(clip_ids)
        previous_cancel = self.external_cancel
        self.external_cancel = cancel_cb or previous_cancel
        results: list[dict] = []

        for index, clip_id in enumerate(clip_ids):
            if cancel_cb and cancel_cb():
                break
            clip = self.db.get_clip(clip_id)
            if clip is None:
                results.append({"clip_id": clip_id, "error": "clip not found"})
                continue

            target = batch / f"clip_{clip_id:03d}_{_safe_folder(clip['title'])}.mp4"
            target.parent.mkdir(parents=True, exist_ok=True)

            def cb(pct: float, msg: str, idx: int = index) -> None:
                if progress_cb:
                    progress_cb(idx, total, msg, pct)

            try:
                info = self.render_clip(
                    clip_id, target, deepcopy(settings), analysis,
                    make_thumbnails=True, progress_cb=cb,
                )
                size = int(info.get("size_bytes", 0))
                thumbs = info.get("thumbnails") or []
                self.db.update_clip(
                    clip_id, status="exported", output_path=str(target),
                    thumbnail_path=thumbs[0] if thumbs else "",
                )
                export_id = self.db.create_export(
                    project_id=self.project_id, clip_id=clip_id,
                    output_path=str(target), status="done", size_bytes=size,
                    duration=float(info.get("duration", 0.0)),
                    width=int(info.get("width", settings.width)),
                    height=int(info.get("height", settings.height)),
                    fps=int(settings.fps), codec=settings.codec,
                    bitrate=int(settings.bitrate_kbps),
                )
                info.update({"clip_id": clip_id, "output_path": str(target), "export_id": export_id, "error": ""})
                results.append(info)
            except PipelineCancelled:
                self.db.update_clip(clip_id, status="cancelled")
                break
            except Exception as exc:
                self.db.update_clip(clip_id, status="error")
                log.exception("export failed for clip %s", clip_id)
                self.db.create_export(
                    project_id=self.project_id, clip_id=clip_id,
                    output_path=str(target), status="failed", size_bytes=0,
                    duration=0.0, error=str(exc),
                )
                results.append({
                    "clip_id": clip_id, "output_path": str(target),
                    "size_bytes": 0, "error": str(exc),
                })
            manifest_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        self.external_cancel = previous_cancel
        return results


def _safe_folder(title: str) -> str:
    """Turn a clip title into a filesystem-safe folder name."""
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in (title or "clip"))
    safe = safe.strip()[:64].rstrip(" .") or "video"
    if safe.upper().split('.')[0] in {"CON", "PRN", "AUX", "NUL", *[f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1,10)]}:
        safe = "_" + safe
    return safe


# --------------------------------------------------------------------------------------
# Convenience: the full one-click run
# --------------------------------------------------------------------------------------


def run_full_analysis(
    db: Database,
    project_id: int,
    clip_count: int = 10,
    duration_range: str = "30-45",
    aspect: str = "9:16",
    stt_model: str = "base",
    language: str = "",
    progress_cb: Callable[[PipelineProgress], None] | None = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    selected_ranges=None,
) -> AnalysisResult:
    """Analyse a project and generate + persist clips in one call."""
    pipe = ClipOSPipeline(db, project_id)
    pipe.external_cancel = cancel_cb
    if progress_cb:
        pipe.set_progress_callback(progress_cb)

    project = db.get_project(project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")
    source = project["source_path"]
    if not source or not Path(source).exists():
        raise FileNotFoundError(f"Source video missing for project {project_id}")

    db.update_project(project_id, status="analyzing")

    try:
        analysis = pipe.analyse(source, stt_model=stt_model, language=language)
        pipe.save_transcript(analysis)

        lo, hi = CLIP_DURATION_PRESETS.get(duration_range, (30, 45))
        clips = pipe.detect_clips(
            analysis, min_duration=lo, max_duration=hi, target_count=clip_count, selected_ranges=selected_ranges,
        )
        pipe.save_clips(clips, aspect=aspect)
        db.update_project(project_id, status="ready")
        db.log_activity(project_id, "analysis",
                        f"Analysis complete — {len(clips)} clips generated", level="success")
        return analysis
    except Exception as exc:
        db.update_project(project_id, status="error")
        db.log_error("analysis", str(exc), traceback.format_exc())
        db.log_activity(project_id, "error", f"Analysis failed: {exc}", level="error")
        raise


def run_one_click(
    db: Database,
    project_id: int,
    out_dir: str | Path,
    clip_count: int = 10,
    duration_range: str = "30-45",
    aspect: str = "9:16",
    stt_model: str = "base",
    language: str = "",
    progress_cb: Callable[[PipelineProgress], None] | None = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    recipe: str | None = None,
    gaming_enhance: bool = False,
) -> dict:
    """One-click editing: analyse, cut, caption, reframe and export finished clips.

    This is the full "AI produces a ready-to-upload video without manual
    editing" path.  It runs the whole chain unattended and returns a summary
    with everything the caller needs to show the result:

    ``{"analysis": AnalysisResult, "clips": [...], "exports": [...], "errors": [...]}``
    """
    pipe = ClipOSPipeline(db, project_id)
    pipe.external_cancel = cancel_cb
    if progress_cb:
        pipe.set_progress_callback(progress_cb)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    analysis = run_full_analysis(
        db, project_id,
        clip_count=clip_count, duration_range=duration_range, aspect=aspect,
        stt_model=stt_model, language=language, progress_cb=progress_cb, cancel_cb=cancel_cb,
    )

    from ..core.editing import render_settings
    overrides = {"aspect_ratio":aspect}
    if recipe: overrides["editing_preset"] = recipe
    if gaming_enhance: overrides["gaming_enhance"] = True
    settings = render_settings(db, overrides)

    clip_rows = db.list_clips(project_id)
    if not clip_rows:
        return {"analysis": analysis, "clips": [], "exports": [], "errors": []}

    def on_progress(index: int, total: int, message: str, pct: float) -> None:
        # Map the per-clip progress onto the overall pipeline progress.
        overall = 30.0 + ((index + pct / 100.0) / max(1, total)) * 65.0
        if progress_cb:
            progress_cb(PipelineProgress(stage="export", percent=overall, message=message))

    exports = pipe.export_clips(
        [c["id"] for c in clip_rows], out_dir, settings, analysis,
        progress_cb=on_progress, cancel_cb=cancel_cb,
    )

    errors = [e for e in exports if e.get("error")]
    db.update_project(project_id, status="ready")
    db.log_activity(
        project_id, "export",
        f"One-click editing finished — {len(exports) - len(errors)} of {len(exports)} "
        f"clips exported",
        level="success" if not errors else "warning",
    )
    return {
        "analysis": analysis,
        "clips": clip_rows,
        "exports": exports,
        "errors": errors,
        "output_dir": str(out_dir),
    }
