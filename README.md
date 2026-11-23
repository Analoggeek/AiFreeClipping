# CLIPOS — AI Automatic Video Clipping Studio

**CLIPOS** is a native, offline-first desktop application that turns a long video
into upload-ready short-form clips. It runs entirely on your own machine: import
a file, let the local AI find the engaging moments, and export finished vertical
videos with captions, reframing, zoom and metadata — with no cloud account and
no automatic upload of your media. Optional YouTube publishing in v2 requires
explicit account authorization and upload confirmation.

Built with **Python** (AI + video pipeline) and **PySide6** (native desktop UI).
Ships with genuine **FFmpeg/FFprobe** binaries for macOS (Intel + Apple Silicon)
and Windows 10/11.

---

## New in 2.0.0 — Gaming Studio

Gaming Studio opens by default: authorized link/local video → one-click edit and
render → real MP4 playback → optional, user-confirmed YouTube upload. Automatic
face-based player/gameplay composition, clean split-position captions, optional
SDR clarity and glass-style native UI are included. No face found means
 gameplay-only, not an invented player. See the [complete setup and limitations](docs/GAMING_V2.md),
including Google Desktop OAuth setup, secure keychain requirements and upload restrictions.
No engagement guarantees; this is not genuine HDR or native OS background blur.

## Table of contents

- [What it does](#what-it-does)
- [The five headline features](#the-five-headline-features)
- [Screens](#screens)
- [Install](#install)
- [First run](#first-run)
- [Where your data lives](#where-your-data-lives)
- [How the AI works](#how-the-ai-works)
- [Output formats](#output-formats)
- [URL import — what works and what does not](#url-import--what-works-and-what-does-not)
- [Model manager](#model-manager)
- [Hardware acceleration](#hardware-acceleration)
- [Building from source](#building-from-source)
- [Building installers](#building-installers)
- [Development](#development)
- [Troubleshooting and logs](#troubleshooting-and-logs)
- [Privacy](#privacy)
- [Project layout](#project-layout)

---

## What it does

1. **Import** a local video (`MP4`, `MOV`, `MKV`, `AVI`, `WEBM`, `M4V`) by browsing
   or dragging and dropping, or paste a direct media URL.
2. **Analyse** the whole video locally — speech, audio energy, silence, scenes,
   faces, subject tracking.
3. **Detect** the engaging moments, rank them, and explain *why* each one was picked.
4. **Generate** metadata: five titles, a description, hashtags, keywords and
   thumbnail text.
5. **Edit**: auto-reframe to 9:16 / 1:1 / 16:9 with speaker-aware cropping,
   dynamic zoom, jump cuts over silence, colour and audio enhancement.
6. **Caption** with synchronised, word-highlighted subtitles in eight styles.
7. **Export** batch MP4s (H.264 / H.265, 1080×1920, 30/60 fps, configurable
   bitrate, AAC) ready for YouTube Shorts, Instagram Reels and TikTok.

---

## The five headline features

| Feature | What it does |
| --- | --- |
| **Virality Score** | Every clip gets a 0–100 shareability score, computed from hook strength, surprise, emotion, humour, questions, keyword density, audio energy, storytelling and length fit. It is a real weighted formula over measured signals — not a placeholder. |
| **Auto Hook Generator** | For each clip, CLIPOS proposes concrete openings for the first 1–3 seconds (open on the punchline, cold open on the hook line, lead with the question), derived from the clip's own transcript and signals. |
| **Multi-Clip Mode** | Ask for 5, 10, 15 or 20+ shorts from one source. Overlap suppression stops the detector from returning the same moment repeatedly, and it will return fewer clips rather than pad the list with duplicates. |
| **Speaker Tracking** | Faces are detected with YuNet, clustered into people, and attributed speaking time from the audio. The reframe follows the person who is actually talking, so a two-person podcast stays on the right face. |
| **One-Click Editing** | `Auto Clip Studio → One-Click Edit` runs the entire chain unattended — analyse, cut, caption, reframe, render, export — and writes finished MP4s to your output folder. |

---

## Screens

The application has eleven sections, all reachable from the left sidebar:

| Section | What it does |
| --- | --- |
| **Home** | Dashboard with live SQLite statistics, recent projects, model status, hardware usage and the export queue. |
| **New Project** | Drag-and-drop import, URL import, real metadata preview, project creation. |
| **Auto Clip Studio** | Run the analysis, review the ranked clips, read the rationale, see the hooks and titles, render or export. |
| **My Projects** | Search, open, rename, duplicate and delete projects. |
| **Clip Library** | Every clip from every project, searchable and sortable by virality, engagement and date. |
| **Templates** | Presets for YouTube Shorts, Instagram Reels and TikTok, plus caption-style previews. |
| **Caption Studio** | Live animated preview of all eight caption styles, with font, size, position, stroke, shadow and background controls. |
| **Preview Editor** | Timeline with waveform, split, trim, merge, reorder, speed, zoom, crop, mute, undo/redo and frame-by-frame navigation. |
| **Export Center** | Batch export with a real queue, live progress, cancellation, output folder picker and export history. |
| **AI Models** | Download, enable, disable and remove speech-to-text models; monitor the cache. |
| **Settings** | Theme, language, defaults, caption style, Ollama, storage, privacy and hardware status. |

---

## Install

CLIPOS ships as a **native offline installer** for each platform. Installing
it needs no internet connection: the package carries the application, the
Python runtime, FFmpeg, the face-detection models and the sound effects.

### macOS (Intel or Apple Silicon)

1. Download the `.dmg` (or the `.app` bundle) for your architecture.
2. Open the `.dmg` and drag **CLIPOS** into your `Applications` folder.
3. Right-click the app once and choose **Open** the first time — macOS Gatekeeper
   blocks unnotarised apps until you do this.
4. Launch **CLIPOS**.

### Windows 10 / 11

1. Download `CLIPOS-Setup.exe` (installer) or the portable zip.
2. Run the installer. It creates a Start-menu shortcut and a desktop icon.
3. Launch **CLIPOS**.

> Windows SmartScreen may warn about an unknown publisher on first run. Choose
> **More info → Run anyway** — the app is unsigned.

### Linux (Debian / Ubuntu)

```bash
sudo apt install ./CLIPOS_1.0.0_amd64.deb
```

That installs the app into `/opt/CLIPOS` and adds a **CLIPOS** entry to your
application menu, with a desktop icon. To remove it:

```bash
sudo apt remove clipos
```

### Linux (Fedora / RHEL / openSUSE)

```bash
sudo dnf install ./CLIPOS-1.0.0-1.x86_64.rpm
```

### Linux (no package manager)

Download the portable zip, unpack it anywhere and run `CLIPOS` from the
`CLIPOS/` folder. Everything it needs is inside — no system libraries beyond
the usual desktop ones.

### What the installers contain

* The complete Python runtime and all Python dependencies.
* Genuine **FFmpeg** and **FFprobe** binaries for the target platform.
* The **YuNet** face-detection models and the **Haar** cascade fallbacks.
* The eight caption styles and the UI design system.

The only thing you download separately is the speech-to-text model (see
[Model manager](#model-manager)). After that one download, the whole workflow
runs offline.

---

## First run

1. Open **AI Models** and download a speech-to-text model.
   * `tiny` — ~75 MB, fastest, good enough for hook detection.
   * `base` — ~145 MB, noticeably better wording. **Recommended.**
   * `small` — ~480 MB, best accuracy; needs ~2 GB of RAM while running.
2. Open **New Project** and drag in a video.
3. Press **Generate Clips with AI** in **Auto Clip Studio**.
4. Review the ranked clips, then press **One-Click Edit** to produce finished
   videos, or **Export All** to batch-render them.

Everything after the model download works with the network switched off.

---

## Where your data lives

| Platform | Location |
| --- | --- |
| macOS | `~/Library/Application Support/CLIPOS` |
| Windows | `%LOCALAPPDATA%\CLIPOS` |
| Linux | `~/.local/share/clipos` |

Inside that folder:

```
CLIPOS/
├── clipos.db          SQLite database: projects, clips, transcripts, exports, settings
├── projects/          Per-project work folders (thumbnails, captions, render artefacts)
├── media/             Imported source files
├── models/            Downloaded speech-to-text models
├── cache/             Temporary WAVs, extracted frames, render scratch space
├── exports/           Finished clips (the default output folder)
├── logs/              Rotating application logs
└── fonts/  sounds/  music/   Optional local assets
```

Nothing is uploaded. There is no account, no subscription, and no telemetry.
The only outbound requests CLIPOS ever makes are:

* downloading a speech-to-text model, when you ask it to;
* downloading a media file, when you paste a direct URL to import.

---

## How the AI works

### Clip detection

CLIPOS scores every candidate window of the video on twelve measurable signals:

| Signal | How it is measured |
| --- | --- |
| `energy` | RMS loudness over the window, normalised against the video's own average. |
| `silence` | Reward for a healthy pause/speech rhythm rather than dead air. |
| `speech_rate` | Words per minute from the transcript. |
| `keywords` | Matches against a curated list of engaging content words. |
| `questions` | Question marks and interrogative phrasing. |
| `surprise` | Numbers, superlatives, "never", "nobody", "secret", "mistake"… |
| `emotion` | Exclamation density and emotional vocabulary. |
| `humor` | Laughter markers and playful phrasing. |
| `scene_change` | Visual cuts detected by OpenCV frame differencing. |
| `subject` | A face is present and visible. |
| `story` | Narrative connective language ("because", "so", "then", "but"). |
| `hook` | Strong opening lines that make sense out of context. |

Those are combined with fixed weights into an **engagement score**. A separate
**virality score** weights shareability factors — hook, surprise, emotion,
humour, questions, keywords, energy, storytelling — then applies an opening-energy
bonus and a length-fit curve (25–50 s is ideal for a short).

Both scores are shown with the concrete reasons that produced them, so you can
see *why* a moment was chosen.

### Speech-to-text

`faster-whisper` (CTranslate2) runs locally on CPU or GPU. Word-level
timestamps come straight from the model, which is what makes the caption
highlighting land on the exact frame.

If no model is installed, CLIPOS still works: it falls back to audio, visual and
scene signals, and the UI states plainly that transcription is unavailable
rather than pretending.

### Speaker tracking

1. Every ~2 frames, faces are detected with the bundled **YuNet** ONNX model
   (falling back to a Haar cascade if ONNX Runtime is unavailable).
2. Face boxes are clustered into *people* by centre distance and size ratio.
3. The audio energy envelope is split into speech ranges; the loudest speaker in
   each range is matched to the nearest face cluster.
4. The result is a per-time "active subject" timeline, sampled into smooth
   keyframes that drive the crop.

### Reframing

For each frame the crop rectangle is computed from the active subject's position
and size, then interpolated smoothly so the camera moves rather than jumps. The
crop expression is time-gated, so the final keyframe only applies at the end of
its own segment.

### Captions

Captions are rendered to an **ASS** subtitle file with a styled, per-word
highlight and burned into the video by FFmpeg's `ass` filter. Eight styles ship
in the box:

`MrBeast` · `Minimal White` · `Neon Gaming` · `Modern Podcast` ·
`Bold Viral` · `Cinematic` · `Karaoke` · `Clean Professional`

---

## Output formats

| Setting | Options |
| --- | --- |
| Aspect ratio | 9:16 (1080×1920), 1:1 (1080×1080), 16:9 (1920×1080) |
| Video codec | H.264 (libx264), H.265 (libx265) |
| Frame rate | 30, 60 |
| Bitrate | configurable, default 8000 kbps |
| Audio | AAC, 160 kbps, 48 kHz stereo |
| Container | MP4 with `+faststart` (streams to the web immediately) |

---

## URL import — what works and what does not

CLIPOS will import a **direct media URL** (an `.mp4`, `.mov`, `.mkv` or similar
that is served over HTTP/HTTPS) by downloading it and treating it exactly like a
local file.

It will **not** download from platforms that require authentication or that
actively block automated access. When you paste such a link, CLIPOS says so
explicitly and tells you to import the file locally instead:

* YouTube — protected by DRM and ToS; CLIPOS does not attempt to bypass it.
* Vimeo private/paid links — require an account.
* Instagram, TikTok, Facebook — require authentication and block direct downloads.

This is a deliberate design decision, not a missing feature. There is no DRM
circumvention anywhere in CLIPOS. Download the video with the platform's own
"save" feature, then drop the file into CLIPOS.

---

## Model manager

**AI Models** shows every available speech-to-text model with its size,
compatibility, quality tier and whether it is already on disk.

| Model | Size | Tier | Notes |
| --- | --- | --- | --- |
| `tiny` | ~75 MB | Fast | Good for hook detection, weak on proper nouns. |
| `base` | ~145 MB | Balanced | Recommended default. |
| `small` | ~480 MB | Accurate | Best wording; needs ~2 GB RAM. |
| `medium` | ~1.5 GB | Best | Large download, slow on CPU. |
| `large-v3` | ~3 GB | Maximum | GPU strongly recommended. |

You can set a default model, remove models you no longer want, and clear the
cache. Every model works offline once downloaded.

An optional **Ollama** integration (Settings → Ollama) improves the generated
titles and descriptions. CLIPOS talks to a local Ollama server on
`http://127.0.0.1:11434` — no cloud provider is involved. When Ollama is not
running, a built-in rule-based generator takes over and still produces five
titles, a description, hashtags, keywords and thumbnail text.

---

## Hardware acceleration

CLIPOS probes the machine at startup and picks the best available encoder:

| Platform | Encoder |
| --- | --- |
| NVIDIA (Windows/Linux) | `h264_nvenc` / `hevc_nvenc` |
| Apple Silicon (macOS) | `h264_videotoolbox` / `hevc_videotoolbox` |
| Intel with Quick Sync | `h264_qsv` / `hevc_qsv` |
| Anything else | `libx264` / `libx265` on the CPU |

If the GPU encoder fails mid-render, the renderer automatically retries on the
CPU, so a render never silently dies.

The **Settings → Hardware** section shows the detected CPU, core count, RAM, GPU
and the encoder that will be used. You can force an encoder, set the thread
count, and enable a low-memory mode.

---

## Building from source

### Requirements

* Python 3.10, 3.11 or 3.12
* A C toolchain is **not** required — all wheels ship prebuilt.

```bash
git clone <your-fork-url> AiFreeClipping
cd AiFreeClipping

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Fetch the native binaries

FFmpeg, FFprobe, the face cascades and the YuNet models are **not** committed to
the repository. Fetch them with:

```bash
python scripts/vendor_ffmpeg.py      # FFmpeg + FFprobe for every platform
python scripts/vendor_cascades.py    # Haar face cascades (from PyPI wheels)
```

`vendor_ffmpeg.py` downloads into `resources/ffmpeg/<platform>/` for
`linux-x64`, `linux-ia32`, `darwin-x64`, `darwin-arm64`, `win32-x64` and
`win32-ia32`.

### Run it

```bash
python -m clipos
```

### Verify the installation

```bash
python scripts/e2e_test.py
```

This generates a real test video and runs the complete chain — import, analyse,
detect, caption, render, batch export — asserting on the actual output files.
It prints a PASS/FAIL line for every check.

---

## Building installers

```bash
python scripts/build.py windows      # -> dist/CLIPOS-Setup.exe
python scripts/build.py macos        # -> dist/CLIPOS.app and dist/CLIPOS.dmg
python scripts/build.py linux        # -> dist/CLIPOS (AppImage)
```

The build script installs PyInstaller, vendors the native binaries, runs the
end-to-end test, freezes the application, packages it, and then verifies the
frozen bundle before it reports success.

* **Windows**: PyInstaller produces a one-folder application, which is then
  wrapped in a native `.exe` installer. Three back-ends are tried in order:

  | Back-end | Produces | Needs |
  |---|---|---|
  | Inno Setup | `CLIPOS-Setup.exe` | `iscc` on the PATH |
  | NSIS | `CLIPOS-Setup.exe` | `makensis` on the PATH |
  | Built-in launcher | `CLIPOS-Setup.exe` | a C cross compiler — `pip install ziglang` |

  The built-in launcher is a small Win32 program that carries the frozen
  application inside itself and unpacks it on the first run, so a Windows
  installer can be produced on any machine — including Linux and macOS.

* **macOS**: PyInstaller produces `CLIPOS.app`; `hdiutil` builds a
  drag-to-install `.dmg` with the app next to an `/Applications` symlink.
  Build on each architecture, or use `--target-arch` for a universal build.
  `scripts/installer_macos.py` can also sign the bundle with a Developer ID
  and submit it to Apple's notary service, so Gatekeeper lets the app open
  without a warning.

* **Linux**: PyInstaller produces a folder, a portable zip and a native
  `.deb` (plus an `.rpm` where `rpmbuild` is available).

### Building the installers from GitHub Actions

Two workflows do this for you, on the real target operating systems:

| Workflow | Trigger | Produces |
|---|---|---|
| `build-installers.yml` | every push to `main`, every pull request | the installer for each platform, as a downloadable artifact |
| `release.yml` | pushing a `v*` tag | the installers attached to a GitHub release |

The Windows job runs on `windows-2022`, the macOS jobs on `macos-14`
(Apple Silicon) and `macos-13` (Intel), and the Linux job on `ubuntu-22.04`.
Each job runs the end-to-end test and the bundle verifier before it uploads
anything.

```bash
git tag v1.0.0
git push origin v1.0.0        # the release workflow publishes the installers
```

### If PyInstaller cannot find the Python shared library

PyInstaller's bootloader links against `libpython3.x.so`, so the interpreter
that runs the build must provide it. Most Python installers do; some minimal
Linux distributions do not.

```bash
# Debian / Ubuntu
sudo apt install libpython3.11
# Fedora / RHEL
sudo dnf install python3-libs
# macOS — use the python.org installer or Homebrew Python
# or build inside a conda environment, which always ships it
```

If you cannot install packages, build the library yourself — this needs only a
C compiler and `make`, and installs into a directory you own:

```bash
python scripts/build_python_shared.py --prefix /tmp/pyshare
LD_LIBRARY_PATH=/tmp/pyshare/lib python scripts/build.py linux
```

The helper downloads the matching CPython source, enables the same core
modules Debian compiles into the interpreter (`_struct`, `zlib`,
`unicodedata`, …), and installs a working `libpython3.x.so`.

### Verifying a bundle by hand

```bash
python scripts/verify_bundle.py dist
```

This checks that every bundled resource is present, that the FFmpeg binaries
kept their executable bit, and that the application binary starts and reaches
its ready state. Every build runs it automatically.

---

## Development

```bash
# Headless UI smoke test — renders every page and screenshots it
./scripts/run_headless.sh /tmp/test_ui.py

# End-to-end pipeline test
python scripts/e2e_test.py

# Unit tests — timeline model, render_timeline() and GUI regressions
python -m unittest discover -s tests -t .

# Screenshot every page with real data (writes to /tmp/clipos_gui)
./scripts/run_headless.sh scripts/gui_walkthrough.py

# Verify a frozen bundle
python scripts/verify_bundle.py dist

# Generate test fixtures
python scripts/make_test_video.py testdata/sample.mp4
python scripts/make_face_video.py testdata/faces.mp4 14

# Re-check that every UI icon renders on every platform
python scripts/replace_icons.py
```

### Headless Linux CI

Bare containers have no `libGL`, `libEGL`, `libxkbcommon` or `libdbus`.
`scripts/build_gl_stubs.py` generates no-op stubs for them and
`scripts/run_headless.sh` launches Qt with the VNC platform plugin:

```bash
python scripts/build_gl_stubs.py
./scripts/run_headless.sh your_script.py
```

---

## Troubleshooting and logs

Application logs are written to `<data dir>/logs/clipos.log` with rotation
(5 files × 2 MB). Errors are also recorded in the SQLite `error_log` table and
shown in **Settings → Storage**.

| Symptom | Cause and fix |
| --- | --- |
| "FFmpeg not found" | The native binaries are missing. Run `python scripts/vendor_ffmpeg.py`. |
| "Could not load whisper model" | No model is installed, or the download was interrupted. Open **AI Models** and download it again. |
| Transcription is unavailable | `faster-whisper` is not installed: `pip install faster-whisper`. |
| Face tracking is weak | The subject is small or poorly lit. YuNet needs a reasonably sized face in frame. |
| The render falls back to the CPU | The GPU encoder failed. The render still completes; check **Settings → Hardware**. |
| The app will not start on macOS | Right-click the app → **Open** (Gatekeeper). |
| SmartScreen blocks the installer on Windows | **More info → Run anyway** — the build is unsigned. |
| The caption font is wrong | Set an explicit caption font in **Settings → Captions**. |

To report a problem, include `clipos.log` from `<data dir>/logs/`.

---

## Privacy

* No account, no subscription, no telemetry, no analytics.
* Your media, transcripts, projects and clips never leave the device.
* No automatic cloud upload and no background network transmission.
* The only network access is the one-time model download and importing a URL
  you explicitly paste.
* Setting **Offline mode** in Settings blocks outbound requests entirely.

---

## Project layout

```
clipos/
├── app.py                  Entry point: environment, logging, database, theme
├── __main__.py             Enables `python -m clipos`
├── core/
│   ├── config.py           Paths, defaults, aspect ratios, duration presets
│   ├── logging_setup.py    Rotating file + console logging
│   ├── ffmpeg.py           Binary discovery, probing, extraction, loudness
│   └── hardware.py         Hardware probe and encoder selection
├── db/
│   ├── schema.py           SQLite schema (version 4)
│   └── database.py         Thread-local SQLite/WAL CRUD, migrations, statistics
├── ai/
│   ├── audio_analysis.py   Waveform, energy, silence, speech ranges, pitch
│   ├── transcription.py    Faster-Whisper offline transcription
│   ├── visual_analysis.py  Scenes, motion, brightness, YuNet/Haar faces
│   ├── speaker_tracking.py Person clustering and speaking-time attribution
│   ├── clip_detector.py    Signal scoring, virality, hooks, overlap suppression
│   └── title_generator.py  Ollama metadata with a rule-based fallback
├── captions/
│   └── caption_engine.py   Eight ASS styles, cue building, highlighting
├── video/
│   ├── renderer.py         Real rendering: reframe, zoom, cuts, captions
│   ├── pipeline.py         Orchestration: analysis, detection, render, export
│   ├── timeline.py         Editable timeline model with undo/redo
│   └── importer.py         Local and URL import with validation
└── ui/
    ├── theme.py            Dark/light palettes and the stylesheet
    ├── fonts.py            Font registration and caption font selection
    ├── main_window.py      Title bar, sidebar, navigation, shortcuts
    ├── widgets/common.py   Reusable cards, tiles, badges, toasts
    └── pages/              The eleven application pages

resources/
├── ffmpeg/                 Native FFmpeg + FFprobe (not in git)
├── cascades/               Haar face cascades
└── models/                 YuNet ONNX face detectors

scripts/
├── vendor_ffmpeg.py        Download the native FFmpeg binaries
├── vendor_cascades.py      Download the Haar cascades
├── build.py                Build the installers
├── build_python_shared.py  Build a libpython for PyInstaller
├── verify_bundle.py        Smoke-test a frozen bundle
├── e2e_test.py             Full-pipeline verification
├── build_gl_stubs.py       Headless Linux GL stubs
├── run_headless.sh         Headless Qt launcher
└── make_*_video.py         Test fixture generators
```

---

## Licence

The bundled FFmpeg binaries are built under the LGPL/GPL terms of their
respective projects. The YuNet models come from the OpenCV Zoo (MIT). The
Haar cascades are part of OpenCV (Apache 2.0).

## Creator workflow improvements (source branch)

- **Editing recipes:** Settings → One-click editing recipe. Choose Clean Studio,
  Podcast Focus, Gameplay + Facecam or Story Highlight. These are original local
  rules, not model training or a promise of increased engagement.
- **Gaming composition:** Export Center → Gameplay + Facecam. Set the source
  facecam rectangle using X/Y/width/height percentages. Gameplay is fitted above,
  the selected camera region below. The default rectangle is only a starting
  point, not automatic facecam recognition. Use **Preview recipe · 4 seconds**
  before exporting. This is a real draft-resolution render opened in your system
  player; captions are previewed separately in Caption Studio.
- **Saved edits:** timeline edits autosave by clip and are restored on reopen.
  Batch export uses saved edits instead of silently reverting to original timing.
  Clip captions are retimed through trims/speed changes in batch export.
- **Export recovery:** a failed hardware encoder now retries using software
  encoding. Timeline mute, zoom and crop are honoured. Inspect warnings if a
  complex effect required the simplified recovery path.
- **YouTube:** paste a public video URL and confirm permission. Requires internet
  and `yt-dlp` (installed by `scripts/install_deps.py`). Downloads the highest
  available video/audio streams and merges them locally. Private, DRM,
  authentication and platform blocks are not bypassed. Source availability and
  extractor changes can still cause failure; local import remains available.
- **Updates:** Settings → Check for updates checks GitHub on demand and opens the
  matching published installer download after confirmation. This is **not silent
  auto-installation**. Quit CLIPOS and run the installer; project data lives in
  the OS application-data folder, separately from application binaries. Back up
  important projects before upgrading; migrations still need platform testing.
- **Website:** [`docs/`](docs/README.md) contains the public download site and
  GitHub Pages publication instructions. Buttons resolve actual release assets.
  Publishing the site does not publish new application binaries.

### Current validation limits

Automated Linux tests exercise real FFmpeg exports and edited timelines. macOS
and Windows native install/update tests, physical-device validation, live YouTube
network imports and the full Whisper workflow with model weights still need
verification. GPU availability and export speed depend on the device. No product
can guarantee engagement or virality. A published older installer does not
contain these source changes until a new verified release is built.
