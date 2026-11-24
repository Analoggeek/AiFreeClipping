# Animated caption implementation (draft source, not a release)

CLIPOS now retains its eight legacy styles and adds **30 animated combinations**:
ten motion treatments times three typography/color profiles. This is deliberately
not described as thirty unique animation algorithms. These are real ASS tags and
word events consumed by the existing FFmpeg/libass export paths, not button-only
presets. No model, account, upload or network connection is used by animation.

## Preset matrix

Every cell is an actual `caption_style` key in the shared registry:

| Motion | Studio: white, light weight, fine outline | Impact: yellow, bold caps, thick outline | Arcade: cyan, bold, purple outline |
|---|---|---|---|
| Fade | `studio_fade` | `impact_fade` | `arcade_fade` |
| Spring scale pop | `studio_pop` | `impact_pop` | `arcade_pop` |
| Rise into position | `studio_slide_up` | `impact_slide_up` | `arcade_slide_up` |
| Horizontal glide | `studio_slide_left` | `impact_slide_left` | `arcade_slide_left` |
| Zoom settle | `studio_zoom_out` | `impact_zoom_out` | `arcade_zoom_out` |
| Rotation settle | `studio_tilt` | `impact_tilt` | `arcade_tilt` |
| Blur/scale focus reveal | `studio_blur_reveal` | `impact_blur_reveal` | `arcade_blur_reveal` |
| Scale pulse | `studio_pulse` | `impact_pulse` | `arcade_pulse` |
| Timed single-word pop | `studio_word_pop` | `impact_word_pop` | `arcade_word_pop` |
| Timed cumulative build | `studio_word_reveal` | `impact_word_reveal` | `arcade_word_reveal` |

The registry feeds existing caption selectors, render settings and bounded local
agent allowed-style validation. Saved style keys use existing settings storage.
No existing key or default was removed or renamed.

## Timing and editor behavior

- Cue-level animations use actual cue duration with bounded entry/exit timings.
- Timed word styles require finite, ordered, nonoverlapping word timestamps
  inside the cue, matching the cue's current text. Text edited independently of
  its old timing will not accidentally render the stale words.
- Missing/invalid/stale timings use whole-cue pop/fade instead. The implementation
  does **not** fabricate word timestamps and claim synchronized transcription.
- Inter-word gaps hold the displayed word/build until the next word; the final
  event ends at the cue boundary. Word-pop intentionally shows one active word;
  build-up progressively reveals the line.
- Motion geometry follows top/middle/bottom/split positioning. Existing font,
  size and outline overrides continue through the same ASS render entrypoint.
- The Caption Studio's painted sample is labelled **Typography Sample**, not a
  real ASS animation preview. Exact animation is rendered by FFmpeg on export.
  Native real-time ASS playback is not delivered here.
- Ten motions across three profiles provide thirty distinct combinations.
  Per-word highlighted-keyword overrides in the older whole-cue path are not a
  new per-word color editor for the timed styles.

## Validation and limits

`tests/test_animated_captions.py` tests all 30 combinations twice: with supplied
word timestamps and without them. Each renders five real RGB frames through
FFmpeg/libass, verifies visible text and temporal pixel changes. Additional
checks cover registry uniqueness, ASS escaping, positioning, stale timing and
cue-level fallback. Three integration cases export actual audiovisual MP4s
through `ClipRenderer`, not just raw ASS: Studio Word Pop, Impact Rise and Arcade
Build Up.

Selected regression suite: **174 passed, 2 deselected** in 5.12 s. Included caption,
creator export, timeline history/recovery, reference activity, encoder preflight
and local-agent tests. The two Qt-dependent agent tests are excluded because
native `libGL.so.1` is absent in this sandbox; their initial attempted execution
failed to import Qt, not passed or silently counted as successful. Full-suite
collection remains blocked by environment dependencies noted in the roadmap.

This is not a certification of multilingual shaping/fonts, physical device
readability, long-video/4K performance, audio synchronization quality, native
macOS/Windows live preview, thirty unique animation algorithms, or a complete
professional caption timeline. Real installed-Whisper/offline acceptance and
manual native visual review remain required. The wider PRO work is incomplete.

The generated-video pipeline E2E was also rerun: **35/35 passed**. Its obsolete
exact-eight-styles assertion initially failed after the expansion; the assertion
now requires preservation of all legacy keys plus at least thirty animated keys.
