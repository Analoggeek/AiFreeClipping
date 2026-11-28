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

- **Everything local after the first model download** — speech analysis for clip scoring, clipping, rendering and editing stay on your machine.
- **One connected workflow** — download → analyse → clip → edit → export.
- **Professional editor** — video, sticker and audio tracks, sound effects, stock media, AI image generation and a generated-clips list that adds source cuts directly to the timeline.
- **Composition-aware clipping** — arrange gameplay/player panels with adjustable proportions and export-matched clean, neon or double outlines; see the same composition in the live preview, individual renders and timeline exports. On full-frame portrait clips, available local tracking can follow a visible subject and snap at scene cuts.
- **Reliable exports** — neutral-contrast Rec.709 H.264/AAC MP4s with fast-start metadata and real `.mp4` download filenames for QuickTime. Exports have no app watermark by default; add your own channel logo in Settings if you want one.
- **Hardware aware** — uses NVENC / Apple VideoToolbox when available, otherwise optimized libx264; CPU/RAM/GPU usage lives in the sidebar.
- **Automatic models** — on first launch the app detects RAM and GPU memory, then installs a balanced Whisper/Gemma/YOLOX set for that hardware. Large image models and cloud APIs remain optional; SDXL can use a checkpoint already on disk.
- **Your folders, your rules** — choose where models, downloaded videos and rendered clips go; safely remove downloads without deleting imported files or project-shared sources; every download uses the bundled CA store.
- **Operations & export** — see, dismiss or cancel background jobs; select all clips, bulk-export them or delete selected clips and safely unshared outputs.

> The marketing website is the repository root [`index.html`](index.html). The desktop app entry is [`app.html`](app.html).

## What it can do

| Stage | What you get |
|---|---|
| **Download** | Paste a YouTube/Instagram/TikTok/Twitch URL (or 1000+ yt-dlp sites), choose max quality, and download full playlists with item selection. YouTube remains a source-download option; local file import works too. |
| **Understand** | Local Whisper transcript features for moment scoring, YOLOX Nano ONNX + ByteTrack-style tracking (Torch-free in packaged builds), scene changes and hardware-matched Gemma 2/3 reranking. Transcripts are not rendered as subtitles. |
| **Clip** | Several non-overlapping candidates with concise factual titles from one source or a batch of videos. Draw source-aware focus regions, adjust split proportions and outline styles, then carry the selected composition into every render. |
| **Enhance** | Procedural royalty-free SFX, music beds, stickers, blurred-background 9:16 reframing, speed/color controls and an optional user-supplied channel watermark. |
| **Edit** | CapCut-style timeline with resizable Media, video preview, Inspector and Timeline panels; drag-resizable player, reset-to-default layout, split/trim, generated clips, stock search and Nano Banana / SDXL art. |
| **Export** | Select, render, download or delete clips; parallel H.264/AAC MP4 exports with `+faststart`. The app does not upload/publish to YouTube. |

## Quick start

### 1. Install v6.0.1 (recommended)

The v6.0.1 installers include the app, Python engine, FFmpeg and platform icons. Download the build for your machine:

- **Windows x64:** [Installer (.exe)](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/AI-Clipper-Pro-6.0.1-Windows-x64.exe)
- **Windows ARM64:** [Installer (.exe)](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/AI-Clipper-Pro-6.0.1-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/AI-Clipper-Pro-6.0.1-macOS-x64.dmg) · [ZIP fallback](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/AI-Clipper-Pro-6.0.1-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/AI-Clipper-Pro-6.0.1-macOS-arm64.dmg) · [ZIP fallback](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/AI-Clipper-Pro-6.0.1-macOS-arm64.zip)
- **Linux x64 AppImage:** [AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/AI-Clipper-Pro-6.0.1-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [DEB package](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/AI-Clipper-Pro-6.0.1-Linux-amd64.deb)

[View the v6.0.1 release and all assets](https://github.com/Analoggeek/AiFreeClipping/releases/tag/v6.0.1) · [SHA256 checksums](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/SHA256SUMS.txt) · [Manifest](https://github.com/Analoggeek/AiFreeClipping/releases/download/v6.0.1/manifest.json)

The engine, FFmpeg and icons are bundled; model weights install from the app's **Local Models** page. If a macOS DMG will not mount, verify its checksum and use the matching ZIP. On first launch, remove the download quarantine with `xattr -cr "/Applications/AI Clipper Pro.app"` if macOS blocks it. [Latest release](https://github.com/Analoggeek/AiFreeClipping/releases/latest).

### 2. Run from source

```bash
# Node 22.12+ and Python 3.11+
npm install
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

npm start          # browser studio — works even without Electron
npm run dev:app    # Electron desktop window; falls back to npm start if Electron is missing
```

Open the URL printed in the terminal. The local token is read from `~/.AiFreeClipping/.api_token`.

**Hindi quick start:** `npm install` → `pip install -r backend/requirements.txt` → `npm start` → **Local Models** me Whisper, YOLOX aur Gemma install karein → **Downloader** me link paste karein → **AI Clipper** se clips nikalein → **Editor** me edit karein → **Export** se MP4 render aur download karein.

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
| Pexels / Pixabay | Stock APIs | Get API key | Linked from the Models page. |

## Hardware & performance

The sidebar shows live CPU, RAM, disk, GPU and worker count. Rendering automatically prefers NVIDIA NVENC or Apple VideoToolbox, then falls back to libx264.

```bash
export RENDER_WORKERS=4     # requested parallel batch count (bounded by the per-job CPU budget)
export RENDER_THREADS=4     # FFmpeg thread cap for standalone renders; batch jobs set a shared cap automatically
export AIFREECLIP_ENCODER=libx264   # override auto encoder
export FORCE_SOFTWARE_ENCODER=1     # force CPU rendering
```

Auto Edit and batch exports budget worker and FFmpeg filter/codec threads together, leaving CPU capacity for the app and system. Each rendered clip records the exact hardware used, and **Apply look to all** applies the current color, audio and export settings while keeping each clip's own composition.

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
bash scripts/release-all.sh 6.0.1 --all
```

By default, the script builds and verifies the full eight-installer matrix (Windows x64/ARM64, macOS Intel/Apple Silicon DMG + ZIP, Linux x64 AppImage/DEB) in GitHub Actions without publishing. The all-target dispatch requires a clean working tree with the current branch pushed to `origin`, so CI builds the exact source revision. Add `--publish` only when the full matrix is ready; the workflow then creates the GitHub Release with checksums. See [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md).

## Troubleshooting

- **App shows a blank window:** the UI now has an error boundary and auto-reloads crashed renderers. Reload once; if it persists open `npm start` browser mode.
- **Download job failed:** update yt-dlp (`pip install -U yt-dlp`) and retry. The job error is shown in the toast and job tracker.
- **Model install failed:** open the linked official download page and check your connection; Ollama models require Ollama to be running.
- **Electron does not launch:** run `npm start` — it starts the same studio in your browser without Electron.

## License

MIT © 2026 — made by **analoggeek**.
