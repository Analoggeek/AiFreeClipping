# Ai clipping PRO 3.5 — implementation status

This branch is an integration stage, **not a published 3.5 release or a claim of complete showcase parity**.

## Screen mapping

| Destination | Native implementation | Integration in this stage |
| --- | --- | --- |
| Home | `ui/pages/home.py` | Restored; database statistics, recent projects, model-file status, grounded Director handoff |
| Create Clips | `ui/pages/workflow.py` | Existing four-step import/style/review/export pipeline retained |
| Projects | `ui/pages/my_projects.py` | Searchable two-column gallery, sort by updated/name/duration, archive-state filter; existing CRUD retained |
| Clip Library | `ui/pages/clip_library.py` | Existing clip database and editing entry points retained |
| Editor (Pro) | `ui/pages/editor.py`, `multitrack.py` | Clip editor linked to existing real multitrack workspace, with return navigation |
| Caption Studio | `ui/pages/caption_studio.py` | Restored 38 styles and typography controls; explicit background-worker FFmpeg/libass rendered frame; default preferences restored on reopen |
| Templates | `ui/pages/templates.py` | Restored existing platform export presets and caption choices |
| AI Models | `ui/pages/ai_models.py` | Existing Whisper/Gemma lifecycle retained; distribution versions and weight-file checks distinguish dependencies from continuously running models |
| Export Center | `ui/pages/export_center.py` | Existing real batch render queue/history and encoder options directly accessible |
| Settings | `ui/pages/settings_page.py` | Existing persisted settings retained; dark/light/system appearance |

## Shared design and upgrade compatibility

`clipos/ui/theme.py` remains the centralized Qt stylesheet/palette and spacing system. The shell provides ten destinations, tooltip-labelled collapsed navigation and a persisted collapse preference. System appearance follows Qt's reported OS color scheme.

Application-facing name is **Ai clipping PRO**. Source version is **3.5.0** in preparation for the eventual release. Windows installer display name and macOS bundle display name are updated. Internal `CLIPOS` executable/artifact names, macOS bundle identity, SQLite filename, environment variables and legacy application-data directories intentionally remain stable. This avoids stranding existing projects or breaking frozen-artifact verification. No database migration or destructive data move is performed.

## Verification performed

- Linux sandbox: **639 passed, 21 skipped** in the full pytest suite.
- Explicit navigation smoke test opened every registered native page with a real local project.
- Real ASS preview regression verifies an actual FFmpeg PNG, not an illustrative painter result.
- `git diff --check` clean.

The sandbox's minimal Qt platform does not establish native audio/device/OS acceptance. Skipped tests remain skipped; no trained Gemma weights were downloaded or exercised.

## Remaining release gates

- Full showcase-level layout polish and responsive editor/inspector consolidation.
- Caption category browsing, editable colors/highlights/animation/alignment/timing and their end-to-end export integration. Current motion comes from the selected existing preset; the rendered preview is a frame at one second, not a playback viewer.
- Independent effects/transitions/caption tracks and additional editing controls beyond the existing engine's supported operations. Linking the existing multitrack workspace does not create missing engine features.
- Full Director instruction acceptance with actual local Gemma weights; current bounded command implementation and review requirements remain documented in `GEMMA_DIRECTOR.md`.
- Complete dependency/weights compatibility and memory reporting; installed package versions are not evidence that a model can execute.
- Native Windows, Apple Silicon and Intel macOS installer/regression checks on this exact revision, plus manual import/edit/reopen/export acceptance.
- Complete release notes, source PR review/merge, then gated installer publication. No tag or release should be published merely because the source version was prepared.

Public v3.1.1 download links remain untouched until a verified successor exists.
