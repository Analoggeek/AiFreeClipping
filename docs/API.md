# Local API reference

Base URL: `http://127.0.0.1:<port>`. Every `/api/*` and `/media/*` request needs the header `X-AI-Clipper-Token: <token from ~/.AiFreeClipping/.api_token>` (a `?token=` query parameter also works for media URLs used by `<video>` tags).

Jobs are asynchronous: endpoints return `{ "job_id": "job_…" }`; poll `GET /api/jobs/{id}` or stream `GET /api/jobs/{id}/events` (SSE).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Version, token file location |
| GET | `/api/system/capabilities` | FFmpeg, Python, GPU and optional engine availability |
| GET | `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/events` | Job list, details, live progress |
| POST | `/api/downloads/inspect` | Resolve URL metadata without downloading |
| POST | `/api/downloads` | Download single video or playlist (`url`, `mode`, `quality`, `folder`, `playlist_items`) |
| POST | `/api/media/import` | Register local files by absolute path |
| GET/DELETE | `/api/media`, `/api/media/{id}` | Library list / remove |
| GET | `/api/media/{id}/stream`, `/api/media/{id}/thumbnail` | Range-capable video stream, cached thumbnail |
| GET | `/media/file?path=…` | Stream any rendered file with HTTP range support |
| GET | `/api/playlists`, `/api/playlists/{id}` | Saved playlists and their downloaded media |
| POST | `/api/analysis/transcribe` | Whisper transcript with word timings (job) |
| GET | `/api/analysis/{media_id}/transcript` | Cached transcript |
| POST | `/api/analysis/vision` | YOLO/YOLOX + ByteTrack / motion timeline (job) |
| GET | `/api/analysis/{media_id}/vision` | Cached activity timeline |
| POST | `/api/clips/propose` | Full viral-clip pipeline (job) |
| GET/PATCH/DELETE | `/api/clips`, `/api/clips/{id}` | Candidates, edit timings/title, delete |
| POST | `/api/clips/{id}/render` | Render one clip with captions/SFX/sticker/music (job) |
| POST | `/api/exports/batch` | Render many clips in one job |
| GET/POST | `/api/projects` | List / create timeline projects |
| GET/PUT | `/api/projects/{id}` | Load / save timeline |
| POST | `/api/projects/{id}/export` | Render full multi-track project (job) |
| POST | `/api/assets/search`, `/api/assets/download` | Copyright-friendly stock media |
| GET | `/api/assets/file?path=…` | Serve generated/downloaded assets |
| POST | `/api/images/generate` | Nano Banana or ComfyUI image generation (job) |
| GET | `/api/sfx`, `/api/sfx/{name}/path` | Procedural sound effect names/local paths |
| POST | `/api/tts` | Piper offline narration (job) |
| GET/POST/DELETE | `/api/models`, `/api/models/install`, `/api/models/{id}` | Local model catalogue / install / remove |
| GET/POST | `/api/youtube/status`, `/api/youtube/authorize`, `/api/youtube/upload` | OAuth status, connect, resumable upload |
| GET/PUT | `/api/settings`, `/api/folders` | Local keys and data paths |

### Example: download and clip from the command line

```bash
TOKEN=$(cat ~/.AiFreeClipping/.api_token)
API=http://127.0.0.1:8787

curl -s -H "X-AI-Clipper-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID","mode":"single","quality":"max"}' \
  "$API/api/downloads"

curl -s -H "X-AI-Clipper-Token: $TOKEN" "$API/api/jobs" | python -m json.tool
```

### Job states

`queued → running → done | error | cancelled`. Progress is 0–100 and `message` is human-readable; `result` contains paths/IDs on success.

### Render options (excerpt)

```json
{
  "aspect": "9:16",
  "resolution": "1080p",
  "caption_style": {"preset": "hype", "position": "bottom"},
  "captions": [{"word": "GO!", "start": 4.2, "end": 4.8}],
  "sticker": "/path/to/sticker.png",
  "music": "/path/to/music.mp3",
  "music_volume": 0.22,
  "sfx": ["whoosh", "pop"],
  "speed": 1.0,
  "contrast": 1.0,
  "blur_background": true,
  "watermark": true
}
```

The watermark flag only enables the optional logo selected in **Settings**. If no user logo is configured, exports remain unbranded; the app logo is never burned into video.
