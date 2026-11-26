# Ai clipping PRO 4.0.0 — Integrated offline Studio

## Included
- Integrated Clip Queue, selective per-clip/batch preset application and local rendering.
- Shared composited video/audio playback, timeline captions, effects and transitions.
- Verified local .cube LUT import, curves, tonal wheels and global/six-range HSL.
- Audio processors, explicit dialogue/music roles and signal-driven music ducking.
- 50 original editable CC0 title-scene designs with offline pack ZIP export.
- Optional 50-image Noto Emoji Apache-2.0 library: explicit individual/full-library
  download, integrity verification, offline reuse and source/license records.
- Existing AI clipping, model management and source crop ownership retained.

## Evidence and limitations
Local regression: **698 passed, 15 skipped**. Actual tests render all 50 original
designs with both animations, inspect alpha, verify pack archives and check color,
PCM processing, persistence and invalid-input rejection. All 50 optional library
images were actually downloaded and verified in development.

Publication is gated on all seven native installer/archive assets. Native build
checks are not physical hardware certification. Physical speaker/display sync,
human Windows/macOS permission/consent flows and sustained device/GPU performance
remain NOT RUN. Use docs/NATIVE_DESKTOP_ACCEPTANCE.md. macOS ad-hoc integrity does
not mean Apple notarization. Do not disable OS security to install.

The 50 designs are editable title-scene packs, not stock footage/music libraries
or arbitrary layered motion-project interchange. This release does not certify
completion of every advanced editor requirement, including restart-resumable
render jobs or broad physical-device acceptance. Back up projects before upgrading.
Original and third-party artwork licenses are distinct; see THIRD_PARTY_NOTICES.md.
Compatibility filenames and data paths retain CLIPOS.

---

# Ai clipping PRO 3.6.1 — Reference-aligned native workspace

- Native Create Clips dashboard now follows the supplied layout: purple/blue hero,
  connected four-step cards, local-file/link import target and six real edit recipes
  on the left; local AI Director, actual recent projects and measured model availability
  on the right. Narrow windows stack the two columns rather than squeezing controls.
- Paste Video Link reads the system clipboard for review; it does not automatically
  download or transmit clipboard content. Existing authorised-source checks remain.
- Quick-style selection now stays synchronized when settings change or a project opens.
- Editor (Pro) adds a Project Media panel listing real imported video/audio metadata;
  activating a source selects its existing timeline item and seeks the decoded monitor.
- Settings adds section navigation without replacing or resetting saved controls.
- Existing caption/color-effect/cross-dissolve lanes, save formats, processing pipelines,
  ten sidebar destinations and project data are preserved.

## Verification boundaries

Automated tests exercise actual widget actions, settings persistence, narrow-window
layout, project-step guards, clipboard review and real media selection. Platform
builds run the same regressions plus the real import/render/batch-export E2E suite.
The UI is reference-aligned native Qt, not a pixel-identical web recreation: no fake
stock project thumbnails, profile/account, cloud generation, notification counts,
uninstalled-model readiness or realtime playback guarantee is introduced. Gemma live
quality still requires explicitly installed actual weights and a recording; it is not
verified by mocked/deterministic tests. macOS ad-hoc integrity is not notarization.

---

# Ai clipping PRO 3.6.0 — Real overlay lanes and a refreshed product website

## Native editor

- Dedicated **caption lanes**: add/edit real text, choose registered caption presets,
  inherit validated Caption Studio export options, move/trim timing, undo/redo and
  save/reopen. Actual ASS/libass caption rasterization is used in decoded preview
  and caption burning is part of the real multilayer MP4 export graph.
- Dedicated **color-effect lanes**: bounded timeline ranges apply brightness,
  contrast and saturation to the composite below them. Presets initialize real
  numeric controls; the Inspector updates actual render parameters.
- Dedicated **cross-dissolve lanes**: the incoming overlapping video fades over the
  outgoing layer using real alpha compositing. References, overlap and layer order
  are validated transactionally. Invalid edits do not partially change a project.
- Caption/effect/transition lanes are visible/selectable in the timeline and detailed
  track table. They support enable/disable, locking, deletion and project history.
- Existing video/audio edits and saved project files remain supported. Project/data
  paths, bundle identity and installer filenames retain compatibility.

## Website and documentation

The accompanying website/README refresh uses **Ai clipping PRO** branding, current
release downloads and actual compressed app captures. It includes responsive layouts,
scroll/hover animations, accessible screenshot tabs, mobile navigation, platform
filters, native FAQ disclosures, command copying and reduced-motion support. README
content focuses on the current release, with collapsible setup/help sections rather
than a history of previous versions. Website publication follows verified installer
publication; no installer links are advertised as ready while assets are missing.

## Boundaries

Color effects are brightness/contrast/saturation treatments, not an arbitrary plugin
library. Transitions currently support cross-dissolve between actually overlapping
video items; audio fades remain independent. Decoded preview is best-effort, not a
universal realtime A/V guarantee. Caption frames are rendered locally and can cost
more CPU than ordinary video preview. Word animation still needs real word timestamps;
manual caption text uses cue-level fallback rather than invented word synchronization.

Actual Gemma weights were not available in the sandbox. Live trained-model quality is
**not verified**; local runtime/model tests remain explicit user actions. This release
does not claim unrestricted autonomous editing or universal physical-device acceptance.

---

# Ai clipping PRO 3.5.0 — Native workspace and caption customization

CLIPOS is now displayed as **Ai clipping PRO**. This release keeps existing local
projects, data paths, database and bundle identities. Installer asset and executable
filenames retain `CLIPOS` for upgrade and verification compatibility.

## Implemented

- Ten native destinations: Home, Create Clips, Projects, Clip Library, Editor (Pro),
  Caption Studio, Templates, AI Models, Export Center and Settings.
- Persistent collapsed navigation with tooltips and dark/light/system appearance.
- Home database statistics, recent projects and grounded local Director handoff.
- Searchable project gallery with name/duration/updated sorting and archive filter.
- Restored Caption Studio with 38 working presets and category browsing; saved local
  custom profiles; typography, text/highlight/outline colors, animation, alignment,
  position and timing offset. Actual FFmpeg/libass preview frames update in the
  background and share validated overrides with both clip/timeline export paths.
- Existing independent-video/audio multitrack workspace is accessible from the clip
  editor. Wrapping toolbars, a selected-layer inspector, brightness/contrast/
  saturation/rotation, gameplay-above and facecam-below layouts, canvas sizes and
  frame rates are connected to the real project model, undo history and renderer.
- Export Center supports AAC quality selection in addition to the existing video
  codec, aspect ratio, FPS, bitrate, hardware encoder and batch export controls.
- Local model management remains explicit-consent/offline-first. Dependency versions
  and file-presence checks do not pretend a model is running or compatible.

## Validation and boundaries

The local full suite passed **653 tests, with 21 skipped**. New regression cases
include actual FFmpeg caption rasterization and actual multitrack color/rotation
MP4 export, plus native widget navigation, profile persistence and inspector actions.
Exact-revision native installer run [45622794542](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45622794542), Intel engine audit and signature/DMG checks passed. Tagged release run [45628180998](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45628180998) built and verified Windows, Apple Silicon, Intel and Linux installers before publishing all seven assets. Local end-to-end checks passed 35/35.

This is **not full parity with every control in the showcase illustration**. The
multitrack engine currently supports video/audio layers, fades and opacity/gain
keyframes, not dedicated caption/effect/transition lanes. Caption burning uses the
clip/timeline export pipeline. The decoded color preview is draft quality; final
filters are rendered by FFmpeg. Caption preview displays a frame, not full animated
playback. Existing bounded Director commands still require review and do not imply
unrestricted autonomous video editing. No trained Gemma weights were available in
the sandbox, so live model quality is not claimed. Native signing integrity is not
Apple notarization or a promise that unsigned installers avoid OS warnings.

No publishing/account integration or automatic media upload has been reintroduced.

---

# CLIPOS 3.1.1 — Native render crash stability update

Developed by **Analoggeek**. Targets the reported Intel Mac exports terminating
with `ffmpeg failed (exit -11)` before the first output frame.

## What the report establishes

`-11` is a native SIGSEGV, not a normal FFmpeg command-line error. The report
shows an old FFmpeg/x264 build, 14 encoder workers, CoreText/libass importing
supplemental fonts (including an NISC18030 metadata warning), and AV1-branded
source metadata. The final scaler alignment warning alone does not establish
why the process crashed. The exact user's machine/source fault is not reproduced
in the sandbox; the changes below address concrete risky paths and add recovery.

## Fixes and enhancements

- Refresh the **Intel macOS** FFmpeg binary to upstream ffmpeg-static `b6.0`,
  pinned by SHA-256 with architecture validation and retained upstream license/
  provenance files. An existing legacy binary without the new verified manifest
  is not silently reused. Other platform binaries are not advertised as upgraded.
- Pass libass an isolated directory containing one real fallback font, rather
  than the entire OS font directory. CoreText/system font discovery remains
  available; captions are not silently removed or replaced with fake text.
- If a render process has a recognized native fault, retry the same timing,
  filters, captions, mappings and output with single-worker/scalar compatibility
  settings. x264's separate assembly dispatch is disabled for this retry.
- Subsequent render commands using the same binary identity remain in
  compatibility mode for the session, avoiding a fresh crash for every clip.
  Relaunch/binary replacement resets this policy. Compatibility mode is slower
  by design; normal successful renders retain accelerated/default performance.
- Fix Intel music export cleanup hangs by calculating finite music repeats for
  the edited duration rather than using an infinite demux loop. Actual looped
  music and ducking remain present and are waveform-tested.
- Never treat cancellation, out-of-memory killing, ordinary bad media/arguments
  or a second conservative failure as a successful export. Retries are bounded;
  pre-existing successful output remains protected by atomic replacement.
- Save a bounded **local-only** native-fault diagnostic under the application
  logs directory. Settings now offers **Open local logs / render crash
  diagnostics** and displays the actual selected engine version. Nothing is
  uploaded automatically; reports can contain local file paths/media names.
- Retain v3.1 performance improvements, removed Multitrack workspace UI, existing
  saved data, native editing, offline-first behaviour and platform encoder checks.

## Verification and limits

Native Intel full release regression audit: **477 passed, 9 skipped**
(run45579158883), including native playback and actual music/caption recovery.
Local full suite: **607 passed, 20 skipped**; real import-to-export/batch E2E:
**35/35 passed**. Optional native/model checks account for skips; Intel runtime
verification is mandatory in release CI, not asserted from Linux tests.

Regression coverage includes injected fatal return codes, bounded failed retries,
cancellation, session compatibility behaviour, font isolation, archive hash
rejection, and real H264/AV1 inputs rendered to 1080x1920 H264/AAC with actual
caption pixels preserved after an injected initial failure. Injected faults
prove recovery contracts, not the original crash's root cause. Native Intel CI
requires FFmpeg >=6.0 with ASS/drawtext and rejects `--enable-nonfree` builds.

Platform installers are published only after native gates and all seven
nonempty release assets succeed. This is not physical-device/driver or arbitrary
source-media certification; disk errors, invalid media and incompatible devices
can still fail explicitly. Model/physical A/V acceptance limitations from the
prior release remain unchanged. macOS signing integrity is not notarization.
Back up important projects before upgrading; user projects/data are not deleted.
