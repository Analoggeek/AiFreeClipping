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


### Advanced timeline controls and regression follow-up

The native timeline now exposes snap on/off, track reorder/rename, linked
ripple-removal on each linked item's own track, and existing linear video-opacity
or audio-gain keyframes at the cursor. Keyframe set/remove/clear is validated and
undoable. This does not claim arbitrary property keyframes, easing, graphical
multi-selection, global ripple editing or complete professional timeline controls.

Full local regression: **667 passed, 15 skipped** in 50.32 seconds. This includes
native dashboard output, persisted manifests, actual output probing, linear
keyframe controls and track-order interactions.

The live speech diagnostic at `97bbf6f` confirms standalone known-English speech
WER **0.0**. Integrated export stopped because that minimal CI job lacked FFmpeg,
not because a captioned output passed. The job now explicitly installs/verifies
FFmpeg and FFprobe before integrated speech acceptance. That retry remains pending.

## Shared-graph playback and original creative library increment

### Implemented

- Streaming composited playback uses the **same FFmpeg filter graph** as final
  export, including real captions, effects, transitions and mixed audio. NUT
  packets are demuxed through PyAV into RGB frames and stereo S16LE PCM, without
  rendering a whole preview video first. The native widget schedules video by
  the audio sink's processed-sample clock. Pause/resume and cursor restart exist.
- Queues and decoded buffers are bounded. Late video frames drop instead of
  intentionally dropping audio. Unsupported/missing audio devices produce an
  explicit error and offer the already-existing rendered snapshot alternative.
  This is an implementation, NOT measured physical-device sync/throughput
  certification. Full-res filter processing may still be slower than real time;
  on-the-fly downscaled frames are not a persistent high-resolution proxy system.
- Edits are guarded while composited playback runs. Shutdown refuses to destroy
  a still-running worker; cancellation may need to wait for model inference or
  source inspection to return. Source and composite playback are distinguished.
- 50 original caption compositions: ten palette/typography families × five
  implemented motion treatments. These are 50 distinct presets, not 50 animation
  algorithms. Existing 38 compatibility styles remain. Script glyph coverage
  depends on installed fonts; Hindi family names are not quality certification.
- 50 original asset-free editing recipes: color/audio/transform/caption settings,
  with real rendered demo thumbnails on request. They are not elaborate motion
  graphics, title packs or replaceable-logo/music scene templates. Loading a
  recipe changes no project until the user reviews target scope and clicks Apply.
- Eight implemented adjustable video filters and twenty original combinations:
  blur, sharpen, vignette, seeded grain, desaturation, hue, red/blue mixing and
  negative exposure. Effect lists validate before execution, participate in
  presets/Apply-to-All, persist in assemblies and render in shared-graph playback.
  Arbitrary FFmpeg strings/scripts/URLs are rejected.
- Forty overlap-based transition recipes: ten alpha-mask families × four curves.
  They use actual overlapping incoming/outgoing video layers, not invented source
  handles. Transition creation fails atomically when overlap is insufficient.
  Cross dissolve compatibility is preserved. The legacy silent draft compositor
  explicitly rejects unsupported new effects/transitions rather than showing an
  incorrect preview; use shared-graph playback or snapshots instead.
- Inspector, captions, export, playback and creative libraries are organized in
  functional tabs. PyAV is an explicit installed/frozen dependency, not a lucky
  transitive import. Frozen runtime checks now exercise real video/PCM streaming.

### Evidence

- Full local suite: **677 passed, 15 skipped**, 58.01s.
- All 50 original caption presets rasterized through actual FFmpeg/libass.
- All 40 transitions and all 28 primitive/combination effect cases encoded.
- All 50 recipe configurations validated/applied/undone; five treatment variants
  actually exported. This is NOT a claim that every recipe got full media QA.
- Real streaming tests verify seek position, decoded source pixels, video frame
  count, PCM duration, bounded worker backpressure and cancellation. Physical
  speakers, audio drift, GPU performance and long-session memory need native QA.
- Linux actual speech run `45687423349` at `18c71bc` PASSED: standalone known-English
  WER 0.0; integrated editor emitted 4 cues / 22 timed words and exported/probed
  captioned video. It is one English sample, not multilingual speech certification.
- Local source-mode explicit runtime command emits 3 video and 15 audio frames.
  New frozen/native builds still need their own results; source execution is not
  evidence that a packaged build passed.

### Still not the entire original specification

Unfinished requirements include complete advanced curves/wheels/HSL/LUT grading,
full audio EQ/compressor/ducking/music workflows, arbitrary/eased keyframes,
professional motion graphics/stickers and replaceable-asset templates, graphical
multi-selection/global ripple, caption merge/speaker UX, rational timecode/proxy
cache management, restart-resumable export jobs, broad export codecs/profiles,
project autosave/recovery UI, and physical Windows/macOS/GPU release acceptance.
No stable release or complete-professional-editor claim is made by this increment.

## Native Windows pipe fix and color/audio processing increment

Native run `45689688721` at `60350e0`: Linux package and macOS app/disk-image
jobs PASSED (the macOS job includes Intel and Apple Silicon). Windows FAILED
before packaging: PyAV attempted `fseek` on a Windows pipe and raised EINVAL;
streaming tests and their dependent worker test caught this. This was not skipped.
`ReadOnlyPipe` now exposes read callbacks only, with no seek/tell methods, so
PyAV cannot install an invalid callback. A regression simulates Windows pipe
seek/tell failures, and actual streaming/backpressure tests still pass locally.
**The new Windows native rerun remains pending**, not certified by Linux tests.

New implemented workflows:

- Eight bounded audio processors: three fixed-band EQ controls (100 Hz, 2.5 kHz,
  8 kHz), FFT noise-floor reduction, ratio-controlled compressor, peak limiter,
  echo and rumble high-pass. They are not trained AI voice reconstruction.
- Audio processor lists participate in selective batch presets, undo, saved
  assemblies, shared-graph streaming, mixed export and the legacy audio preview
  graph. Only checked audio-processing settings change. Audio gain/fades remain
  independently selectable. Existing gain automation retains its current model
  semantics and takes precedence over static gain.
- A local background-audio import creates an independent audio lane at the
  cursor in a worker. It never overwrites source audio, invents music, loops or
  silently ducks it. Apply gain/fades or trim explicitly.
- Color grading adds exposure stops, gamma and RGB shadows/midtones/highlights,
  separate from basic brightness/contrast/saturation. Its own selective category
  participates in presets, batch application, project save and the same render
  graph. This is not complete RGB curves/wheels/HSL/temperature grading.
- Local normalized 3D `.cube` LUT import supports sizes 2–65, finite bounded
  samples, strict row counts, a 16 MiB cap and explicit SHA256 binding. Unsupported
  domains/formats fail clearly. Strength blends the LUT samples against identity
  in an isolated work asset. Modified or missing original assets fail rather than
  silently changing the look. Presets reference LUT files, not embedded copies;
  retain those authorized assets when moving projects.

Evidence: full local suite **683 passed, 15 skipped** in 60.07s. All eight audio
processors were actually encoded and an EQ/high-pass change was measured in
streamed PCM. Tests encoded and inspected LUT pixels at full/zero strength,
checked streaming uses the same LUT graph, rejected changed LUT bytes, exercised
exposure/balance, roundtripped saved grades, and drove native audio/LUT controls.
Physical speakers, long-session audio drift, GPU throughput, real human OS
permission dialogs and full asset-based motion graphics remain unverified or
unimplemented; none are claimed passed by this increment.

## Explicit dialogue-driven automatic music ducking

Native build run `45720086014` at `8ccc387` PASSED for Windows, Linux and macOS
(the macOS job builds Intel and Apple Silicon). Thus the Windows non-seekable
pipe fix passed its native streaming tests and installer build, not just Linux
regression. This does not certify a physical audio output device or OS dialog.

The Audio tab now assigns **dialogue**, **music** or **neutral** roles explicitly.
Imported background audio defaults to music with ducking OFF. Generated/ordinary
audio retains dialogue compatibility defaults; mark game/SFX as neutral if they
must not drive a music compressor. This is signal routing, not speaker detection.

For music, enable automatic ducking and set threshold dB, ratio, attack and release.
Load Audio Routing into the inspector, choose targets and Apply. Dialogue signals
are split into audible output plus a summed control bus; only that control bus
attenuates enabled music. Neutral/game signals do not drive it. No duplicated
voice is added to the audible mix. Missing enabled dialogue is an explicit error,
not a fabricated successful ducking result. Voice-silent intervals leave music
unattenuated, and seeks/windows retain prior driver history so compressor release
is not silently reset. All processing uses the shared graph for streaming/export;
legacy raw-audio preview has matching routing. Visual recipes never relabel music.

Audio routing is a separate selective preset category, validates atomically,
persists in assemblies, and supports undo. Threshold/ratio/time values are finite
and bounded. No external service/model is involved.

Full local regression: **686 passed, 15 skipped**, 57.31 seconds. Actual mixed PCM
tests isolate the 1 kHz music tone from a 400 Hz dialogue driver and verify >50%
attenuation during dialogue, >90% recovery in voice-silent intervals, and seek
release-envelope parity. Window exports, saved routing, UI configuration and
undo are covered. These are digital signal tests, NOT speaker-loopback tests.
New native builds for this ducking revision are pending until CI reports them.

Still unfinished: complete asset-based motion-graphics packs, full curves/wheels/
HSL grading controls, physical audio latency/drift/throughput QA and human OS
permission-dialog acceptance. Do not mark these complete based on build success.


### Curves, wheels and original asset graphics (development branch)

- Color panel now exposes draggable master/R/G/B natural-cubic curves,
  linked shadows/midtones/highlights wheels and **global** HSL. Global HSL
  is not selective hue-range grading. Legacy saved grades remain accepted.
- Motion graphics panel adds three original transparent geometric plates with
  editable title/subtitle and verified local raster logo. Fade/slide animations
  render to real alpha MOV media; the shared compositor handles final export.
  Select a generated graphic to reload/rebuild its settings. Older files remain
  available for undo; keep generated media alongside project references.
- Actual tests render all three plates with both animations, inspect alpha,
  composite over source video, check logo-change rejection and saved settings;
  curves/HSL tests inspect encoded and streaming pixels.
- Local regression: **689 passed, 15 skipped**. Native builds for this increment
  and physical speaker/desktop acceptance are not yet verified. This small pack
  does not fulfill the remaining request for complete asset-rich template packs.


### Original graphics pack and sync QA tooling update

Motion graphics now includes **12 original asset-backed compositions** (nine new
geometric layouts), each with replaceable title, subtitle and verified local logo.
All twelve are actually rendered with fade and slide in automated alpha tests.
This is not a claim of 50 complete asset-rich packs.

`python scripts/create_av_sync_fixture.py /local/path/sync.mov --seconds 300`
creates a real 60 FPS flash / 48 kHz PCM click stimulus without overwriting media.
See `docs/NATIVE_DESKTOP_ACCEPTANCE.md` for calibrated device measurement and result
recording. Physical speaker/display QA remains **NOT RUN** in this sandbox.

At inspection, commit `a404987` passed macOS packaging-integrity and website checks;
installer run `45736934646` was pending with no jobs yet. Packaging-integrity is
not native runtime/installer acceptance. New pack native results are also pending.


### Selective HSL grading and native verification queue

The Color panel now switches between global HSL and six secondary hue ranges
(red/yellow/green/cyan/blue/magenta). Overlapping triangular masks span 60 degrees
on either side of each hue center, use original hue to avoid order-dependent
selection, and suppress changes to neutral gray. These are hue qualifiers, not
spatial/power-window masks. Settings persist and apply through the existing
selective color-grade preset category and shared preview/export LUT graph.
Actual tests verify red desaturation with blue/gray protection, encoded and
streamed gray pixels, round-trip settings and atomic invalid-input rejection.
Local regression: **691 passed, 15 skipped**.

Superseded installer run 45736063073 (92a0291) had completed Windows/Linux but
was still building Intel macOS, blocking the newer run. Cancellation was requested
to unblock the current asset-pack revision. Run **45738604181** (4f8fa30) now has
Windows, macOS and Linux jobs **in progress**, not yet passed. Subsequent grading
revision requires its own native verification. Physical device tests remain
NOT RUN; twelve geometric templates do not complete a 50-pack asset library.


### Illustrated asset-library increment

The motion-graphics library now contains **20 original compositions**, including
8 newly authored illustrated scenes: rocket launch, learning/book, podcast/mic,
growth/chart, travel/mountains, kitchen/chef, gaming/controller and science/
microscope. Each includes an original illustration, multi-part title/subtitle
plate and replaceable local logo slot. Offline plate thumbnails in the native
panel show actual bundled artwork; they are explicitly labeled static plate
previews, not animated or text/logo previews. Use rendered timeline playback to
review the complete result. All 20 assets are rendered with both fade and slide
in actual tests; catalog tests check unique file hashes, RGBA format and editable
slot bounds. **692 passed, 15 skipped** in the full local regression.

Native status at this increment: Windows installer job for `4f8fa30` succeeded
(run 45738604181); Linux/macOS jobs still running. `dfbcf35` native installer run
45739066758 remains pending behind it. Neither result certifies this newer asset
revision. Physical audio-sync/permission tests remain NOT RUN. This library is
20 compositions, not completion of 50 full asset-rich packs.


### Optional one-click freely licensed artwork library

Motion graphics now has a **50-item Noto Emoji illustration library**. Choose an
item and click **Download / use selected library art as graphic logo**. Only the
chosen PNG is downloaded; then Add/Rebuild applies it to the editable graphic.
Cached verified artwork works offline. No account, API key or mandatory cloud is
required. Internet is required only for the first explicit download. This is 50
illustrations plus 20 original compositions, **not 50 complete template packs**.

Assets are pinned to Google Noto Emoji revision
`e8073ab740292f8d5f19b5de144087ac58044d06` under Apache-2.0. Freely licensed does
not mean copyright-free or public-domain. The panel identifies provider/license;
full license and per-file source/revision/SHA256 metadata are saved beside each
PNG. Pinned Git blob/size and PNG format/dimensions are checked before atomic
publication. Corrupt caches are rejected, not silently overwritten. Network,
rate-limit and cancellation failures surface without fake success. Artwork is
used unmodified; no trademark endorsement is implied.

Verification: all **50 real upstream PNG downloads** succeeded and passed identity
and image checks in this sandbox; one downloaded rocket was actually rendered
into an alpha MOV with editable title/subtitle. Unit tests separately cover cache
reuse, corruption/cancellation and license provenance. Full local regression:
**695 passed, 15 skipped**. Native tests include the library contracts, not an
assumed network availability pass.

At last inspection native run 45738604181 (`4f8fa30`) had successful Windows and
Linux jobs, with macOS still running. Newer commits need their own native results.
Physical speaker/display sync and human permission-dialog QA remain **NOT RUN**;
they require actual devices and cannot be fixed by claiming a simulated pass.


### Full-library offline download and artwork provenance

Motion graphics includes **Download / verify all 50 illustrations for offline use**.
This is an explicit opt-in download, not a startup network request. Progress
reports checked/ready/failed counts; per-file failures do not mark the library
successful. Retry reuses verified cached files. Cancellation retains completed
files. The selected-art preview only reads integrity-checked local cache and
never triggers a network fetch. Full-library verification was actually executed:
**50 ready, 0 failures** (reusing already downloaded, verified files).

Generated alpha MOV graphics now carry adjacent `.source.json` records and,
when recognized Noto artwork is used, `.LICENSE.txt` including copyright,
Apache-2.0 license and modification notice. Preserve these records when sharing
generated assets/projects; this is not a promise that flattened downstream exports
automatically package every third-party license. A real downloaded-art derivative
was rendered and its source/license records inspected. Local regression:
**696 passed, 15 skipped**.

Native installer run **45738604181** for `4f8fa30` is now **SUCCESS**, covering
Windows/Linux/macOS jobs. This verifies that revision only. Run 45740805406
(`42956c9`) is still in progress; later library revisions await their own native
results. Physical device audio-sync/permission QA remains NOT RUN. The count is
still 20 original compositions plus 50 licensed illustrations, not 50 packs.


### Fifty original offline title-scene designs

The Motion graphics catalog now contains **50 original compositions**: 20 prior
designs plus 30 new authored illustrations (film, laptop, phone, satellite, robot,
battery, shield, lock, key, compass, globe, clock, calendar, trophy, dumbbell,
football, basketball, music, piano, headphones, palette, bulb, umbrella, anchor,
sailboat, train, gift, diamond, leaf and butterfly). These are distinct drawings,
not 30 palette-only variants. The new scenes include separate illustration and
panel PNG assets as well as the composed RGBA plate.

Every design has a CC0 offline `.pack.json` describing title/subtitle/logo slots,
defaults and fade/slide animations. **Export selected original offline pack ZIP**
in the native panel exports the actual plate/components, editable recipe, license
and usage note, refusing to overwrite an existing file. Installed fonts, user
logos and third-party library illustrations are not redistributed inside these
original-design ZIPs. The 50 Apache-2.0 downloaded illustrations remain a separate
optional library, not part of the original-pack count.

Actual tests render all **50 designs with both animations**, inspect alpha and
frame count, validate all editable slot bounds, verify all 50 ZIP archives and
manifests, reconstruct the 30 component-based plates, and test no-overwrite.
Full local regression: **698 passed, 15 skipped**. These are complete editable
**title-scene design packs**, not stock-video/music bundles or arbitrarily layered
After Effects-style projects. Full professional-editor acceptance, physical
speaker/display/permission QA and exact-revision native release remain separate
gates; no stable-complete release claim is made by this increment.
