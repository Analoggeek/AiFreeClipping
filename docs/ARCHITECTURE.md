# Architecture

```text
┌──────────────────────── Electron shell (electron/main.cjs) ────────────────────────┐
│  React 18 + TypeScript UI (src/)  ──HTTP + token──▶  Python engine (127.0.0.1)   │
│  native dialogs, file reveal, backend lifecycle                                    │
└──────────────────────────────────────────────────────────────────────────────────┘
                                        │
            ┌───────────────────────────┴───────────────────────────┐
            ▼                                                       ▼
   FastAPI app (backend/app/main.py)                       SQLite (~/.AiFreeClipping/db.sqlite3)
   ├─ Downloader  → yt-dlp (single / playlist)             media, playlists, jobs, projects,
   ├─ Analysis    → Whisper transcript + vision/tracking    clips, analyses, settings
   ├─ Discovery   → engagement scoring + Gemma rerank
   ├─ Render      → FFmpeg filter graphs, SFX, stickers
   ├─ Assets      → Pexels / Pixabay / Openverse / AI art
   └─ Export      → clip, batch and multi-track project MP4s
```

## Request flow: find viral clips

1. `POST /api/clips/propose` creates a background job managed by `jobs.JobManager`.
2. For each selected video:
   - `services/asr.py` loads faster-whisper once, records word-timed transcript data for internal scoring and caches it in `analyses`.
   - `services/vision.py` samples frames via OpenCV; ultralytics/YOLOX detections feed `tracking.ByteTrackLite`. Without weights, it falls back to FFmpeg scene-change energy.
3. `services/scoring.py` aligns speech density, transcript keyword cues, visual activity and scene peaks on a 0.5-second grid, then selects non-overlapping windows in the requested duration range. Transcript excerpts can appear as source context in the clip review UI; they are not subtitle assets.
4. If Ollama is reachable, `services/llm.py` asks Gemma to rerank candidates and refine clip titles. Failures are non-fatal; deterministic scores remain available.
5. Candidate timing, title and composition metadata are stored in `clips` rows.

Whisper is part of analysis only. There is no standalone transcription endpoint, social-caption editor, subtitle download, or subtitle rendering in v6.

## Renderer and exports

`services/render.py` builds FFmpeg commands as argument arrays (never `shell=True`):

- Video: `trim → setpts → fps → scale/crop (or blurred pad for 9:16) → eq → sticker overlay → optional user watermark → yuv420p`
- Audio: `atrim → asetpts → atempo → volume/adelay → amix → apad → atrim`
- Encoder: `libx264`, `h264_videotoolbox` or `h264_nvenc`; AAC audio, `+faststart`
- Progress is parsed from `-progress pipe:1` and sent to the job stream (`GET /api/jobs/{id}/events`, SSE).

Project export concatenates video segments and mixes timed audio/sticker overlays. It does not create ASS files or burn text into output. Older project documents are normalized to `video`, `stickers` and `audio` tracks; obsolete caption tracks and text-effect metadata are discarded when projects are read or saved.

## Frontend state

Simple React state plus polling (`src/api.ts: pollJob`) keeps the UI responsive without a state-management dependency. The editor keeps a serializable timeline:

```ts
{
  tracks: {
    video:    [{ path, sourceStart, duration }],
    stickers: [{ path, start, end, x, y }],
    audio:    [{ path, start, end, volume }]
  },
  aspect: '9:16' | '1:1' | '16:9',
  resolution: 'source' | '720p' | '1080p'
}
```

Projects are saved through `PUT /api/projects/{id}` and rendered by `POST /api/projects/{id}/export`. Editor panel sizes and preview scale are stored separately in browser local storage, so resetting the layout never changes project edits.

## Security and privacy

- Loopback-only API with a random per-launch token written to `~/.AiFreeClipping/.api_token`. Electron injects it through the preload; browser mode reads it from the URL/local storage.
- `contextIsolation: true`, `nodeIntegration: false`, and remote navigation disabled by default.
- FFmpeg/yt-dlp arguments are passed as arrays; user paths are never interpolated into shell commands.
- YouTube and other supported sites are source-download inputs only. No YouTube OAuth or upload integration is included.
- Optional cloud image/stock calls happen only when a key is configured and the feature is selected.

## Extending

- **New scoring signal:** add it in `scoring.build_features` and blend it into `window_score`.
- **New renderer effect:** add a filter stage in `render.build_clip_args`/`render_timeline` and expose supported inputs through `schemas.RenderRequest`.
- **New model provider:** add a catalogue entry in `services/models.py` and an installer branch.
- **New UI page:** add a component under `src/pages` and register it in `src/App.tsx` `NAV`.
