# Multi-source workspace, audio-clock path and neural diarization integration

This increment adds real engines and a working native Qt workspace. It is not a
claim that the entire professional specification or native/offline acceptance is
complete. The existing single-source editor, gaming flow and project files remain
unchanged and available.

## 1. Actual multitrack editing and export

Open **Multitrack workspace** in the sidebar. Import authorized local video/audio.
A video with sound creates separate video and audio tracks; each imported source
is independent. Later video rows composite above earlier rows. Edit table cells
for timeline start, source in/length, playback speed, gain, normalized canvas
position/size and opacity. Enabled toggles video visibility/audio mute. Locks
protect item edits. Split uses the timeline cursor; delete optionally ripples
within that track only. Layer order, source relink and runtime undo/redo are real
operations, not placeholder controls.

Save/open `.clipos-mt.json` projects with independent sources, tracks and items.
Project writes are atomic and retain a previous valid revision as backup; every
edit also saves a separate recoverable workspace. A missing source can be relinked
without rebuilding item IDs. Invalid operations validate on a copy and cannot
partially change the live project. Existing media cannot be overwritten by a
project save/export. Model limits: 64 sources, 64 lanes, 256 items; export currently
allows at most 64 enabled items and six hours of output. Paths are absolute local
paths; relink is required when transferring machines. Current defaults are
1080×1920/30 fps; other validated canvas settings are supported by the file/API,
not a new graphical canvas inspector.

Export genuinely decodes multiple inputs, trims/speeds each item, composites
overlapping video rectangles with opacity and mixes independently delayed/gained
audio tracks. Pitch-preserving tempo chains, compensated amix gain, peak limiting,
runtime encoder preflight and hardware→CPU retry are used. Final output is an
atomic MP4 replacement; failure/cancellation preserves an older output.

**Not yet professional-complete:** the current editor is a track/item table,
not the requested drag-and-drop professional timeline. No caption/adjustment/
transition lanes, automation curves, rotation, keyframe UI, snapping, grouped
video/audio edits, cross-track ripple, speed ramps, proxy/cache scheduler or
persisted multitrack undo stack is claimed. The legacy segment editor retains
its own already implemented persistent undo. Imported video/audio items start
aligned but later edits are independent. Per-track advanced audio/caption recipes
are not automatically imported from the single-source renderer.

## 2. Decoded preview and actual native audio-clock path

**Play silent preview** decodes and composites active source frames on a background
worker with a latest-request queue, not an intermediate rendered movie. Position,
size, opacity, speed, visibility and order are applied. This mode is explicitly
silent and best effort; it is not described as audio-synchronized playback.

**Play with audio** uses a separate FFmpeg raw-PCM mixer feeding a real Qt
`QAudioSink`. The video cursor uses `processedUSecs()` from that audio sink, not
an invented elapsed-time success clock. Audio queues and decoder counts are
bounded; empty queues stall the audio clock rather than pretend audio played.
Seeking pauses playback; pressing play resumes from the new cursor. Video frames
can drop under load. Hiding the page stops playback; shutdown stops readers,
audio and workers. Preview supports at most eight simultaneous decoded video
sources, max 640-pixel display extent. Nominal source FPS timing is used; VFR,
long/4K/high-FPS performance and exact device latency are not certified. The
limiter and millisecond audio delays may introduce small timing differences.

Missing QtMultimedia/backend/device/PCM support produces an explicit error; it
never silently reports successful A/V playback. Silent preview remains a separate
user choice. Export is independent of having an audio device.

The actual native sink test **skips in this Linux sandbox** because Qt multimedia
backend loading is unavailable. This code path therefore still requires Windows,
Apple Silicon and Intel Mac device acceptance and listening/synchronization
review. A source code path and PCM tests are not proof of working native playback.

## 3. Actual neural diarization integration, conditional on installed models

Explicit setup command:

```sh
python scripts/install_deps.py --diarization
```

This installs sherpa-onnx 1.12.34, not trained model weights. In Settings select
both **sherpa-compatible local segmentation and speaker embedding ONNX** files,
or disable diarization. The runtime performs neural segmentation, embedding
extraction and clustering on mono 16 kHz signed PCM audio. It is not the old
energy/face-prominence heuristic relabelled as AI. CPU inference is explicit.
Model permissions/licenses, including any gated model terms, must be satisfied
before local selection. The editor requests no account/token and never downloads
missing weights.

The analysis pipeline invokes a fault-isolated native worker. Invalid native
weights may terminate that worker, but not the desktop process. Parent-side
cancellation kills it, waits and preserves the previous artifact. The frozen-app
worker entry is routed before GUI startup; progress/error files work without a
console. Successful inference writes a bounded, atomic `analysis/diarization.json`
with anonymous file-local Speaker A/B labels, overlap-preserving turns, hashes
of audio/models and word-speaker associations from transcript timing. Ambiguous
words/overlap remain unknown. No confidence score or named identity is invented.
Input changes while processing are rejected. Current limit is 30 minutes of
audio; long-file/global clustering remains pending rather than silently chunking
speakers into inconsistent identities.

**No real trained diarization weights were available here.** Tests establish
label/overlap rules, no-download failure, cancellation and actual worker failure
isolation using intentionally invalid weights—not successful voice inference or
accuracy. The old visual-subject heuristic stays separate, with corrected UI/log
wording. Diarization labels are NOT automatically associated with visible faces/
bodies, and there is no complete correction/enrollment UI or cross-file voice
identity system. Transcript edits require fresh label association; the artifact
records the analysis-time transcript snapshot.

## 4. Validation and open acceptance gates

- Full local suite: **520 passed, 10 skipped**, 100.95 seconds.
- Existing generated-video pipeline E2E: **35/35 passed**.
- New tests verify real multi-source color/opacity pixels, independently mixed/
  muted audio frequencies, seek-correct PCM, decoded compositing, edits/locks/
  relink/undo/recovery, atomic export cancellation, GUI save/reopen/frame delivery
  and neural-worker fault isolation.
- The added skip is the actual native audio-sink test: Qt multimedia backend is
  unavailable. Existing development GL stubs allow headless widget tests; they do
  not demonstrate native graphics/audio behavior.
- Build/release gates include new tests and explicitly install optional tracking
  and diarization runtimes, including isolated x86_64 macOS test execution.
  Latest native results remain pending; packaged runtime/model collection also
  requires native validation.
- Real YOLO/Whisper/diarization/Ollama weights plus OS-enforced disconnection and
  end-to-end acceptance on Windows → Apple Silicon → Intel Mac remain required.
  Model-download egress and network-isolation privilege blockers recorded in
  `PRO_INTEGRATED_MILESTONE.md` have not disappeared. No disconnected success,
  native device success, merge, release or full PRO completion is asserted.

## Next increment: fades, transport and explicit acceptance runner

Both video and audio items now persist editable linear fade-in/out durations
(output seconds). Export video fades alter alpha, so overlapping layers can
produce dissolves; audio uses a matching timeline envelope before delay/mix.
Decoded video preview and seeked PCM preview evaluate the same fade timing.
Validation rejects overlapping fade lengths; split outside fades preserves only
the relevant outer fades. Split inside a fade is explicitly rejected rather than
silently changing its shape. Old files default to zero fades. This is not a
full transition library or keyframe editor.

Native workspace has previous/next frame buttons (project-frame grid), Alt+Left/
Right frame step, Ctrl+Z undo and Ctrl+Shift+Z redo, scoped to this page. These
still use nominal-FPS source seeking, not a VFR precision guarantee.

Explicit trained-model smoke runner (no downloads):

```sh
python scripts/accept_real_models.py --video authorized-person-sample.mp4 \
  --wav authorized-speech-16k-mono-pcm16.wav --yolo yolox_nano.onnx \
  --segmentation segmentation.onnx --embedding embedding.onnx \
  --report real-model-report.json
```

It runs continuous real tracking and neural diarization, requires positive person
observations and speech turns, and writes machine/architecture/input hashes plus
success or failure. It does not certify speaker accuracy or establish OS network
isolation. Run separately on each target with externally verified network
blocking. Do not substitute synthetic model outputs or publish private sample
media as acceptance evidence.

For a target's actual audio-device gate, set `CLIPOS_REQUIRE_NATIVE_AUDIO=1`
and run `tests/test_multitrack.py::test_real_native_audio_sink_when_device_exists`.
Missing device/backend then FAILS instead of skipping. This confirms sink clock
advancement only; physical loopback/listening, drift and video presentation latency
still need measured native A/V acceptance. Generic hosted CI lacks physical output
hardware and must not be labelled certified by bypassing this gate.

Official YOLOX release download retried during this increment: access to
`release-assets.githubusercontent.com` is denied by this environment's outbound
host policy. Real weights are still absent. Native workflow 45399594657 reported
Windows/Linux success but macOS failed at isolated Intel editing tests; the
restricted log-artifact host prevented retrieving the underlying failure log.
Workflow 45403335558 remained in progress at the time of inspection. Neither
native Intel acceptance nor a disconnected three-target pass is established.

Latest local validation after this increment: **522 passed, 10 skipped in 94.41 s**.
Workflow 45403335558 subsequently reported **Windows installer job success**;
Linux/macOS remained in progress. Installer build success is not physical audio
or disconnected acceptance.

## Graphical track gestures increment

The workspace now additionally includes a native painted graphical timeline
above the retained table inspector. Each lane displays its actual items using
persisted start and output duration. Drag clip bodies to move; drag either edge
to trim source/time ranges. A ghost rectangle previews changes without mutating
the project. Release commits one validated transaction, with existing autosave,
undo/redo and project save/reopen. Locked lanes do not emit edits. Trimming cannot
read before source start or beyond source end; model validation also rejects
invalid fades rather than silently changing their shape.

Click the ruler to seek. Enable snapping to nearby item boundaries/playhead,
otherwise the project frame grid; Shift temporarily bypasses snapping. Zoom is
5–240 pixels/second with horizontal/vertical scrolling. Selection is shared with
the table inspector. Edits remain independent per item; there is no implicit
video/audio link or cross-lane move. Same-lane overlaps remain allowed by the
compositor. No fabricated thumbnails/waveforms are drawn.

This closes the previous table-only limitation, not the entire professional
specification. Waveforms, thumbnails/proxies, keyframe/automation editing,
caption/adjustment lanes, grouped operations, cross-track ripple, drag-between-
track gestures and audiovisual speaker association remain pending. Snap gestures
use project frame timing; source VFR accuracy remains unverified. Native pointer/
high-DPI/accessibility acceptance is still separate from headless Qt tests.

Validation: **527 passed, 10 skipped in 95.54 seconds**. Five new tests include
actual Qt mouse move/release/edge trims, non-mutating drag preview, save/reopen,
undo, seek, snapping and locked-lane behavior. The native build and release gates
include this module on regular and isolated Intel Python runs. Real model and
physical audio/disconnected acceptance blockers recorded above are unchanged.

## Persisted linear opacity/gain automation increment

Video items now support absolute opacity keyframes (0–1); audio items support
absolute gain keyframes (0–4). Select an item, place the timeline cursor inside
it and use **Set key at cursor** with the value control. Remove the key within
half a project frame of the cursor, or clear the selected curve. Existing keys
can be replaced by setting at the same time. The inspector lists clip-relative
output seconds/values; the graphical timeline draws actual curve lines/markers.
Markers are visual inspection only, not draggable curve handles.

Curves are persisted with each item and default empty for old projects. Empty
curves use the constant opacity/gain inspector value. Non-empty curves override
that property's constant value, interpolate linearly between keys and hold the
first/last values outside their key range. Fade-in/out envelopes multiply this
result. There are at most 64 keys per curve, ordered at least one microsecond
apart. Unknown/wrong-track/out-of-range data is rejected transactionally.

Export video evaluates alpha through FFmpeg geq; decoded preview evaluates the
same curve in local output time. Audio export and direct PCM preview evaluate
volume after tempo conversion and before timeline delay, compensating for a
preview seek's offset. FFmpeg audio volume evaluates per audio frame, not every
sample. Video is evaluated per output frame. Curved alpha adds CPU cost; realtime
4K performance is not claimed. No GPU keyframe processing is implied.

Splitting inserts matching boundary values on both resulting curves and shifts
the right item's key times, preserving continuous automation. Moving an item
carries its local keys. Source trim/speed changes do NOT automatically retime or
remove keys; if a proposed new duration would place keys out of bounds, the edit
is rejected instead of silently destroying automation. Clear/re-author keys
before shortening such an item. Geometry/rotation/speed keyframes, easing,
Bezier handles, multiple selection and automation recording remain pending.

Validation: **531 passed, 10 skipped in 94.76 seconds**. Real FFmpeg pixel tests
verify animated alpha; direct seeked PCM measurements verify gain changes. Qt
control tests verify key creation/removal, recovery persistence and undo. Existing
fade/multitrack/graphical gesture tests still pass. These are generated-media
regressions, not real-model or physical native A/V acceptance.

Native run 45403335558 finished Windows/Linux jobs successfully; macOS failed
at **Verify editing under isolated Intel Python**. Its redirected Actions log
host is not reachable under this sandbox's egress policy. New CI runs preserve
pytest failure status while emitting bounded JUnit failure annotations directly
into check results, so the next failure should be diagnosable without pretending
Intel passed. This does not fix an unknown native failure preemptively.
