# Architecture

```
┌──────────────────────── Electron shell (electron/main.cjs) ────────────────────────┐
│  React 18 + TypeScript UI (src/)  ──HTTP + token──▶  Python engine (127.0.0.1)   │
│  native dialogs, file reveal, backend lifecycle                                    │
└──────────────────────────────────────────────────────────────────────────────────┘
                                        │
            ┌───────────────────────────┴───────────────────────────┐
            ▼                                                       ▼
   FastAPI app (backend/app/main.py)                       SQLite (~/.AiFreeClipping/db.sqlite3)
   ├─ Downloader  → yt-dlp (single / playlist)             media, playlists, jobs, projects,
   ├─ Analysis    → faster-whisper + vision + tracking     clips, analyses, settings
   ├─ Discovery   → engagement scoring + Gemma rerank
   ├─ Render      → ffmpeg filter graphs, ASS captions, SFX
   ├─ Assets      → Pexels / Pixabay / Openverse / AI art
   └─ Publish     → YouTube Data API v3 (optional)
```

## Request flow: "find viral clips"

1. `POST /api/clips/propose` creates a background **job** (`jobs.JobManager`).
2. For each selected video:
   - `services/asr.py` loads `faster-whisper` once, transcribes with `word_timestamps=True`, caches result in the `analyses` table.
   - `services/vision.py` samples frames via OpenCV; `ultralytics`/YOLOX detections feed `tracking.ByteTrackLite` (two-stage IoU association). Without weights it falls back to ffmpeg scene-change energy.
3. `services/scoring.py` aligns speech density, hook keywords (English + Hindi), visual activity and scene peaks on a 0.5-second grid, then greedily searches non-overlapping windows for the requested duration range.
4. If Ollama is reachable, `services/llm.py` asks Gemma for schema-constrained JSON to rerank and rewrite titles. Failures are non-fatal — deterministic scores remain.
5. Candidates are stored as `clips` rows and returned with reasons, title, hashtags and transcript excerpt.

## Renderer

`services/render.py` builds ffmpeg commands as **argv arrays** (never `shell=True`):

- Video: `trim → setpts → fps → scale/crop (or blurred pad for 9:16) → eq → subtitles (ASS) → sticker overlay → watermark → yuv420p`
- Audio: `atrim → asetpts → atempo → volume/adelay → amix → apad → atrim`
- Encoder: `libx264` / `h264_videotoolbox` / `h264_nvenc`, AAC 192 kbps, `+faststart`
- Progress is parsed from `-progress pipe:1` and pushed into the job stream (`GET /api/jobs/{id}/events`, SSE).

Project exports use the same primitives with `concat` over timeline video/audio tracks plus timed caption/sticker overlays.

## Frontend state

Simple React state + polling (`src/api.ts: pollJob`) keeps the UI responsive without a state-management dependency. The editor keeps a serializable `Timeline` document:

```ts
{
  tracks: {
    video:    [{ path, sourceStart, duration }],
    captions: [{ text, start, end }],
    stickers: [{ path, start, end, x, y }],
    audio:    [{ path, start, end, volume }]
  },
  aspect: '9:16' | '1:1' | '16:9',
  resolution: '720p' | '1080p'
}
```

It is saved through `PUT /api/projects/{id}` and rendered by `POST /api/projects/{id}/export`.

## Security

- Loopback-only API with a random per-launch token (written to `~/.AiFreeClipping/.api_token`). The Electron preload injects it into the renderer; the browser build reads it from the URL/localStorage.
- `contextIsolation: true`, `nodeIntegration: false`, remote navigation disabled by default.
- ffmpeg/yt-dlp arguments are passed as arrays; user paths are never interpolated into shell commands.
- Optional cloud calls only happen when a key is configured and the feature is selected.

## Extending

- **New scoring signal:** add a feature list in `scoring.build_features` and blend it in `window_score`.
- **New renderer effect:** add a filter stage in `render.build_clip_args`/`render_timeline` and expose it in `schemas.RenderRequest`.
- **New model provider:** add a catalogue entry in `services/models.py` and an installer branch.
- **New UI page:** add a component under `src/pages`, register it in `src/App.tsx` `NAV`.
