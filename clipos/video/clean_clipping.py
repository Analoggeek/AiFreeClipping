"""Small orchestration layer over the existing analysed-moments/FFmpeg pipeline.

Framing and moment selection are independent. Retired experimental settings in an
upgraded database do not silently activate extra models or editing effects here.
"""

from dataclasses import replace
from pathlib import Path

from .crop_config import save_crop, display_dimensions
from .pipeline import ClipOSPipeline, PipelineCancelled
from ..core.ffmpeg import probe


class ClippingDatabase:
    """Per-operation settings view; preserves the actual user's saved database."""

    overrides = {
        "automatic_selection": True,
        "selection_local_rerank": False,
        "selection_compile_intent": False,
        "selection_visual_review": False,
        "selection_ocr_review": False,
        "selection_sound_review": False,
        "talknet_enabled": False,
        "diarization_segmentation": "",
        "diarization_embedding": "",
        "selection_include": "",
        "selection_exclude": "",
        "selection_direction": "",
        "learn_selection_preferences": False,
        "use_llm": False,
        "person_model_path": "",
        "speaker_caption_colors": False,
    }

    def __init__(self, db, speech, tracking):
        self.db = db
        self.values = dict(self.overrides)
        if not speech:
            self.values["stt_model"] = "__explicitly_disabled__"
        if tracking:
            path = db.get_setting("person_model_path", "")
            if not path or not Path(path).is_file():
                raise ValueError(
                    "YOLOX tracking is enabled but verified weights are unavailable; open AI Models"
                )
            self.values["person_model_path"] = path

    def get_setting(self, key, default=None):
        return self.values.get(key, self.db.get_setting(key, default))

    def get_settings(self):
        return {**self.db.get_settings(), **self.values}

    def __getattr__(self, key):
        return getattr(self.db, key)


def generate_clips(
    db,
    project_id,
    crop,
    output,
    *,
    count=5,
    duration="15-30",
    speech=False,
    tracking=False,
    rerank=False,
    progress=None,
    cancelled=None,
    settings=None,
):
    from ..ai.transcription import model_installed
    from ..core.config import CLIP_DURATION_PRESETS
    from ..ai.automatic_selection import local_order
    from ..core.local_ai import LocalOllama

    if type(count) is not int or not 1 <= count <= 30:
        raise ValueError("Choose 1–30 clips")
    if duration not in CLIP_DURATION_PRESETS:
        raise ValueError("Unsupported duration range")
    project = db.get_project(project_id)
    if project is None:
        raise ValueError("Project missing")
    dimensions = display_dimensions(probe(project["source_path"]).video)
    crop.filter(*dimensions)
    save_crop(db, project_id, crop)
    stt = db.get_setting("stt_model", "base") if speech else "__explicitly_disabled__"
    if speech and not db.get_setting("stt_enabled", True):
        raise ValueError("Speech model is disabled; enable it in AI Models")
    if rerank and not db.get_setting("ollama_model_enabled", True):
        raise ValueError("Local language model is disabled; enable it in AI Models")
    if speech and not model_installed(stt):
        raise ValueError(
            "Speech analysis selected, but the model is not installed. Open AI Models; no silent visual-only fallback."
        )
    if rerank:
        LocalOllama(
            db.get_setting("ollama_host", "http://127.0.0.1:11434")
        ).require_local_model(db.get_setting("llm_model", "gemma:7b"))
    if tracking:
        from ..ai.model_manager import ModelManager
        from ..core.config import PATHS

        expected = PATHS.models / "yolox" / "yolox_nano.onnx"
        if (
            Path(db.get_setting("person_model_path", "")).resolve()
            != expected.resolve()
        ):
            raise ValueError(
                "Tracking weights are not the managed verified model; enable tracking again in AI Models"
            )
        ModelManager(db).verify_yolox(expected)
    view = ClippingDatabase(db, speech, tracking)
    pipe = ClipOSPipeline(view, project_id)
    pipe.external_cancel = cancelled
    pipe.set_progress_callback(
        lambda state: (
            progress(state.percent * 0.55, state.message) if progress else None
        )
    )
    db.update_project(project_id, status="analyzing")
    try:
        analysis = pipe.analyse(
            project["source_path"], stt_model=stt, speech_enabled=speech
        )
        if speech and not analysis.transcription_available:
            raise RuntimeError(
                analysis.transcription_error
                + "; generation stopped rather than silently downgrading analysis"
            )
        pipe.save_transcript(analysis)
        lo, hi = CLIP_DURATION_PRESETS[duration]
        candidates = pipe.detect_clips(
            analysis,
            min_duration=lo,
            max_duration=hi,
            target_count=min(30, count * 3) if rerank else count,
        )
        if rerank and candidates:
            rows = [
                {
                    "id": str(i),
                    "text": c.transcript_text,
                    "measured_score": c.engagement_score,
                }
                for i, c in enumerate(candidates[:24])
            ]
            order = local_order(
                rows,
                "Prefer coherent self-contained excerpts",
                db.get_setting("ollama_host", "http://127.0.0.1:11434"),
                db.get_setting("llm_model", "gemma:7b"),
            )
            candidates = [candidates[int(key)] for key in order]
        ids = pipe.save_clips(
            candidates[:count], aspect=crop.aspect_ratio, replace_existing=False
        )
        if settings is None:
            from .renderer import RenderSettings

            settings = RenderSettings(
                show_captions=False,
                encoder_preference=db.get_setting("use_gpu", "auto"),
            )
        settings = replace(
            settings,
            crop_config=crop.to_dict(),
            width=crop.output_width,
            height=crop.output_height,
            aspect=crop.aspect_ratio,
        )

        def rendering(index, total, message, pct):
            if progress:
                progress(55 + 45 * (index + pct / 100) / max(1, total), message)

        pipe.set_progress_callback(lambda state: None)
        results = pipe.export_clips(
            ids, output, settings, analysis, progress_cb=rendering, cancel_cb=cancelled
        )
        if cancelled and cancelled():
            raise PipelineCancelled(
                "Clipping cancelled; completed outputs were preserved"
            )
        db.update_project(
            project_id,
            status="error" if any(row.get("error") for row in results) else "ready",
        )
        return results
    except Exception:
        db.update_project(project_id, status="error")
        raise
