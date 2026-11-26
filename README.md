# AI Clipper Pro

**Local-first AI video clipping, editing and publishing studio — made by analoggeek.**

Paste a link (or import a file), let local AI find the engaging moments, polish the clips in a full timeline editor, and export/upload them — without sending your footage to a cloud service.

> Everything runs on your machine: Gemma via Ollama, Whisper word-level transcription, YOLOX/YOLO + ByteTrack activity tracking, FFmpeg rendering, optional local SDXL via ComfyUI, optional Piper narration. Cloud integrations (Nano Banana image generation, stock media search, YouTube upload) are opt-in and use **your own** API keys.

<p align="center">
  <img src="brand/logo.svg" width="520" alt="AI Clipper Pro — made by analoggeek" />
</p>

---

## What it does

| Stage | What you get |
|---|---|
| **Download** | Highest quality available video/audio via `yt-dlp`, playlist mode with item selection, subtitles, custom save folder, local file import, searchable media library |
| **Understand** | `faster-whisper` word timestamps + optional YOLOX/YOLO11 detection with ByteTrack IDs + motion/scene energy fused into a per-second engagement timeline |
| **Clip** | Multiple non-overlapping viral candidates from one or many videos, region locking (player/gameplay area), local Gemma reranking, hook titles and hashtags |
| **Enhance** | Auto captions with 4 presets, procedural royalty-free SFX, stickers, music bed, vertical 9:16 reframing with blurred background, watermark, speed/color controls |
| **Edit** | CapCut-style multi-track editor: video, captions, stickers and audio tracks; split, trim, drag-position, inspector, stock asset search, AI image generation, keyboard shortcuts |
| **Publish** | One-click batch export at 1080p H.264/AAC with `+faststart`, downloadable files, optional resumable YouTube Data API v3 upload |

## Quick start

### Installed app (recommended)

1. Download the installer for your machine from [GitHub Releases](https://github.com/Analoggeek/AiFreeClipping/releases):
   - **Windows 10/11** — `AI-Clipper-Pro-*-Windows-x64.exe` or `arm64.exe`
   - **macOS Intel** — `AI-Clipper-Pro-*-macOS-x64.dmg`
   - **macOS Apple Silicon (M1/M2/M3/M4)** — `AI-Clipper-Pro-*-macOS-arm64.dmg`
   - **Linux x86_64** — `AI-Clipper-Pro-*-Linux-x64.AppImage` or `.deb`
2. Launch the app. It starts its own bundled Python engine on `127.0.0.1` with a per-launch token — nothing is exposed to your network.
3. Open **Local Models** and install `Whisper Small`, `Gemma 2 7B` (or `Gemma 3 4B`) and `YOLO11 Nano`. First download needs internet; after that, everything is offline.
4. Paste a URL in **Downloader**, then send the video to **AI Clipper**.

> macOS unsigned builds need *Right click → Open* the first time. Windows SmartScreen may warn for unsigned installers; this is expected until the app is code-signed.

### Run from source

```bash
# 1. JavaScript UI + Electron shell
npm install
npm run build

# 2. Python engine
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python scripts/generate-icons.py

# 3. Desktop dev mode (engine + Vite + Electron)
npm run dev:app

# ...or run the pieces separately
npm run dev                          # http://localhost:5173
PYTHONPATH=backend python -m backend.app.main   # http://127.0.0.1:8787
```

Point the browser at `http://localhost:5173?token=<value in ~/.AiFreeClipping/.api_token>&api=http://127.0.0.1:8787` when running the UI without Electron.

**Hindi quick start (हिंदी में):** `npm install` → `pip install -r backend/requirements.txt` → `npm run dev:app` → app खोलें → **Local Models** में Whisper + Gemma install करें → **Downloader** में link paste करें → **AI Clipper** से clips निकालें → **Editor** में edit करें → **Publish** से export/upload करें।

---

## Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 64-bit, macOS 12, Ubuntu 20.04 / any AppImage-capable distro | Latest OS with GPU drivers |
| CPU | 4 cores | 8+ cores / Apple Silicon |
| RAM | 8 GB | 16–32 GB (7B LLM + Whisper Large) |
| Disk | 6 GB for app + ~10 GB for models | 40 GB+ for model packs and media |
| GPU | Not required (CPU fallback) | NVIDIA CUDA or Apple Metal for faster inference |

The app never requires a GPU. `faster-whisper` uses `int8` on CPU and `float16` on CUDA/Metal where available.

---

## Local AI stack

| Model / engine | Role | Installed via |
|---|---|---|
| `gemma2:7b` (or `gemma3:4b` / `gemma3:12b`) | Viral title rewriting, hashtags, structured clip reranking | Ollama `api/pull` from the Models page |
| `faster-whisper` small / medium / large-v3 | Word-timed transcript used for captions and scoring | Hugging Face hub snapshot |
| YOLO11 Nano / YOLOX Nano + ByteTrack | Player and object detection, stable track IDs, activity curve | Ultralytics weights |
| OpenCV / ffmpeg scene detection | Motion and shot-change energy (fallback when no vision weights) | Bundled |
| ComfyUI + SDXL 1.0 | Fully offline sticker/thumbnail generation | Local checkpoint, optional |
| Piper TTS | Offline narration / voice-over | Local ONNX voice, optional |
| Nano Banana (`gemini-2.5-flash-image`) | Optional high-quality on-the-spot image generation | Your Gemini key in Settings |
| Pexels / Pixabay / Openverse | Optional copyright-friendly stock search | Your free API keys (Openverse needs none) |

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for model-pack and offline instructions.

---

## Repository layout

```text
AiFreeClipping/
├── src/                    React + TypeScript UI (downloads, clipper, editor, publish, models, settings)
├── electron/               Electron main process + secure preload, launches local engine
├── backend/
│   ├── app/
│   │   ├── main.py         FastAPI routes (token-protected, loopback only)
│   │   ├── db.py           SQLite store: media, playlists, jobs, projects, clips, analyses, settings
│   │   ├── jobs.py         Background jobs + SSE progress
│   │   └── services/       downloader, asr, llm, vision, tracking, scoring, render, images, assets, models, youtube, tts, sfx
│   ├── tests/              pytest suite (scoring, rendering, tracking, API)
│   └── requirements*.txt   Core and optional YouTube dependencies
├── scripts/
│   ├── release-all.sh      ONE COMMAND: checks → icons → UI → engine → installers → checksums → release
│   ├── release-all.ps1     Windows PowerShell equivalent
│   ├── package-backend.py  PyInstaller bundle of Python engine + ffmpeg
│   └── dev-app.cjs         dev launcher for engine + Vite + Electron
├── .github/workflows/      Cross-platform installer matrix (Windows x64/arm64, macOS Intel/AS, Linux x64)
├── website/                Product website with download buttons and docs links
├── brand/                  Vector logo + generated platform icons (made by analoggeek)
└── docs/                   Architecture, installation, API, credits, roadmap
```

Full design notes: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). API reference: [docs/API.md](docs/API.md).

---

## One-command release

```bash
# Installers for the current machine (Windows / macOS / Linux)
bash scripts/release-all.sh

# Every supported platform in one command, via GitHub Actions
bash scripts/release-all.sh 5.1.0 --all

# ...and publish a GitHub Release with SHA256 checksums
bash scripts/release-all.sh 5.1.0 --all --publish

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts\release-all.ps1 -All -Publish
```

The script runs type checks, Python tests, icon generation, UI build, PyInstaller engine bundling (including FFmpeg), `electron-builder` packaging, artifact checksums and a manifest. For `--all`, the repository's `release.yml` workflow builds on native runners for each OS/architecture and uploads installers to a GitHub Release. macOS code signing/notarization and Windows Authenticode signing require developer certificates and are not included; unsigned installers still work locally.

---

## Privacy & offline behavior

- The FastAPI engine binds to `127.0.0.1` only and requires a random token regenerated on every launch.
- Source footage, transcripts and projects never leave the machine unless you explicitly enable a cloud feature.
- Model weights are downloaded once into `~/.AiFreeClipping/cache` (or `HF_HOME`), then reused offline.
- Sound effects are generated procedurally with Python's `wave` module — no sample downloads, no license issues.
- Keys are stored in local SQLite, never in the frontend bundle.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| “Engine offline” | Check the terminal output; install `backend/requirements.txt` in the venv the app uses, then restart. |
| Downloads fail / 403 cookies needed | Add a Netscape `cookies.txt` in Settings → `cookies_file`, or update `yt-dlp` with `pip install -U yt-dlp`. |
| No captions | Install a Whisper model in **Local Models**; the app still clips using visual/audio energy without it. |
| “Gemma is refining titles…” is slow | Use `gemma3:4b` or disable Gemma reranking in clipper settings. |
| ComfyUI image generation not available | Start ComfyUI at `http://127.0.0.1:8188` with an SDXL checkpoint, or add a Gemini key for Nano Banana. |
| Render error about fonts | Install a system font (Arial/DejaVu/Georgia); ASS subtitles fall back to the system default. |
| macOS app won’t open | Right-click → Open, or `xattr -d com.apple.quarantine /path/to/app`. |
| Linux AppImage won’t launch | `chmod +x AI-Clipper-Pro-*.AppImage` and run it directly. |

---

## Tech credits

Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org/), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Ollama](https://ollama.com/), [Ultralytics](https://github.com/ultralytics/ultralytics), [ByteTrack](https://github.com/ifzhang/ByteTrack), [ComfyUI](https://github.com/comfyanonymous/ComfyUI), [Piper](https://github.com/OHF-Voice/piper1-gpl), [FastAPI](https://fastapi.tiangolo.com/), [Electron](https://www.electronjs.org/) and [React](https://react.dev/). See [docs/CREDITS.md](docs/CREDITS.md).

## License

MIT © 2026 analoggeek. Third-party models and libraries keep their own licenses; review them before commercial use of generated media. Stock assets remain under their respective provider licenses (Pexels, Pixabay, Openverse/CC).

**Made by analoggeek.**
