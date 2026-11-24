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
