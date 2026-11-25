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
