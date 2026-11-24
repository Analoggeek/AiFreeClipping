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
