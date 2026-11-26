# Release notes

## v5.1.1 — reliable startup & redesigned site

- **Startup fixed:** added a browser studio launcher (`npm start`) that works without Electron; `npm run dev:app` now falls back to it automatically when the Electron binary is unavailable. Vite accepts proxied preview hosts.
- **Packaged app fix:** the Windows/macOS/Linux engine binary is now matched by both platform **and** architecture, so x64 and ARM64 installers no longer pick the wrong bundled runtime.
- **Website redesigned:** a new immersive static site with an animated hero, bento feature grid, interactive screenshot tabs, tech marquee, hardware section, model/API links and direct installer downloads.
- **Clearer docs:** README and installation guide now lead with the one-command browser start.

## v5.1.0 — 3D studio, one-click model setup & hardware awareness

- **One-click model setup:** every local model card now has a real download URL and a one-click installer that saves weights into `~/.AiFreeClipping/cache`. Cloud models show a direct **Get API key** button (Gemini/Nano Banana, YouTube, Pexels, Pixabay).
- **YOLOX without Torch:** the packaged app downloads the 4 MB YOLOX Nano ONNX model and runs it with OpenCV DNN + the built-in ByteTrack-style tracker. Gemma/Whisper/YOLOX all work offline after the first download.
- **Hardware HUD:** the dashboard and Models page show live CPU, RAM, disk, GPU/encoder and parallel-worker counts. Per-clip render results record the exact hardware used and can be copied with one click.
- **Copy effects to all:** tune one clip, then press **Copy effects to all** to apply the same captions, SFX, speed, color, aspect and reframing settings to every candidate in one request.
- **Fully optimized exports:** batch renders now run in parallel (configurable with `RENDER_WORKERS`), ffmpeg uses all available threads, and NVENC / VideoToolbox is selected automatically when available.
- **New 3D identity:** redesigned neon 3D clapperboard logo across the desktop app, packaging icons and website.
- **Animated responsive website:** a fully static, animated marketing site with live release download links, model/API links and interface screenshots.
- **App polish:** motion, 3D hover depth, focus states, model cards and mobile/desktop responsive layouts throughout.

## v5.0.0 — complete local AI studio

The first full release of **AI Clipper Pro — made by analoggeek**.

### Highlights

- **Downloader:** highest-quality single downloads and full playlists with item selection, subtitles, custom folders and a persistent local media library.
- **AI discovery:** faster-whisper word timings, YOLOX/YOLO11 + ByteTrack activity tracking and Gemma 2 7B reranking combine into ranked viral clip candidates. Player/gameplay region selection is supported.
- **Enhancements:** auto captions with four presets, procedural royalty-free sound effects, stickers, music beds, 9:16 blurred-background reframing, speed/color controls and branding.
- **Editor:** CapCut-style multi-track timeline with split/trim/inspector, local imports, copyright-friendly stock search (Pexels/Pixabay/Openverse), Nano Banana or local ComfyUI SDXL image generation and keyboard shortcuts.
- **Publishing:** one-click 1080p batch export with `+faststart`, downloadable MP4s and optional resumable YouTube uploads through the user's own OAuth app.
- **Release automation:** one-command installer builds for Windows x64/ARM64, macOS Intel/Apple Silicon and Linux x64 via `scripts/release-all.sh` and the GitHub Actions matrix, with SHA256 checksums.

### Offline behavior

The engine binds to `127.0.0.1` with a per-launch token. Model weights download once, then inference, clipping, editing and rendering work offline. Cloud features are opt-in and use user-supplied keys.

### Installers

| Platform | Artifact |
|---|---|
| Windows x64 / ARM64 | `AI-Clipper-Pro-5.0.0-Windows-x64.exe`, `...-arm64.exe` |
| macOS Intel | `AI-Clipper-Pro-5.0.0-macOS-x64.dmg` |
| macOS Apple Silicon | `AI-Clipper-Pro-5.0.0-macOS-arm64.dmg` |
| Linux x64 | `AI-Clipper-Pro-5.0.0-Linux-x64.AppImage`, `...-x64.deb` |

Installers include the Electron UI, a slim PyInstaller Python runtime, FFmpeg and platform icons. Speech and Gemma model packs are installed from the app's **Local Models** page; Torch-based YOLO vision is available in source installs via `backend/requirements-vision.txt`, while packaged builds use the built-in local motion detector until a vision model is supplied.
