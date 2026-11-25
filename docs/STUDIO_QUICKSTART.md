# Development studio quickstart

This describes implemented controls, not a completed professional editor release.

1. **Video Clipper:** import authorized media, set the source crop, choose the
   analysis mode and Generate. Completed outputs appear in Clip Queue & Editor.
2. **Queue:** select clips and add them to the timeline. Rename/group/reorder
   library entries as needed. Duplicate references do not duplicate media files.
3. **Timeline:** drag items to move/trim, or use numeric fields. Linked A/V timing
   edits stay paired. Lock/show tracks, split, undo/redo and set linear video
   opacity/audio-gain keyframes at the timeline cursor.
4. **Batch inspector:** Read current item settings, check ONLY desired categories,
   choose Current/Selected/All/Group and Apply. Caption text/timing and unchecked
   categories remain unchanged. Geometry controls affect the editor layer; they
   do not silently modify the immutable crop used by AI clipping.
5. **Captions:** explicitly install/verify Whisper in AI Models first. Select the
   target scope in Batch inspector, choose language/style in Captions and Generate.
   This appends a caption track from trimmed source dialogue. Read a selected cue
   to correct text, word times, font, color, position or animation. Keep word text
   and dialogue consistent or clear stale word timings before applying corrections.
6. **Original library:** choose a caption composition or editing recipe. Render
   its illustrative FFmpeg demo if desired; these demo timings are not speech
   recognition data. Load the recipe, review checked categories/targets and Apply.
   These are offline configurations, not motion-graphics asset packs.
7. **Effects:** load a single adjustable filter or one of twenty combinations
   into the inspector. Review targets and Apply. Only Effects is checked by the
   effect loader. Preview uses the actual render graph.
8. **Transitions:** move incoming video so it overlaps a preceding lower video
   layer. Select incoming item, choose recipe/duration and Add. The duration must
   fit the genuine overlap. Preview via composite playback or rendered snapshot.
9. **Composited playback:** put the timeline cursor inside the project, open the
   playback tab and Play. It streams composited frames with mixed audio, using
   the physical audio clock where available. Stop before editing; pause/resume
   is supported. Heavy projects can buffer/drop video frames. If audio hardware
   is unavailable, use Render timeline preview (with audio) instead.
10. **Export queue:** choose an existing output folder and a unique project name.
    Render selected/all *already imported* queue entries. Each enabled video item
    becomes one output; split items become separate outputs. Overlapping layers
    and audio are intentionally included. MP4/H.264/AAC only in this dashboard.
    Completed outputs are validated; failures do not stop unrelated jobs. Retry
    uses the original batch snapshot and skips successful files. Existing files
    are not overwritten; choose another name/folder to render fresh versions.
11. Save the assembly JSON and any custom preset JSON separately. Source files
    are referenced, not embedded: keep them in place. Batch manifests record job
    status but do not yet support restarting jobs after the app restarts.

## Current acceptance boundaries

Real physical-device audio sync/performance, high-resolution proxies, full
advanced color/audio/motion workflows and new frozen installer acceptance remain
separate gates. Hindi requires suitable installed Devanagari fonts and multilingual
recognition review. See [phase status](PRODUCTION_STUDIO_PLAN.md).
