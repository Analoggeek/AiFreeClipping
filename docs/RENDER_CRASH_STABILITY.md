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
