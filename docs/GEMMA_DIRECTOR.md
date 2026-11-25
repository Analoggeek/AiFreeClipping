# Native CLIPOS dashboard and local Gemma director

## Visible changes

The supplied dashboard is a design reference for the **native PySide6 desktop
application**, not a replacement website or a webview. Dark surfaces, purple/blue
gradients, a recreated scalable play mark, reorganized sidebar, actual file drop,
quick edit recipes, director review and real recent-project links share the
existing four-step import/edit/export pipeline. No dummy projects, notification
counts, user accounts or green model-ready indicators are populated.

Automatic long-form, standalone Presets/Templates and Caption Studio are removed
from page registration and navigation at the user's request. Their engine files,
existing projects and stored preferences remain intact for future reintroduction.
Inline caption editing/rendering is retained. Existing 38 caption styles continue
to use the real ASS engine; this change does not claim to have newly implemented
38 styles. Quick Gaming, Podcast, Talking Head, Educational, Reaction and
Cinematic buttons select actual deterministic recipes with distinct framing,
caption/colour settings, not arbitrary model labels.

The new logo is original SVG geometry in resources/icons/clipos-mark.svg. The
same design is rasterized for PNG, Windows ICO and macOS ICNS. It is not a copied
bitmap from the supplied reference.

## Local runtime and setup

1. Install and start Ollama separately from https://ollama.com/ . CLIPOS does not
   install a system daemon, change system services or run arbitrary shell commands.
2. Open **AI models → Gemma**. Refresh installed models; select a verified local
   model or explicitly approve a multi-GB download. Download consent is a one-time
   network exception, including when editing offline mode is enabled.
3. Default new configurations use `gemma:7b`; existing selected model settings are
   preserved on upgrade. Optional download identifiers include
   `gemma:7b-instruct-v1.1-q4_K_S`,
   `gemma:7b-instruct-v1.1-q3_K_S`, and `gemma:2b`. Official library references:
   https://ollama.com/library/gemma and
   https://ollama.com/library/gemma:7b-instruct-v1.1-q4_K_S . These are library tags,
   not embedded model weights or permission to redistribute Google's weights.
   Ollama errors if a tag is unavailable; there is no silent model substitution.
4. Verification uses local `/api/show` GGUF/architecture metadata and rejects
   cloud/remote models. **Test offline inference** runs an actual generation when
   a local model is installed. No prerecorded response counts as verification.
5. Low memory/Balanced/High quality set bounded director context and output token
   budgets (2048/4096/8192 context). GPU placement/quantization is handled by the
   installed Ollama runtime, not assumed from display hardware. Loaded memory
   queries `/api/ps` for runtime-reported allocation, not fabricated GPU usage.
   Unload releases model weights; it does not stop the Ollama system service.

Download progress is actual Ollama pull status/byte counts. The model registry
must be reachable only for explicit installation. Inference never calls a remote
AI endpoint. Proxy environment variables and redirects are disabled; endpoints
must be literal loopback or localhost normalized to loopback. CLIPOS cannot act
as an OS firewall for an independently modified local server.

## Director paths that execute real changes

### Create Clips

Import/open a project, type the desired editing direction, then request a plan.
The orchestrator summarizes actual persisted source dimensions/duration/audio,
a bounded transcript excerpt and up to 24 measured candidate clip records. Missing
transcript/vision artifacts are marked missing, not described as analyzed images.
Gemma does not substitute for Whisper, YOLO, ByteTrack or FFmpeg.

Only enumerated existing settings and in-bounds source ranges are accepted.
Unexpected fields, unknown presets/layouts, nonfinite/out-of-bounds numbers,
overlapping ranges, commands, paths and code are rejected. One regeneration is
allowed after malformed JSON/schema output; two bad responses fail without edits.
Review the JSON, apply it, or approve and run the existing actual local pipeline.
Applying settings alone is explicitly not presented as a rendered video.

Reviewed settings/ranges have transactional, durable, bounded undo/redo records.
Undo refuses to overwrite newer manual edits. This history survives DB reopen;
rendered files are not deleted/replaced by undo. Native preview/settings/ranges
refresh; re-edit renders the changed plan.

### Advanced editor

A second director panel operates on the **actual loaded clip timeline** using
strict typed commands for split, trim, speed, zoom, crop, mute, reorder and delete.
Every segment reference, numeric range and supported field is validated. A draft
is evaluated in isolation; conflicting/destructive commands fail atomically.
Approval checks project/clip identity and a canonical timeline fingerprint again.
A validated batch is committed as one real undoable Timeline operation, autosaved
through the existing editor and reflected in its actual frame preview/cache.
Existing Render performs the final FFmpeg export. No final export is claimed
from merely displaying a proposal.

This is bounded control of supported operations, not arbitrary autonomous access
to all application internals. New media tracks, freeform transitions, audio asset
download/selection, generated music, arbitrary zoom keyframes and unrestricted
multitrack agents are **not** implemented by this director. Unknown operations
are rejected, never approximated silently. Existing separate local analysis,
tracking, caption and editor engines are preserved, not falsely relabelled as
new Gemma capabilities. Automatic long-form remains retired as requested.

## Screenshot error handling

The supplied Settings screenshot has enabled optional analysis with empty paths
and no Ollama server. A checked option is a request, not model readiness. Settings
now calls out missing trusted TalkNet checkpoints, empty AST model directories
and missing vision-model selection, with wrapped/expanding form fields. Dashboard
readiness checks verify local model metadata off the UI thread. Missing runtime
or weights is an actionable error, not a green badge. Gemma text weights are not
advertised as a vision detector. All inference/download jobs run off the GUI
thread, and owning windows retain their threads during bounded shutdown.

The older export screenshot only establishes zero successful/5 failed outputs,
not a native backtrace. Prior 3.1.1 engine/font/native recovery fixes remain;
no new crash root cause is inferred just from the image. Current per-clip actual
errors and diagnostics remain accessible; no fake progress/success is added.

## Verification boundary

Automated tests cover transport/download consent, cloud tag refusal, bounded JSON
repair, real project application/history/reopen, missing analysis markers,
stale/destructive typed plans, real timeline persistence/undo/redo, approved
captioned timeline export and all six quick-style actual FFmpeg exports.
Injected transport/generation responses are contract tests, **not trained Gemma
acceptance**. The sandbox has no running Ollama/Gemma weights; live Gemma output
quality, model OOM/driver behaviour and whole-system offline inference are not
claimed tested. The in-app explicit test is available for installed local models.
Native release workflows now include this regression suite; installer publication
is a separate gated operation, not automatic from changing source/UI.
