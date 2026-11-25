# Ai clipping PRO 3.5 — implementation status

**Ai clipping PRO v3.5.0 is published:** https://github.com/Analoggeek/AiFreeClipping/releases/tag/v3.5.0

This is **not a claim of complete showcase parity**. Source PR #146 merged as
`ada2e5906ad76101e8e93ca7022d13b65723251e`; the release tag points to that commit.

## Screen mapping

| Destination | Native implementation | Integration in this stage |
| --- | --- | --- |
| Home | `ui/pages/home.py` | Restored; database statistics, recent projects, model-file status, grounded Director handoff |
| Create Clips | `ui/pages/workflow.py` | Existing four-step import/style/review/export pipeline retained |
| Projects | `ui/pages/my_projects.py` | Searchable two-column gallery, sort by updated/name/duration, archive-state filter; existing CRUD retained |
| Clip Library | `ui/pages/clip_library.py` | Existing clip database and editing entry points retained |
| Editor (Pro) | `ui/pages/editor.py`, `multitrack.py` | Clip editor linked to real multitrack workspace; wrapping toolbars, selected-layer inspector, color/rotation, canvas/FPS and gameplay/facecam layout controls |
| Caption Studio | `ui/pages/caption_studio.py` | 38 styles; category browsing; named local custom profiles; editable colors, motion, alignment and timing; debounced background FFmpeg/libass preview using the same overrides as both export paths |
| Templates | `ui/pages/templates.py` | Restored existing platform export presets and caption choices |
| AI Models | `ui/pages/ai_models.py` | Existing Whisper/Gemma lifecycle retained; distribution versions and weight-file checks distinguish dependencies from continuously running models |
| Export Center | `ui/pages/export_center.py` | Real batch render queue/history and encoder options; AAC quality selection; synchronized persisted defaults |
| Settings | `ui/pages/settings_page.py` | Existing persisted settings retained; dark/light/system appearance |

## Shared design and upgrade compatibility

`clipos/ui/theme.py` remains the centralized Qt stylesheet/palette and spacing system. The shell provides ten destinations, tooltip-labelled collapsed navigation and a persisted collapse preference. System appearance follows Qt's reported OS color scheme.

Application-facing name is **Ai clipping PRO**. Source version is **3.5.0** in preparation for the eventual release. Windows installer display name and macOS bundle display name are updated. Internal `CLIPOS` executable/artifact names, macOS bundle identity, SQLite filename, environment variables and legacy application-data directories intentionally remain stable. This avoids stranding existing projects or breaking frozen-artifact verification. No database migration or destructive data move is performed.

## Verification performed

- Linux sandbox: **653 passed, 21 skipped** in the full pytest suite.
- Explicit navigation smoke test opened every registered native page with a real local project.
- Real ASS preview regression verifies an actual FFmpeg PNG, not an illustrative painter result.
- Custom caption defaults/profiles and timing validation tested; preset registry and cue inputs remain unmodified.
- Color/rotation changes tested through undo/redo, reopen, decoded preview and a real multilayer MP4 export. Native inspector/canvas/layout controls have regression coverage.
- `git diff --check` clean.

The sandbox's minimal Qt platform does not establish native audio/device/OS acceptance. Skipped tests remain skipped; no trained Gemma weights were downloaded or exercised.

## Native release verification

- Exact application revision: installer run [45622794542](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45622794542), Intel audit [45622891646](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45622891646) and signature/DMG integrity [45622794567](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45622794567) passed.
- Official tagged release [45628180998](https://github.com/Analoggeek/AiFreeClipping/actions/runs/45628180998): Windows, macOS Apple Silicon, macOS Intel and Linux builds, architecture/frozen-bundle verification and publication passed. All seven expected assets are uploaded and nonempty.
- Local real end-to-end workflow: **35/35 passed**.

## Known limitations / remaining roadmap

- Full showcase parity remains a product roadmap item; the implemented inspector and wrapping controls do not imply every illustrated control exists.
- Caption motion preview is an actual frame at one second, not a continuous libass playback viewer. The existing word-pop/reveal presets require actual word timestamps; missing timing falls back to cue motion, never invented synchronization.
- Independent effects/transitions/caption tracks and additional editing controls beyond the existing engine's supported operations. Linking the existing multitrack workspace does not create missing engine features.
- Full Director instruction acceptance with actual local Gemma weights; current bounded command implementation and review requirements remain documented in `GEMMA_DIRECTOR.md`.
- Complete dependency/weights compatibility and memory reporting; installed package versions are not evidence that a model can execute.
- All native CI installer/regression checks passed. This does not substitute for manual acceptance on every end-user device and source recording.
- Dedicated multitrack caption/effect/transition lanes and full illustrated feature parity remain unimplemented; existing capabilities are not presented as those missing features.

Public download documentation now points to v3.5.0. Prior v3.1.1 assets remain available and unchanged.
