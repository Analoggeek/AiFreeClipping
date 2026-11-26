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

## Color and audio processing

- **Color tab:** adjust exposure/gamma and RGB tonal balances, or explicitly
  import a normalized `.cube` LUT. Verification happens in a worker. Set strength,
  Load grade into Batch inspector, review targets and Apply. Keep the original LUT
  file with your project; changed bytes require an explicit re-import.
- **Audio tab:** choose an implemented processor and amount. Load or append it
  into the inspector, review selected targets and Apply. The processor category
  does not silently replace static gain/fades. Import local background audio at
  the timeline cursor as a separate track, then trim and mix explicitly.
- The current fixed-band controls are not a full parametric EQ UI, automatic
  voice reconstruction, automatic music ducking or a full color-wheels/curves
  grading suite. Review outputs before delivering them.

## Automatic music ducking

1. Identify source/dialogue audio items that should drive music attenuation.
   Existing ordinary audio defaults to dialogue. Use Audio Routing to mark game
   audio or sound effects **neutral**, and background music **music**.
2. In Audio, choose music role and enable automatic ducking. Set threshold, ratio,
   attack and release; Load audio role/ducking into inspector.
3. Select current/selected/all/group targets carefully and Apply. Do not apply the
   music role to your dialogue driver. Routing is its own checked category.
4. Listen through composite playback or render a snapshot/export. Actual dialogue
   signal controls music; the feature does not infer who is speaking.
5. An enabled dialogue track is required. Silence between phrases releases the
   attenuation. Read the saved project roles when troubleshooting; do not expect
   a neutral track to drive ducking. Physical-device QA remains separate.


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
