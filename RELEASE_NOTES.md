# CLIPOS 3.0.0 — Native local editing and source-grounded AI tools

Developed by **Analoggeek**. This release includes the accumulated native desktop
work from PR #92, preserving the existing editing workflow and local user data.
No cloud publishing, automatic upload, mandatory account or subscription is added.

## What's new

- Multitrack timeline improvements, linked A/V manipulation, decoded waveforms,
  keyframe editing, fades and native editing gestures.
- Conservative longform silence/freeze cleanup and reviewable automatic selection
  with selected-range protection and bounded optional export-preference learning.
- Source-bound anonymous speaker-coloured captions with cut/speed retiming.
- Shot-held face framing with scene-cut resets; manual/gaming/body framing keeps
  precedence. Gaming player/gameplay regions remain manually adjustable.
- Local trained ONNX OCR on sampled finalist frames; optional loopback-only
  Ollama vision review and grounded direction compilation.
- Optional CPU TalkNet audiovisual face association and local AST sound-model
  inference integrations, with source checks, bounded windows and truthful errors.

## Downloads and upgrades

Choose Windows x64 EXE, macOS Apple Silicon or Intel DMG/app archive, or Linux
DEB/portable ZIP. Quit the old application before replacing it. Back up important
projects; upgrading does not intentionally remove the existing user-data directory.
This is still an offline-first native Qt application, not a website redesign.

Standard installers include the OCR runtime/models installed explicitly by the
build setup. They do **not** bundle the large optional TalkNet/AST runtimes or
checkpoints. Those integrations currently require an explicitly prepared source
installation/build with `scripts/install_deps.py --talknet --sound` and compatible
local checkpoints. Do not enable them expecting automatic downloads or cloud
fallback. Optional local Ollama models also require explicit prior installation.
See `docs/AUTOMATIC_EDITING_ENGINE.md` for model formats and acceptance commands.

## Validation and important limits

- Installed-runtime source suite: **579 passed, 10 skipped** after the v3.0.0 version bump;
  CPU TalkNet checkpoint/forward and local safetensors AST/decoded-audio tests run.
- Existing import-to-export/batch E2E: **35/35 passed** on v3.0.0 source. Release installers are separately gated by native CI.
- Actual trained OCR was exercised. TalkNet/AST runtime tests used random weights:
  trained-model quality is **not verified** because official trained-weight delivery
  hosts were unavailable in the sandbox. Finite logits are not accuracy evidence.
- Direction handling is constrained, not arbitrary natural-language editing.
  Shot-centred TalkNet sampling is not continuous speaker tracking; anonymous
  face-track IDs are not named people or diarization voice identities.
- Sound/vision scores and OCR text are fallible evidence, not guaranteed game
  kills/wins. Optional export preferences are not engagement learning.
- This release does not complete the entire PRO roadmap. Physical A/V sync,
  native driver/performance, OS-enforced disconnected operation and real-model
  quality acceptance remain unverified. Optional PyTorch >=2.6 engines are not
  certified on Intel macOS and may lack a compatible runtime there.
- macOS packaging integrity/ad-hoc signing is not Apple notarization. No advice
  to disable operating-system security protections is provided.

The release workflow requires all seven nonempty versioned installer/archive
assets before publishing the final release. Platform build success must not be
interpreted as physical-device or trained-model quality certification.
