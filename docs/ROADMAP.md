# Roadmap

## Shipped in v5.1.4

- Crash-proof Settings view and normalized folder responses
- Bundled CA certificates for SSL-safe model/media downloads
- User-selectable model, download and rendered-clip folders
- Hardware-aware unattended offline model setup with live progress
- Exact requested clip count across non-overlapping windows
- Automatic edit section with direct clip rendering and focus crops
- Zero-based synchronized timeline and free mouse scrubbing
- Live operation lines and app-folder storage in the sidebar HUD
- Offline image fallback when SDXL/Nano Banana are unavailable

## Shipped in v5.1.3

- Instant splash screen and route-level lazy loading for a fast first paint
- Fully automatic model runtime download, install, activation and settings save
- Multiple focus regions per clip (player + gameplay layouts) fused into AI scoring
- Icon-only timeline toolbar and synchronized playhead/playback controls
- Cleaner macOS DMG/ZIP builds with CI copy verification

## Shipped in v5.1.2

- Legacy-safe job progress updates and reliable download jobs
- Direct in-app model download/install with working external links
- Renderer crash recovery and compact sidebar hardware HUD
- Real app version display and refined small 3D logo
- Marketing website moved to repository root and README rewritten

## Shipped in v5.1.1

- Reliable browser start (`npm start`) with Electron fallback
- Correct platform + architecture matching for bundled engine binaries
- Fully redesigned animated static website with interactive screenshot tabs

## Shipped in v5.1.0

- One-click model downloads and direct API-key links inside the app
- YOLOX ONNX + ByteTrack inside packaged builds (no Torch required)
- Live hardware HUD, per-clip render telemetry and copy-to-all effects
- Parallel hardware-aware batch exports
- Redesigned 3D brand identity, animated app UI and animated static website

## Shipped in v5.0.0

- Link/playlist downloader with max-quality selection and local library
- Whisper + YOLO/YOLOX + ByteTrack engagement scoring with Gemma reranking
- Multi-clip discovery with player/gameplay region selection
- Captions, procedural SFX, stickers, music, vertical reframing and watermark
- CapCut-style timeline editor with import, stock search and AI image generation
- One-click batch export and optional YouTube upload
- Single-command release automation for Windows, macOS Intel/Apple Silicon and Linux

## Next

- [ ] GPU-assisted preview rendering and proxy workflow for 4K sources
- [ ] Native Apple Silicon Metal acceleration toggle for Whisper/YOLO
- [ ] Keyframe animation and masking in the editor
- [ ] Multi-language caption translation with local Gemma
- [ ] Viral-score analytics feedback loop from YouTube Analytics (opt-in)
- [ ] Scheduled publishing queue with rate-limit-aware batching
- [ ] Code-signed/notarized installers when developer certificates are available
- [ ] Dedicated model-pack installer with resumable offline mirrors

Feature requests and PRs welcome at github.com/Analoggeek/AiFreeClipping.
