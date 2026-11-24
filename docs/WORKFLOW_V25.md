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
