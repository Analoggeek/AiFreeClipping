# 3.1.1 native render crash investigation

## Observed user evidence

Five Intel macOS clip exports terminate with exit -11 (SIGSEGV), around the first
frame. Logs show Lavf58.24.101, Lavc58.42.102, x264 core157 (2018 generation),
14 x264 workers, ASS/CoreText initialization, importing supplemental system font
files and NISC18030 metadata warnings. Output copied source container branding
includes av01; this suggests an AV1 input but is not an input codec probe.
The scaler alignment message is a warning, not a native backtrace. None of these
last log lines alone proves which library crashed. Original source media and a
native crash backtrace are unavailable; no exact root-cause reproduction claimed.

## Changes

1. Intel macOS vendor artifact is now ffmpeg-static b6.0 with pinned gzip hash,
   architecture validation, and pinned LICENSE/README retained with the binary.
   A binary without a matching validated provenance manifest is refreshed.
   The release's native Intel gate requires >=6.0 and ASS/drawtext and rejects
   --enable-nonfree. Other platform engine versions are not claimed upgraded.
2. fontsdir no longer imports an entire system font directory. A single actual
   fallback font is staged in a content-addressed local cache, atomically. Basic
   size/header guards avoid passing arbitrary nonfont files. This is not a full
   font-security validator. System provider lookup remains available; no styles,
   speaker colours or caption words are deliberately discarded.
3. Caption/timeline and longform part renders opt into a bounded native-fault
   retry. Only recognized fatal signals/access violations qualify, not exit1,
   cancellation or OOM killing. The retry preserves graph/mapping/times, sets
   decode/filter/encode workers to1 and disables FFmpeg CPU flags plus x264/x265
   assembly paths where applicable. This reduces concurrency/SIMD risk but does
   not guarantee a repair for corrupt media, malformed fonts or driver faults.
4. A process-session cache keyed by binary path/mtime/size keeps later render
   commands conservative after a native fault. Already-conservative commands do
   not repeatedly retry the same settings. Existing hardware-to-CPU fallback is
   still bounded and preserves the same edit. Restart or binary change resets
   the policy; no permanent user setting is overwritten.
5. Bounded local diagnostics retain the original command/returncode/stderr and
   compatibility-command outcome in logs/ffmpeg-native-crash-last.json. A command
   exit0 is explicitly not called verified output in that record. Reports may
   contain local paths/media names and are not uploaded. Settings opens the logs
   folder and reports actual runtime version on the background diagnostics thread.
6. Atomic final output replacement from3.1 remains: failure/cancellation cannot
   overwrite a previously successful output. Caption removal is not a fallback.

## Validation

Local 600 passed/20 skipped and FFmpeg E2E35/35. Actual H264 and AV1 test inputs
produce 1080x1920 H264/AAC with visible caption pixels after an injected initial
native fault. Unit tests establish fatal-code classification, retry bounds,
cancellation, session policy, command preservation, font isolation and artifact
hash rejection. Injected failures are recovery-contract tests, not a native
reproduction of the user's clip crash. Intel release CI must run the real new
Intel binary and native caption/AV1 tests before any final publication.

The sandbox cannot download release-storage assets directly. It did not pretend
to run the pinned Mac binary on Linux. The native release pipeline performs that
download/check; missing/bad hashes fail the build, never fall back silently to
the obsolete Intel npm binary. All seven platform release assets remain required.

## Native candidate selection

The first b6.1.1 candidate passed native captions but the Intel gate rejected it
for missing drawtext. Do not remove that gate: hooks and timeline text require
this filter. A native macos-15-intel audit (run45557497487, issue115) downloaded
b6.0, recorded archive/LICENSE/README hashes, executed FFmpeg6.0-tessus, and
confirmed ASS plus drawtext without --enable-nonfree. We pin this full-feature
build instead. This is a deliberate compatibility choice, not a claim to bundle
the newest FFmpeg. The complete Intel render/package gates must still pass.

Native Intel follow-up run45569570614 (issue122): **51/51 passed** for every
layout, multi-part caption timelines, H264/AV1 recovery pixels and engine gate.
The Apple-Silicon-hosted Rosetta Intel test process hung in the release's full
suite and hit the job timeout; it is not substituted for native validation.
Official release jobs now build/test macos-15 arm64 and macos-15-intel x86_64
separately, each with its own frozen bundle checks, arch-labelled DMG/archive and
all-platform publication gate. Verbose test identity/120s stack diagnostics
make future stalls actionable instead of waiting without test identification.

Full-order bounded Intel tests isolated a second concrete issue (issue133):
**range** renders with an infinitely looped music input hang inside FFmpeg6.0
once the downstream atrim reaches EOF; timeline cases finish. This occurs on
native Intel too, so the earlier Rosetta stall was not sufficient evidence of
a Rosetta-specific fault. Music inputs are now explicitly time-bounded at the
demuxer (`-stream_loop -1 -t <edited duration> -i music`) for both range and
timeline paths. Existing tests assert this scope and continue measuring actual
looped music beyond source EOF and requested export duration, with/without
ducking. Nothing is fixed by removing music. The bounded audit also forced
QT_QPA_PLATFORM=minimal on macOS, which prevented native playback; it now uses
the native GUI platform, just like release tests (not a playback-test skip).

Further native evidence (issue135) corrects the initial demux hypothesis:
FFmpeg finishes all frames/audio and the MP4 trailer, then its infinite-loop
input cleanup hangs. Input/output `-t`, scalar mode, one filter worker and input
queues did NOT fix it. Native comparison run45578337455/issue136 showed finite
`-stream_loop 2` exits0; `-stream_loop -1` did not. Production now computes
`max(0, ceil(edited_duration / music_duration)-1)` repeats, also bounds input
length, and rejects unknown/non-audio duration explicitly. This preserves real
repeated/ducked music without a giant PCM staging file or caption/effect removal.
Range/timeline tests inspect finite input scope and measure real looped waveform
past the original music length. The full native suite is rerun after this fix;
not merely the smaller successful layout subset. Full local600/20 plus focused
51passed1skipped (including seven added finite-loop edge-case checks).
