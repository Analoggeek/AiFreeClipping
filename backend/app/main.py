"""AI Clipper Pro local API server (binds to 127.0.0.1 only)."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import subprocess
import sys
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
    DownloadRequest, ExportAllRequest, ExportRequest, FolderPatch, ImageRequest, ImportRequest,
    ModelInstallRequest, ProjectCreate, ProjectUpdate, RegionSelection, RenderRequest, SettingsPatch,
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


def brand_asset(name: str) -> str | None:
    candidates = [
        Path(os.getenv("AIFREECLIP_ASSET_DIR", "")).expanduser() / name if os.getenv("AIFREECLIP_ASSET_DIR") else None,
        Path(__file__).resolve().parents[2] / "brand" / name,
        Path(getattr(sys, "_MEIPASS", ".")) / "brand" / name,
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate)
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
def list_jobs(limit: int = 50):
    return {"jobs": jobs.list(limit)}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"detail": "Job not found"}, status_code=404)
    return job


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
def delete_media(media_id: str):
    db.delete("media", "id", media_id)
    return ok()


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
def stream_file(request: Request, path: str):
    target = Path(path).expanduser()
    if not target.exists():
        return Response("Not found", status_code=404)
    suffix = target.suffix.lower()
    mime = "video/mp4" if suffix in {".mp4", ".mov", ".m4v"} else "image/jpeg" if suffix in {".jpg", ".jpeg"} else "application/octet-stream"
    return file_stream(target, request, mime)


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


@app.post("/api/clips/propose")
async def propose_clips(payload: ClipProposalRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = ClipProposalRequest(**(p or {}))
        rows = [media_row(mid) for mid in req.media_ids]
        transcripts: dict[str, Any] = {}
        visions: dict[str, Any] = {}
        region_map: dict[str, list[dict[str, float]]] = {}
        layout_map: dict[str, str] = {}
        for region in req.regions:
            boxes = [box for box in ([*region.boxes, region.box] if region.box else region.boxes) if box]
            region_map[region.media_id] = boxes if region.kind in ("custom", "player", "gameplay") else []
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
            cached_vision = last_analysis(row["id"], "vision")
            if not cached_vision or cached_vision.get("region_key", json.dumps([], sort_keys=True)) != expected_key:
                try:
                    jobs.update(job_id, progress=base + 25, message=f"Analysing visuals of {row['title']}…")
                    vresult = await vision.analyze(
                        row["path"], None, 2.0, "auto",
                        on_progress=lambda pct, msg: jobs.update(job_id, progress=base + 25 + pct / 4, message=msg),
                        regions=boxes,
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
            req.platform, region_map, layout_map,
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


@app.get("/api/clips")
def list_clips(project_id: str | None = None):
    sql = "SELECT * FROM clips"
    params: tuple = ()
    if project_id:
        sql += " WHERE project_id=?"
        params = (project_id,)
    sql += " ORDER BY score DESC"
    return {"clips": [db.loads(row, "metadata") for row in db.query(sql, params)]}


class ClipPatch(BaseModel):
    start: float | None = None
    end: float | None = None
    title: str | None = None
    score: float | None = None
    status: str | None = None


@app.patch("/api/clips/{clip_id}")
def patch_clip(clip_id: str, payload: ClipPatch):
    db.update("clips", "id", clip_id, payload.model_dump(exclude_none=True))
    return ok(clip=db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata"))


@app.post("/api/clips/apply-effects")
def apply_effects(payload: ApplyEffectsRequest):
    """Copy one clip's effect settings to every selected clip in one click."""
    changed = 0
    for clip_id in payload.clip_ids:
        row = db.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not row:
            continue
        document = db.loads(row, "metadata")
        document["effects"] = payload.effects
        db.update("clips", "id", clip_id, {"metadata": dumps(document)})
        changed += 1
    return ok(changed=changed, effects=payload.effects)


@app.delete("/api/clips/{clip_id}")
def delete_clip(clip_id: str):
    db.delete("clips", "id", clip_id)
    return ok()


@app.post("/api/clips/{clip_id}/render")
async def render_clip_endpoint(clip_id: str, payload: RenderRequest):
    async def work(job_id: str, p: dict[str, Any]):
        req = RenderRequest(**(p or {}))
        clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
        if not clip:
            raise RuntimeError("Clip not found")
        media = media_row(clip["media_id"])
        options = req.model_dump()
        document = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata") or {}
        focus = (document.get("regions") or [document.get("region")] or [None])[0]
        if focus and not options.get("region"):
            options["region"] = focus
        if req.captions is None:
            words: list[dict[str, Any]] = []
            for segment in last_analysis(clip["media_id"], "transcript").get("segments", []):
                for word in segment.get("words") or []:
                    if clip["start"] <= word["start"] <= clip["end"]:
                        words.append(word)
            options["captions"] = words
        options["watermark_path"] = brand_asset("icon.png") if req.watermark else None
        output = req.output or render.export_path(clip.get("title") or clip_id)
        await render.render_clip(
            media["path"], float(clip["start"]), float(clip["end"]), output, options,
            on_progress=lambda pct, msg: jobs.update(job_id, progress=pct, message=msg),
        )
        document = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata") or {}
        document["effects"] = {k: v for k, v in options.items() if k in {
            "aspect", "resolution", "caption_style", "sfx", "speed", "brightness", "contrast", "saturation", "blur_background", "watermark"
        }}
        document["hardware"] = hardware_info()
        db.update("clips", "id", clip_id, {
            "status": "rendered", "output": output, "metadata": dumps(document),
        })
        return {
            "output": output, "url": "/media/file?path=" + output, "clip_id": clip_id,
            "hardware": document["hardware"], "effects": document["effects"],
        }

    return ok(job_id=jobs.run("render", work, payload.model_dump()))


@app.post("/api/auto-edit")
async def auto_edit(payload: AutoEditRequest):
    """Apply the full local enhancement stack and render finished clips in one job."""
    async def work(job_id: str, p: dict[str, Any]):
        req = AutoEditRequest(**(p or {}))
        total = max(len(req.clip_ids), 1)
        outputs: list[dict[str, Any]] = []
        for index, clip_id in enumerate(req.clip_ids):
            row = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata")
            if not row:
                jobs.update(job_id, progress=round((index + 1) / total * 100, 1), message=f"Clip {index + 1}: not found")
                continue
            media = media_row(row["media_id"])
            metadata = row.get("metadata") or {}
            analysis = last_analysis(row["media_id"], "transcript") or {}
            captions = []
            for segment in analysis.get("segments", []):
                for word in segment.get("words") or []:
                    if row["start"] <= float(word.get("start", 0)) <= row["end"]:
                        captions.append(word)
            if not captions:
                captions = [
                    segment for segment in analysis.get("segments", [])
                    if segment.get("start", 0) <= row["end"] and segment.get("end", 0) >= row["start"]
                ]
            focus = (metadata.get("regions") or [metadata.get("region")] or [None])[0]
            options = {
                "aspect": req.aspect, "resolution": "1080p",
                "caption_style": {"preset": req.style, "position": "bottom"},
                "captions": captions[:140],
                "sfx": ["whoosh", "pop"],
                "sticker": metadata.get("sticker"),
                "speed": 1.04, "brightness": 0.02, "contrast": 0.05, "saturation": 1.08,
                "blur_background": req.aspect == "9:16", "watermark": True,
                "watermark_path": brand_asset("icon.png"),
                "region": focus,
                "source_width": media.get("width") or 1080,
                "source_height": media.get("height") or 1920,
            }
            output = render.export_path(f"{row.get('title') or clip_id}_auto_edited")
            jobs.update(job_id, progress=round(index / total * 100, 1), message=f"Auto-editing clip {index + 1}/{total}…")
            await render.render_clip(
                media["path"], float(row["start"]), float(row["end"]), output, options,
                on_progress=lambda pct, msg, i=index: jobs.update(
                    job_id,
                    progress=round((i + (pct or 0) / 100) / total * 100, 1),
                    message=f"Clip {i + 1}/{total}: {msg}",
                ),
            )
            document = db.loads(db.one("SELECT * FROM clips WHERE id=?", (clip_id,)), "metadata") or {}
            document.update({
                "status": "auto_edited", "output": output, "effects": options,
                "hardware": hardware_info(), "auto_edited": True,
            })
            db.update("clips", "id", clip_id, {"status": "auto_edited", "output": output, "metadata": dumps(document)})
            outputs.append({"clip_id": clip_id, "output": output})
        return {"outputs": outputs, "count": len(outputs), "hardware": hardware_info()}

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
                output = render.export_path(f"{clip.get('title', clip_id)}_{index+1}")
                effects = clip.get("effects") or {}
                options = {
                    "aspect": effects.get("aspect", req.aspect),
                    "resolution": effects.get("resolution", req.resolution),
                    "caption_style": effects.get("caption_style", {"preset": "hype"}),
                    "captions": [],
                    "watermark_path": brand_asset("icon.png"),
                    "sfx": effects.get("sfx", ["whoosh", "pop"]),
                    "speed": effects.get("speed", 1),
                    "brightness": effects.get("brightness", 0),
                    "contrast": effects.get("contrast", 0),
                    "saturation": effects.get("saturation", 1),
                    "blur_background": effects.get("blur_background", True),
                    "region": (clip.get("regions") or [clip.get("region")] or [None])[0],
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
                db.update("clips", "id", clip_id, {"status": "rendered", "output": output})
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
    timeline = payload.template or {"tracks": {"video": [], "captions": [], "stickers": [], "audio": []}, "aspect": "9:16", "resolution": "1080p"}
    if payload.clip_id:
        clip = db.loads(db.one("SELECT * FROM clips WHERE id=?", (payload.clip_id,)), "metadata") or {}
        media = media_row(clip.get("media_id", ""))
        timeline["tracks"]["video"].append(
            {"path": media["path"], "sourceStart": clip.get("start", 0), "duration": clip.get("end", 0) - clip.get("start", 0)}
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
        timeline["aspect"] = req.aspect
        timeline["resolution"] = req.resolution
        output = req.output or render.export_path(row.get("name", "project"))
        await render.render_timeline(
            timeline, output,
            on_progress=lambda pct, msg: jobs.update(job_id, progress=pct, message=msg),
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
            images.generate, req.prompt, req.provider, req.aspect, req.reference_path, req.negative_prompt
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
