# Roadmap

## Shipped in v6.0.1 — more responsive, reliable rendering

- Bound Auto Edit and batch-export concurrency to a shared CPU budget, including FFmpeg codec and filter-graph threads
- Reduce blur-fill cost by blurring a downscaled background while retaining a full-resolution foreground
- Stream finished Auto Edit clips into the editable timeline, continue after per-clip render failures, and support stopping a batch without discarding completed work
- Add large-batch confirmation, faster-resolution guidance and performance regressions

## Shipped in v6.0.0

- Retire caption/subtitle editing, subtitle download, social-copy fields and text-overlay rendering while retaining Whisper internally for transcript-aware clip scoring
- Remove YouTube OAuth and channel uploads; preserve YouTube as a source-download site through yt-dlp
- Preserve remaining video/sticker/audio timeline editing, composition controls, Auto Edit and MP4 export, including safe cleanup of legacy project metadata
- Publish and verify all eight release artifacts across Windows x64/ARM64, macOS Intel/Apple Silicon DMG/ZIP and Linux x64 AppImage/DEB

## Carried forward from the superseded v5.2.7 candidate — not released as v5.2.7

- Confirmed, reference-safe clearing of app-managed downloads from the effective folder; imported originals and still-referenced files/library entries are retained
- Flexible timeline insertion at the playhead or a drag-selected point, clip reordering and movable overlays with linked timing preserved
- Ollama v0.40.19 asset mapping and streaming Linux `.tar.zst` extraction, covered by mocked platform/model-install tests
- Installer compression tuned where supported; Windows, macOS and Linux targets unchanged and macOS DMGs kept as UDRO
- No v5.2.7 GitHub Release or release assets published

## Shipped in v5.2.6 (historical; caption features retired in v6.0.0)

- Offline Whisper captions reuse cached transcripts, map word-level timings onto matching timeline clips, and keep each word editable
- Preserve the caption-template design while exposing 136 selectable looks and 44 font families in the Inspector
- Drag-resize the Media, Shorts preview, Inspector and Timeline panels; resize the Shorts player directly and reset saved layout dimensions from the top bar
- Reuse caption style, placement and size in Auto Edit without carrying over aspect ratio or resolution

## Shipped in v5.2.5

- Rebuild all Windows, macOS, and Linux installers together, validate each platform's native package format, and verify every published artifact against its SHA-256 manifest
- Build exactly one Windows/macOS architecture per matrix job to keep the bundled local engine matched to the installer target
- Confirm the Electron Framework binary and executable load reference survive both DMG and ZIP installation paths on Intel and Apple Silicon; preserve UDRO images and direct ZIP alternatives

## Shipped in v5.2.4

- macOS installers use read-only uncompressed UDRO disk images with format, mount, and app-copy verification; matching SHA-256 checksums are published
- Intel and Apple Silicon macOS ZIP installers are linked as direct alternatives; documentation explains checksum recovery for unreadable images

## Shipped in v5.2.3

- Player/gameplay split proportions and clean/neon/double/none outlines shared across browser composition preview and FFmpeg renders
- Transcript-grounded, user-editable social captions and title hooks, with four selectable burned-in caption styles
- Per-clip composition, caption and visual settings retained in batch and timeline export paths
- Persistent day/night theme, in-video Editor playhead overlay and app-icon front-screen branding
- RAM/GPU-memory-aware Whisper and Gemma recommendations; compact YOLOX remains enabled and SDXL is no longer part of automatic setup

## Shipped in v5.2.2

- Editor asset panel now contains only Clips and Media, with Stock, AI Art and SFX shortcuts removed
- Selecting an AI clip previews it immediately and replaces the existing video selection on the timeline
- Import local video files from Media and add them to the editable timeline
- Opening a clip from Clipper no longer creates a duplicate Editor project

## Shipped in v5.2.1

- Clipper removes stale media IDs from its selection when the library refreshes and revalidates before analysis
- Clip proposal skips deleted IDs when other selected sources remain, with actionable warnings or a clear empty-selection error

## Shipped in v5.2.0

- Optional full-frame portrait reframing from local ByteTrack detections, with steadier subject framing and cut-boundary snaps
- Candidate-local crop paths carried through render, Auto Edit, batch, timeline export and the Editor preview
- Vision sampling spread across long sources within a fixed analysis budget
- Existing manual regions, multi-panel layouts and no-tracking fallback preserved

## Shipped in v5.1.8

- Auto Edit action beside Export, with saved preferences in Settings
- Editable Auto Edit recipes for video, captions, music/SFX, stickers and source crops
- Speed-aware Editor playback with matching timeline render effects
- Media-library removal control and immediate UI cleanup
- Three-option AI art generation with visible provider failures and no silent decorative fallback
- Player/gameplay order and crops preserved through discovery, preview and export
- Editor copy cleaned of the requested local-save and mode labels

## Shipped in v5.1.7

- Shared crop/composition logic for accurate Editor/Clipper previews and renders
- Source-quality defaults and configurable resolution/aspect across clip and batch exports
- Date-organized export folders under the user's selected destination
- Auto Edit fallbacks for missing sources and transcription errors, with saved captions and effects retained for batch export
- Persisted local model/voice selections and local weights across app restarts
- Branded splash screen and automatic dismissal for completed operations
- No app watermark by default; user-configured channel logos remain optional

## Shipped in v5.1.6

- Live crop preview and source-aspect-aware drag regions applied to clip and timeline renders
- Generated-clip list in the Editor with click-to-add timeline workflow
- Explicit download removal with protection for imported, duplicate and project-referenced sources
- Existing SDXL checkpoint selection and configurable ComfyUI checkpoint folder
- Neutral-contrast Rec.709 H.264/AAC MP4s, with optional custom channel watermark and no default app logo
- Explicit MP4 download filenames and QuickTime-friendly output metadata
- Export view supports Select all, rendered-only selection, bulk export and shared-file-safe deletion
- Scrollable borderless Operations widget with cancellation and dismissal controls
- Cancellation cleanup, unique export names and regression tests for these failure paths

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
- [ ] Code-signed/notarized installers when developer certificates are available
- [ ] Dedicated model-pack installer with resumable offline mirrors

Feature requests and PRs welcome at github.com/Analoggeek/AiFreeClipping.
