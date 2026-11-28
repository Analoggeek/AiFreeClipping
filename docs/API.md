# Local API reference

Base URL: `http://127.0.0.1:<port>`. Every `/api/*` and `/media/*` request needs the header `X-AI-Clipper-Token: <token from ~/.AiFreeClipping/.api_token>`; a `?token=` query parameter is also accepted for media URLs used by `<video>` tags.

Long-running work is asynchronous. Endpoints return `{ "job_id": "job_…" }`; poll `GET /api/jobs/{id}` or stream `GET /api/jobs/{id}/events` (SSE).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | App version, token-file path and data-home path |
| GET | `/api/system/capabilities`, `/api/system/hardware` | Runtime availability and hardware snapshot |
| GET | `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/events` | Job list, details and live progress |
| POST | `/api/jobs/{id}/cancel` | Cancel a running job |
| POST | `/api/downloads/inspect` | Resolve URL metadata without downloading |
| POST | `/api/downloads` | Download a single video or playlist (`url`, `mode`, `quality`, `folder`, `playlist_items`, `cookies_file`) |
| DELETE | `/api/downloads/storage` | Clear confirmed, app-managed downloads that are not referenced by the library or projects |
| POST | `/api/media/import` | Register local files by absolute path |
| GET/DELETE | `/api/media`, `/api/media/{id}` | List library media or remove a media record |
| GET | `/api/media/{id}/stream`, `/api/media/{id}/thumbnail` | Range-capable source stream and cached thumbnail |
| GET | `/media/file?path=…` | Stream or download a rendered file with HTTP range support |
| GET | `/api/playlists`, `/api/playlists/{id}` | Saved playlists and their downloaded media |
| POST | `/api/analysis/vision` | Run a vision/activity analysis (job) |
| GET | `/api/analysis/{media_id}/vision` | Read cached vision/activity analysis |
| POST | `/api/clips/propose` | Analyze selected sources and rank non-overlapping clip candidates |
| GET/PATCH/DELETE | `/api/clips`, `/api/clips/{id}` | List clips, edit title/timing or delete a clip |
| POST | `/api/clips/apply-effects` | Apply export settings to selected clips |
| POST | `/api/clips/{id}/render` | Render one clip (job) |
| POST | `/api/auto-edit` | Render and create editable video/sticker/audio tracks (job) |
| POST | `/api/exports/batch` | Render selected clips in one job |
| GET/POST | `/api/projects` | List or create timeline projects |
| GET/PUT | `/api/projects/{id}` | Load or save a timeline project |
| POST | `/api/projects/{id}/export` | Render a project timeline (job) |
| POST | `/api/assets/search`, `/api/assets/download` | Search or download stock media |
| GET | `/api/assets/file?path=…` | Serve generated/downloaded assets |
| POST | `/api/images/generate` | Generate image assets (job) |
| GET | `/api/sfx`, `/api/sfx/{name}/path` | Procedural sound-effect names and local paths |
| POST | `/api/tts` | Piper offline narration (job) |
| GET/POST/DELETE | `/api/models`, `/api/models/install`, `/api/models/{id}` | Catalogue, install and remove local models |
| GET/PUT | `/api/settings`, `/api/folders` | Local settings and data paths |

### Download example

YouTube remains a supported **source-download** site through yt-dlp. The download request has no subtitle-writing option. The app no longer exposes YouTube channel authorization or upload endpoints.

```bash
TOKEN=$(cat ~/.AiFreeClipping/.api_token)
API=http://127.0.0.1:8787

curl -s -H "X-AI-Clipper-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID","mode":"single","quality":"max"}' \
  "$API/api/downloads"

curl -s -H "X-AI-Clipper-Token: $TOKEN" "$API/api/jobs" | python -m json.tool
```

### Internal transcription

Whisper is invoked internally by clip proposal for transcript-aware scoring and candidate context. There is no public transcription endpoint, caption editor, subtitle-download option or rendered subtitle track. Existing cached transcripts remain available to the analysis pipeline; they are not burned into exported video.

### Render options (excerpt)

```json
{
  "aspect": "9:16",
  "resolution": "1080p",
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

Project timelines contain `video`, `stickers` and `audio` tracks. Legacy caption tracks and text-render options are stripped when old projects are read or saved. The watermark flag only enables the optional user-selected logo; if no logo is configured, exports remain unbranded.

Job states are `queued → running → done | error | cancelled`. Progress is 0–100; `message` is human-readable and `result` contains paths/IDs on success.
