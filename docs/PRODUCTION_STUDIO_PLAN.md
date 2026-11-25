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
