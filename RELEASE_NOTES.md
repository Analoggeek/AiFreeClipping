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
