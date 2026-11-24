# Automatic selection and reviewable cleanup — independent implementation

Implemented after the Clips Studio reference review, without copying its AGPL
application code, prompts or tests. Existing native editors, recipes, body tracking,
multitrack and manual workflows remain available. This increment is NOT the entire
reference feature set: audiovisual active-speaker association, semantic game
sound/OCR/vision adapters, long-form mode, preferences and proxies remain pending.

## 1. Selection engine and Settings

**Strict automatic clip selection** is enabled by default for the analysis pipeline.
The legacy detector API/default path remains available; uncheck the setting to use
the prior count-filling policy. The new engine consumes real existing CLIPOS
transcript/scene/activity candidate windows and their measured heuristic scores.
It does not invent transcript, vision detections or semantic events.

Settings now provide:

- Prefer transcript phrases, comma-separated (up to 20, at most 100 characters
  each): modest bounded ranking preferences, not required semantic matches.
- Exclude transcript phrases, comma-separated: explicit word/phrase matches are
  excluded before ranking. "kill" does not match "skill". Normalization is Unicode
  case-folded token matching, not cross-language translation or named-entity AI.
- Optional free-text selection direction (up to 1000 characters), consumed only
  by the optional installed local model. Without successful local reranking, the
  report explicitly says this direction was NOT interpreted. It does not pretend
  that arbitrary instructions became guaranteed hard rules/time spans.
- Optional local reranking of up to 24 finalists. Uses the existing loopback-only,
  proxy/redirect-free Ollama transport, installed-local-GGUF validation and selected
  local model. No new cloud path, account, implicit model pull or upload is added.
  Title generation remains a separate setting.

The shortlist preserves the best candidate from each of 16 source-time regions,
then fills by measured score to a maximum of 96. This bounds *post-scoring*
shortlisting/model input; it is not a new bound on the existing full candidate
window generation or initial visual/audio analysis. Local reranking sees only the
first 24 shortlisted finalists and 600 transcript characters per candidate; it
cannot judge context it has not received. One request uses a 30-second per-request
transport timeout; model validation is a separate request, not a total 30-second
pipeline deadline. In-flight urllib requests are not asynchronously interrupted;
cancellation is checked before/after them and throughout selection.

Model responses must be exactly a permutation of immutable candidate IDs. Unknown,
duplicated, missing IDs or extra fields are rejected. No scores are fabricated or
changed to make an LLM answer look successful. Failure explicitly retains measured
ordering. Ordering tests use stub responses; no real Ollama weights ran here.

Selection rejects >25%-overlapping clips and highly repeated transcript stories
(three-word-shingle similarity, only for sufficiently long text). It never relaxes
exclusions/diversity to fill the requested count. Thus a 16-second source with
15-second requested clips yields one genuine clip, not six overlapping copies.
Heuristic fields still have legacy `virality_score` names, but no audience-retention
or actual virality measurement is claimed.

`projects/<id>/analysis/selection.json` is an atomic local report containing
criteria, selected ranges/IDs, selected count, model applied/fallback status,
rejection counts, up to 2048 rejection details and warnings. `AnalysisResult`
exposes it, and activity logs record actual selected counts. Existing selected
source ranges are applied before this engine and remain hard boundaries. The
report does not certify those candidates as semantic game highlights.

## 2. Automatic cleanup proposal → editable timeline

The pipeline generates `analysis/tightening.json` from actual audio-analysis
silence intervals for selected clips. It uses original source time, not gaps in
ASR text. Short gaps are preserved; internal cuts retain 180 ms breathing room;
known timed words protect a proposed gap. Tiny retained islands and all-silence
cases cause abstention rather than destructive guesses. There is no filler-word
removal yet, especially no English-only filler list applied blindly to Hinglish.

The source is bound by path/size/mtime signature recorded at analysis start and
checked at analysis completion, proposal generation and review. This detects normal
source replacement/editing but is not a cryptographic content hash or adversarial
file-lock guarantee. Old analysis objects without a source signature cannot create
new cleanup proposals.

In **Preview Editor**, **Review auto cleanup** loads the current clip's matching
proposal, verifies source freshness, validates against a copy of the current
timeline and shows resulting keep-segment count/output duration. Only **Apply**
commits one undoable edit; **Cancel** changes nothing. No separate confirmation is
needed to run selection, but these editing-product review controls intentionally
preserve reversible human oversight. They are not chat permission prompts.

Applying intersects source-time keep ranges with current segments, preserving
existing order, speed, crop, zoom and mute properties. Current edits outside the
proposal range, invalid intervals, tiny resultant edits, more than 10,000 output
segments and total deletion are rejected without partial changes. Existing timeline
autosave, persisted undo/recovery, source-time preview/caption rendering and export
continue to operate on the resulting segments. The cleanup bridge currently targets
the existing single-source editor, not arbitrary multitrack automation; multitrack
item/group/keyframe policies remain separate and are not silently flattened.

## 3. Validation and truthful boundaries

- Full local suite: **556 passed, 10 skipped**, 95.76 seconds.
- Focused new tests exercise phrase grounding, strict diversity, late-source
  candidates, exact-ID local ranking/fallback, cancellation, hard selected ranges,
  pipeline report persistence, measured audio silence, cleanup word protection,
  preserved timeline properties/persisted undo, editor Apply/Cancel and stale sources.
- Generated-video import→analysis→selection→captions→render→export→ZIP E2E:
  **35/35 passed** after correcting the old fixture expectation that one 16-second
  source must produce multiple differently scored near-duplicate 15-second clips.
  The revised assertion requires one actual clip plus an explicit report shortfall;
  changing scores or refilling duplicates just to pass would be incorrect.
- Full-suite result precedes two final allocation guards in cleanup; targeted
  regressions were rerun after those guards. No model/physical-device acceptance
  is inferred from unit tests or the generated-media fixture.
- Build/release regular and isolated Intel gates include the new engine tests.
  Previous native Intel failure is unresolved until actual new native diagnostics
  are available. No merge, release, offline native certification or whole-scope
  completion is claimed.

## 4. Remaining reference carry-forward work

The code-level review remains `CLIPS_STUDIO_REFERENCE_REVIEW.md`. Still needed:
complete grounded natural-language intent parsing (especially time spans/exclusions
and unsupported intent reporting), richer semantic candidate generation, sentence/
hook end-to-end quality fixtures, actual audiovisual active-speaker inference and
association, semantic game audio/OCR/vision, shot-aware camera policy, chronological
long-VOD cleanup, bounded resettable preference learning and remaining professional
editor/proxy work. Each must retain explicit unavailable/unknown states and be
validated with authorized real media and actual models. No upstream publishing,
social tokens, mandatory cloud services, marketplace execution or branding is added.

## Long-form editor and opt-in local preference increment

### Native long-form flow

New additive **Automatic long-form** sidebar page: select an authorized local
video, run automatic analysis, review/edit source start/end boundaries, save/open
the versioned JSON plan, then export a chronological 1920×1080/30fps MP4. Source
aspect ratio is preserved with padding, not a forced vertical crop. No existing
short-clip project, editor or file is removed/replaced.

`video/longform.py` measures actual FFmpeg `silencedetect` and `freezedetect`
evidence in at most 120-second decode windows, over video up to six hours.
A proposed downtime cut needs BOTH audio <= -45 dBFS and a sustained frozen
picture for at least eight seconds. It retains 0.6 seconds of padding on each
side. This is a conservative signal policy, NOT semantic scene/game understanding;
very quiet static but meaningful material may still be proposed for removal.
The native plan table allows review before export. Normal audio or normal image
motion prevents that interval being cut. No-audio videos retain the whole source
instead of inventing silence evidence. All evidence remains local.

Evidence windows are independent: a freeze/silence that straddles a 120-second
boundary may be missed or produce an extra retained boundary island. That is a
safe false-negative tradeoff, not exact global downtime segmentation. Fine noise,
source audio gain, compression and image scaling affect these fixed thresholds.
No automatic word-level speech guarantee is claimed for this no-transcription
long-form path. Keep boundaries can be edited manually; this first page does not
include waveform/preview/undo controls of the separate existing editors.

Plans bind source path/size/mtime signature and validated source-time segments.
Export accepts 1–2000 chronological keeps at unchanged speed, encodes one part at
a time with identical libx264 CPU/AAC parameters and concatenates compatible
streams. It does not create one enormous N-input filter graph or load the entire
VOD into memory. Disk use still grows with encoded keep parts plus the final
output. Export validates final duration/streams and source freshness, checks
cancellation, and only then atomically replaces the requested MP4. Existing
outputs survive error/cancellation; temporary parts are removed. Missing source,
invalid plan and out-of-bounds user edits fail explicitly. It is a CPU path with
honest encoding progress, not an unmeasured GPU-performance promise.

### Local ranking preference learning

Settings has **Learn bounded local selection preferences from successful exports**,
off by default. Only while opted in, saving selected clips records a limited
snapshot of already measured channels (motion/loudness/energy/story/hook) in their
existing clip metadata. No transcript, audio or video is uploaded, and no schema
migration or new external account is required.

On later automatic selections, `ai/preferences.py` compares distinct successfully
exported clips with their local library baseline (at most the latest 5000 clips).
Repeated exports of the same clip do not increase its sample count. Failed/empty
exports and missing/invalid feature values do not train. Fewer than eight unique
exported feature profiles => no bias. Per-channel coefficients are bounded to
±0.15; total candidate influence is clamped to ±4 ordering points. Measured scores
are not rewritten, explicit exclusions/diversity still apply, and reports expose
the profile used. The optional local reranker runs after this heuristic stage and
can order its candidate pool differently.

Exports are an implicit user preference proxy, NOT observed audience performance.
Batch/one-click exports can reflect the automatic choice rather than a separate
manual endorsement; if exported profiles match the whole library, bias tends to
zero. There is no claim of causal preference accuracy or higher engagement.
**Delete learned selection feature snapshots** transactionally removes these
snapshots, retaining unrelated clip metadata and actual export history. Reads and
reset batches are bounded. Disabling the feature stops recording/applying learning;
use reset as well to delete already retained snapshots. A fresh opt-in can learn
again from newly recorded clips.

### Validation

Full local suite **561 passed / 10 skipped in 97.14s**. New tests cover actual
FFmpeg frozen+quiet analysis, real chronological output streams/duration, old-output
preservation on cancellation, stale-source rejection, native plan edits/save/open,
unique-export learning, coefficient bounds, invalid/failed feedback and reset
preserving unrelated metadata. A final bounded-reset change also passed targeted
regressions. Build/release regular and isolated Intel gates include the new tests.

The earlier review's long-form/preferences items are now implemented to the
specific limits above; this does not turn signal-based downtime into semantic
understanding or certify physical audio/video and real-model accuracy. Latest
inspected native run 45408739163 had Windows/Linux jobs successful and macOS still
running; no native acceptance result is inferred from a hosted build alone.

## Source-grounded local evidence and captions

The Settings page adds independent opt-ins for local visual review, installed
OCR, and constrained direction compilation. All remain local; there is no
publishing or upload path. Visual review requires an explicitly installed,
vision-capable Ollama model on the existing loopback-only transport. Up to four
finalists get three decoded frames each. Model verdicts are fallible evidence;
the bounded +/-3 ranking adjustment never changes the measured signal score.
Failures are recorded instead of manufacturing successful reviews.

`python scripts/install_deps.py --ocr` explicitly installs RapidOCR 1.4.4 and
its wheel-bundled PaddleOCR detector/recognizer/classifier ONNX files. No model
is fetched by the OCR application path. Installed models are SHA-256 identified
in evidence, CPU sessions are bounded, ONNX telemetry is disabled, and source
freshness/cancellation is checked. OCR observations include timestamps,
normalized boxes and confidence (>=0.8); they do not themselves establish a
kill, win, game state, or sound event. OCR text is supplied as labelled evidence
to the optional local semantic selector, not a guaranteed keyword boost.
Optional installed OCR is collected into frozen builds; native build workflows
explicitly request it. Apache notices are in `resources/licenses/` (RapidOCR
and PaddleOCR). No reference application's code, prompts or tests were copied.

Intent compilation accepts only phrases literally grounded in the instruction
and explicitly written valid clock endpoints. Positive ranges intersect, never
expand, the user's hard selected ranges. Unsupported directions and failures
remain visible in the selection report. This is not complete arbitrary natural
language editing or semantic time-exclusion interpretation.

Speaker caption colours use source-bound anonymous diarization turns, validate
word text/timestamps, split at unambiguous speaker changes, and survive ordinary
and saved-timeline speed/cut retiming. Overlap, missing words or stale text use
the default caption colour. These are audio speaker labels, not visible person
identities. Existing caption styles and keyword emphasis remain available.

Shot-aware crop resets at scene boundaries and holds the best-observed face
track within each shot. No-evidence shots reset to centre. Piecewise crop times
are mapped through kept ranges; explicit manual composition, gaming layout and
body framing keep precedence. This is face-coverage framing, **not TalkNet
active-speaker audiovisual association**. TalkNet inference and semantic gaming
sound classification are not implemented by this increment; no synthetic or
mock local-model response constitutes acceptance of those capabilities.

Validation: full suite 570 passed / 10 skipped; E2E import-to-export/batch 35/35.
Tests include actual libass colour pixels, FFmpeg cut-boundary crop pixels,
source-frame decoding and real trained OCR on a generated text video with
network requests blocked. Ollama responses are mocked in automated contracts;
those tests do not prove real visual/intent model quality. Skips/headless runs
do not certify physical A/V sync, disconnected OS operation, or native
Windows/macOS hardware acceptance. No release is implied by these results.
