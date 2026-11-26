# Release notes

## v5.1.4 — crash-proof settings, user folders and automatic editing

### Download the installers

GitHub keeps binaries in the collapsible **Assets** section at the bottom of this release. These links go straight to the files:

- **Windows x64:** [AI-Clipper-Pro-5.1.4-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.1.4-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.1.4-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.1.4-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/manifest.json)

### Changes

- **No more Settings crash:** folder/settings responses are normalized before rendering, so a missing or null value can never break the view.
- **No more SSL download failures:** every in-app HTTPS request now uses the bundled `certifi` CA store with a standard-library fallback, so model and media downloads work behind custom certificate chains.
- **Choose your folders:** Models, Downloads and Rendered clips can each be pointed at any folder you own with a native folder picker; model weights and runtimes honor the chosen location.
- **Hardware-aware auto setup:** on first launch the app detects RAM/GPU and downloads, activates and saves the best offline model pack automatically, with one visible progress line per action.
- **Exact clip counts:** the AI scorer keeps searching non-overlapping windows and enforces the requested number of clips across all selected videos.
- **Automatic edit section:** cut clips appear immediately in the editor, where you can auto-edit all of them (images, captions, motion, SFX, crop focus) or render any single clip directly.
- **True timeline sync:** a fixed track-label gutter and zero-based ruler make the playhead, scrubbing and the starting line agree at every zoom level; the mouse can scrub anywhere along the timeline.
- **Storage HUD:** app-folder usage appears beside the hardware meters, and live operation progress appears directly under the navigation.

## v5.1.3 — automatic models, faster startup, pro timeline and multi-region AI

### Download the installers

GitHub keeps binaries in the collapsible **Assets** section at the bottom of this release. These links go straight to the files:

- **Windows x64:** [AI-Clipper-Pro-5.1.3-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.1.3-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.1.3-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.1.3-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/manifest.json)

### Changes

- **Instant startup:** the desktop app now shows an animated splash immediately and loads the React workspace in lazy route chunks while the local engine boots in the background.
- **Fully automatic models:** one click now downloads, installs, activates and saves the model. Ollama itself is downloaded and started automatically for Gemma; Whisper, YOLOX, Piper and SDXL save into `~/.AiFreeClipping` and become the active model in Settings. A **Set up all recommended** button does the whole pipeline in one job.
- **Multi-region AI clipping:** mark several focus areas in the same video — gameplay above/player below, player above/gameplay below, square player over full gameplay, or side-by-side. Video is decoded once, all selected regions are scored, and the AI picks moments using the fused activity.
- **Professional editor:** all editing actions are icon-only in the timeline toolbar; play/pause and 5-second jump controls sit directly below the preview; the playhead scrubs in sync with the ruler and tracks and auto-scrolls with zoom.
- **macOS reliability:** DMGs and ZIPs are built without signing, stripped of AppleDouble/extended-attribute metadata, and verified in CI by mounting and copying the bundle.

## v5.1.2 — stable downloads, compact HUD and root-level site

- **Downloader fixed:** `JobManager.update()` now accepts positional progress/message arguments, so any legacy progress callback works. Download jobs no longer fail mid-run.
- **Model downloads fixed:** the primary card button now downloads **and** installs directly in the app; external links use Electron's proper `openExternal` handler. API-key status reflects keys saved in Settings.
- **Blank-screen guard:** React error boundary plus Electron renderer recovery reloads a crashed view instead of leaving an empty window.
- **Correct version:** the sidebar and health endpoint now show the real app version (from `package.json` / Electron), not `1.0.0`.
- **Cleaner layout:** live hardware usage moved into a compact sidebar panel below Settings and above the version line; duplicate center panels removed. App logo is now a small refined 3D mark.
- **Website at repository root:** the animated marketing site is now `index.html`, `site.css`, `site.js` and `assets/` at the repo root; the React app entry is `app.html`. Site rebuilt with clearer sections and direct installer links.
- **README rewritten:** quick start, model table, hardware tips, structure and troubleshooting in one place.

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
