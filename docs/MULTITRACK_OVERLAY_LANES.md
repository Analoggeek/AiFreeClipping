# Dedicated overlay lanes — Ai clipping PRO 3.6

## What is implemented

The multitrack project now has five real lane kinds: `video`, `audio`, `caption`,
`effect`, and `transition`. These are not decorative timeline rows. Each is part of
validation, persistence/history and the export/preview execution path.

### Caption lanes

Use **Add caption** in the multitrack workspace. Choose text, duration and a preset;
current global Caption Studio typography/color/motion/alignment preferences are copied
into the item and validated. **Edit caption** changes selected text/preset. Drag/trim
the timeline item or edit start/length in the detailed table.

`overlay_tracks.write_caption` creates real ASS cues clipped to the item range.
Export adds the ASS filter at the lane's position in the compositing order. Preview
uses a bounded `CaptionRaster` cache of actual transparent libass frames; it does not
replace captions with a QPainter approximation. No word timing is invented for manual
text. Explicitly set animation overrides take precedence over the chosen preset.

### Color-effect lanes

**Add color effect** creates a timed composite adjustment. Monochrome, Punchy and
Lifted Shadows are starting values for real brightness/contrast/saturation parameters.
Select the item and adjust those values in the Inspector. An effect modifies the
composition below its lane, so ordering effects above/below captions changes whether
caption colors are affected. Out-of-range times are not processed. Preview color
math remains approximate; export uses FFmpeg `eq`.

### Transition lanes

Arrange two overlapping video items first. The incoming video must begin later and
composite above the outgoing video. Select the incoming item and choose **Dissolve
into selected video**. Duration must fit the actual overlap. A dedicated transition
item stores both video IDs and the validated range. Export multiplies incoming alpha
by the transition ramp; preview applies the same duration/ramp.

There is one cross-dissolve per incoming item. It is a visual transition, not an audio
crossfade. Disable/delete the transition to remove it; opacity/fades can still be
configured on the video/audio items themselves. Moving/removing referenced videos
in a way that invalidates the transition is rejected atomically; remove/update the
transition first. A transition cannot be split into fragments.

## Integrity and compatibility

- Old `clipos.multitrack.v1` files load with neutral defaults for added fields.
- New lanes are additive within that project representation. Older application
  versions that do not recognize these lane kinds cannot open projects containing
  them. Keep backups and do not downgrade a new-lane project into an older editor.
- No existing project file is rewritten just by browsing the library.
- Dedicated overlay items cannot pretend to be arbitrary source files or contain
  unsupported media geometry/automation. Text is bounded; font/color/animation
  options are validated; caption filenames are hashed from IDs, not user paths.
- Timing, order, references, locks and history are transactionally validated on a
  copy before replacing live state. Invalid edits preserve both project and history.
- Actual exports retain source-overwrite protection, bounded duration/item counts,
  CPU fallback on hardware encoder failure and atomic final-output replacement.

## Acceptance

`tests/test_overlay_tracks.py` exercises actual caption pixels in preview and MP4,
timed color effects, a real blended red/blue dissolve, round trips, undo/redo,
invalid-reference atomicity, forged-state rejection, cue bounds and native add/edit
controls. Native regression/release workflows include this suite. Model quality and
physical-device acceptance are separate from those deterministic engine contracts.
