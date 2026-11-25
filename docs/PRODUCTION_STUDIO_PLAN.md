# Integrated production studio — development status

The latest studio request supersedes the four-destination-only restriction.
This is an additive integration, not a replacement clipping/model engine.
No release version or public download is changed by this development increment.

## Architecture audit

Retained and reused: `video/multitrack.py` validated transactional model,
`ui/widgets/multitrack_timeline.py` graphical trim/move/snap gestures,
`video/multitrack_render.py` FFmpeg export and `multitrack_preview.py` compositor.
The latter is silent and best-effort, not a professional audio-clocked preview.
Existing crop/automatic clipping and centralized model lifecycle remain unchanged.
The studio consumes generated output references rather than modifying sources.

## Phase 1 foundation implemented

- Integrated Clip Queue & Editor navigation, accessible from Clip Library.
- Successful clipping navigates to the queue; database change signals refresh it.
- Multi-select queue with name, duration, aspect, file size, missing-file and
  timeline-membership status. These are actual filesystem/model values.
- Source playback through Qt Multimedia; explicit system-player fallback if
  platform multimedia libraries are unavailable. This is NOT timeline playback.
- Background FFprobe inspection and sequential assembly of selected sources.
- Existing graphical multitrack move/trim/snap gestures, paired A/V timing edits,
  numeric trims/moves, linked split/remove, undo/redo and JSON save/open.
- Existing project validation/backup recovery and no-overwrite-media protection.

## Phase 1 follow-up implemented

- Persistent queue order and custom groups; multi-selected up/down movement.
- Rename and non-destructive duplicate library records. Remove asks confirmation
  and keeps media plus existing timeline references; it does not delete sources.
- Available stored thumbnails and export dimensions shown, with explicit
  unavailable metadata rather than invented resolution/thumbnail data.
- Per-track lock and visibility controls, plus timeline zoom controls.
- Canvas width/height/fps configuration uses validated undoable transactions.
- Background source-amplitude waveform decoding with cancellation and bounded
  caching (current engine supports sources up to 30 minutes).
- Rendered timeline snapshot preview with mixed audio, using the actual export
  graph and canvas, background progress, cancellation and CPU encoding. It is
  explicitly a rendered snapshot, not a real-time/proxy playback claim.
- Track/item selection survives transactions so repeated lock/show operations
  continue to act on the selected track.

## Phase 1 remaining — do not advertise a complete professional editor

Graphical multiselection, real-time/proxy composited audio-clocked preview,
queue metadata generation for legacy outputs without metadata, full timeline
toolbar, and frame-timecode UI remain to be integrated.
The current timeline stores seconds with frame-grid snapping; this is not yet
a complete rational-timebase editor. Queue state is not a fabricated render,
caption or editing-completion indicator.

Later phases (batch configuration application; caption studio; original preset,
template, effect/transition libraries; color/audio/keyframes; batch rendering;
autosave/performance and native release) are NOT completed by this increment.
No buttons for these unimplemented features are shown.

## Validation

Full current regression: **652 passed, 15 skipped** in 51.77 seconds.
Focused queue/native timeline/render suite: **33 passed, 1 skipped**.
Queue restart tests cover groups/order/rename/duplicates and original file
preservation. Native integration renders and probes the actual timeline preview
with audio and builds a real decoded waveform. These are headless checks. The added queue integration test creates 20 database entries
referencing a real generated FFmpeg fixture, imports them in a worker, splits
linked media and saves/reopens the assembly. It is NOT evidence of generating
20 distinct AI clips. Physical permission dialogs and GPU acceptance remain
manual/unrun gates. Prior actual Windows/macOS Ollama installation audit passed.


## Selective batch configuration increment

The integrated inspector now provides **Current timeline media**, **Selected
queue clips on timeline**, **All timeline media**, and **Named queue group** scopes.
Generated clip IDs travel with imported media and persist in assembly files, so
selected duplicated library entries sharing one file can still be targeted
independently. Older/manual imports without queue IDs use explicit path matching.

Implemented categories are deliberately bounded to existing render support:

- Color: brightness, contrast, saturation.
- Transform: layer X/Y, width/height, opacity, rotation (canvas geometry, not a
  replacement for the original immutable AI source crop).
- Audio: static gain and duration-relative fade in/out.
- Captions: registered style/options on **existing** caption items wholly inside
  targeted video spans; this does not transcribe speech or copy dialogue.

Only checked categories change. The complete target set validates as one undoable
transaction; an affected locked track rejects everything without a partial apply.
Source trims, caption text/timing, existing automation and unchecked properties
are preserved. Audio fades adapt to each target's own duration. Overlapping video
windows may share captions; containment is a timing rule, not speaker ownership.

The inspector can read current item settings, save/load versioned JSON presets,
and persist explicit defaults for future imports. Future defaults are device-local
settings, not portable project metadata. Future caption defaults are explicitly
rejected until caption generation is integrated. Preset load itself changes no
project. Only Apply performs a transaction. This is not yet the complete CRUD
preset-manager phase or a full caption studio.

Latest tests: **658 passed, 15 skipped** (full suite); focused native editor/model
render tests **38 passed, 1 skipped**. Added checks prove selective color-only and
caption-only application, different-duration audio fades, locked-track rollback,
undo/redo, JSON roundtrip, exact queue-group targeting, future imports and actual
encoded color changes through FFmpeg. GPU, real-time playback and physical OS
permission dialogs remain unverified by these headless tests.


## Automatic Caption Studio integration increment

- Offline local Whisper transcription is integrated into the editor's existing
  target scopes. It never silently downloads a model; missing weights are an
  actionable AI Models error.
- Each enabled video item is transcribed from its actual trimmed source audio.
  Source trims and speed are mapped to timeline cue/word times. This uses original
  dialogue, not the muted/processed audio mix. Diarization is not claimed.
- Actual word timestamps persist in project files and feed the shared ASS
  export/composited-preview renderer. Manual corrections can change cue text,
  timing, words and their times. Timed caption splits preserve bounded word data.
- Registered styles and supported font/color/position/animation overrides are
  exposed. Existing batch caption-style application preserves dialogue/timing.
- Generation runs in a background worker, checks cancellation before extraction
  and between transcription segments, and commits the entire new caption lane as
  one undoable transaction. In-flight model inference is not forcibly killed.
- Captions are explicitly appended, never silently replacing manual corrections.
  Repeated generation therefore intentionally creates additional tracks.

Full current regression: **662 passed, 15 skipped**. Local extraction/render tests
use explicitly injected transcripts for deterministic timing contracts; those are
not recognition-quality evidence. The live workflow now adds actual official JFK
speech through the integrated editor path and exports/probes the result; its new
revision result is pending until read from CI. Earlier standalone known-English
speech inference passed, but does not certify this new integration.

Still not complete: 50 original style thumbnails, full split/merge workflow,
speaker detection, multilingual quality acceptance, automatic style previews,
real-time playback, complete transition/template/effect libraries and batch
export dashboard. Do not advertise a complete professional studio release.

## Batch export dashboard increment

- Selected/all queue entries already imported on the timeline can now render
  through the native batch dashboard. Each enabled video item becomes a separate
  MP4/H.264/AAC output (split items are separate outputs).
- Exports use the same compositing, caption and mixed-audio graph as timeline
  rendering, trimmed at each item's actual timeline window. Non-contributing
  missing media is not opened. Other overlapping layers/audio intentionally
  remain part of the composition.
- Actual per-job pending/processing/completed/failed/cancelled states, progress,
  counts, errors, encoder and measured-rate ETA are shown. Estimates remain
  labelled. Cancellation and in-session failed/cancelled retry use the same
  immutable project snapshot; completed files are not rerendered.
- Encoded dimensions/duration and audio/video are validated before publishing.
  Same-filesystem atomic no-clobber publication prevents replacing source or
  existing outputs, including a concurrent file-creation race. Filesystems without
  hard-link support fail explicitly instead of silently overwriting files.
- A JSON status manifest is written beside the outputs. Resuming a batch across
  application restarts is not implemented; the manifest is evidence, not a claim
  of restart recovery. Full MOV/HEVC/bitrate/export-profile controls remain absent.

Local native dashboard and batch tests render actual windows, inspect decoded red
and blue source pixels, probe dimensions/audio/duration, isolate missing-source
failures, retry only failed output, and test cancellation/no-clobber publishing.
The newest integrated live-speech CI failed; detailed stderr/evidence publishing
has been added so the cause can be read without unavailable runner log hosts.
Do not count that new live pipeline acceptance as passed.
