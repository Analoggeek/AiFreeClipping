# Clips Studio / Clips Kitty: automatic-editing reference review

## Scope and provenance

User request: first fully analyse `ColinGPT9/clips-studio`, explain the important
parts and identify what CLIPOS should carry forward without deleting existing
features. This increment is **analysis, comparison and implementation planning**;
it does not import upstream application code or claim its engines are integrated.

Reviewed revision: **bd39d8bc675db91d5a2092a472be0dcb5409ddb5** (main at inspection).
Reference source was cloned into excluded `.local/references/clips-studio`, not
vendored into our shipped application. No upstream installers, services, model
weights or download scripts were executed. Python-only targeted tests were run in
a separate process using the existing development environment.

Our comparison baseline: CLIPOS **46681f7**, including multitrack layers, linked
A/V timing, opacity/gain curves, waveforms, recovery and actual FFmpeg exports.
This is a source-level architecture/engine review, not a claim of line-by-line
security audit of every ancillary web/publishing/plugin file or real-world quality
certification of either application.

## Executive finding

The useful upgrade is **not replacing our desktop with their Electron app**.
It is a more evidence-grounded automatic-editing pipeline:

1. Understand the user's clip direction and exclusions.
2. Measure transcript + sound + visual/game events on a shared source timeline.
3. Generate candidates from both speech and non-speech events.
4. Score, de-duplicate and relatively rerank candidates with a local LLM.
5. Preserve hook/setup/payoff and complete sentence boundaries.
6. Propose safe tightening edits as reviewable edit decisions.
7. Reframe according to scene cuts and genuine audiovisual active-speaker evidence.
8. Remap captions/mutes/voice labels through cuts and speed changes.
9. Render, validate, retain explanations and learn bounded preferences locally.

Several components already exist in CLIPOS, but our current local agent primarily
compiles instructions into supported recipes/settings/ranges. It is not yet the
full multimodal, intent-conditioned selection/reframing loop found in this
reference. Our current activity metrics are measured motion/loudness, not semantic
game understanding. Our visual face-prominence heuristic is not active-speaker
recognition, and anonymous diarization is not an audiovisual face association.

## What the source actually implements

### A. Selection and automatic edit planning

- `analysis/fusion.py`: two candidate pools—transcript/LLM picks and signal peaks.
  Finalists receive a relative rerank rather than trusting absolute LLM scores
  alone. Non-verbal clips redistribute text influence; gaming can use game and
  sound evidence when the streamer is quiet. This matters for gameplay where a
  good moment has few spoken words.
- `analysis/highlights.py`: long-video chunk handling, bounded window batches,
  strongest-peak allocation rather than early-video-only budgets, time-based
  response matching, overlap/text/segment-reuse controls, sentence-aware starts
  and lead-in protection. A neutral/missing model score is not silently matched
  to the wrong candidate by list position.
- `analysis/intent.py`: structured requested subjects, time spans, exclusions,
  clip-count/duration preferences and grounded direction bonuses. It reports
  what was understood/not applied. This is different from a free-text field that
  simply changes an editing preset.
- `analysis/clip_edit.py`: conversational modifications to existing clip timing,
  crop, filters, captions and text corrections, using constrained edit controls.
  LLM parsing failure returns a no-op rather than executing arbitrary code.
- `analysis/tighten.py`: proposes dead-air/filler keep-ranges to the normal editor
  rather than silently rendering destructive cuts. Silence is audio-measured,
  not inferred just from transcript gaps; breath padding/minimum keeps protect
  rhythm. Its filler list is largely English; that list is not a safe multilingual
  policy for Hindi/Hinglish without additional evidence and tests.

### B. Better gaming evidence

- `analysis/game_audio.py` + `analysis/panns.py`: AudioSet sound tagging (e.g.
  gunfire/explosions/people reactions), stream-relative baselines, bounded chunks.
  This can distinguish semantic sound categories from simple loudness jumps,
  although it still cannot prove a kill/win from loud audio alone.
- `analysis/game_text.py`: local on-screen OCR/event words. Useful for banners,
  victory screens and score changes; low-confidence OCR must remain uncertain.
- `analysis/game_vision.py`: local image-capable Ollama models inspect a bounded
  number of frames for top candidates. The adapter limits the score adjustment,
  candidate count and time budget. No image-capable local model means no visual
  verdict; their cloud path intentionally skips this private-image step.
- Gaming profiles combine channels without treating in-game character faces as
  reliable streamer reactions. Chat/hype can add evidence, but it is optional,
  source-dependent and not required for offline local-file editing.

### C. Genuine active-speaker framing: highest relevance to our pending engine

- `video/asd.py` adapts **TalkNet-ASD**: synchronized face crops and audio features
  are evaluated to judge whether that visible face is speaking. This answers a
  different question from our diarization's "which anonymous voice is heard?".
- Input geometry is model-specific: 25 visual fps, 112-pixel grayscale face crops,
  16-kHz audio and aligned MFCC timing. Existing detector boxes are interpolated
  between sampled frames rather than rerunning the person detector at 25 fps.
- `video/tracker.py` separates unavailable/off-screen/silent/contested evidence,
  and uses persistence/margins to avoid switching on every small fluctuation.
  Missing TalkNet has a heuristic fallback; CLIPOS must explicitly label that
  fallback, not continue displaying a neural-speaker success state.
- `video/cuts.py` + `video/framing.py`: detect shot boundaries, reset subject state
  across hard cuts, select one subject rather than average two, hold the crop
  until meaningful drift, then move deliberately. Flash/motion handling and local
  frame refinement matter for avoiding false shot cuts.
- `video/podcast.py`: separate shot-aware podcast policy with stable framing and
  sustained turns rather than applying the gaming layout to all content.
- `analysis/voice_turns.py`: file-level voice profiles/segmentation/embeddings and
  second-speaker caption colouring. These voice labels alone are NOT a named
  identity, nor are they automatically persistent face IDs across camera cuts.

Upstream performance/accuracy numbers in module comments are **their reported
observations**, not measurements we reproduced. Some podcast comparisons use
TalkNet's own decisions as the reference, not independent human ground truth.
Single-visible-face/prominence fallbacks are framing policies, not proof that a
visible face is the audible speaker; off-screen narration remains possible.

### D. Editing, orchestration and long-form automation

- `video_editor/timeline.py` defines original-clip-time keep/mute/speed/audio/hook
  edit decisions; export modules remap/render those edits. This is useful time-map
  design, but it is not evidence that their editor is a replacement for our genuine
  independently overlapping multi-source project model.
- `longform/downtime.py` identifies sustained quiet/low-motion sections for edited
  streams; `longform/assemble.py` cuts bounded segments and concatenates compatible
  outputs instead of building a gigantic fragile filter graph. This is useful
  for long VODs, but quiet gameplay is not automatically worthless downtime.
- `core/pipeline.py`, `core/prefetch.py`, `core/outcome.py`: stage/queue state,
  bounded concurrency, pause/cancel behaviour, output-duration validation and
  explicit no-clips/render-failure outcomes. A failed render should not yield a
  fake completed clip card.
- `creator/learning.py`: preferences derived from the user's own exports/edits,
  inert until enough feedback and bounded/renormalized so scoring cannot drift
  uncontrollably. Useful as a resettable local preference feature, not as proof
  of audience retention or guaranteed virality.

## Gap / carry-forward matrix

| Area | CLIPOS already has | Important missing extension | Recommendation |
|---|---|---|---|
| Candidate generation | Sentence/scene/activity anchors, selected ranges, scored windows | Stronger semantic pools and bounded late-peak coverage under long-video budgets | Independently extend existing detector, retain current fallback |
| Selection | Measured signal scores, temporal overlap suppression, hooks/titles | Local-LLM relative reranking, transcript similarity/segment reuse, explicit rejection ledger | High priority; no fabricated scores on LLM failure |
| Natural-language editing | Validated local edit-plan compiler for settings/recipes/ranges | Grounded clip intent and per-clip conversational caption/crop/timing changes | Extend strict schemas, don't replace with permissive arbitrary actions |
| Semantic gaming | Motion/loudness activity, manual/automatic gaming regions | Sound tags, OCR and image-model verification of top candidates | Optional local evidence adapters with model availability/quality gates |
| Speech cleanup | Silence analysis/removal, renderer jump cuts | Reviewable silence/filler proposals with language-aware protection | Add edit proposals and reversible application, preserve laughter/music/reactions |
| Active speaker | Body tracks, visual heuristic, conditional anonymous neural diarization | Real audiovisual active-speaker scores and evidence-based association | Highest engine priority; use licensed original upstream ASD project, not main app copy |
| Framing | Existing dynamic face path, fixed body-driven export crop, manual gaming layouts | Shot-local identity reset, deliberate hold/move, speaker persistence | Improve in parallel with ASD; manual layout always wins |
| Captions | Word timing/editing, animated styles, retiming support | Consistent speaker-aware styling and all edit-time mappings | Unify source→output mapping; don't regenerate pretend word timings |
| Editor | Native real multitrack, linked A/V, fades, opacity/gain curves, waveforms, export | Proposal→editable timeline bridge, caption lanes, proxies and remaining advanced UI | Keep/enhance our model, no Electron rewrite |
| Long VOD automation | Batch/source ranges, bounded components | Dedicated edited-stream downtime plan, resumable chunk assembly/global labels | Add separate opt-in genre mode; never cut all quiet gameplay by default |
| Preferences | Explicit settings and recipes | Bounded local feedback-based candidate preferences | Later priority, reset/export/delete controls |
| Reliability | Atomic saves/output, recovery, cancellation and native CI | Rich per-stage outcome evidence, model/backend provenance, real native acceptance | Strengthen; source-level review doesn't satisfy device/offline acceptance |

## Licensing: no blind copy

The reference application's root `LICENSE`/`NOTICE` identify **AGPL-3.0-or-later**.
This is not the MIT licensing of the earlier DigiRG reference. Copying/adapting
main-app code or substantial protected material requires a compatibility and
compliance decision for the combined distributed software; attribution alone is
not a substitute. Root license/compatibility of CLIPOS was not established by
this review (there is no root `LICENSE` file in the checked-out baseline). Do not
infer permission merely because either repository is public.

Recommendation: independently implement the functional ideas in CLIPOS and use
original separately licensed upstream libraries/model adapters where appropriate.
Treat this report as architectural review, not as legal clearance or a substitute
for license review of any later implementation. Prompts, profiles, branding,
assets and tests are not automatically exempt from the upstream application's
license. Model **weights**, datasets and runtime code need separate checks.

The reference NOTICE describes TalkNet's vendored original as MIT, PANNs original
network code as MIT with CC-BY-4.0 weights, and Ultralytics as AGPL. Verify each at
its original pinned source/model card before distribution. Their custom adapters
are not presumed to inherit a dependency's permissive license. Do not replace our
YOLOX/supervision path with Ultralytics just because their tracker uses it.

## Explicitly do not carry over

- Publishing/auto-upload, scheduled posting, social tokens or account connections:
  conflicts with the user's standing requirement to remove publishing entirely.
- Mandatory cloud LLM/transcription, OpenRouter sign-in, remote rendering uploads,
  analytics/feedback uploads or account-gated editing.
- Electron/web/API architecture merely to imitate their UI; retain native Qt.
- Twitch/Kick/YouTube live-watch infrastructure as a prerequisite for editing
  authorized local files; source acquisition remains separate and lawful.
- Unreviewed plugins/marketplace execution, branding, outro media, secrets, binary
  bundles, model auto-downloaders or their entire dependency manifest.
- Security-bypass advice present in ancillary upstream documentation.
- Their benchmark claims as our own acceptance results.

## Prioritized independent implementation sequence

1. **Evidence contract + source/output time map:** versioned observations,
   availability/error states, source/model identity, bounded reads and per-stage
   outcomes. Bridge automatic edit decisions to editable/recoverable project data.
2. **Selection upgrade:** whole-video bounded candidate budgets, intent-conditioned
   candidates, robust sentence/hook boundaries, text/temporal dedup, small local
   rerank batches matched by immutable IDs and an explainable rejection report.
3. **Reviewable tightening:** audio-measured dead air plus conservative,
   language-aware filler proposals; preview/apply/undo; remap captions and labels.
4. **Active speaker + shot policy:** original licensed ASD runtime/weights,
   synchronized face/audio preprocessing, abstention and shot resets; associate
   diarized voice turns only where time-aligned evidence is sufficient. Never map
   a voice to a face from body size or temporal coincidence alone.
5. **Semantic gaming adapters:** local OCR/sound tags and limited visual-model
   review of finalists. Manual gameplay/player regions retain priority.
6. **Long-form and preferences:** opt-in downtime/chronological assembly with
   bounded resources, then resettable local preference learning.
7. **Acceptance throughout, not deferred marketing:** same authorized talking-head,
   multi-speaker, quiet gameplay and edited-camera fixtures; human label coverage;
   actual trained models; measured frame/caption/audio alignment; exported output
   inspection; Windows, Apple Silicon and real Intel disconnected runs. Do not
   declare current blockers solved by adding these source-level modules.

## Tests actually executed during review

Targeted upstream tests at the pinned revision, separate process:

```text
python -m pytest -o addopts='' -q \
  tests/test_selection_fusion.py tests/test_clip_intent.py \
  tests/test_speaker_detection.py tests/test_podcast_framing.py
82 passed, 1 failed, 3 skipped in 1.35s
```

Failure: `test_clip_intent.py::test_a_time_range_gets_windows_and_points`—the test
expected added windows within 480–590 seconds but obtained none. This is an
observed reference regression in this environment, not a proved diagnosis of
all upstream releases. Tests use generated data/stub LLMs and speaker decision
logic; they do **not** demonstrate real TalkNet inference, real gaming accuracy,
native output, disconnected inference or human-rated clipping quality. The
reference test suite was not run in full. Existing CLIPOS baseline remains
**538 passed / 10 skipped** from the previous implementation increment; no
application changes were made or regression suite rerun for this report-only review.

## Pinned source index

All links below refer to the inspected commit rather than moving main:

- [Architecture](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/ARCHITECTURE.md)
- [License / notices](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/NOTICE)
- [Multimodal fusion](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/analysis/fusion.py)
- [Highlight selection](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/analysis/highlights.py)
- [Grounded intent](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/analysis/intent.py)
- [Tightening proposals](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/analysis/tighten.py)
- [Conversational editing](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/analysis/clip_edit.py)
- [Active-speaker adapter](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/video/asd.py)
- [Shot-aware podcast framing](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/video/podcast.py)
- [Frame-cut refinement](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/video/cuts.py)
- [Voice turns](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/analysis/voice_turns.py)
- [Local gaming vision](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/analysis/game_vision.py)
- [Semantic game audio](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/analysis/game_audio.py)
- [Edit time model](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/video_editor/timeline.py)
- [Preference learning](https://github.com/ColinGPT9/clips-studio/blob/bd39d8bc675db91d5a2092a472be0dcb5409ddb5/creator/learning.py)
