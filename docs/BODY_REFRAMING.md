# Body-evidence export integration

This increment connects existing continuous person artifacts to actual FFmpeg
exports. It does not add a new detector or claim real detector acceptance.

## Selection and precedence

- Settings → Continuous person tracking: enable/disable body-follow and choose a
  person ID. ID 0 means auto: longest-supported track in the requested interval,
  breaking ties by observed area and then smaller ID. An interval must have at
  least 60% observed bins for that ID; auto does not hop between people.
- Requires smart reframe, enabled body-follow, and a person artifact in the
  analysis result. Body evidence takes priority over the old face-prominence
  heuristic only in non-gaming auto framing.
- Gaming composition retains independent gameplay/facecam rules; body evidence
  does not override it. Explicit per-segment crop/zoom retains priority. To keep
  a neutral static center, disable body-follow; the existing segment model has
  no separate per-segment auto-framing flag.
- With insufficient evidence the existing face/center fallback remains. Range
  exports report the fallback. Body IDs are spatial tracks, not speaker labels.

## Render behavior

The renderer uses a fixed even aspect crop and per-frame center expressions.
Centers are based on bounded temporal bins (at most 122), with local smoothing
only where neighboring bins contain evidence. Missing bins use neutral center,
not invented positions or another person's ID. Crop position is clamped to the
source frame. This follows body centers; it is **not** full-body fit, segmentation,
dynamic zoom, appearance reidentification or a guarantee every person fits a
vertical crop.

Range exports map center keys onto actual kept intervals after silence removal.
Timeline exports use each segment's original source interval, apply center motion
before its speed transform, and then concatenate in edited order. Captions/music
continue through the existing edited-output paths. The pipeline now passes
visual analysis to saved-timeline rendering too.

## Artifact validation and storage

The reader streams JSONL twice and bounds retained data to 256 IDs × at most 122
time bins, with 64 KiB maximum individual rows. It requires valid normalized
finite body boxes, a terminal versioned summary, matching resolved source path,
source file size and nanosecond mtime. This is stale-file protection, not a
cryptographic authenticity guarantee. Source replacement with identical metadata
is not detected. Frame-limited tracking artifacts cannot drive an export.

The tracking writer now records source size/mtime and rejects a source modified
during processing. **Earlier draft artifacts lacking these fields must be
regenerated**; a mismatched/invalid artifact raises an explicit error, not a
successful AI-framing claim. The existing artifact/atomic-write behavior remains.

## Validation

Fresh complete local pytest suite: **495 passed, 9 skipped**, 98.61 seconds.
New tests include actual FFmpeg range and reordered/speed-edited timeline exports
of a known moving white test subject; decoded output pixels verify visibility at
early and late times. Additional tests exercise chosen IDs, insufficient coverage,
manual precedence, malformed/oversized/stale/incomplete artifacts and silence-cut
key remapping. CI build/release editing gates include this module.

Test body coordinates are synthetic ground-truth fixtures; these tests establish
render integration, not real YOLO accuracy, natural-person quality, OS-level
disconnected AI inference or native playback. The sandbox's development GL stubs
are not physical graphics-driver proof. Continuous model acceptance remains
blocked as recorded in `PRO_INTEGRATED_MILESTONE.md`. Genuine professional
multitrack/live playback and actual local diarization remain unimplemented.
