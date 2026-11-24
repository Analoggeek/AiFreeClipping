# CLIPOS PRO engineering and acceptance ledger

This document tracks the additional PRO specification. It is **not** a completion
announcement. Released 2.5.1 remains the baseline; the current source work adds a
bounded local-agent/security foundation plus measured activity ranking,
face-confirmed static-panel refinement and safer sampled face association.
See [the pinned DigiRG review](DIGIRG_REFERENCE_REVIEW.md) for the feature-by-feature
reuse/improvement/new-work report and exact validation limits. No PRO installer/version
is being published on the strength of UI controls or protocol mocks.

## Non-negotiable inference policy

- Application AI requests must target numeric loopback (IPv4/IPv6), never LAN,
  Internet or arbitrary DNS hosts. `localhost` is canonicalized to 127.0.0.1.
- Local Ollama calls bypass environment proxies and reject redirects. Before
  sending a prompt, `/api/show` must expose local GGUF architecture metadata and
  no remote model/host reference; cloud-named models are refused.
- Whisper inference loads an installed local directory with
  `local_files_only=True`. Missing weights stop captioned editing with an
  actionable message. Legacy auto-download preferences cannot initiate downloads
  from editing. AI Models' explicit Download action remains the setup mechanism.
- Existing metadata generation now uses the same local-only transport. If local
  metadata inference is unavailable, the existing labelled rule-based fallback
  remains local; the editing agent instead fails explicitly, without pretending
  a model made a plan.
- A user-controlled local runtime is a trust boundary. A modified local server
  could lie/forward traffic; application URL validation is not an OS firewall or
  proof of what a separate daemon does. Final offline acceptance also requires
  disconnecting or externally blocking network access for the application **and**
  its inference/render subprocesses.

## Implemented in this source milestone

### Bounded editing agent

`clipos/ai/editing_agent.py` converts an installed local model's response to a
strict versioned plan. Supported edits are existing recipes/layouts, caption
style/size, count/duration/aspect preferences, selected silence/audio controls,
and validated source time ranges. Studio layouts activate the applicable Gaming
recipe. Unsupported fields, paths, URLs, shell commands, FFmpeg strings, invented
crop boxes, unknown presets, NaN/infinite/out-of-source ranges and incompatible
operations are rejected.

Only saved transcript excerpts and supplied evidence are sent to the local model.
No new vision detector is hidden behind the LLM. Transcript text is labelled
untrusted; model output is data and cannot execute code. Without visual evidence,
people/objects/gameplay identification is unknown, not a claimed detection.

**Select & style → Local editing agent** provides:

1. Enter an instruction and propose a plan using the configured installed local
   Ollama model (Settings → Local LLM). No automatic model pull/download occurs.
2. Review the read-only validated JSON plan.
3. Apply it to real settings/project ranges, or approve it and run the existing
   local edit/render pipeline. Merely generating a plan does not alter media.

Application is atomic in SQLite and the last approved plan is recorded in
`agent_plan:<project ID>`; existing
manual source crops are preserved. Invalid/write-failed plans cannot partially
apply. Settings use the application's current shared-default model; they are not
isolated per-track effects. Applying changes does not silently rewrite existing
rendered outputs—execution/re-editing does that.

### Tests completed for this milestone

- Remote/ambiguous endpoints rejected before I/O; numeric loopback canonicalized.
- Proxy bypass, redirect denial, cloud/remote-model denial before transcript
  submission, bounded JSON schema and adversarial output handling.
- Atomic application/rollback, preservation of manual crops, real GUI approval
  changing controls/ranges, and refusal of automatic model download even with an
  old enabled preference.
- A validated plan drives real FFmpeg composition, playable file delivery and
  database reopen while Python socket connection methods are denied.

Local HTTP server responses in transport tests are **fixtures, not a real LLM**.
The network-denied render test does not exercise real speech/LLM weights or act
as an OS firewall for FFmpeg/Ollama. Model-backed interpretation quality and a
complete disconnected AI workflow are **not verified** in this environment.

## Remaining implementation milestones

| Milestone | Required real deliverables | Status |
| --- | --- | --- |
| M1: local-agent boundary | Local-only inference, consent, bounded plans, project execution and rollback | Implemented/tested scope above; real-weight evaluation pending |
| M2: model manager + offline harness | Versioned model manifest, checksums, purpose/license/compatibility, approved resumable downloads, enable/disable, hardware recommendations; disconnected full workflow with real weights | Partial existing Whisper manager; PRO extension pending |
| M3: perception and stable crop | Local body/object detector and tracker, facecam/game/screen classifier, scene resets, speaker association, confidence/uncertainty, smoothing/hysteresis, manual priority overrides, annotated-video accuracy/jitter tests | Existing face/speaker/scene heuristics only; PRO detectors/tracking/segmentation pending |
| M4: media engine and player | Crash-safe versioned multi-track document and effect graph; proxies/cache invalidation, audio/video clocks, waveform, scrubbing/frame stepping/rate/fullscreen, actual transition/keyframe preview | Current source/rendered player and single-source timeline exist; professional engine pending |
| M5: multitrack editor | Genuine video/audio/caption/music/SFX/overlay/transition/adjustment tracks, drag/trim/split/merge/ripple, locks/visibility, automation/keyframes/rotation/opacity/speed ramps, undo/redo/copy/snap/shortcuts mapped to renderer | Pending; no dummy track rows counted as implemented |
| M6: captions and audio | 30 distinct functioning presets, editable word timings/transcript, colour/highlight/spacing/alignment/margins/animation controls; voice separation where supported, ducking and audio automation | Eight current ASS styles and existing audio filters only; PRO expansion pending |
| M7: autonomous modes | Gaming/podcast/talking-head/education/cinematic/reaction plans grounded in perception, actual effect/transition decisions, safe iterative instructions | Bounded supported-operation agent only; full six-mode autonomous intelligence pending |
| M8: native reliability/release | Long/4K/multitrack stress, RAM/VRAM limits, recovery, offline and native driver/install/update tests, reproducible signed builds and acceptance artifacts | Prior 2.5.1 native evidence does not certify new PRO work |

Gaming PRO geometry must add the requested 65/35 default and selectable 70/30,
65/35, 60/40 and 50/50 ratios without silently changing saved projects. Current
11 layouts remain available; dual-camera/three-panel sources, professional
borders/spacing and dynamic gameplay object priority require the multitrack/
perception milestones, not extra layout names alone.

No YOLO/MediaPipe/ByteTrack/PyTorch dependency or weights are silently installed.
Model/code licenses and CPU/NVIDIA/Intel/Apple compatibility must be reviewed
before choosing optional perception/separation backends. A local LLM is not a
replacement for those detectors.

## Final acceptance gates — not yet complete

| User acceptance test | Required evidence before completion |
| --- | --- |
| 1–2: import gameplay + facecam, detect independently | Consented real sample set, labelled region ground truth and model/version/confidence report |
| 3–4: vertical composition + stable player tracking | Actual export and frame-level crop/identity/jitter checks through motion/occlusion/cuts |
| 5–6: synchronized captions, 30 functioning presets | Installed speech weights, word-alignment checks, all-preset real render suite and visual review |
| 7–9: actual player, timeline edits, save/reopen | Native media clock tests, multitrack/effect output checks, edit persistence/recovery tests |
| 10: complete 1080×1920 export | ffprobe dimensions, duration/AV synchronization, captions/layout/effects checks and output checksum |
| 11–12: disconnect and repeat; no cloud API | Same workflow with real weights and OS-level network denied, including inference daemons/subprocesses, with observed results |

The complete PRO label/release must wait for all gates. The absence of a cloud API
key alone is not an offline acceptance test. Passing fixture/protocol tests alone
is not evidence of autonomous editing quality.

### Encoder reliability follow-up

Hardware export selection now requires a bounded, cached three-frame runtime
encode (NVENC/QSV/VideoToolbox, H.264/HEVC), rather than advertised availability
alone. VideoToolbox software fallback cannot be labelled hardware. Full-render
CPU retry remains. Diagnostics show an unverified candidate without UI-thread
probing. Source suite: 331 passed / 9 skipped; generated-video E2E: 35/35.
These policy/integration results do not establish native GPU or PRO completion.

### Timeline save/recovery follow-up

The existing single-source segment timeline now saves through same-directory
atomic replacement, flush/fsync and temporary-file cleanup. Before replacement,
a validated previous revision is atomically retained as `.json.bak`; corrupted
primary data never rotates over that backup. Load validates bounded JSON,
version, unique IDs, finite/ranged numeric fields and positive source intervals,
then tries the backup if the primary is missing/invalid. Legacy unversioned files
remain supported. New segment IDs resume after the highest saved numeric ID,
not the segment count. Invalid in-memory state is rejected before file writes.

Both editor reopening and pipeline export discover backup-only saves. Recovery
is explicitly reported as a previous revision (latest edits may be missing).
Editor autosave failures are reported without discarding the live edit. Backup
load does not silently rewrite the damaged primary; the next successful edit save
does so. If neither copy is valid, export fails rather than silently rendering an
unedited source; the editor warns when it must show the original clip.

Validation for this increment: **78 targeted tests passed** (`test_timeline.py`,
`test_timeline_recovery.py`, `test_creator_workflows.py`), including real FFmpeg
renders and recovered-save → reopen → speed-retimed vertical export. This is not
a new full-suite/native acceptance result. This is previous-revision protection
for existing segment edits, **not** multitrack project recovery, persisted undo
history, cross-process locking, media relinking or a power-loss guarantee on every
filesystem. A first save has no previous revision to recover; `.bak` appears on
a subsequent save. No new UI mockup or model dependency was introduced.
