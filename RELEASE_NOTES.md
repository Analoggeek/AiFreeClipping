# CLIPOS 3.1.1 — Native render crash stability update

Developed by **Analoggeek**. Targets the reported Intel Mac exports terminating
with `ffmpeg failed (exit -11)` before the first output frame.

## What the report establishes

`-11` is a native SIGSEGV, not a normal FFmpeg command-line error. The report
shows an old FFmpeg/x264 build, 14 encoder workers, CoreText/libass importing
supplemental fonts (including an NISC18030 metadata warning), and AV1-branded
source metadata. The final scaler alignment warning alone does not establish
why the process crashed. The exact user's machine/source fault is not reproduced
in the sandbox; the changes below address concrete risky paths and add recovery.

## Fixes and enhancements

- Refresh the **Intel macOS** FFmpeg binary to upstream ffmpeg-static `b6.0`,
  pinned by SHA-256 with architecture validation and retained upstream license/
  provenance files. An existing legacy binary without the new verified manifest
  is not silently reused. Other platform binaries are not advertised as upgraded.
- Pass libass an isolated directory containing one real fallback font, rather
  than the entire OS font directory. CoreText/system font discovery remains
  available; captions are not silently removed or replaced with fake text.
- If a render process has a recognized native fault, retry the same timing,
  filters, captions, mappings and output with single-worker/scalar compatibility
  settings. x264's separate assembly dispatch is disabled for this retry.
- Subsequent render commands using the same binary identity remain in
  compatibility mode for the session, avoiding a fresh crash for every clip.
  Relaunch/binary replacement resets this policy. Compatibility mode is slower
  by design; normal successful renders retain accelerated/default performance.
- Never treat cancellation, out-of-memory killing, ordinary bad media/arguments
  or a second conservative failure as a successful export. Retries are bounded;
  pre-existing successful output remains protected by atomic replacement.
- Save a bounded **local-only** native-fault diagnostic under the application
  logs directory. Settings now offers **Open local logs / render crash
  diagnostics** and displays the actual selected engine version. Nothing is
  uploaded automatically; reports can contain local file paths/media names.
- Retain v3.1 performance improvements, removed Multitrack workspace UI, existing
  saved data, native editing, offline-first behaviour and platform encoder checks.

## Verification and limits

Local full suite: **600 passed, 20 skipped**; real import-to-export/batch E2E:
**35/35 passed**. Optional native/model checks account for skips; Intel runtime
verification is mandatory in release CI, not asserted from Linux tests.

Regression coverage includes injected fatal return codes, bounded failed retries,
cancellation, session compatibility behaviour, font isolation, archive hash
rejection, and real H264/AV1 inputs rendered to 1080x1920 H264/AAC with actual
caption pixels preserved after an injected initial failure. Injected faults
prove recovery contracts, not the original crash's root cause. Native Intel CI
requires FFmpeg >=6.0 with ASS/drawtext and rejects `--enable-nonfree` builds.

Platform installers are published only after native gates and all seven
nonempty release assets succeed. This is not physical-device/driver or arbitrary
source-media certification; disk errors, invalid media and incompatible devices
can still fail explicitly. Model/physical A/V acceptance limitations from the
prior release remain unchanged. macOS signing integrity is not notarization.
Back up important projects before upgrading; user projects/data are not deleted.
