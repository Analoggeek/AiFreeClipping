# CLIPOS 2.5 — connected desktop workflow

## Four steps

1. **Import:** choose a local recording or explicitly download an authorised
   public video link. No account connection or upload control exists in 2.5.
2. **Select & style:** play/seek the original video, mark start/end in seconds,
   and add one or more allowed time ranges. Empty range list means whole source.
   Draw player and gameplay rectangles on a decoded source frame. Choose a
   composition preset, caption style, size, clip count and duration band here.
3. **Edit & review:** batch analysis and FFmpeg rendering apply the chosen
   composition, cuts, captions, colour and audio processing. Play actual rendered
   MP4s, not an unedited source frame labelled as a finished preview. Check which
   clips to deliver. Advanced trim is optional, not part of the required flow.
4. **Export:** copy checked finished edits into one batch directory:
   `chosen folder / YYYY-MM-DD / recording name / clip files`. All clips from that
   source/date share the folder. Unique clip IDs prevent same-title collisions.
   A JSON manifest records each result/error. Failed clips are not counted as
   successful, and other clips continue when one clip fails.

The one-click button imports and runs step 3 using the preferences in step 2.
It does not upload anything or silently publish a video. The optional final
export action makes review possible before delivery to the chosen directory.

## Player below, gameplay above

Automatic face inference is conservative, based on repeated stationary peripheral
face observations. It is not a semantic classifier capable of reliably
identifying every streamer, animated avatar or game character. A missed camera
falls back to gameplay-only with a warning; it never invents a player.

For dependable placement, choose **Manual**, drag the real facecam rectangle on
the source image, then optionally drag a gameplay rectangle. If only the player
is selected, the largest remaining non-overlapping gameplay rectangle is used.
The lower player panel occupies one third of portrait height; gameplay fills the
upper two thirds. Review the actual 4-second recipe preview before batch editing.
Cropped portrait gameplay can lose peripheral HUD information.

Select **Gameplay only** for recordings without a camera. A chosen gameplay
rectangle is still respected. Save the project; ranges and camera/gameplay crops
are restored when it is reopened. This version uses one fixed manual layout per
project; recordings whose overlay moves need separate selections/projects.

## Presets and captions

Every preset/caption tile has a local visual thumbnail. They are labelled visual
style/composition previews, not pre-rendered samples pretending to be your video.
Once imported, composition tiles use the recording thumbnail. **Preview recipe**
renders four real seconds from the recording (composition/colour, no speech model
needed); the complete edit adds transcribed captions. The preview and final edit
use the same rendering settings builder.

A selected caption style is no longer overwritten by the recipe. Clean
Professional uses shorter cues and captions above the gameplay/player split.
Export Settings, defaults and the four-step workflow share the renderer preference
builder: output directory, codec/fps/bitrate, caption settings, silence threshold,
thread budget, CPU/GPU preference and low-memory mode are actually read.
Changing edit preferences after a completed batch requires re-editing before
export; it does not falsely change an already encoded MP4.

Editing is deterministic local processing, not generative video reconstruction:
framing, silence cuts, readable captions, colour/clarity and audio cleanup.
It does not guarantee perfect editorial taste, recognise every gaming highlight,
or promise views. SDR clarity is not genuine HDR conversion.

## Performance and platform optimisation

- macOS builds use capability-detected VideoToolbox (including supported Intel
  Macs), with a CPU fallback if the hardware encoder fails.
- Windows builds choose detected NVIDIA NVENC or Intel Quick Sync where usable;
  otherwise CPU. A dedicated GPU is not assumed.
- CPU fallback preserves the edit graph and bounded thread budget. Low-memory
  mode caps render threads at two and uses a faster software encoding profile.
- Silence cuts now decode the source once, rather than opening an independent
  decoder for every retained segment. Audio analysis uses read-only strided
  windows, small RMS batches and bounded pitch sampling, avoiding the previous
  large frame-index/copy matrix for long recordings.
- Source and final playback use Qt multimedia rather than running the render
  filter graph for every UI frame. Codec availability/hardware still affect
  playback; external-player fallback is available.
- A background monitor reports measured system CPU/RAM and CLIPOS + child-tool
  CPU/RAM. NVIDIA GPU percentage is shown when its counter is available.
  Unavailable GPU counters (including most standard macOS installs) are labelled
  unavailable, not fabricated.

These are native platform paths in the same codebase, not a renamed ARM build
sold as Intel. Physical-device performance remains hardware/driver dependent.

## Export defect and diagnostics

The reproduced captioned-render defect appended `fontsdir` directly to the ASS
filename. The filter now uses separated named arguments in contiguous, silence-cut
and timeline renders. Automated tests render five actual captioned/audio clips
into a single date/video folder, and test the real import → one-click edit →
review → export GUI path. User screenshots alone do not reveal every possible
source/codec issue: per-clip tool errors are now kept visible and in manifests /
export-history tooltips instead of being replaced only by a failed count.

Local editing stays offline after model setup. If requested captions need a model,
use the one-time model download or AI Models; a failed transcription is reported
instead of claiming captions were produced. Existing local projects/models remain
in the same data directory. Back up projects before any upgrade.

YouTube publishing/OAuth code and dependencies were removed. Any previously
issued Google grant can be revoked in your Google account settings; CLIPOS 2.5
no longer accesses the old publishing token.


### Platform responsiveness policy

- Automatic CPU pools reserve at least 25% of logical processors (one minimum)
  for playback/UI/OS, cap at eight workers, and cap at four on machines with
  8 GiB RAM or less. At 85% live RAM use, new automatic pools cap at two.
  Explicit thread settings remain respected within detected logical CPU limits.
- FFmpeg render children run at below-normal priority on Windows and nice +5 on
  macOS/Linux, best effort. The application/playback thread priority is unchanged.
- Available RAM is sampled live through psutil, including unified-memory Macs;
  cached startup memory is not used for memory-pressure decisions. GPU core count
  is never presented as VRAM. Intel Macs are not labelled Apple Silicon.
- macOS retains capability-selected VideoToolbox on both Intel and Apple Silicon;
  Windows retains detected NVENC/Quick Sync with software retry. These are encode
  paths, not a claim that every filter or speech model runs on the GPU. Speech
  uses supported CUDA or CPU int8, not an unsupported MPS backend.
- Native playback/thermal/driver measurements still require physical Windows and
  macOS testing; Linux policy/regression tests do not establish native frame rates.


### Additional studio layouts (DigiRG Cloud adaptation)

In **Select & style**, choose the **Gameplay + Facecam** preset and then a
**Studio layout**. Existing recipes/caption styles and the original gameplay-above,
player-below default are retained. Added choices are camera above, blurred fill,
full-screen fill, selected gameplay, four corner overlays, circular camera and
side-by-side columns (11 choices including the original default).

- Camera size controls 20–50% of the relevant output dimension; corner overlays
  are bounded by output height. Camera layouts need a real selected/detected camera.
  Failed detection falls back to gameplay, never an invented person/camera.
- Blur/fill/gameplay-only do not require a facecam. Blur keeps the complete source
  over a low-resolution blurred backdrop; fill crops the complete source.
- Layout icons illustrate geometry. **Preview recipe** renders your real source;
  batch editing and the advanced timeline use the same layout settings/graphs.
- Existing clean/podcast/story presets retain their original framing; the new
  studio-layout selector applies to the Gameplay preset only.
- These layouts run locally in FFmpeg; circle masking/blur can cost more CPU than
  the original stacked layout. No cloud service or new model is needed.

Upstream and full MIT license: see `THIRD_PARTY_NOTICES.md`, also included in
frozen application data. Native installer verification remains a separate gate.


## 2.5.1 crop, player, preset and delivery fixes

- Select PLAYER (pink) or GAMEPLAY (cyan), then drag on the source. Both labelled
  rectangles remain visible when switching targets, during playback and after
  reopening the project. Small accidental clicks restore the previous region.
- Live decoded source frames feed the selection canvas and a side-by-side
  composition view (GUI conversion capped at 15 fps / 1280×720). No frame-by-frame
  FFmpeg subprocesses are spawned. The composition uses the shared layout geometry.
- Caption text in that live view is explicitly a **style sample**, not a speech
  transcript. Blur is a low-cost approximation. Use Preview recipe for actual
  FFmpeg composition/colour, then Edit all clips for captions, cuts and AI framing.
- Camera source-placement presets (top/bottom left/right/centre) set both source
  regions as editable starting points, not a claim of automatic face detection.
- Selecting a camera crop or studio layout activates the Gameplay recipe, rather
  than silently ignoring it under a different recipe. Style/layout/camera-size/
  caption/count/duration changes persist immediately and survive navigation.
- Recipe rendering now respects the chosen output aspect rather than always using
  a 9:16 preview. Playback handles are cleared before edit/delivery file operations.
- Export copies the **checked rendered versions**. Changing a control no longer
  blocks delivery with a full-settings-signature mismatch or an unrelated missing
  manual camera selection. Run Edit all clips again to apply changed styles to
  outputs; delivery does not pretend to apply new effects. A successful export
  updates clip status and records the actual copied file size.
- If speech download/transcription fails, an explicit Retry without speech
  captions action disables captions and re-runs editing. Captions are never
  fabricated or silently claimed successful.

The exact installed-app export failure still requires its logs to diagnose. These
fixes address reproduced control/data-flow defects, not every possible source,
filesystem, codec, model-download or GPU-driver failure.
