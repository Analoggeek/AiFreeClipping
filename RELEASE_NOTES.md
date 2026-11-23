# CLIPOS 1.1.1 — macOS installer integrity fix

By **Analoggeek**.

## macOS Intel and Apple Silicon

- Re-sign the final application after plist/icon changes, fixing a packaging
  defect that could invalidate the app signature.
- Require strict signature verification before packaging.
- Verify the actual DMG checksum and the mounted app signature, executable
  permissions and CPU architecture.
- Correct optional Apple notarization ZIP submission and ticket stapling.

The fix passed native Intel and Apple Silicon signature/DMG regression checks
and full Windows, Linux and macOS installer CI before release preparation.
Release installers are rebuilt and verified separately by the release workflow.

**Important:** these builds use ad-hoc signing unless a Developer ID identity is
configured. Valid bundle integrity is **not** Apple notarization or Gatekeeper
approval. A developer-verification warning may still occur; this release does
not claim to resolve every Gatekeeper or older-macOS compatibility error.
Do not disable Gatekeeper globally. See
[macOS installation diagnostics](https://github.com/Analoggeek/AiFreeClipping/blob/main/docs/MACOS_INSTALLATION.md).

## Downloads

- Intel Mac: `CLIPOS-1.1.1-intel.dmg`
- Apple Silicon Mac: `CLIPOS-1.1.1-arm64.dmg`
- Windows 10/11: `CLIPOS-Setup.exe`
- Linux x86_64: DEB or portable ZIP
- Both macOS `.app` archives are also available.

Back up important projects before updating. Application data is stored separately
from the app binaries. Speech models require a one-time download; public-video
imports and update checks require internet. No engagement guarantees.

---

# CLIPOS 1.1.0 — Creator workflow update

By **Analoggeek**.

- Restored persistent timeline edits in batch exports; corrected crop, zoom,
  mute, caption retiming and hardware-to-CPU recovery without discarding edits.
- Offline clean, podcast, gaming and story recipes; configurable gameplay-above,
  facecam-below composition and real four-second draft previews.
- Permission-confirmed public YouTube imports via yt-dlp, highest available
  streams; no DRM, login or access-control bypass.
- Refreshed native theme, navigation icons and app logo.
- Opt-in GitHub update checks and compatible installer downloads. Installation
  remains manual, not a silent self-updater. Project data is separate from app
  binaries; back up important projects before upgrading.
- Public static download website under `docs/` with Analoggeek branding.
- Isolated Intel wheels and architecture verification; no partial release may
  publish as latest if any platform's build fails.

Validation: 182 local tests and 35 real-video E2E checks passed before release.
Native CI results must be checked separately. Physical Mac/Windows upgrade tests,
real-time compositing, live YouTube downloads and full offline speech-model runs
are not certified. Recipes are deterministic, not newly trained AI weights.
Engagement or virality is not guaranteed.

---

# CLIPOS 1.0.0 — AI Automatic Video Clipping Studio

**CLIPOS** is a native, offline-first desktop application that turns a long video
into upload-ready short-form clips. It runs entirely on your own machine: import
a file, let the local AI find the engaging moments, and export finished vertical
videos with captions, reframing, zoom and metadata — with no cloud account and
no upload of your media.

Built with **Python** (AI + video pipeline) and **PySide6** (native desktop UI).
Ships with genuine **FFmpeg/FFprobe** binaries for macOS (Intel + Apple Silicon)
and Windows 10/11.

## Downloads

| Platform | File | Notes |
|---|---|---|
| Windows 10/11 | `CLIPOS-Setup.exe` | Native installer, installs and runs offline |
| macOS (Apple Silicon) | `CLIPOS-arm64.dmg` | Drag the app to Applications |
| macOS (Intel) | `CLIPOS-intel.dmg` | Drag the app to Applications |
| Linux | `CLIPOS_1.0.0_amd64.deb` | Debian / Ubuntu |

## The five headline features

- **Virality Score** — every clip gets a 0–100 score for engagement potential.
- **Auto Hook Generator** — a hook suggestion for the first one to three seconds.
- **Multi-Clip Mode** — ten to twenty different shorts from one source.
- **Speaker Tracking** — the frame follows whoever is speaking.
- **One-Click Editing** — the AI produces a ready-to-upload video.

## Everything else

- Eleven working pages: Home, New Project, Auto Clip Studio, My Projects, Clip
  Library, Templates, Caption Studio, Preview Editor, Export Center, AI Models
  and Settings.
- Real transcription with Faster-Whisper, real face detection, real scene
  detection, real rendering. Nothing is simulated.
- Clip detection weighs speech, keywords, emotion, questions, storytelling,
  facts, humour, reactions, topic and scene changes, energy, pauses and
  semantic context.
- Nine caption styles with word-by-word highlighting, punctuation, sizing,
  colour and placement.
- A preview editor with a timeline, waveform, tracks, trim, split, merge, crop,
  resize, speed, zoom, frame navigation and undo/redo.
- Batch export with H.264 and H.265, 1080×1920, 30 and 60 FPS, a configurable
  bitrate, AAC audio, a queue, cancellation and a history.
- Real thumbnail generation with three templates.
- Hardware detection for NVENC, Apple Silicon, Quick Sync and CPU fallback,
  with the RAM, the GPU, the thread count and a low-memory mode all visible.
- A model manager with downloads, progress, sizes, enable/disable, removal and
  an offline availability indicator.

## Privacy

Everything stays on your machine. There is no account, no subscription, no
automatic upload and no background transmission of your media. The application
works fully offline once the speech-to-text model has been downloaded once.

## Notes

- The first run needs an internet connection **only** to download the
  speech-to-text model. After that everything happens locally.
- A message about blocked URLs is shown plainly when a link cannot be
  imported; importing the file locally always works.
- Logs are written to the application data folder and are listed in the
  Troubleshooting section of the README.

## Building from source

See the *Building from source* and *Building installers* sections of the
README. The test suite is:

```
python -m pytest tests/ -q
```
