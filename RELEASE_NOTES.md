# CLIPOS 3.1.0 — Faster local editing and safer exports

Developed by **Analoggeek**. Performance and responsiveness update to v3.0.0.

## Performance and acceleration

- Detect and runtime-test AMD AMF encoders, in addition to NVENC, Quick Sync and
  Apple VideoToolbox. Hybrid GPU systems no longer depend only on the primary
  display adapter's vendor. No unsupported GPU is assumed usable.
- Raise the automatic high-core CPU budget from an eight-thread ceiling to up to
  32 threads, retaining OS/UI headroom and low-memory pressure safeguards.
  Explicit CPU-only/manual thread preferences remain available.
- Use faster CPU `veryfast`, NVENC `p4` and QSV `fast` presets. CPU filters and
  supported hardware encoding can work together; not every effect/inference
  stage can run on every GPU. No claim of universal full-GPU processing.
- Long-form export now uses detected hardware and adaptive threads instead of
  hardcoded two-thread CPU assembly. Hardware failure restarts all parts on CPU
  rather than mixing inconsistent encoder configurations.
- Scene detection operates on reduced-resolution samples at approximately 8 fps,
  rather than full-resolution content differences on every source frame. This
  trades sub-frame scene-boundary precision for faster analysis; review cuts.
- GPU speech initialization failure retries local CPU inference. This is not a
  promise that every possible model or mid-inference device failure is repaired.

## Responsiveness and interface

- Construct inactive pages only when opened; no startup initialization of all
  editors/previews. Hardware diagnostics run off the GUI thread.
- Keep task busy state until queued GUI completion is handled, fixing a race
  where a worker had finished but its export result was not displayed yet.
- Remove the separate **Multitrack workspace** navigation/page registration as
  requested. Existing multitrack saved/recovery files are not deleted or migrated;
  the underlying modules remain to preserve data compatibility.
- Refine dark palette and improve text contrast in both themes; retain lightweight
  native widgets rather than adding expensive blur or animation effects.

## Export reliability

- Clip and timeline renders use temporary sibling files and verify output before
  atomic replacement. A failed/cancelled render cannot destroy an earlier good
  output. Source overwrite is explicitly rejected.
- Hardware encoding failures retain the complete edit/filter graph on CPU retry.
  A failed CPU render is not pointlessly run again with the same graph. Cancelling
  a CPU fallback remains cancellation, not a successful export or another retry.
- Native Windows path and Intel macOS playback fixes from v3.0.0 are retained.
- Per-clip batch results and existing error reporting remain available. Without
  a user's failing media/log, their particular historical error cannot be claimed
  reproduced or eliminated. Disk space, permissions, corrupt media and device
  failures can still prevent export; no blanket error-free guarantee is made.

## Validation and measured scope

Local full suite: **581 passed, 19 skipped**; real import-to-export/batch E2E:
**35/35 passed**. Optional runtimes/devices absent in this sandbox account for
skips; native CI separately exercises the packaged platform dependencies.

A local CPU-only FFmpeg microbenchmark used a four-second 1280x720/30fps testsrc2
clip scaled to 1080x1920, libx264 CRF 21, two threads: `fast` took **3.509s** and
`veryfast` **1.764s** on this sandbox (one run each). This is a synthetic workload,
not a whole-app or Windows/Mac performance guarantee; encoder preset tradeoffs
can change compression/visual quality. No physical GPU throughput benchmark was
available in the sandbox. Native installers remain gated by platform CI and
all seven nonempty release assets before publication.

Offline/local-data and model limitations from v3.0.0 remain: optional TalkNet/AST
runtimes/checkpoints are not bundled by default, their trained quality is not
certified, and physical A/V sync/native hardware/driver acceptance is not implied.
macOS ad-hoc signing is not Apple notarization. No cloud upload/publishing or
mandatory account/subscription is added. Upgrade without deleting user data;
back up important projects before replacing the application.
