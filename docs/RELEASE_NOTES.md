# Release notes

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

Installers include the Electron UI, a PyInstaller Python runtime, FFmpeg and platform icons. Model packs are installed from the app's **Local Models** page.
