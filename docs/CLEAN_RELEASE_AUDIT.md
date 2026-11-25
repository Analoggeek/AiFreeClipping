# Clean clipping release audit

## Existing architecture (before implementation)

- PySide6 native shell (`ui/main_window.py`), lazy page construction, SQLite project/clip/export library. Existing model files, project database and delivered media are separate from application binaries and must not be deleted by upgrades.
- `video/pipeline.py` orchestrates real local audio/visual/speech analysis, automatic moment selection, clip persistence and FFmpeg exports on worker threads. Preserve this orchestration and decoder/encoder implementations.
- `video/renderer.py` already probes original dimensions, supports hardware encoder preflight with CPU fallback, output probing, cancellable FFmpeg processes and atomic replacement of completed renders.
- Crop root cause: the workflow's selector persists *player/gameplay* rectangles used only by a specific gaming recipe; there is no generic selected-region field in RenderSettings. Other presets enter body/shot/speaker/center framing. Automatic facecam detection can also replace gaming regions. Thus a visible source selection is not an authoritative crop contract.
- `core/editing.py` merges global editing presets into render settings. Old scene/subject framing is not independent of user crop. New explicit CropConfig must take precedence before any automatic framing and reject invalid geometry instead of silently falling back.
- `ai/gemma_runtime.py` already performs consented streamed Ollama pulls and verifies local GGUF metadata. It does not install Ollama, preflight actual storage/RAM, run inference after pull or persist an installation registry. Its UI is incorrectly labeled Director and tells users to install the runtime separately.
- `ai/person_tracking.py` already implements CPU-compatible ONNX YOLOX raw-head decoding with supervision ByteTrack. It requires a matching ONNX artifact; Python package availability alone is not model readiness. Do not install the unrelated legacy `bytetrack`/`yolox` source distributions and their incompatible compiled dependencies.
- Speech uses faster-whisper/CTranslate2; torch is deliberately not a core dependency. OpenCV GUI/headless collision is already handled by the dependency installer. Preserve that fix.

## Scope reversal

The requested clean product exposes four destinations only: Video Clipper, Clip Library, AI Models and Settings. Remove the old workflow/editor/Director/caption/template routes and their page construction, not the core FFmpeg/analysis modules or stored legacy user data. Shared render/data-format modules must not be deleted solely because the editor UI is retired.

## Verification requirements

- Actual FFmpeg crop exports for landscape, square and portrait sources, repeated clips, changed selection, CPU mode, output dimensions and decoded pixels.
- Invalid geometry and mismatched source dimensions fail before encoding; crop overrides automatic scene/subject framing. Preview and encoding consume one immutable config.
- Actual weight downloads/inference and OS installer execution are separate acceptance gates. Mocked HTTP, dependency tests and compilation do not count as those gates.
- Sandbox outbound networking is restricted to GitHub and package registries. Ollama model-registry and Hugging Face downloads cannot be established here; report this explicitly rather than mark live model acceptance passed.
- Do not publish an unverified clean stable release or update the public website to claim unavailable installers/models. Native Windows/macOS builds and model acceptance must be distinguished.

## Additional confirmed root causes

- The frozen build explicitly excluded `matplotlib`, but supervision's package
  initializer imports it even when only ByteTrack is used. The new build includes
  supervision, its distribution metadata and the noninteractive Agg backend;
  `onnxruntime` metadata is also retained for dependency verification. Tracking
  dependencies are installed by the standard dependency setup, not by pip inside
  the end-user executable.
- The old model page equated cached speech files / imported libraries with an
  installed integration. The new registry is updated only after an actual runtime
  operation; integrity failures, missing dependencies and failed inference are
  errors, not installed success.
- Clean generation does not read stale Director, captions, facecam recipes or
  experimental model-review settings from upgraded databases. It uses an explicit
  per-operation settings view without deleting the user's stored data.
- Existing `save_clips` replaced prior generated database records. Clean generation
  appends a new batch instead, preserving earlier playable outputs and library
  entries when the selected crop changes.

## Actual model evidence so far

GitHub Actions `45669932654` downloaded the official YOLOX nano ONNX release
(3,659,407 bytes), computed SHA256
`c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`, loaded
those real weights in CPU ONNX Runtime and executed inference. The same run
executed supervision 0.27.0 ByteTrack on a synthetic sequence and observed a stable
track ID. ByteTrack's actual CPU association test also ran locally after its
missing matplotlib dependency was installed. These are runtime/loading tests,
not real-person accuracy or trained clipping-quality acceptance.

### Additional native-runtime gates

The actual Linux Ollama run at `df155e9` completed Qwen2.5:0.5b and
`gemma:7b` pulls, GGUF inference returning READY, and database-reopen registry
checks. These results do not certify Windows/macOS interactive installation.
The upstream `gemma:7b` tag reported 9B/Q4_0 metadata; the application must not
infer the downloaded architecture solely from the human-readable tag.

Frozen-bundle verification now explicitly exercises ByteTrack synthetic
association, the ONNX CPU provider, and (on CI) checksum-pinned official YOLOX
weights through the actual packaged executable. This catches missing frozen
imports that a source-only test cannot detect. Detector accuracy remains unclaimed.

A separate disposable-runner workflow exercises official Windows/macOS installer
lifecycles and actual tiny Whisper download/loading/inference. Windows unattended
installer switches are restricted to that CI harness; application installation
continues to require explicit consent and the normal OS dialog. Headless jobs
cannot certify a human permission-dialog experience. Whisper inference uses
silence and is a runtime check, not speech-accuracy certification.

Speech downloads bind all files to one upstream immutable revision and verify
LFS SHA256/size or Git blob identity before inference and registration; large
weights use the resumable downloader with real byte progress and cancellation.
