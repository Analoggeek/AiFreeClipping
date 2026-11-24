# DigiRG technical review and CLIPOS implementation ledger

Reference: [DIGIRGCLOUD/DIGIRGCLIPPINGFREE](https://github.com/DIGIRGCLOUD/DIGIRGCLIPPINGFREE/tree/0987925fa4e99c5d90c68239dc8071421c56d121), pinned revision `0987925fa4e99c5d90c68239dc8071421c56d121` (MIT). This is a source review, not a benchmark of the upstream app. Existing copied/adapted placement/layout contributions remain attributed in THIRD_PARTY_NOTICES.md. New activity, panel and association implementations here are independently written; upstream architecture is not imported.

## Reference → actual implementation, feature by feature

| Feature | Reference implementation | CLIPOS reuse / improvement / new work | Honest status |
|---|---|---|---|
| YuNet facecam | `facecam_detect.py`: 14 small samples; local YuNet, repeated face support; stationary peripheral-face fallback | **Reused existing CLIPOS capability**, not newly delivered: bundled YuNet and Haar fallback; repeated peripheral face observations in `gaming_layout.py` | Real sampled face detection; cannot distinguish a human camera from an in-game face with certainty |
| Static-edge localization | Persistent Sobel edges, rectangle scoring, YuNet confirmation | **New independent implementation** `panel_edges.py`: persistent Canny edges, separated bounded edge candidates, four-border support and >=60% sampled face coverage; called by `detect_gaming_layout`, falls back to previous face-based crop | Adds actual panel boundary refinement; needs >=3 observations; does not infer a camera from a HUD border alone. Largest nonoverlapping residual region remains gameplay, not semantic gameplay segmentation |
| Optical-flow highlights | `highlights.py`: 3 fps Farneback p90 flow, cut rejection, 8 kHz loudness/shout signals, rolling baseline and smoothing | **Improved** `activity.py` + `visual_analysis.py`: Farneback residual motion after median camera-flow subtraction, cut rejection, timestamp-aligned samples. **New ranking integration** in `clip_detector.py`: activity anchors, motion and preceding-baseline dB rises contribute to engagement and final candidate ordering | Actual measured signals, not semantic excitement/virality truth. Existing sparse sampling is retained: flow deliberately abstains for gaps >2 seconds. Not equivalent to upstream dense 3 fps analysis |
| Faster-Whisper | `captions.py`: word timestamps, VAD, model/device choice, GPU warmup/CPU retry; can download snapshots | **Existing CLIPOS implementation**, foundation improved installed-local-weight-only loading and explicit setup downloads | Local word transcription exists; no new speech model or real-weight disconnected acceptance in this change |
| Ollama refinement | `smart.py`: local model selection, transcript JSON scoring/titles/hooks and evidence checks, deterministic fallback | **Existing CLIPOS title path plus prior foundation** strict loopback transport and bounded reviewed edit plans; rejects proxies/redirects/cloud model references | No newly ported evidence-validated semantic highlight reranker. Reviewed agent changes supported settings/ranges, not arbitrary multitrack edits or vision |
| Gameplay/facecam layouts | `layouts.py`: crop/scale/overlay, masks, blur; independent camera/game source rectangles | **Previously adapted with MIT attribution**; existing native crop controls, FFmpeg composition and presets retained. New panel refinement feeds the existing path | Real rendering, not semantic player extraction. Manual crop override remains important; existing adjustable/split/PIP options are not a newly built professional compositing engine |
| Animated ASS captions | `captions.py` / `subtitles.py`: grouped word events, full-line/highlight/build-up/pop styles, ASS transforms/fades | **Existing pipeline retained; 30 new independently developed animated combinations** (10 motion treatments × 3 typography/palette profiles) | All 30 raster-tested with/without word timings; three real video export integrations. Native visual review, multilingual editorial UI and caption timeline automation remain pending |
| Local processing / hardware fallback | `encoders.py`: advertised encoder discovery plus cached tiny test encode; CPU-last retry | **Improved with independently implemented runtime preflight** for NVENC, QSV and VideoToolbox, H.264 and HEVC; existing full-render CPU retry retained | Three-frame local encode, eight-second timeout per candidate, bounded cache keyed by binary identity and 60-second epoch. VideoToolbox software fallback is disabled to avoid labelling a software session as hardware. No native driver/performance claim from Linux policy tests |
| Subject association | Upstream facecam sampling is not a continuous multiperson tracker | **Improved** `build_tracks`: one-to-one per timestamp, bounded velocity prediction, size gating, shot-cut retirement, stable IDs, observed-interval duration | Spatial sampled face association only; not biometric identity, YOLO, ByteTrack, person/body tracking or speaker diarization |

The previous frame-difference motion list was N-1 values and unused in ranking. It is now aligned one-to-one with keyframe timestamps, begins with zero evidence, and contributes to actual candidate generation and scores. Loudness preprocessing is reused across candidate scoring rather than recalculated for each candidate. A static loud soundtrack alone is not a loudness-rise event. Modest activity weights preserve transcript-led ranking; no claim of validated editorial quality is made.

## Requested professional features: completion boundary

| Requested capability | Implemented/retained | Remaining work (not shipped by this patch) |
|---|---|---|
| Continuous YOLO + ByteTrack; dynamic face/body/person tracking | Sampled YuNet and improved spatial associations | Explicit model installation/licensing, actual body detector + ByteTrack runtime, occlusion/reidentification tests and continuous decode scheduling |
| Gameplay and player separation | Independent source rectangles, face-supported crop and new static-edge refinement | Semantic gameplay understanding, foreground segmentation, moving/resizing-camera benchmark |
| Multiple speakers | Existing audio-energy/face-prominence heuristic | Actual diarization, audiovisual active-speaker identity, overlap handling |
| Dynamic vertical / subject-aware reframing | Existing FFmpeg crop/layout/subject-follow paths retained | Continuous body-aware composition and editable motion-keyframe timeline |
| Professional multitrack timeline | Existing bounded range/settings editing retained | Persistent editable video/audio/caption/overlay tracks, trim/split/ripple, automation, snapping, keyframes, undo integration |
| Real-time playback / preview | Existing native source playback and composition preview retained | True multitrack live engine, proxy/cache scheduling and native acceptance; rendered previews are not real-time editing |
| >=30 functional animated caption presets | 30 new animated combinations plus eight legacy styles; real ASS raster and export tests | Native visual review, editable word timing/text workflow and multilingual acceptance |
| Local editing agent | Prior foundation validates/reviews/applies supported settings and ranges transactionally | Vision-guided autonomous modes, arbitrary timeline operations and real installed-LLM acceptance |
| Advanced audio | Existing analysis/render filters retained | Validated denoising, separation, sync, VAD-driven editing, track ducking/automation workflow |
| AI scene understanding | Existing cuts/text heuristics and measured activity | Installed local vision-language model, explicit model management, grounded semantic evidence |
| GPU video rendering | Platform encoder selection, new runtime preflight, and full-render CPU retry | Actual native GPU acceptance/performance tests; preflight does not establish full-size/filter-graph success |
| Project saving / recovery | Existing persisted project/settings/ranges and atomic plan application retained; new validated atomic segment-timeline autosave and previous-revision backup recovery | Professional multitrack schema, media relink, crash journal and native recovery acceptance |
| Fully disconnected professional acceptance | Existing local transport/installed-model restrictions and test fixtures | Real model weights + OS-level disconnected gaming import→detect→captions→timeline edit→save/reopen→1080x1920 export on macOS Intel/ARM and Windows |

No current feature was intentionally removed. No upstream web-server architecture, implicit editing-time downloads, upload/publishing service or replacement UI was added. This source patch is an incremental enhancement to draft PR #92, not a complete PRO release or native installer validation.

## Validation for this increment

Command: `LD_LIBRARY_PATH=$PWD/.stublibs QT_QPA_PLATFORM=minimal .venv/bin/python -m pytest -q`.

Result: **312 passed, 9 skipped** in 74.19 seconds. New tests cover simultaneous-face exclusivity, shot/gap retirement, measured audio/motion ranking and activity anchors, static/pan/local-motion/cut/sparse flow, face-confirmed panel boundaries and abstention without repeated faces. Existing gaming integration suite: **10 passed**, including real YuNet/decoded-video/FFmpeg composition coverage. New panel/flow fixtures are synthetic algorithm tests, not a real-world gaming quality benchmark. No new real speech/LLM-weight, native OS, driver or physical installation test was run. See `CLIPOS_PRO_ROADMAP.md` for the broader incomplete acceptance ledger.

### Follow-up: runtime encoder preflight

The next increment closes the preflight gap identified above. Export selection now
checks an actual three-frame 256×256 YUV420P encode with CLIPOS's resolved FFmpeg
before returning a hardware choice. Each candidate has an eight-second timeout;
missing binary, nonzero exit, driver error and timeout reject it. Automatic mode
tries eligible alternatives and ends at CPU. Explicit CPU mode never probes.
Successful and failed checks are cached for at most 60 seconds; binary size/mtime
changes invalidate the cached identity. No input media, network or output file is
needed. VideoToolbox uses `-allow_sw 0` both in the check and the two rendering paths.
A successful tiny encode still cannot prove a long/4K render will work: the full
render CPU retry remains intact.

Settings diagnostics deliberately request an **unverified candidate**, explicitly
labelled as such, instead of synchronously probing drivers on the UI thread.
No new dependency or model download was introduced.

Follow-up validation: **331 passed, 9 skipped** (74.98 s) for the full pytest suite;
real generated-video integration script **35/35 passed**. New policy tests cover
all six encoder/codec pairs, bounded subprocess invocation, cached failure,
expiry/replacement, timeout/error handling, alternate selection, explicit CPU
and nonblocking diagnostics. The real FFmpeg CPU-retry integration now exercises
simulated failure for NVENC, QSV and VideoToolbox; these simulated failures are
not evidence of successful native GPU encoding. Native macOS/Windows GPU tests,
physical installation and real-weight disconnected PRO acceptance remain pending.

### Follow-up: existing timeline persistence

Independently developed beyond the clipping reference: the existing segment
editor now uses validated atomic saves, a previous-valid-revision backup,
explicit recovery/failure notices and collision-safe IDs after reopen. Editor
and export both discover backup-only saves. See `CLIPOS_PRO_ROADMAP.md` for exact
limits. Targeted validation: **78 passed**, including an actual recovered timeline
render. Professional multitrack persistence/recovery remains pending; this is not
a claim that the reference provides a professional timeline engine.

### Follow-up: persistent edit history

New independent editor work: the current segment timeline's undo and redo stacks
now persist through save/reopen and backup recovery. Latest 50 operations are
retained, snapshots and chain continuity are validated, legacy saves still load,
and editing after undo clears the old redo branch. This supersedes only the
previous persisted-undo limitation, not the pending professional multitrack
scope. Validation: **93 targeted tests passed**, including actual exports whose
duration changes correctly after reopened undo/redo. Full-suite collection was
blocked by missing `yaml`/native `libGL.so.1` in this environment; no new full-suite
result or native UI acceptance is claimed. See `CLIPOS_PRO_ROADMAP.md`.

### Follow-up: actual animated caption presets

Added thirty new ASS animation/typography combinations while retaining eight
legacy styles. Full matrix and limits: `ANIMATED_CAPTIONS.md`. All thirty have
real libass temporal-pixel tests, with/without word evidence; three additional
actual MP4 export cases verify renderer integration. Selected regression:
174 passed / 2 Qt-dependent tests deselected; generated-video E2E: 35/35 passed.
This does not establish native real-time ASS preview or multilingual/editorial
acceptance. Professional timeline and continuous YOLO/ByteTrack remain pending.

### Follow-up: actual music ducking and shared export mixing

Independent improvement beyond the reference: source-signal music sidechain
compression, independent foreground/music gain, edited-duration looping and
shared range/timeline audio mix. The previous source-attenuation bug and omitted
timeline music are fixed. Persisted local selection/level/ducking controls are
connected. `AUDIO_DUCKING.md` records measured PCM and real MP4 evidence:
189 selected tests passed / 2 Qt-dependent tests deselected. This is not speaker
recognition, VAD, source separation or completed multitrack audio editing.

### Follow-up: broader validation and safe edit execution

New independent fixes: portable pitch-preserving tempo chains and merge guards
that preserve distinct crop/zoom/speed/mute edits. Regression tests cover the
editing data model and actual FFmpeg exports, not real AI inference weights.
Native build/release gates now include recent feature tests,
including an isolated x86_64 macOS regression step. On ARM macOS that interpreter
uses Rosetta; physical Intel acceptance remains separate.

Fresh complete local suite: **478 passed / 9 skipped**; generated-video E2E:
**35/35 passed**. Earlier missing-dependency notes are superseded for this local
run: development PyYAML/CTranslate2 and the existing headless GL stub utility
allowed the full suite to execute. Stubs are not native graphics/playback proof.
No new AI weights or genuine disconnected-model acceptance occurred. Latest
native CI results remain pending, and the main PRO engines remain incomplete.
