# CLIPOS 2.5.1 — visible dual-region editing and unblocked rendered export

By **Analoggeek**.

- Independent, colour-labelled PLAYER and GAMEPLAY selections stay visible
  together; source playback updates the canvas and live composition view.
- Added editable source camera placement presets, based on DigiRG Cloud's MIT
  presets; attribution retained. Native Qt interaction, not an embedded website.
- Live framing and sample caption styling react while dragging/changing layouts;
  the full rendered recipe/final output remains the effects/caption authority.
- Persist style/layout/caption/count/duration controls so navigation cannot reset
  them. Choosing a crop/layout activates the applicable Gameplay recipe.
- Preserve the selected aspect ratio in actual short recipe renders.
- Export checked finished videos independently from current edit controls; old
  signatures or a missing current camera region no longer block copying a ready
  clip. Changed effects still require an explicit re-edit before they appear.
- Release playback decoder handles before edit/export operations (important for
  Windows file locks), and update delivered clip status with real export records.
- Explicit retry without captions when a speech model/transcription fails; no
  fake speech captions or false success.
- Regression coverage includes real GUI mouse drags, crop persistence, recipe
  navigation, pixel-checked FFmpeg output and playable exported files. Real Qt
  source decoding is mandatory in Windows/macOS CI, skipped only where minimal
  Linux lacks multimedia system libraries.

Local tests: **270 passed, 9 skipped**; E2E **35/35**.
[Native release checks](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45376503798)
passed Windows, macOS Intel/Apple Silicon and Linux; all seven assets uploaded.
These tests do not replace physical-device validation; physical-device performance and installer/driver behaviour
are not established by automated tests. macOS ad-hoc signing is not notarization;
do not disable OS security. Existing local projects/data are retained.

See [the updated workflow guide](docs/WORKFLOW_V25.md).

---

# CLIPOS 2.5.0 — connected editing and reliable batch export

By **Analoggeek**.

- Replaced Gaming Studio 2.0 with Import → Select & style → Edit & review → Export.
- Removed YouTube publishing/account controls and their API dependencies.
- Added source playback/range selection, visual manual player/gameplay crops,
  preset/caption thumbnails and real short recipe rendering before batch editing.
- Kept one-click import and automatic editing, plus review of actual rendered MP4s.
- Fixed captioned FFmpeg export failure: the `fontsdir` option was accidentally
  appended to the subtitle filename. Fixed all captioned render paths.
- Batch exports share `YYYY-MM-DD / recording name / all clips`, include manifests
  and visible per-clip errors, continue after a failure and preserve cancellations.
- Unified shared settings/project events; respected custom export folders and
  selected captions rather than overwriting them when applying presets.
- Reduced long-recording audio-analysis memory, bounded pitch sampling, and used
  a single source decoder for automatic silence-cut renders.
- Added native macOS VideoToolbox / Windows NVENC-QSV-CPU capability-based paths,
  bounded CPU fallback, low-memory render mode and live measured CPU/RAM usage.
- Simplified navigation and added consistent vector icons.

See [the 2.5 workflow guide](https://github.com/Analoggeek/AiFreeClipping/blob/main/docs/WORKFLOW_V25.md).

Automatic camera/highlight detection remains heuristic: review results, or use
manual crops. Preset tiles are visual previews; real recipe previews render your
source. GPU counters are shown only where supported. No claims of genuine HDR,
perfect editing, native OS background blur or guaranteed engagement.

Native CI must pass before publication. Automated tests do not replace physical
Windows/Mac installation or driver-specific playback testing. macOS builds remain
ad-hoc signed unless Developer ID signing is configured; bundle integrity is not
Apple notarization/Gatekeeper approval. Do not disable system security.
