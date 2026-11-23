# CLIPOS 2.0.0 — Gaming Studio

By **Analoggeek**.

## Gaming-first native editor

- New default Gaming Studio: authorised link or local recording → one-click
  highlight selection/edit/captions/render → actual MP4 preview and seek.
- Face-based automatic layout places detected player below gameplay, with a
  gameplay-only fallback and warnings when detection is uncertain. Manual layout
  overrides remain available in Export Center.
- Clean Professional captions above the panel split and optional restrained SDR
  clarity. This is not HDR and does not guarantee viral or editorially perfect clips.
- Layered glass-style gradients, borders and transparent labels throughout the
  desktop UI; not native OS background blur.
- Bounded visual sampling, CPU thread budgets and correct CTranslate2 CUDA/CPU
  selection. Fixed per-instance database connection isolation.
- Complete locally downloaded speech model discovery, with first-run setup and
  offline subsequent editing. Real progress/errors; no simulated render success.

## Optional YouTube publishing

- Connect your own Google Desktop OAuth client/account using the OS secure
  keychain. Review editable generated metadata, rights, audience, visibility and
  disclosure; confirm before uploading checked rendered clips.
- Real resumable API upload with cancellation, error reporting and recorded-file
  duplicate protection. No automatic publishing during import or editing.
- Google API setup, verification/audit restrictions, quota and account permissions
  apply. Disclaimers and attribution do not grant copyright permission.
- See [Gaming Studio setup](https://github.com/Analoggeek/AiFreeClipping/blob/arena/c30e6e2b-aifreeclipping/docs/GAMING_V2.md).

## Downloads and compatibility

Native Windows 10/11 EXE, genuine macOS Intel and Apple Silicon APP/DMG, plus Linux
packages are built by release CI. All native jobs must pass before publication.
The existing website design is unchanged. Existing project/model data is stored
separately from binaries; back it up before upgrading.

Automated Linux validation: **205 passed, 7 skipped**, plus **35/35** end-to-end
checks. Includes actual face detection/FFmpeg render; Google API tests are mocked.
Live account uploads, physical-device installs and real-world gameplay variety
still require validation. No claim of completed physical Mac/Windows testing.

macOS bundle integrity checks remain enabled. Builds are ad-hoc signed unless a
Developer ID is configured: valid integrity does not mean Apple notarization or
Gatekeeper approval. Do not disable system security; see the
[macOS installation guide](https://github.com/Analoggeek/AiFreeClipping/blob/main/docs/MACOS_INSTALLATION.md).
