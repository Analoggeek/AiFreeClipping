"""Application-wide configuration and paths for CLIPOS."""
from __future__ import annotations

import os
import platform
from pathlib import Path


def _default_data_dir() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "CLIPOS"
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "CLIPOS"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "clipos"


class AppPaths:
    """Central registry of on-disk locations. Everything CLIPOS writes lives here."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else _default_data_dir()
        self.projects = self.root / "projects"
        self.media = self.root / "media"
        self.cache = self.root / "cache"
        self.models = self.root / "models"
        self.exports = self.root / "exports"
        self.tmp = self.root / "tmp"
        self.logs = self.root / "logs"
        self.db_path = self.root / "clipos.db"
        self.fonts = self.root / "fonts"
        self.sounds = self.root / "sounds"
        self.music = self.root / "music"

    def ensure(self) -> None:
        for p in (
            self.root,
            self.projects,
            self.media,
            self.cache,
            self.models,
            self.exports,
            self.tmp,
            self.logs,
            self.fonts,
            self.sounds,
            self.music,
        ):
            p.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AppPaths root={self.root}>"


PATHS = AppPaths()

# --------------------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------------------

DEFAULT_SETTINGS: dict = {
    "theme": "dark",
    "editing_preset": "gaming",
    "gaming_enhance": False,
    "language": "en",
    "output_dir": str(PATHS.exports),
    "default_aspect": "9:16",
    "default_clip_duration": "30-45",
    "default_clip_count": 10,
    "caption_style": "clean_professional",
    "caption_font": "DejaVu Sans",
    "caption_size": 48,
    "caption_position": "bottom",
    "caption_stroke": 4,
    "caption_shadow": True,
    "caption_background": False,
    "stt_model": "base",
    "stt_language": "",
    "use_gpu": "auto",
    "processing_threads": 0,  # 0 => auto
    "low_memory_mode": False,
    "offline_mode": True,
    "auto_download_models": False,
    "learn_selection_preferences": False,
    "automatic_selection": True,
    "selection_local_rerank": False,
    "selection_visual_review": False,
    "selection_ocr_review": False,
    "selection_vision_model": "",
    "selection_include": "",
    "selection_exclude": "",
    "selection_direction": "",
    "selection_compile_intent": False,
    "llm_model": "llama3.1:8b",
    "ollama_host": "http://127.0.0.1:11434",
    "bgm_volume": 0.12,
    "background_music": "",
    "bgm_ducking": True,
    "person_model_path": "",
    "speaker_caption_colors": True,
    "diarization_segmentation": "",
    "diarization_embedding": "",
    "body_reframe": True,
    "shot_aware_reframe": True,
    "body_track_id": 0,
    "sfx_enabled": True,
    "silence_threshold_db": -32.0,
    "min_silence_duration": 0.35,
    "auto_caption": True,
    "auto_title": True,
    "auto_thumbnail": True,
    "one_click_editing": True,
    "virality_threshold": 45,
    "restore_on_launch": True,
    "minimize_to_tray": False,
    "check_updates": False,
    "telemetry": False,
}

ASPECT_RATIOS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
    "4:5": (1080, 1350),
}

CLIP_DURATION_PRESETS = {
    "15-30": (15, 30),
    "30-45": (30, 45),
    "45-60": (45, 60),
    "60-90": (60, 90),
    "custom": (20, 60),
}

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv"}

CAPTION_STYLES = [
    "mrbeast",
    "minimal_white",
    "neon_gaming",
    "modern_podcast",
    "bold_viral",
    "cinematic",
    "karaoke",
    "clean_professional",
]
