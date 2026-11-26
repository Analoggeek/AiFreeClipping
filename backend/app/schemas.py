"""Pydantic request/response models shared by the whole API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DownloadRequest(BaseModel):
    url: str
    mode: Literal["auto", "single", "playlist"] = "auto"
    quality: Literal["max", "1080p", "720p", "audio"] = "max"
    folder: str | None = None
    playlist_items: str | None = None
    subtitles: bool = False
    cookies_file: str | None = None


class ImportRequest(BaseModel):
    paths: list[str]


class MediaInfo(BaseModel):
    id: str
    title: str
    path: str
    source_url: str | None = None
    duration: float = 0
    width: int = 0
    height: int = 0
    thumbnail: str | None = None
    playlist_id: str | None = None
    created_at: str = ""


class TranscribeRequest(BaseModel):
    media_id: str
    model: str | None = None
    language: str | None = None
    word_timestamps: bool = True


class VisionRequest(BaseModel):
    media_id: str
    region: dict[str, float] | None = None  # normalized x, y, w, h
    fps: float = 2.0
    engine: Literal["auto", "yolox", "ultralytics", "motion"] = "auto"


class RegionSelection(BaseModel):
    media_id: str
    kind: Literal["full", "player", "gameplay", "custom"] = "full"
    box: dict[str, float] | None = None  # normalized x, y, w, h
    boxes: list[dict[str, float]] = Field(default_factory=list)
    layout: str | None = None


class ClipProposalRequest(BaseModel):
    media_ids: list[str]
    regions: list[RegionSelection] = Field(default_factory=list)
    count: int = 5
    min_duration: float = 15
    max_duration: float = 60
    platform: Literal["shorts", "reels", "tiktok", "landscape"] = "shorts"
    style: Literal["hype", "story", "clean", "cinematic"] = "hype"
    captions: bool = True
    sound_effects: bool = True
    stickers: bool = True
    music: str | None = None
    use_llm: bool = True
    llm_model: str | None = None


class CaptionStyle(BaseModel):
    preset: Literal["hype", "karaoke", "minimal", "premium", "none"] = "hype"
    font_size: int = 62
    primary_color: str = "&H00FFFFFF"
    outline_color: str = "&H00000000"
    position: Literal["bottom", "center", "top"] = "bottom"


class RenderRequest(BaseModel):
    clip_id: str | None = None
    output: str | None = None
    aspect: Literal["9:16", "1:1", "16:9", "source"] = "9:16"
    resolution: Literal["720p", "1080p", "source"] = "1080p"
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    captions: list[dict[str, Any]] | None = None
    sticker: str | None = None
    sticker_position: dict[str, float] = Field(default_factory=lambda: {"x": 0.72, "y": 0.16, "scale": 0.22})
    music: str | None = None
    music_volume: float = 0.22
    sfx: list[str] = Field(default_factory=list)
    sfx_volume: float = 0.5
    speed: float = 1.0
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 1.0
    blur_background: bool = True
    watermark: bool = True
    hardware: bool = False


class ProjectCreate(BaseModel):
    name: str = "Untitled project"
    media_id: str | None = None
    clip_id: str | None = None
    template: dict[str, Any] | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    timeline: dict[str, Any] | None = None


class ExportRequest(BaseModel):
    project_id: str | None = None
    output: str | None = None
    aspect: str = "9:16"
    resolution: str = "1080p"
    hardware: bool = False


class ExportAllRequest(BaseModel):
    clip_ids: list[str]
    aspect: str = "9:16"
    resolution: str = "1080p"


class ApplyEffectsRequest(BaseModel):
    clip_ids: list[str]
    effects: dict[str, Any]


class ImageRequest(BaseModel):
    prompt: str
    provider: Literal["auto", "nano-banana", "comfyui"] = "auto"
    aspect: str = "9:16"
    reference_path: str | None = None
    negative_prompt: str = "text, watermark, logo, blurry, low quality"


class AssetSearchRequest(BaseModel):
    query: str
    source: Literal["pexels", "pixabay", "openverse"] = "pexels"
    kind: Literal["image", "video", "audio"] = "image"
    per_page: int = 12


class AssetDownloadRequest(BaseModel):
    url: str
    name: str | None = None
    source: str = ""


class ModelInstallRequest(BaseModel):
    model_id: str


class YouTubeUploadRequest(BaseModel):
    clip_id: str
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    privacy: Literal["private", "unlisted", "public"] = "private"
    publish_at: str | None = None
    made_for_kids: bool = False


class SettingsPatch(BaseModel):
    values: dict[str, str]
