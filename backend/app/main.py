"""AI Clipper Pro local API server (binds to 127.0.0.1 only)."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from . import __version__
from .config import (
    ASSETS, CLIPS, CACHE, DOWNLOADS, EXPORTS, SECRET_PATH, capabilities, ffmpeg_binary,
    hardware_info,
)
from .db import db, dumps, now, uid
from .jobs import jobs
from .schemas import (
    ApplyEffectsRequest, AssetDownloadRequest, AssetSearchRequest, AutoEditRequest, ClipProposalRequest,
    ComfyCheckpointRequest, DeleteClipsRequest, DownloadRequest, ExportAllRequest, ExportRequest,
    FolderPatch, ImageRequest, ImportRequest, ModelInstallRequest, ProjectCreate, ProjectUpdate,
    RegionSelection, RenderRequest, SettingsPatch,
    TranscribeRequest, VisionRequest, YouTubeUploadRequest,
)
from .services import assets, downloader, images, llm, models, render, scoring, sfx, vision, youtube
from .services.asr import transcribe
from .services.tts import synthesize
from .services.utils import file_stream, probe, thumbnail

app = FastAPI(title="AI Clipper Pro API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_TOKEN = os.getenv("AIFREECLIP_TOKEN") or secrets.token_urlsafe(24)
if not os.getenv("AIFREECLIP_TOKEN"):
    SECRET_PATH.write_text(API_TOKEN, encoding="utf-8")


@app.middleware("http")
async def token_guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") or path.startswith("/media/"):
        supplied = request.headers.get("x-ai-clipper-token") or request.query_params.get("token")
        if supplied != API_TOKEN:
            return JSONResponse({"detail": "Invalid local API token"}, status_code=401)
    return await call_next(request)


def ok(**kwargs) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def media_row(media_id: str) -> dict[str, Any]:
    row = db.loads(db.one("SELECT * FROM media WHERE id=?", (media_id,)), "metadata")
    if not row:
        raise ValueError(f"Media {media_id} not found")
    return row


def project_row(project_id: str) -> dict[str, Any] | None:
    """Return a project document with timeline at the top level (not nested under `data`)."""
    row = db.one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not row:
        return None
    try:
        document = json.loads(row.get("data") or "{}")
    except json.JSONDecodeError:
        document = {}
    document.update(
        {
            "id": row["id"],
            "name": row["name"],
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
    )
    return document


def last_analysis(media_id: str, kind: str) -> dict[str, Any]:
    row = db.one(
        "SELECT data FROM analyses WHERE media_id=? AND kind=? ORDER BY created_at DESC LIMIT 1",
        (media_id, kind),
    )
    return json.loads(row["data"]) if row and row.get("data") else {}


def save_analysis(media_id: str, kind: str, data: dict[str, Any]) -> None:
    db.insert(
        "analyses",
        {"id": uid("an_"), "media_id": media_id, "kind": kind, "data": dumps(data), "created_at": now()},
    )


def configured_watermark_path() -> str | None:
    """Return the optional user-selected channel logo; never inject app branding."""
    configured = db.get_setting("watermark_path", "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or not path.is_file():
        return None
    try:
        return str(path.resolve())
    except (OSError, RuntimeError):
        return None


# --- health / system -----------------------------------------------------
@app.get("/api/health")
def health():
    return ok(
        version=os.getenv("AIFREECLIP_VERSION") or __version__,
        token_file=str(SECRET_PATH), home=str(SECRET_PATH.parent),
    )


@app.get("/api/system/capabilities")
def system_capabilities():
    return ok(**capabilities())


@app.get("/api/system/hardware")
def system_hardware():
    return ok(**hardware_info())


@app.get("/api/jobs")
def list_jobs(limit: int | None = None):
    bounded_limit = max(1, min(limit, 10000)) if limit is not None else None
    return {"jobs": jobs.list(bounded_limit)}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"detail": "Job not found"}, status_code=404)
    return job


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    if not jobs.get(job_id):
        return JSONResponse({"detail": "Job not found"}, status_code=404)
    if not jobs.cancel(job_id):
        return JSONResponse({"detail": "This operation is already finished."}, status_code=409)
    return ok(cancelled=True)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    from fastapi.responses import StreamingResponse

    return StreamingResponse(jobs.stream(job_id), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# --- downloading / library ----------------------------------------------
@app.post("/api/downloads/inspect")
def inspect_download(payload: DownloadRequest):
    return ok(info=downloader.inspect(payload.url, playlist=payload.mode == "playlist"))


@app.post("/api/downloads")
async def start_download(payload: DownloadRequest):
    job_id = jobs.run("download", lambda jid, p: downloader.download(DownloadRequest(**(p or {})), jid), payload.model_dump())
    return ok(job_id=job_id)


@app.post("/api/media/import")
def import_media(payload: ImportRequest):
    inserted = []
    for path in payload.paths:
        file = Path(path).expanduser()
        if not file.exists() or not file.is_file():
            continue
        inserted.append(downloader.register_file(file))
    return ok(media=[db.loads(row, "metadata") for row in inserted])


@app.get("/api/media")
def list_media():
    rows = db.query("SELECT * FROM media ORDER BY created_at DESC")
    return {"media": [db.loads(row, "metadata") for row in rows]}


@app.get("/api/media/{media_id}")
def get_media(media_id: str):
    return ok(media=media_row(media_id))


@app.delete("/api/media/{media_id}")
def delete_media(media_id: str, delete_file: bool = False):
    row = db.one("SELECT * FROM media WHERE id=?", (media_id,))
    if not row:
        return JSONResponse({"detail": "Video not found"}, status_code=404)
    file_deleted = False
    file_error = None
    source_path = Path(row.get("path") or "").expanduser()
    file_kept_shared = False
    # Only delete files that were registered as yt-dlp downloads. Imported files
    # can be anywhere on disk and are always kept safe from an accidental delete.
    # A source file stays on disk if another library entry or saved project uses it.
    if delete_file and row.get("source_url") and source_path.is_file():
        try:
            if _file_is_referenced(source_path, exclude_media_id=media_id):
                file_kept_shared = True
            else:
                source_path.unlink()
                file_deleted = True
        except OSError as exc:
            file_error = str(exc)
    db.execute("DELETE FROM analyses WHERE media_id=?", (media_id,))
    db.execute("DELETE FROM clips WHERE media_id=? AND (output IS NULL OR output='')", (media_id,))
    (CACHE / "thumbs" / f"{media_id}.jpg").unlink(missing_ok=True)
    db.delete("media", "id", media_id)
    return ok(file_deleted=file_deleted, file_error=file_error, file_kept_shared=file_kept_shared)


@app.get("/api/media/{media_id}/stream")
def stream_media(media_id: str, request: Request):
    row = media_row(media_id)
    return file_stream(row["path"], request)


@app.get("/api/media/{media_id}/thumbnail")
def media_thumbnail(media_id: str):
    row = media_row(media_id)
    path = CACHE / "thumbs" / f"{media_id}.jpg"
    if not path.exists():
        thumb = thumbnail(row["path"], media_id)
        if not thumb:
            return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg")


@app.get("/media/file")
def stream_file(request: Request, path: str, download: bool = False):
    target = Path(path).expanduser()
    if not target.exists() or not target.is_file():
        return Response("Not found", status_code=404)
    suffix = target.suffix.lower()
    mime = (
        "video/mp4" if suffix in {".mp4", ".m4v"}
        else "video/quicktime" if suffix == ".mov"
        else "video/webm" if suffix == ".webm"
        else "image/jpeg" if suffix in {".jpg", ".jpeg"}
        else "application/octet-stream"
    )
    return file_stream(target, request, mime, download=download)


@app.get("/api/playlists")
def list_playlists():
    rows = db.query("SELECT * FROM playlists ORDER BY created_at DESC")
    return {"playlists": [db.loads(row, "items") for row in rows]}


@app.get("/api/playlists/{playlist_id}")
def get_playlist(playlist_id: str):
    row = db.loads(db.one("SELECT * FROM playlists WHERE id=?", (playlist_id,)), "items")
    if not row:
        return JSONResponse({"detail": "Playlist not found"}, status_code=404)
    media = db.query("SELECT id,title,path,duration FROM media WHERE playlist_id=?", (playlist_id,))
    return ok(playlist=row, media=media)


# --- analysis & clip discovery ------------------------------------------
@app.post("/api/analysis/transcribe")
async def start_transcribe(payload: TranscribeRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = TranscribeRequest(**(p or {}))
        row = media_row(req.media_id)
        result = await transcribe(
            row["path"], req.model, req.language, req.word_timestamps,
            on_progress=lambda pct, msg: jobs.update(job_id, progress=pct, message=msg),
        )
        save_analysis(req.media_id, "transcript", result)
        return result

    return ok(job_id=jobs.run("transcribe", work, payload.model_dump()))


@app.get("/api/analysis/{media_id}/transcript")
def get_transcript(media_id: str):
    return ok(transcript=last_analysis(media_id, "transcript"))


@app.post("/api/analysis/vision")
async def start_vision(payload: VisionRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = VisionRequest(**(p or {}))
        row = media_row(req.media_id)
        result = await vision.analyze(
            row["path"], req.region, req.fps, req.engine,
            on_progress=lambda pct, msg: jobs.update(job_id, progress=pct, message=msg),
        )
        save_analysis(req.media_id, "vision", result)
        return result

    return ok(job_id=jobs.run("vision", work, payload.model_dump()))


@app.get("/api/analysis/{media_id}/vision")
def get_vision(media_id: str):
    return ok(vision=last_analysis(media_id, "vision"))


def _region_boxes(region: RegionSelection) -> list[dict[str, float]]:
    # The UI sends both `box` (for older API clients) and `boxes` (multi-region).
    # Prefer the latter so the first focus area is not analyzed twice.
    return region.boxes if region.boxes else ([region.box] if region.box else [])


@app.post("/api/clips/propose")
async def propose_clips(payload: ClipProposalRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = ClipProposalRequest(**(p or {}))
        rows = [media_row(mid) for mid in req.media_ids]
        transcripts: dict[str, Any] = {}
        visions: dict[str, Any] = {}
        region_map: dict[str, list[dict[str, float]]] = {}
        focus_map: dict[str, dict[str, float]] = {}
        layout_map: dict[str, str] = {}
        for region in req.regions:
            boxes = [box for box in _region_boxes(region) if box]
            if region.kind in ("custom", "player", "gameplay"):
                region_map[region.media_id] = boxes
                focus = region.box or (boxes[0] if boxes else None)
                if focus:
                    focus_map[region.media_id] = focus
            else:
                region_map[region.media_id] = []
            if region.layout:
                layout_map[region.media_id] = region.layout
        total = max(len(rows), 1)
        for index, row in enumerate(rows):
            base = index / total * 85
            if not last_analysis(row["id"], "transcript"):
                try:
                    jobs.update(job_id, progress=base + 5, message=f"Transcribing {row['title']}…")
                    result = await transcribe(
                        row["path"], word_timestamps=True,
                        on_progress=lambda pct, msg: jobs.update(job_id, progress=base + pct / 8, message=msg),
                    )
                    save_analysis(row["id"], "transcript", result)
                except Exception as exc:
                    jobs.update(job_id, message=f"Transcription skipped: {exc}")
                    result = {"segments": [], "text": ""}
            else:
                result = last_analysis(row["id"], "transcript")
            transcripts[row["id"]] = result
            boxes = region_map.get(row["id"], [])
            expected_key = json.dumps(boxes, sort_keys=True)
            cached_vision = last_analysis(row["id"], "vision") or {}
            wants_reframe = req.platform in {"shorts", "reels", "tiktok"} and not boxes
            needs_reframe = wants_reframe and cached_vision.get("reframe_version") != vision.REFRAME_VERSION
            if (
                not cached_vision
                or cached_vision.get("region_key", json.dumps([], sort_keys=True)) != expected_key
                or needs_reframe
            ):
                try:
                    jobs.update(job_id, progress=base + 25, message=f"Analysing visuals of {row['title']}…")
                    vresult = await vision.analyze(
                        row["path"], None, 2.0, "auto",
                        on_progress=lambda pct, msg: jobs.update(job_id, progress=base + 25 + pct / 4, message=msg),
                        regions=boxes, track_reframe=wants_reframe,
                    )
                    vresult["layout"] = layout_map.get(row["id"])
                    save_analysis(row["id"], "vision", vresult)
                except Exception as exc:
                    jobs.update(job_id, message=f"Vision skipped: {exc}")
                    vresult = {"timeline": [], "region_key": expected_key}
            else:
                vresult = cached_vision
            visions[row["id"]] = vresult

        jobs.update(job_id, progress=88, message="Scoring engaging moments…")
        candidates = scoring.propose(
            rows, transcripts, visions, req.count, req.min_duration, req.max_duration,
            req.platform, region_map, layout_map, focus_map,
        )
        if req.use_llm and await llm.reachable():
            jobs.update(job_id, progress=94, message="Gemma is refining titles…")
            candidates = await scoring.refine_with_llm(candidates, llm.structured, req.llm_model)
        for candidate in candidates:
            db.insert(
                "clips",
                {
                    "id": uid("clip_"), "project_id": None, "media_id": candidate.media_id,
                    "start": candidate.start, "end": candidate.end, "score": candidate.score,
                    "title": candidate.title, "reason": ", ".join(candidate.reasons),
                    "status": "proposed", "output": None,
                    "metadata": dumps(candidate.model_dump()), "created_at": now(),
                },
            )
        return {"clips": [item.model_dump() for item in candidates]}

    return ok(job_id=jobs.run("clips", work, payload.model_dump()))


def _clip_metadata(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    loaded = db.loads(row, "metadata") or {}
    metadata = loaded.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    # Flatten rows written by older apply-effects versions, which accidentally
    # nested the original metadata object inside a second metadata wrapper.
    while isinstance(metadata.get("metadata"), dict):
        nested = metadata["metadata"]
        metadata = {**nested, **{key: value for key, value in metadata.items() if key != "metadata"}}
    return metadata


def _clip_response(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    loaded = db.loads(row, "metadata") or {}
    metadata = _clip_metadata(loaded)
    result = {**metadata, **loaded, "metadata": metadata}
    if not isinstance(result.get("reasons"), list):
        result["reasons"] = [result["reason"]] if result.get("reason") else []
    result.setdefault("hook", "")
    result.setdefault("hashtags", [])
    result.setdefault("transcript", "")
    if not isinstance(result.get("regions"), list):
        result["regions"] = []
    return result


@app.get("/api/clips")
def list_clips(project_id: str | None = None):
    sql = "SELECT * FROM clips"
    params: tuple = ()
    if project_id:
        sql += " WHERE project_id=?"
        params = (project_id,)
    sql += " ORDER BY score DESC"
    return {"clips": [_clip_response(row) for row in db.query(sql, params)]}


class ClipPatch(BaseModel):
    start: float | None = None
    end: float | None = None
    title: str | None = None
    score: float | None = None
    status: str | None = None


@app.patch("/api/clips/{clip_id}")
def patch_clip(clip_id: str, payload: ClipPatch):
    if not db.one("SELECT id FROM clips WHERE id=?", (clip_id,)):
        return JSONResponse({"detail": "Clip not found"}, status_code=404)
    db.update("clips", "id", clip_id, payload.model_dump(exclude_none=True))
    return ok(clip=_clip_response(db.one("SELECT * FROM clips WHERE id=?", (clip_id,))))


@app.post("/api/clips/apply-effects")
def apply_effects(payload: ApplyEffectsRequest):
    """Copy one clip's effect settings to every selected clip in one click."""
    changed = 0
    for clip_id in payload.clip_ids:
        row = db.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not row:
            continue
        metadata = _clip_metadata(row)
        metadata["effects"] = payload.effects
        db.update("clips", "id", clip_id, {"metadata": dumps(metadata)})
        changed += 1
    return ok(changed=changed, effects=payload.effects)


def _same_file(left: str | Path, right: str | Path) -> bool:
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except (OSError, RuntimeError):
        return False


def _paths_in_project(value: Any):
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str) and path:
            yield path
        for child in value.values():
            yield from _paths_in_project(child)
    elif isinstance(value, list):
        for child in value:
            yield from _paths_in_project(child)


def _file_is_referenced(
    path: str | Path,
    *,
    exclude_media_id: str | None = None,
    exclude_clip_id: str | None = None,
) -> bool:
    """Keep a shared source/export file while any other record or project uses it."""
    target = Path(path).expanduser()
    for row in db.query("SELECT id,path FROM media WHERE path IS NOT NULL"):
        if row.get("id") != exclude_media_id and row.get("path") and _same_file(target, row["path"]):
            return True
    # Rendered clip records survive library-media removal; keep their source
    # available so the clip can still be reopened or re-rendered later.
    for row in db.query(
        "SELECT media.path FROM clips JOIN media ON media.id=clips.media_id "
        "WHERE clips.output IS NOT NULL AND clips.output!='' AND media.path IS NOT NULL"
    ):
        if row.get("path") and _same_file(target, row["path"]):
            return True
    for row in db.query("SELECT id,output FROM clips WHERE output IS NOT NULL AND output!=''"):
        if row.get("id") != exclude_clip_id and row.get("output") and _same_file(target, row["output"]):
            return True
    for row in db.query("SELECT data FROM projects"):
        try:
            document = json.loads(row.get("data") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if any(_same_file(target, candidate) for candidate in _paths_in_project(document)):
            return True
    return False


def _delete_clip_record(clip_id: str, delete_output: bool = True) -> tuple[bool, bool]:
    row = db.one("SELECT * FROM clips WHERE id=?", (clip_id,))
    if not row:
        return False, False
    file_deleted = False
    output = row.get("output")
    if delete_output and output:
        target = Path(output).expanduser()
        roots = [EXPORTS]
        for setting in ("exports_folder", "clips_folder"):
            configured = db.get_setting(setting, "")
            if configured:
                roots.append(Path(configured).expanduser())
        try:
            resolved = target.resolve()
            allowed = any(resolved.is_relative_to(root.resolve()) for root in roots)
            shared = _file_is_referenced(resolved, exclude_clip_id=clip_id)
            if allowed and not shared and resolved.is_file() and resolved.suffix.lower() in {".mp4", ".m4v", ".mov"}:
                resolved.unlink()
                file_deleted = True
        except (OSError, RuntimeError):
            # Never fail removal of the library record over an inaccessible file.
            pass
    db.delete("clips", "id", clip_id)
    return True, file_deleted


@app.delete("/api/clips/bulk-delete")
def delete_clips(payload: DeleteClipsRequest):
    deleted = 0
    files_deleted = 0
    for clip_id in dict.fromkeys(payload.clip_ids):
        removed, file_removed = _delete_clip_record(clip_id)
        deleted += int(removed)
        files_deleted += int(file_removed)
    return ok(deleted=deleted, files_deleted=files_deleted)


@app.delete("/api/clips/{clip_id}")
def delete_clip(clip_id: str):
    removed, file_deleted = _delete_clip_record(clip_id)
    if not removed:
        return JSONResponse({"detail": "Clip not found"}, status_code=404)
    return ok(file_deleted=file_deleted)


@app.post("/api/clips/{clip_id}/render")
async def render_clip_endpoint(clip_id: str, payload: RenderRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = RenderRequest(**(p or {}))
        clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
        if not clip:
            raise RuntimeError("Clip not found")
        media = media_row(clip["media_id"])
        options = req.model_dump()
        metadata = _clip_metadata(clip)
        regions = req.regions or metadata.get("regions") or []
        focus = req.region or metadata.get("region") or (regions[0] if regions else None)
        if focus:
            options["region"] = focus
        options["regions"] = regions
        options["region_layout"] = req.region_layout or metadata.get("region_layout")
        options["crop_path"] = metadata.get("crop_path") or []
        options["title"] = req.title or clip.get("title") or metadata.get("title")
        if req.captions is None:
            words: list[dict[str, Any]] = []
            for segment in last_analysis(clip["media_id"], "transcript").get("segments", []):
                for word in segment.get("words") or []:
                    if clip["start"] <= float(word.get("start", 0)) <= clip["end"]:
                        words.append(word)
            options["captions"] = words
        options["watermark_path"] = configured_watermark_path() if req.watermark else None
        output = req.output or render.export_path(f"{clip.get('title') or 'clip'}_{clip_id}")
        await render.render_clip(
            media["path"], float(clip["start"]), float(clip["end"]), output, options,
            on_progress=lambda pct, msg: jobs.update(job_id, progress=pct, message=msg),
        )
        metadata = _clip_metadata(db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata"))
        metadata["effects"] = {k: v for k, v in options.items() if k in {
            "aspect", "resolution", "caption_style", "captions", "title", "sticker", "sticker_position",
            "music", "music_volume", "sfx", "sfx_volume", "speed", "brightness", "contrast",
            "saturation", "blur_background", "watermark", "watermark_path", "region", "regions", "region_layout",
        }}
        metadata["hardware"] = hardware_info()
        db.update("clips", "id", clip_id, {
            "status": "rendered", "output": output, "metadata": dumps(metadata),
        })
        return {
            "output": output, "url": "/media/file?path=" + output, "clip_id": clip_id,
            "hardware": metadata["hardware"], "effects": metadata["effects"],
        }

    return ok(job_id=jobs.run("render", work, payload.model_dump()))


@app.post("/api/auto-edit")
async def auto_edit(payload: AutoEditRequest):
    """Apply an edit recipe, render it, and return the matching editable timeline tracks."""
    async def work(job_id: str, p: dict[str, Any]):
        req = AutoEditRequest(**(p or {}))
        clip_ids = list(dict.fromkeys(req.clip_ids))
        total = max(len(clip_ids), 1)
        outputs: list[dict[str, Any]] = []
        edits: list[dict[str, Any]] = []
        warnings: list[str] = []
        watermark_path = configured_watermark_path()
        styles = {
            "hype": {"speed": 1.04, "brightness": 0.02, "contrast": 1.05, "saturation": 1.08},
            "minimal": {"speed": 1.0, "brightness": 0.0, "contrast": 1.0, "saturation": 1.0},
            "premium": {"speed": 1.0, "brightness": 0.01, "contrast": 1.08, "saturation": 1.04},
        }
        for index, clip_id in enumerate(clip_ids):
            row = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
            if not row:
                warnings.append(f"Clip {clip_id} was not found and was skipped.")
                continue
            media = media_row(row["media_id"])
            if not media or not Path(str(media.get("path") or "")).is_file():
                warnings.append(f"{row.get('title') or clip_id}: source media is missing; clip was skipped.")
                continue
            metadata = _clip_metadata(row)
            clip_start, clip_end = float(row["start"]), float(row["end"])
            source_duration = max(0.2, clip_end - clip_start)
            effects = metadata.get("effects")
            if not isinstance(effects, dict):
                effects = {}

            captions: list[dict[str, Any]] = []
            if req.captions:
                analysis = last_analysis(row["media_id"], "transcript") or {}
                if not isinstance(analysis, dict):
                    analysis = {}
                if not analysis.get("segments"):
                    jobs.update(
                        job_id,
                        progress=round(index / total * 100, 1),
                        message=f"Generating captions for clip {index + 1}/{total}…",
                    )
                    try:
                        analysis = await transcribe(
                            media["path"], word_timestamps=True,
                            on_progress=lambda pct, msg, i=index: jobs.update(
                                job_id,
                                progress=round((i + min(35, pct * 0.35)) / total * 100, 1),
                                message=f"Clip {i + 1}/{total}: {msg}",
                            ),
                        )
                        save_analysis(row["media_id"], "transcript", analysis)
                    except Exception as exc:
                        warnings.append(f"{row.get('title') or clip_id}: captions unavailable ({exc}).")
                        analysis = {"segments": []}
                if not isinstance(analysis, dict):
                    analysis = {}
                segments = analysis.get("segments")
                for segment in segments if isinstance(segments, list) else []:
                    if not isinstance(segment, dict):
                        continue
                    try:
                        segment_start = float(segment.get("start", clip_start))
                        segment_end = float(segment.get("end", segment_start))
                    except (TypeError, ValueError):
                        continue
                    words = segment.get("words")
                    selected_words = []
                    for word in words if isinstance(words, list) else []:
                        if not isinstance(word, dict):
                            continue
                        try:
                            word_start = float(word.get("start", 0))
                            word_end = float(word.get("end", word_start))
                        except (TypeError, ValueError):
                            continue
                        if word_start <= clip_end and word_end >= clip_start:
                            selected_words.append(word)
                    if selected_words:
                        captions.extend(selected_words)
                    elif segment_start <= clip_end and segment_end >= clip_start:
                        text = str(segment.get("text") or "").strip()
                        if text:
                            captions.append({
                                "text": text,
                                "start": max(clip_start, segment_start),
                                "end": min(clip_end, segment_end),
                            })
                # A saved candidate transcript remains a useful fallback when
                # local ASR weights are unavailable or only returned empty text.
                if not captions and metadata.get("transcript"):
                    captions = [{
                        "text": str(metadata["transcript"])[:240],
                        "start": clip_start, "end": clip_end,
                    }]
                if not captions:
                    warnings.append(f"{row.get('title') or clip_id}: rendered with a title card; no speech transcript was available.")

            regions = metadata.get("regions") or []
            focus = metadata.get("region") or (regions[0] if regions else None)
            requested_music = req.music if req.music is not None else effects.get("music")
            music = str(requested_music or "").strip() or None
            if music:
                music_path = Path(music).expanduser()
                if music_path.is_file():
                    music = str(music_path)
                else:
                    warnings.append(f"{row.get('title') or clip_id}: selected music file was not found and was skipped.")
                    music = None
            saved_sfx = effects.get("sfx")
            sfx_names = saved_sfx if isinstance(saved_sfx, list) and saved_sfx else ["whoosh", "pop"]
            sfx_items = []
            if req.sound_effects:
                for item in sfx_names:
                    name = item.get("name") if isinstance(item, dict) else item
                    try:
                        sfx_path = sfx.sfx_path(str(name))
                    except ValueError:
                        warnings.append(f"{row.get('title') or clip_id}: unknown sound effect {name!r} was skipped.")
                        continue
                    default_at = 0.0 if not sfx_items else min(0.45, max(0, source_duration - 0.2))
                    at = float(item.get("at", default_at)) if isinstance(item, dict) else default_at
                    effect_duration = float(probe(sfx_path).get("duration") or (0.7 if name in ("whoosh", "riser") else 0.35))
                    sfx_items.append({"name": str(name), "at": max(0, at), "path": str(sfx_path), "duration": effect_duration})

            sticker = (metadata.get("sticker") or effects.get("sticker")) if req.stickers else None
            if sticker:
                sticker_path = Path(str(sticker)).expanduser()
                sticker = str(sticker_path) if sticker_path.is_file() else None
            sticker_position = effects.get("sticker_position") or {"x": 0.72, "y": 0.16, "scale": 0.22}
            title = str(row.get("title") or metadata.get("title") or "Untitled clip").strip()[:100]
            style_effects = styles[req.style]
            timeline_duration = source_duration / float(style_effects["speed"])
            options = {
                "aspect": req.aspect, "resolution": req.resolution,
                "caption_style": {"preset": req.style, "position": "bottom"},
                "captions": captions[:180], "title": title,
                "sfx": [{"name": item["name"], "at": item["at"]} for item in sfx_items],
                "sfx_volume": effects.get("sfx_volume", 0.5),
                "music": music,
                "music_volume": req.music_volume if req.music is not None else effects.get("music_volume", req.music_volume),
                "sticker": sticker, "sticker_position": sticker_position,
                **style_effects,
                "blur_background": req.blur_background,
                "watermark": bool(watermark_path), "watermark_path": watermark_path,
                "region": focus, "regions": regions,
                "region_layout": metadata.get("region_layout"),
                "crop_path": metadata.get("crop_path") or [],
            }
            output = render.export_path(f"{row.get('title') or 'clip'}_auto_edited_{clip_id}")
            jobs.update(job_id, progress=round(index / total * 100, 1), message=f"Applying edit to clip {index + 1}/{total}…")
            await render.render_clip(
                media["path"], clip_start, clip_end, output, options,
                on_progress=lambda pct, msg, i=index: jobs.update(
                    job_id,
                    progress=round((i + (pct or 0) / 100) / total * 100, 1),
                    message=f"Clip {i + 1}/{total}: {msg}",
                ),
            )
            auto_audio: list[dict[str, Any]] = []
            if music:
                auto_audio.append({
                    "path": str(Path(music).expanduser()), "start": 0, "end": timeline_duration,
                    "volume": float(options["music_volume"]), "label": "Music", "kind": "music",
                })
            for item in sfx_items:
                auto_audio.append({
                    "path": item["path"], "start": item["at"],
                    "end": min(timeline_duration, item["at"] + item["duration"]),
                    "volume": float(options["sfx_volume"]), "label": item["name"], "kind": "sfx",
                })
            auto_stickers = []
            if sticker:
                auto_stickers.append({
                    "path": str(sticker), "start": 0,
                    "end": min(4.0, timeline_duration * 0.35),
                    "x": float(sticker_position.get("x", 0.72)),
                    "y": float(sticker_position.get("y", 0.16)),
                    "scale": float(sticker_position.get("scale", 0.22)),
                    "label": "Auto Edit sticker",
                })
            metadata.update({
                "effects": {key: value for key, value in options.items() if key != "crop_path"},
                "hardware": hardware_info(), "auto_edited": True,
            })
            db.update("clips", "id", clip_id, {"status": "auto_edited", "output": output, "metadata": dumps(metadata)})
            outputs.append({"clip_id": clip_id, "output": output})
            edits.append({
                "clip_id": clip_id, "media_id": row["media_id"], "source_path": media["path"],
                "source_start": clip_start, "source_duration": source_duration,
                "duration": timeline_duration, "title": title, "aspect": req.aspect,
                "resolution": req.resolution, "region": focus, "regions": regions,
                "region_layout": metadata.get("region_layout"),
                "crop_path": metadata.get("crop_path") or [],
                "captions": captions[:180] if req.captions else [],
                "audio": auto_audio, "stickers": auto_stickers,
                "effects": {key: value for key, value in options.items() if key != "crop_path"},
            })
        return {"outputs": outputs, "edits": edits, "count": len(outputs), "warnings": warnings, "hardware": hardware_info()}

    return ok(job_id=jobs.run("auto-edit", work, payload.model_dump()))

@app.post("/api/exports/batch")
async def export_batch(payload: ExportAllRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = ExportAllRequest(**(p or {}))
        total = max(len(req.clip_ids), 1)
        progress = [0.0] * total
        workers = hardware_info()["workers"]
        semaphore = asyncio.Semaphore(workers)
        jobs.update(job_id, progress=1, message=f"Exporting {total} clip(s) with {workers} parallel worker(s)")

        async def one(index: int, clip_id: str) -> dict[str, str] | None:
            async with semaphore:
                clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
                if not clip:
                    progress[index] = 1.0
                    return None
                media = media_row(clip["media_id"])
                if not media or not Path(str(media.get("path") or "")).is_file():
                    progress[index] = 1.0
                    return None
                metadata = _clip_metadata(clip)
                output = render.export_path(f"{clip.get('title', 'clip')}_{clip_id}_{index+1}")
                effects = metadata.get("effects")
                if not isinstance(effects, dict):
                    effects = {}
                watermark_enabled = effects.get("watermark", True)
                saved_watermark_path = effects.get("watermark_path")
                watermark_path = None
                if watermark_enabled:
                    if saved_watermark_path and Path(str(saved_watermark_path)).is_file():
                        watermark_path = str(saved_watermark_path)
                    else:
                        watermark_path = configured_watermark_path()
                regions = effects.get("regions") or metadata.get("regions") or []
                options = {
                    "aspect": effects.get("aspect", req.aspect),
                    "resolution": effects.get("resolution", req.resolution),
                    "caption_style": effects.get("caption_style", {"preset": "hype"}),
                    "captions": effects.get("captions") or [],
                    "watermark": watermark_enabled, "watermark_path": watermark_path,
                    "sfx": effects.get("sfx", ["whoosh", "pop"]),
                    "sfx_volume": effects.get("sfx_volume", 0.5),
                    "sticker": effects.get("sticker") or metadata.get("sticker"),
                    "sticker_position": effects.get("sticker_position") or {"x": 0.72, "y": 0.16, "scale": 0.22},
                    "music": effects.get("music"),
                    "music_volume": effects.get("music_volume", 0.22),
                    "speed": effects.get("speed", 1),
                    "brightness": effects.get("brightness", 0),
                    "contrast": render._normalise_contrast(effects.get("contrast", 1.0)),
                    "saturation": effects.get("saturation", 1),
                    "blur_background": effects.get("blur_background", True),
                    "region": effects.get("region") or metadata.get("region") or (regions[0] if regions else None),
                    "regions": regions,
                    "region_layout": effects.get("region_layout") or metadata.get("region_layout"),
                    "crop_path": metadata.get("crop_path") or [],
                    "title": effects.get("title") or clip.get("title"),
                }
                await render.render_clip(
                    media["path"], float(clip["start"]), float(clip["end"]), output, options,
                    on_progress=lambda pct, msg, i=index: (
                        progress.__setitem__(i, pct / 100),
                        jobs.update(
                            job_id,
                            progress=round(sum(progress) / total * 100, 1),
                            message=f"Clip {i+1}/{total}: {msg}",
                        ),
                    ),
                )
                metadata["effects"] = {
                    **effects,
                    **{key: value for key, value in options.items() if key in {
                        "aspect", "resolution", "caption_style", "captions", "title", "sticker", "sticker_position",
                        "music", "music_volume", "sfx", "sfx_volume", "speed", "brightness", "contrast",
                        "saturation", "blur_background", "watermark", "watermark_path", "region", "regions", "region_layout",
                    }},
                }
                metadata["hardware"] = hardware_info()
                db.update("clips", "id", clip_id, {
                    "status": "rendered", "output": output, "metadata": dumps(metadata),
                })
                progress[index] = 1.0
                return {"clip_id": clip_id, "output": output}

        results = await asyncio.gather(*(one(i, cid) for i, cid in enumerate(req.clip_ids)))
        jobs.update(job_id, progress=100, message="Batch export complete")
        return {"outputs": [item for item in results if item], "hardware": hardware_info()}

    return ok(job_id=jobs.run("batch", work, payload.model_dump()))


# --- timeline projects ---------------------------------------------------
@app.get("/api/projects")
def list_projects():
    rows = db.query("SELECT id FROM projects ORDER BY updated_at DESC")
    return {"projects": [project_row(row["id"]) for row in rows]}


@app.post("/api/projects")
def create_project(payload: ProjectCreate):
    project_id = uid("prj_")
    timeline = payload.template or {"tracks": {"video": [], "captions": [], "stickers": [], "audio": []}, "aspect": "9:16", "resolution": "source"}
    if payload.clip_id:
        clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (payload.clip_id,)), "metadata") or {}
        clip_metadata = _clip_metadata(clip)
        media = media_row(clip.get("media_id", ""))
        timeline["tracks"]["video"].append(
            {
                "id": clip.get("id"), "clip_id": clip.get("id"), "path": media["path"],
                "sourceStart": clip.get("start", 0),
                "duration": clip.get("end", 0) - clip.get("start", 0),
                "label": clip.get("title") or media.get("title", "Clip"),
                "region": clip_metadata.get("region"), "regions": clip_metadata.get("regions") or [],
                "region_layout": clip_metadata.get("region_layout"),
                "crop_path": clip_metadata.get("crop_path") or [],
            }
        )
    elif payload.media_id:
        media = media_row(payload.media_id)
        timeline["tracks"]["video"].append({"path": media["path"], "sourceStart": 0, "duration": min(30, media.get("duration") or 30)})
    db.insert(
        "projects",
        {"id": project_id, "name": payload.name, "data": dumps({"id": project_id, "name": payload.name, "timeline": timeline}), "created_at": now(), "updated_at": now()},
    )
    return ok(project={"id": project_id, "name": payload.name, "timeline": timeline})


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = project_row(project_id)
    if not project:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return ok(project=project)


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate):
    project = project_row(project_id) or {"id": project_id, "name": "Untitled", "timeline": {}}
    if payload.name is not None:
        project["name"] = payload.name
    if payload.timeline is not None:
        project["timeline"] = payload.timeline
    document = {"id": project_id, "name": project.get("name", "Untitled"), "timeline": project.get("timeline", {})}
    db.update("projects", "id", project_id, {"name": document["name"], "data": dumps(document), "updated_at": now()})
    return ok(project=document)


@app.post("/api/projects/{project_id}/export")
async def export_project(project_id: str, payload: ExportRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = ExportRequest(**(p or {}))
        row = project_row(project_id)
        if not row:
            raise RuntimeError("Project not found")
        timeline = dict(row.get("timeline") or {})
        if req.aspect:
            timeline["aspect"] = req.aspect
        if req.resolution:
            timeline["resolution"] = req.resolution
        output = req.output or render.export_path(f"{str(row.get('name') or 'project')[:100]}_{project_id}")
        await render.render_timeline(
            timeline, output,
            on_progress=lambda pct, msg: jobs.update(job_id, progress=pct, message=msg),
            watermark_path=configured_watermark_path(),
        )
        return {"output": output, "url": "/media/file?path=" + output}

    return ok(job_id=jobs.run("export", work, payload.model_dump()))


# --- assets, image generation, models, publishing -----------------------
@app.post("/api/assets/search")
def search_assets(payload: AssetSearchRequest):
    return ok(results=assets.search(payload.query, payload.source, payload.kind, payload.per_page))


@app.post("/api/assets/download")
def download_asset(payload: AssetDownloadRequest):
    return ok(asset=assets.download(payload.url, payload.name, payload.source))


@app.get("/api/assets/file")
def asset_file(request: Request, path: str):
    target = Path(path).expanduser()
    if not target.exists():
        return Response("Not found", status_code=404)
    return file_stream(target, request, "image/png" if target.suffix.lower() == ".png" else "application/octet-stream")


@app.post("/api/images/generate")
async def generate_image_endpoint(payload: ImageRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = ImageRequest(**(p or {}))
        jobs.update(job_id, progress=10, message="Generating visual…")
        result = await asyncio.to_thread(
            images.generate_variations,
            req.prompt, req.provider, req.aspect, req.reference_path, req.negative_prompt,
            count=req.count,
            on_progress=lambda pct, message: jobs.update(job_id, progress=max(10, pct), message=message),
        )
        return result

    return ok(job_id=jobs.run("image", work, payload.model_dump()))


@app.get("/api/sfx")
def list_sfx():
    return {"sfx": sfx.list_sfx()}


@app.get("/api/sfx/{name}/path")
def sfx_file_path(name: str):
    return ok(path=str(sfx.sfx_path(name)))


@app.post("/api/tts")
async def tts_endpoint(payload: dict[str, str]):
    async def work(job_id: str, p: dict[str, Any]):
        path = await synthesize(str(p.get("text", "")), p.get("voice"))
        return {"path": path, "url": "/media/file?path=" + path}

    return ok(job_id=jobs.run("tts", work, payload))


@app.get("/api/models")
async def list_models():
    return {"models": await models.status()}


@app.post("/api/models/comfyui-checkpoint")
def select_comfy_checkpoint(payload: ComfyCheckpointRequest):
    try:
        return ok(checkpoint=models.configure_comfy_checkpoint(payload.path))
    except (OSError, RuntimeError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@app.post("/api/models/install")
async def install_model(payload: ModelInstallRequest):
    async def work(job_id: str, p: dict[str, Any]):
        model_id = str((p or {}).get("model_id"))
        return await models.install(
            model_id,
            lambda pct, msg: jobs.update(job_id, progress=pct, message=msg),
        )

    return ok(job_id=jobs.run("model-install", work, payload.model_dump()))


@app.post("/api/models/install-recommended")
async def install_recommended_models():
    async def work(job_id: str, _payload: dict[str, Any]):
        return await models.install_recommended(
            lambda pct, msg: jobs.update(job_id, progress=pct, message=msg)
        )

    return ok(job_id=jobs.run("model-install", work, {}))


@app.post("/api/models/auto-setup")
async def auto_setup_models():
    last = float(db.get_setting("auto_setup_last_attempt", "0") or 0)
    if time.time() - last < 6 * 3600 and db.get_setting("auto_setup_complete", "") != "1":
        return ok(job_id="", skipped=True, message="Offline setup already attempted recently")
    db.set_setting("auto_setup_last_attempt", str(time.time()))

    async def work(job_id: str, _payload: dict[str, Any]):
        return await models.auto_setup(
            lambda pct, msg: jobs.update(job_id, progress=pct, message=msg)
        )

    return ok(job_id=jobs.run("model-install", work, {}))


@app.delete("/api/models/{model_id}")
async def remove_model(model_id: str):
    return ok(result=await models.uninstall(model_id))


@app.get("/api/youtube/status")
def youtube_status():
    return ok(**youtube.status())


@app.post("/api/youtube/authorize")
async def youtube_authorize():
    async def work(job_id: str, _p):
        jobs.update(job_id, message="Open the browser window and allow access…")
        return await youtube.authorize()

    return ok(job_id=jobs.run("youtube-auth", work, {}))


@app.post("/api/youtube/upload")
async def youtube_upload(payload: YouTubeUploadRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = YouTubeUploadRequest(**(p or {}))
        clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (req.clip_id,)), "metadata") or {}
        path = clip.get("output")
        if not path or not Path(path).exists():
            raise RuntimeError("Render this clip first — no exported MP4 found.")
        jobs.update(job_id, message="Uploading to YouTube…", progress=10)
        return await youtube.upload(
            path, req.title, req.description, req.tags, req.privacy, req.publish_at, req.made_for_kids
        )

    return ok(job_id=jobs.run("youtube-upload", work, payload.model_dump()))


@app.get("/api/settings")
def get_settings():
    return ok(values=db.all_settings(), capabilities=capabilities())


@app.put("/api/settings")
def put_settings(payload: SettingsPatch):
    for key, value in payload.values.items():
        db.set_setting(key, value)
    return ok(values=db.all_settings())


def folder_map() -> dict[str, str]:
    """Resolve the effective app folders, including user-chosen overrides."""
    resolved = {
        "downloads": str(DOWNLOADS), "exports": str(EXPORTS), "assets": str(ASSETS),
        "cache": str(CACHE), "clips": str(CLIPS), "models": str(CACHE),
    }
    for key in ("downloads", "exports", "models", "clips"):
        custom = db.get_setting(f"{key}_folder", "")
        if custom:
            resolved[key] = custom
    return resolved


@app.get("/api/folders")
def folders():
    return ok(folders=folder_map())


@app.put("/api/folders")
def set_folder(payload: FolderPatch):
    from pathlib import Path as _Path

    mapping = {
        "downloads": "download_folder", "exports": "exports_folder",
        "models": "models_folder", "clips": "clips_folder",
    }
    key = mapping.get(payload.key)
    if not key:
        raise ValueError(f"Unknown folder: {payload.key}")
    target = _Path(payload.path).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    db.set_setting(key, str(target))
    return ok(folders=folder_map())


def main() -> None:
    import uvicorn

    host = os.getenv("AIFREECLIP_HOST", "127.0.0.1")
    port = int(os.getenv("AIFREECLIP_PORT", "8787"))
    print(f"AI Clipper Pro API on http://{host}:{port} (token: {API_TOKEN})", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
