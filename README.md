<p align="center">
  <img src="assets/logo.svg" alt="AI Clipper Pro" width="96" />
</p>

<h1 align="center">AI Clipper Pro</h1>

<p align="center"><b>Turn any video into viral-ready clips — on your own hardware.</b></p>

<p align="center">
  <a href="https://github.com/Analoggeek/AiFreeClipping/releases/latest"><img src="https://img.shields.io/github/v/release/Analoggeek/AiFreeClipping?color=8b5cf6&label=latest" alt="Latest release" /></a>
  <a href="https://github.com/Analoggeek/AiFreeClipping/actions"><img src="https://img.shields.io/github/actions/workflow/status/Analoggeek/AiFreeClipping/release.yml?branch=main&label=installers" alt="Installer build" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22d3ee" alt="MIT license" /></a>
  <a href="https://github.com/Analoggeek/AiFreeClipping"><img src="https://img.shields.io/badge/made%20by-analoggeek-f472b6" alt="made by analoggeek" /></a>
</p>

---

## Why AI Clipper Pro?

Most clipping tools upload your footage to someone else's cloud, charge per clip, and give you a tiny editor at the end. AI Clipper Pro flips that:

- **Everything local after the first model download** — analysis, clipping, captions, rendering and editing stay on your machine.
- **One connected workflow** — download → analyse → clip → enhance → publish.
- **Professional editor** — multi-track timeline, captions, stickers, sound effects, stock media, AI image generation and a generated-clips list that adds source cuts directly to the timeline.
- **Composition-aware clipping** — arrange gameplay/player panels with adjustable proportions and export-matched clean, neon or double outlines; see the same composition in the live preview, individual renders and timeline exports. On full-frame portrait clips, available local tracking can follow a visible subject and snap at scene cuts.
- **Reliable exports** — neutral-contrast Rec.709 H.264/AAC MP4s with fast-start metadata and real `.mp4` download filenames for QuickTime. Exports have no app watermark by default; add your own channel logo in Settings if you want one.
- **Hardware aware** — uses NVENC / Apple VideoToolbox when available, otherwise optimized libx264; CPU/RAM/GPU usage lives in the sidebar.
- **Automatic models** — on first launch the app detects RAM and GPU memory, then installs a balanced Whisper/Gemma/YOLOX set for that hardware. Large image models and cloud APIs remain optional; SDXL can use a checkpoint already on disk.
- **Your folders, your rules** — choose where models, downloaded videos and rendered clips go; safely remove downloads without deleting imported files or project-shared sources; every download uses the bundled CA store.
- **Operations & publishing** — see, dismiss or cancel background jobs; select all clips, bulk-export them or delete selected clips and safely unshared outputs.

> The marketing website is the repository root [`index.html`](index.html). The desktop app entry is [`app.html`](app.html).

## What it can do

| Stage | What you get |
|---|---|
| **Download** | Paste a YouTube/Instagram/TikTok/Twitch URL (or 1000+ yt-dlp sites), choose max quality, subtitles, and full playlists with item selection. Local file import works too. |
| **Understand** | Whisper word timings, YOLOX Nano ONNX + ByteTrack-style tracking (Torch-free in packaged builds), scene changes and hardware-matched Gemma 2/3 reranking. |
| **Clip** | Several non-overlapping viral candidates from one source or a batch of videos. Draw source-aware focus regions, adjust split proportions and outline styles, then carry the selected composition into every render. |
| **Enhance** | Four selectable caption styles, editable transcript-grounded social copy, procedural royalty-free SFX, music beds, stickers, blurred-background 9:16 reframing, speed/color controls and an optional user-supplied channel watermark. |
| **Edit** | CapCut-style timeline with video/caption/sticker/audio tracks, split/trim/inspector, generated clips that add directly to the timeline, stock search and Nano Banana / SDXL art. |
| **Publish** | Select all, export or delete chosen clips; parallel H.264/AAC 1080p exports with `+faststart`, direct MP4 downloads and optional resumable YouTube uploads. |

## Quick start

### 1. Install an offline build (recommended)

Download the right installer from the [latest release](https://github.com/Analoggeek/AiFreeClipping/releases/latest) and open it. The engine, FFmpeg and icons are bundled. Model weights install from the app's **Local Models** page.

**Direct v5.2.4 downloads** (even if the GitHub **Assets** panel is collapsed, these links go straight to the files):

| Platform | Direct installer |
|---|---|
| Windows x64 | [AI-Clipper-Pro-5.2.4-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-Windows-x64.exe) |
| Windows ARM64 | [AI-Clipper-Pro-5.2.4-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-Windows-arm64.exe) |
| macOS Intel DMG | [AI-Clipper-Pro-5.2.4-macOS-x64.dmg](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-macOS-x64.dmg) |
| macOS Intel ZIP (alternate) | [AI-Clipper-Pro-5.2.4-macOS-x64.zip](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-macOS-x64.zip) |
| macOS Apple Silicon DMG | [AI-Clipper-Pro-5.2.4-macOS-arm64.dmg](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-macOS-arm64.dmg) |
| macOS Apple Silicon ZIP (alternate) | [AI-Clipper-Pro-5.2.4-macOS-arm64.zip](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-macOS-arm64.zip) |
| Linux AppImage | [AI-Clipper-Pro-5.2.4-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-Linux-x86_64.AppImage) |
| Linux Debian/Ubuntu | [AI-Clipper-Pro-5.2.4-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-Linux-amd64.deb) |

The v5.2.4 macOS DMGs use a read-only, uncompressed image format. If Finder still says the disk is unreadable, first verify [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/SHA256SUMS.txt) with `shasum -a 256 -c SHA256SUMS.txt`; if the checksum passes but mounting fails, use the matching ZIP above, unzip it, and drag `AI Clipper Pro.app` to Applications. If the DMG mounts but copying reports **Error code -36**, run `dot_clean` on the mounted volume and retry. On first launch, remove the download quarantine with `xattr -cr "/Applications/AI Clipper Pro.app"` if macOS blocks it.

### 2. Run from source

```bash
# Node 20+ and Python 3.11+
npm install
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

npm start          # browser studio — works even without Electron
npm run dev:app    # Electron desktop window; falls back to npm start if Electron is missing
```

Open the URL printed in the terminal. The local token is read from `~/.AiFreeClipping/.api_token`.

**Hindi quick start:** `npm install` → `pip install -r backend/requirements.txt` → `npm start` → **Local Models** me Whisper, YOLOX aur Gemma install karein → **Downloader** me link paste karein → **AI Clipper** se clips nikalein → **Editor** me edit karein → **Publish** se export/upload karein.

## Models & keys

| Model | Provider | Install inside app | Notes |
|---|---|---|---|
| Gemma 2 7B / Gemma 3 4B / 12B | Ollama | 1-click install | The app installs or starts Ollama as needed and recommends a size for your hardware. |
| Whisper Small / Medium / Large v3 | faster-whisper | 1-click download | Small is used on low-memory systems; Medium is recommended from 16 GB RAM. |
| YOLOX Nano ONNX | OpenCV DNN | 1-click download | Torch-free; used by packaged builds. |
| YOLO11 Nano | ultralytics | 1-click download | Best in a source install. |
| Piper Lessac | piper-tts | 1-click download | Offline narration. |
| SDXL 1.0 | ComfyUI | direct link or select existing file | Choose a `.safetensors` / `.ckpt` file or set your ComfyUI checkpoints folder in Local Models. |
| Nano Banana | Gemini API | Get API key | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| YouTube Data API | Google Cloud | Get API key | [APIs & Credentials](https://console.cloud.google.com/apis/credentials) |
| Pexels / Pixabay | Stock APIs | Get API key | Linked from the Models page. |

## Hardware & performance

The sidebar shows live CPU, RAM, disk, GPU and worker count. Rendering automatically prefers NVIDIA NVENC or Apple VideoToolbox, then falls back to libx264.

```bash
export RENDER_WORKERS=8     # parallel batch exports (default: min(4, CPU cores))
export AIFREECLIP_ENCODER=libx264   # override auto encoder
export FORCE_SOFTWARE_ENCODER=1     # force CPU rendering
```

Each rendered clip records the exact hardware used, and **Apply look to all** applies the current color, caption, audio and export settings while keeping each clip's own composition.

## Project layout

```text
.
├── index.html              Marketing website (static, animated)
├── site.css / site.js      Website styles and interactions
├── assets/                 Website logo, hero art and UI previews
├── app.html                Vite entry for the desktop app
├── src/                    React UI, pages and design system
├── electron/               Electron shell and native IPC
├── backend/                FastAPI local engine, AI services and tests
├── brand/                  Logo, 3D mark and platform icons
├── docs/                   Architecture, installation, API, release notes
├── scripts/                Dev launcher, packaging and release scripts
└── .github/workflows/      Native Windows/macOS/Linux installer matrix
```

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API reference](docs/API.md)
- [Release notes](docs/RELEASE_NOTES.md)
- [Roadmap](docs/ROADMAP.md)
- [Credits](docs/CREDITS.md)

## Build installers

```bash
bash scripts/release-all.sh 5.2.4 --all --publish
```

The script builds Windows x64/ARM64, macOS Intel/Apple Silicon and Linux x64 installers on native GitHub runners, then publishes them with `SHA256SUMS.txt`. See [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md).

## Troubleshooting

- **App shows a blank window:** the UI now has an error boundary and auto-reloads crashed renderers. Reload once; if it persists open `npm start` browser mode.
- **Download job failed:** update yt-dlp (`pip install -U yt-dlp`) and retry. The job error is shown in the toast and job tracker.
- **Model install failed:** open the linked official download page and check your connection; Ollama models require Ollama to be running.
- **Electron does not launch:** run `npm start` — it starts the same studio in your browser without Electron.

## License

MIT © 2026 — made by **analoggeek**.
