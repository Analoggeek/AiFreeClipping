# Integrated PRO milestone: implementation and acceptance boundary

User decisions: validate **Windows → Apple Silicon → Intel Mac**, one at a time;
use the best appropriate speaker behavior. The selected speaker policy is
**anonymous Speaker A/B diarization plus visible active-speaker association**.
No named voice/biometric recognition without separate explicit enrollment.
These four engines must eventually work together; finishing one adapter or
passing synthetic tests does not complete the milestone.

| Engine | Current source | Still required for acceptance |
|---|---|---|
| Continuous YOLO + ByteTrack | New opt-in YOLOX ONNX person detector + actual supervision ByteTrack, every decoded frame, scene-cut retirement, streamed normalized body-track artifact, pipeline/settings/CLI integration | Real YOLO weights acceptance, representative multi-person gaming/occlusion/VFR tests, consumption by body-aware reframing and native performance validation |
| Professional multitrack + live playback | Existing single-source segment timeline, real edits/exports, atomic saves/recovery, persisted undo/redo | Genuine multi-source video/audio/caption/overlay track schema and editing UI, live multitrack decode/composition/audio clock, proxies, seeks/cache/keyframes; rendered preview must not be called live playback |
| Anonymous speakers | Existing energy/face-prominence heuristic remains clearly separate from body tracks | Actual local diarization embeddings/clustering, overlap/unknown handling, audiovisual association with confidence and corrected labels |
| Real-model disconnected acceptance | Strict local-model loading policies and real media export tests exist | Real installed detector/STT/diarization/LLM weights; OS-enforced disconnected run across import→detect→diarize→multitrack edit→save/reopen→1080×1920 export on all three targets |

## Continuous tracking usage (new, opt-in)

Install optional runtime dependencies explicitly during setup:

```sh
python scripts/install_deps.py --tracking
```

This installs supervision 0.27.0 (MIT), SciPy, Matplotlib and support packages;
ONNX Runtime is already a core dependency. The installer deliberately avoids
supervision's GUI-OpenCV dependency and restores bounded headless OpenCV <5,
preserving CLIPOS's existing Haar/YuNet path. No trained model is downloaded by
this command. ByteTrack is the dependency's actual Kalman/two-stage association
implementation, not CLIPOS's earlier sampled face association renamed.

Supply an explicitly installed **trusted raw-head COCO YOLOX ONNX export**. Input
must be float32 `[1,3,S,S]`, S=320/416/640, with one raw output
`[1, sum((S/stride)^2), 85]`, strides 8/16/32. This is a YOLO-family detector,
not a claim to support every YOLOv5/v8/YOLO11 export. Preprocessing uses YOLOX's
BGR 0..255 float32 top-left letterboxing; decoding retains COCO person class 0,
performs NMS, and keeps low confidence observations for ByteTrack association.
CPUExecutionProvider is explicit: no untested GPU-inference claim.

In Settings, select **Continuous person tracking → Select installed model**.
Analysis then performs an additional continuous pass and writes:
`<project data>/analysis/person_tracks.jsonl`. Disable clears the model preference
and preserves existing face analysis. A selected missing/invalid model stops
analysis explicitly, not with invented tracks or an undisclosed fallback.

Headless equivalent:

```sh
python scripts/track_people.py SOURCE.mp4 LOCAL_YOLOX.onnx OUTPUT.jsonl
```

The output streams normalized body observations and a terminal summary with
model SHA-256, source, frame count, observations, engine and provider. It does
not retain an unbounded array of video frames/observations in RAM. Writes use a
temporary file and atomic replace; error/cancellation preserves the old output.
Scene cuts reset associations without reusing IDs. Missing/unsupported models,
unknown frame rates and detected early decode truncation fail actionably.

These body tracks are **not** faces or speaker IDs and are not yet fed into the
subject reframer. Nominal frame-index/fps timestamps are used; variable-frame-rate
alignment is not certified. Continuous means every decoded frame is processed,
not a claim that CPU inference runs at real-time speed. ByteTrack is spatial
association, not appearance-based reidentification through arbitrary occlusions.

## Evidence and blockers for this increment

- Whole local suite: **485 passed, 9 skipped**, 93.20 seconds. Existing development
  GL stubs are used for headless Qt tests, not native graphics acceptance.
- New tests execute **actual supervision ByteTrack** over a real decoded video
  with **synthetic detection boxes**, including a low-confidence observation,
  cut resets, empty detections, frame limits, atomic artifacts and cancellation.
  Raw-head decoding/NMS math and missing-model no-download behavior are tested.
  These are not real YOLO detector accuracy/weights tests.
- Attempted explicit model setup from the official YOLOX `0.1.1rc0` GitHub release
  (`yolox_nano.onnx`) failed when GitHub redirected to
  `release-assets.githubusercontent.com`, outside this sandbox's allowed hosts.
  No trained detector was installed and no real-detector success is claimed.
- `unshare -n true` returned **Operation not permitted**. Therefore an OS-level
  network-disabled acceptance run cannot be certified here. Python socket mocks
  or application offline flags are not substitutes.
- Existing installer/release gates now install the optional tracking runtime and
  include tracking tests. Latest native results remain pending. No installer,
  physical native execution, live multitrack or real diarization was validated
  by this increment. No merge/release is implied.

An accessible, licensed local detector file and suitable native hosts with
network isolation controls are necessary to close those acceptance gates. The
remaining engines require implementation, not merely supplying model weights.
