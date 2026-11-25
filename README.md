# CLIPOS 3.1.1 — Offline-first Video Clip Editor

**CLIPOS**, developed by **Analoggeek**, is a native desktop application for
turning long recordings into edited short-form videos. Import a recording,
select moments and framing, apply editing presets and captions, review the
rendered videos, and export the batch. Processing runs locally with **Python,
PySide6, Faster-Whisper and FFmpeg**—no mandatory cloud account or subscription.

**v3.1.1 release:** YouTube publishing/account connection and the separate
Gaming Studio 2.0 navigation have been removed; authorised URL import remains.

## Download v3.1.1

| Platform | Installer |
| --- | --- |
| Windows 10 / 11, x64 | [CLIPOS-Setup.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v3.1.1/CLIPOS-Setup.exe) |
| macOS, Apple Silicon | [Apple Silicon DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v3.1.1/CLIPOS-3.1.1-arm64.dmg) |
| macOS, Intel x86_64 | [Intel DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v3.1.1/CLIPOS-3.1.1-intel.dmg) |
| Debian / Ubuntu, amd64 | [DEB package](https://github.com/Analoggeek/AiFreeClipping/releases/download/v3.1.1/CLIPOS_3.1.1_amd64.deb) |
| Linux, x86_64 portable | [Portable ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v3.1.1/CLIPOS-3.1.1-linux-x86_64.zip) |

[All seven release assets, including macOS app archives](https://github.com/Analoggeek/AiFreeClipping/releases/tag/v3.1.1)
· [Release notes](RELEASE_NOTES.md)
· [Detailed workflow guide](docs/WORKFLOW_V25.md)

### Stability fix in 3.1.1

- Replace the legacy Intel macOS FFmpeg binary with pinned/checksummed 6.1.1.
- Stop importing the entire system font library into each caption render.
- On a native FFmpeg fault, retry the exact edit once with conservative scalar,
  single-worker settings; retain compatibility mode for the remaining session.
- Preserve existing successful exports and expose local crash diagnostics in
  Settings. Ordinary CLI/media errors and cancellation are not infinite retries.

### Included performance update from 3.1.0

- Runtime-probed AMD AMF plus hybrid-system QSV/NVENC selection; CPU fallback.
- Adaptive CPU budget up to 32 workers rather than an eight-thread ceiling,
  with memory/UI headroom, and faster default encoder presets.
- Long-form assembly now uses the same detected hardware policy as clip exports.
- Sampled lower-resolution scene analysis, lazy page construction, background
  hardware diagnostics, and corrected queued-task busy state.
- Transactional verified clip/timeline output protects earlier successful files.
- Removed the separate Multitrack workspace navigation; existing saved data is
  retained. Improved theme contrast without expensive blur/animation effects.

### Included from 3.0.0

- Native multitrack timeline improvements, linked audio/video editing, waveforms,
  keyframes, gestures, fades and conservative longform cleanup.
- Grounded automatic selection, source-wide candidate review, selected-range
  protection and optional local export-preference learning.
- Speaker-coloured captions, shot-held face framing and local OCR evidence.
- Optional loopback-only visual/intent models and local TalkNet/AST inference
  integrations; large optional runtimes/checkpoints are not bundled by default.
- Existing native editing, manual gaming regions, local data and offline-first
  workflow are preserved. No publishing/upload feature has been added.

See [release notes](RELEASE_NOTES.md) for installation details and acceptance
limits. This version number does not imply that the full PRO roadmap or native
physical-device/model-quality certification is complete.

## Contents

- [What is new in 2.5](#what-is-new-in-25)
- [Install and upgrade](#install-and-upgrade)
- [Create your first batch](#create-your-first-batch)
- [Studio layouts](#studio-layouts)
- [Application sections](#application-sections)
- [Local AI and models](#local-ai-and-models)
- [Mac and Windows performance](#mac-and-windows-performance)
- [Output and local data](#output-and-local-data)
- [URL import and privacy](#url-import-and-privacy)
- [Run from source](#run-from-source)
- [Build native installers](#build-native-installers)
- [Validation and limitations](#validation-and-limitations)
- [Troubleshooting](#troubleshooting)
- [Project structure and attribution](#project-structure-and-attribution)

## What is new in 2.5

- **One connected workflow:** Import → Select & style → Edit & review → Export,
  with a one-click automatic import/edit option.
- Source playback, playhead-based range selection and manual gameplay/player
  region drawing. Automatic facecam detection is available, with review/manual
  correction when recognition is uncertain.
- Four editing recipes—Clean Studio, Podcast Focus, Gameplay + Facecam and Story
  Highlight—plus eight caption styles, recipe thumbnails and real four-second
  composition previews.
- **11 studio layouts**, adjustable camera size, and shared composition settings
  across recipe previews, batch rendering and the advanced timeline.
- Review actual rendered MP4s and export checked clips together into
  `YYYY-MM-DD / recording name /`, with per-clip results and batch manifests.
- Fixed a reproduced caption-rendering defect in the ASS filename/`fontsdir`
  arguments. This does not establish the cause of every historical export failure.
- Shared project/settings updates, bounded render thread pools, reduced audio
  analysis memory use, native encoder selection and measured CPU/RAM usage.

## Install and upgrade

### macOS

Download the DMG matching your CPU (**Apple Silicon** or **Intel**), open it and
drag **CLIPOS** to **Applications**. App archives are also on the release page.
The Intel bundle is built and architecture-checked as x86_64, not renamed ARM.

Bundles are ad-hoc signed unless Developer ID signing is configured. Bundle
integrity checks are **not Apple notarization or Gatekeeper approval**. If macOS
blocks installation, follow your organisation's policy and Apple's official
application-verification guidance; do not disable system security.

### Windows

Download and run `CLIPOS-Setup.exe`, then launch CLIPOS from its shortcut.
The release does not include a Windows portable ZIP. Publisher/reputation
warnings may appear; verify the source and follow your system's security policy.

### Linux

On Debian / Ubuntu:

```bash
sudo apt install ./CLIPOS_3.1.1_amd64.deb
```

Alternatively, extract the Linux ZIP and launch the bundled executable on a
compatible desktop system. RPM/AppImage files are not included in this release.

### Existing projects

Quit CLIPOS before upgrading. Application data lives separately from the installed
binaries; upgrading is intended to preserve projects and settings. Back up
important data before any upgrade. Physical install/update testing on every
supported OS configuration has not been independently completed.

Installers include the Python runtime, dependencies, target-platform FFmpeg /
FFprobe and bundled face-detection resources. Speech models require a separate
one-time download; local editing works offline once required resources exist.

## Create your first batch

1. **AI models:** download a speech model if you want transcription/captions.
   Start with `base`, or `tiny` for a smaller/faster model. No transcript means no
   genuine speech captions; models are not simulated.
2. **Create clips → 1 Import:** choose a local video, or import an authorised
   supported URL. One-click mode uses the current editing preferences.
3. **2 Select & style:** play the source, add desired time ranges (or leave the
   whole recording selected), choose the recipe/caption style and draw real
   player/gameplay regions where necessary. For studio compositions, choose
   **Gameplay + Facecam**, then **Studio layout**. Use **Preview recipe** for a
   real short composition/colour render; speech captions are added during editing.
4. **3 Edit & review:** run **Edit all clips**. Analysis detects candidate moments,
   then the pipeline applies the selected edits and renders actual MP4s. Review
   the outputs and check the clips you want. Use **Advanced editor** for timeline
   split/trim, reorder, speed, crop/zoom, mute and undo/redo.
5. **4 Export:** choose a destination and export the checked edited clips together.
   If settings changed after rendering, re-edit before exporting so outputs match.

Automatic mode does not guarantee perfect crops, captions, highlights or
engagement. Review results before sharing; it is editing, not simply file cutting.

## Studio layouts

| Layout | Composition |
| --- | --- |
| Gameplay + face | Large gameplay above, smaller camera below—the existing default |
| Face + gameplay | Selected camera above gameplay |
| Blurred fill | Complete source over a blurred backdrop |
| Fill screen | Full-frame centre crop |
| Gameplay only | Selected gameplay area without a camera panel |
| Camera top-left / top-right | Floating selected camera in either upper corner |
| Camera bottom-left / bottom-right | Floating selected camera in either lower corner |
| Circle camera | Circular camera overlay above gameplay |
| Side by side | Camera and gameplay columns |

Camera proportion is adjustable from **20–50%**; overlay geometry is bounded by
the output dimensions. Missing camera detection falls back to gameplay rather
than inventing a facecam. Layout icons illustrate geometry, not finished footage.
The layout selector applies to the Gameplay preset; other recipes retain their
framing. Blur/circular masking may use more CPU than a simple stacked layout.

Layout geometry and FFmpeg graphs are adapted from the MIT-licensed
[DigiRG Cloud project](https://github.com/DIGIRGCLOUD/DIGIRGCLIPPINGFREE).
See [the review](docs/REFERENCE_FEATURE_REVIEW.md) and
[full attribution/license](THIRD_PARTY_NOTICES.md). Live monitoring, creator
recording and phone remote features were **not** imported.

## Application sections

| Sidebar section | Purpose |
| --- | --- |
| Create clips | Four-step import, selection/style, editing/review and export workflow |
| Projects | Find and reopen local projects |
| Clip library | Browse clips across projects |
| Advanced editor | Source timeline editing with saved edits and rendering |
| Presets & captions | Recipe and caption-style preferences/previews |
| AI models | Manage local speech models |
| Settings | Processing, speech language, captions, storage, privacy and hardware information |

## Local AI and models

Highlight detection combines measured audio energy, silence, speech/transcript
cues, scene changes and visual signals. Scores are deterministic heuristics,
**not predictions or guarantees of virality**. Title/hook suggestions use source
signals; an optional user-configured Ollama server can improve metadata, with a
rule-based fallback when unavailable.

Faster-Whisper uses CTranslate2: supported CUDA hardware or CPU int8. It does not
use PyTorch MPS on Macs. Model sizes and runtime memory vary; `tiny`/`base` favour
speed, while larger models cost more RAM and processing time. Download models
through **AI models**, then reuse them locally. PyTorch is not a required runtime
dependency.

## Mac and Windows performance

| Platform/capability | Encoding path |
| --- | --- |
| macOS Intel / Apple Silicon, available VideoToolbox | H.264 / HEVC VideoToolbox |
| Detected NVIDIA with available encoder | NVENC |
| Detected Intel Quick Sync with available encoder | QSV |
| Unsupported/unavailable accelerator | CPU `libx264` / `libx265` |

A failed hardware render retries with software encoding; errors remain visible
if that also fails. Hardware encoding does not mean every filter or AI operation
runs on the GPU.

- Automatic CPU pools reserve UI/OS headroom and cap at eight workers, or four
  on machines with 8 GiB RAM or less. At 85% live RAM usage, new automatic pools
  cap at two. Explicit thread settings are respected within detected CPU limits.
- Render child processes use below-normal priority on Windows and nice +5 on
  macOS/Linux, best effort; UI/playback priority is unchanged.
- Live available RAM includes unified-memory Macs. GPU core counts are not
  presented as VRAM. CPU/RAM usage is measured; GPU counters are shown only
  where supported.
- **Settings** shows detected hardware, selected auto encoder and the automatic
  thread budget. Low-memory mode is available.

Performance depends on source resolution, filters, model size, drivers, memory
and cooling. Native build success does not establish smooth playback on every
physical device or a particular frame rate.

## Output and local data

Output is MP4 with H.264 or H.265, configurable bitrate/frame rate, and AAC audio.
Standard aspect choices include 9:16, 1:1 and 16:9. Shared batch delivery uses:

```text
chosen destination/
└── YYYY-MM-DD/
    └── recording name/
        ├── clip files.mp4
        └── batch results/manifest
```

Default data locations:

| Platform | Location |
| --- | --- |
| macOS | `~/Library/Application Support/CLIPOS` |
| Windows | `%LOCALAPPDATA%\CLIPOS` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/clipos` |

This folder holds `clipos.db`, projects, media, models, cache, exports and logs.
The export destination is configurable. Keep the database **and referenced media**
when backing up projects.

## URL import and privacy

Local files need no network. Direct media links and supported public video URLs
use explicit download/import actions, including `yt-dlp` for supported sites.
You must own the recording or have permission. Private, paid, authenticated,
DRM-protected or blocked sources are not bypassed. Site/extractor changes can
cause download failures; local import remains available.

There is no mandatory account, subscription, telemetry or background media
upload. Explicit network features include media/model downloads and on-demand
GitHub update checks. Optional Ollama uses the configured server address; keep
it local if you want local-only metadata processing. Do not treat a preference
checkbox as an OS-level network firewall.

## Run from source

Python **3.11** is the native CI baseline. Use the dependency installer rather
than only `pip install -r requirements.txt`: it repairs overlapping OpenCV
packages and pins the compatible headless build.

```bash
git clone https://github.com/Analoggeek/AiFreeClipping.git
cd AiFreeClipping
python3 -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python scripts/install_deps.py --build
python scripts/vendor_ffmpeg.py
python scripts/vendor_cascades.py
python -m clipos
```

The vendor scripts fetch/verify native resources. FFmpeg binaries are kept out of
Git; internet is needed for dependency/resource setup. See the build scripts for
target-platform and architecture selection.

## Build native installers

Build on the target operating system with the matching interpreter/dependencies:

```bash
python scripts/build.py windows
python scripts/build.py macos --target-arch arm64
python scripts/build.py macos --target-arch x86_64
python scripts/build.py linux
python scripts/verify_bundle.py dist
```

`--target-arch` is not a promise that an arbitrary interpreter can cross-build:
Intel Mac packaging needs an isolated x86_64 Python/dependency environment.
See `scripts/setup_intel_python.sh` and `scripts/verify_python_arch.py`.

GitHub Actions uses **windows-2022**, **macos-15** and **ubuntu-22.04**. macOS CI
builds Apple Silicon and isolated Intel bundles, verifies architecture/integrity,
and preserves application permissions/symlinks in release archives.

- [`build-installers.yml`](.github/workflows/build-installers.yml): native build
  checks and downloadable artifacts for main/PR/tag events or manual dispatch.
- [`release.yml`](.github/workflows/release.yml): tag/manual release builds;
  publication requires successful platform builds, not a partial installer set.
- [`macos-integrity.yml`](.github/workflows/macos-integrity.yml): packaging tests
  and diagnostic recovery.

## Validation and limitations

For the v3.0.0 baseline source:

- Local full suite: **579 passed, 10 skipped**; E2E: **35/35 passed**.
- Trained OCR inference is tested; TalkNet/AST runtime tests use random weights,
  not trained-model quality evidence. See the release notes for optional-runtime
  and hardware limitations.

Earlier v2.5.1 validation:
- Real GUI source-region drags, persistence, source playback, pixel-checked recipe
  rendering and playable delivery after changed controls have regression tests.
- [Native v2.5.1 release checks](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45376503798)
  passed Windows, macOS Intel/Apple Silicon and Linux; all seven assets uploaded.
  Windows/macOS CI requires real Qt source-frame playback, not a mocked player.

Earlier v2.5.0 validation:

- Local full suite: **263 passed, 8 skipped**.
- Real FFmpeg tests cover five-clip captioned batch export, GUI
  import/edit/review/delivery, every studio layout, and representative captioned
  multi-segment timelines. End-to-end checks: **35/35 passed** locally.
- [Native installer checks](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45343458484)
  passed Windows, macOS Intel/Apple Silicon and Linux.
- [Release pipeline](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45345465476)
  succeeded after retrying Windows build-tools setup; all seven assets uploaded.

These checks do **not** replace physical-device install/update, thermal,
driver-specific playback, live-source network import or full speech-model
accuracy testing. Automatic detection remains heuristic; no guaranteed
engagement, genuine HDR conversion, universal GPU support or native OS blur is
claimed.

For development:

```bash
python -m pytest tests/ -q
python scripts/e2e_test.py
python scripts/verify_bundle.py dist
```

For minimal Linux test containers, generate GL stubs and use a headless Qt platform
(only for tests, not desktop playback):

```bash
python scripts/build_gl_stubs.py
LD_LIBRARY_PATH="$PWD/.stublibs:${LD_LIBRARY_PATH:-}" QT_QPA_PLATFORM=minimal \
  python -m pytest tests/ -q
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Clip render/export failed | Read the per-clip error and `<data dir>/logs/clipos.log`; share logs rather than assuming the cause. |
| No captions | Confirm a speech model is installed, transcription succeeded and burn-in captions are enabled. |
| Wrong player/gameplay framing | Draw the actual regions in Select & style and re-edit; review the real recipe preview. |
| Export blocked after changing settings | Re-edit the batch so the rendered files match the new settings. |
| High CPU or memory usage | Try a smaller speech model, fewer threads/low-memory mode and a simpler layout. |
| GPU encoder unavailable/fails | Use CPU fallback and inspect the reported warning; accelerator availability depends on drivers/hardware. |
| Embedded preview fails | Use Open in player to inspect the preserved rendered file; report OS/driver and logs. |
| Source checkout cannot find FFmpeg | Run `python scripts/vendor_ffmpeg.py`. |
| OS blocks installation | Verify the release source and follow official OS security guidance; do not disable security protections. |

Include app version, OS, CPU/GPU, source resolution, selected recipe/layout and
relevant logs in an issue. Avoid sharing private media/transcripts unnecessarily.

## Project structure and attribution

```text
clipos/
├── core/       Paths, shared editing preferences, FFmpeg, hardware, logging
├── db/         Local SQLite projects, clips, settings and export records
├── ai/         Audio/visual analysis, transcription, clip and metadata generation
├── captions/   Word-timed ASS caption cues and styles
├── video/      Import, recipes/layouts, timeline, rendering, pipeline and delivery
└── ui/         Native Qt pages, playback, crop selector, previews and usage display
resources/      Native binaries and bundled model/assets
scripts/        Dependency setup, vendor, test, build and bundle verification tools
tests/          Unit, GUI, real rendering and architecture regressions
docs/           Workflow/reference guides and the existing download website
```

[Website documentation](docs/README.md) describes the separate static download
site; updating the README does not redesign or republish that site.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the DigiRG Cloud layout
adaptation's full MIT notice. FFmpeg distributions have their own LGPL/GPL terms;
YuNet models originate in OpenCV Zoo and Haar cascade resources in OpenCV.
Review the corresponding upstream licenses when redistributing dependencies.
