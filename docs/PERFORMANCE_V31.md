# CLIPOS 3.1 performance audit

This is measured/implemented scope, not a promise to saturate every device or
eliminate every possible export failure.

## Findings and corrections

- Hardware policy capped high-core CPUs at eight workers. New automatic budget
  reserves one eighth (at least one logical worker), caps at 32, retains a four
  worker cap on <=8GB systems and drops to two under >=85% memory pressure.
  Explicit thread choice remains bounded to detected logical CPUs.
- AMD AMF was absent from both encoder discovery and rendering branches. Added
  H264/HEVC AMF, runtime-probed before use. NVENC and QSV no longer depend on just
  the single primary display GPU, enabling hybrid adapters when the actual
  encoder probe succeeds. Listed encoders alone never prove usable acceleration.
- Default x264 fast -> veryfast, NVENC p5 -> p4, QSV medium -> fast. Compression
  efficiency/quality can change; resolution/fps/captions/edit graph are retained.
- Longform had fixed two-thread software rendering. It now selects hardware,
  applies adaptive CPU/filter budgets, obeys shared UI encoder/thread settings,
  and restarts *all* parts on CPU after device failure to avoid mixed bitstreams.
- Scene content detection previously compared full-size frames at source fps.
  It now downscales to roughly 480px and samples roughly 8fps. Histogram fallback
  avoids retrieving/converting discarded frames. This is approximate cut
  evidence, not frame-exact boundary certification.
- Eager construction of all pages/previews/device diagnostics slowed startup.
  Only the main workflow is now constructed initially. Settings hardware work
  runs in a QThread; updates to widgets remain signal-based on the GUI thread.
- Workflow busy state could become false before the queued GUI completion slot
  delivered export results (consistent with an intermittent Windows release
  assertion in v3). It now remains busy through the finished handler.
- Clip/timeline output formerly wrote directly to the final file. A temporary
  sibling is now verified for positive duration/video dimensions and atomically
  replaced. Exceptions/cancellation clean the temporary, preserving old output.
  CPU failures no longer pointlessly retry an identical graph, hardware fallback
  preserves all effects, and fallback cancellation remains cancellation.
- Batch cancellation context is restored in finally, including disk/manifest
  errors. Existing per-clip error reporting is retained, not converted to success.
- Removed Multitrack workspace from navigation and page registration without
  deleting its saved/recovery files or low-level compatibility modules. Existing
  single-track advanced editing and automatic longform remain available.
- Dark backgrounds/accent and dark/light secondary text contrast were refined;
  no expensive blur engine or new animation loops were added.

## Validation

Local suite: 581 passed, 19 skipped (optional runtimes/native hardware absent).
Actual FFmpeg E2E: 35/35 passed. New tests cover AMF/hybrid decisions, transactional
output success/failure/cancellation, queued busy state, lazy navigation, background
diagnostics, longform device-loss whole-part CPU restart, and CUDA speech-load
CPU retry. Model/device decisions are mocked where hardware is absent, never
reported as physical GPU throughput acceptance.

Microbenchmark (one run per preset): four-second 1280x720 testsrc2, 30fps, scaled
to 1080x1920, x264 CRF21, two threads. fast: 3.509s / 2,428,458 bytes;
veryfast: 1.764s / 2,169,731 bytes. Generated files remain ignored under .local/.
This is not a Windows/Mac whole-pipeline benchmark or a quality assessment.

## Boundaries

A GPU cannot accelerate every CPU filter/caption/codec/model combination. Both
CPU work and supported hardware encoding run during accelerated rendering;
blindly using all threads/devices can reduce throughput and freeze the desktop.
No parallel unbounded FFmpeg jobs, GPU assumption, or removal of safeguards is
used to make an acceleration claim. Hardware decoder/filter interop, Apple MPS
speech inference, trained model quality, physical A/V sync, thermal behaviour,
all driver versions and arbitrary failing user media remain unverified. The
specific historical user error cannot be reproduced without its media/log.
