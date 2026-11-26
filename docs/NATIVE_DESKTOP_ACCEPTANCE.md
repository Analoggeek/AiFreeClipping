# Physical desktop acceptance — unrun gates

Headless CI, successful installers and digital PCM tests do not establish human
permission-dialog behavior, real speaker latency or sustained desktop performance.
Record actual results per Windows 10/11, Intel macOS and Apple Silicon macOS device.
Never disable OS security to force a pass.

| Gate | Procedure | Current evidence |
| --- | --- | --- |
| Official runtime consent | On a clean device, request Ollama installation, decline consent; confirm no installer launch/download caused by refusal. Then approve once and observe the normal OS flow. | API/lifecycle contracts and real unattended installs passed; human dialog unrun |
| OS permission denial | Deny any OS permission request; app must surface failure/cancellation, retain data and allow retry without fake success. | Manual unrun |
| Existing runtime | Relaunch with Ollama installed; confirm no duplicate runtime installation and local API health. | Automated lifecycle coverage; physical UX unrun |
| Audio-device failure | Disconnect/change default output during composite playback; record surfaced error/state and recovery. | Headless unavailable-device handling only |
| A/V synchronization | Play a known flash/click stimulus, record display plus speaker/loopback output, measure initial offset and drift at start/middle/end. Account for capture-device latency separately. Repeat after seek and pause/resume. | Digital sample/frame timing tests only; physical unrun |
| Sustained throughput | Run representative caption/effect/multitrack 1080p/4K projects for 30+ minutes; record decoded FPS, dropped frames, buffer stalls, RAM, cache size and audio gaps. | Bounded-queue contracts and short synthetic streaming tests; long device run unrun |
| CPU/GPU | Compare authorized source projects through CPU and available hardware encoders; probe dimensions/audio and inspect frames, fallback warnings and output sync. | Local CPU rendering and native CI; actual target GPU acceptance unrun |
| Crash/reopen | Save assembly/presets, reopen after process failure and check media/LUT references and all edits. Distinguish supported manual save from unfinished autosave UI. | Saved-model/backup contracts; broad physical UX unrun |

Do not fill this table with simulated passes. Add device/OS/build revision,
procedure, measured values, logs and explicit pass/fail when someone actually
performs each gate. Full asset-based motion graphics and complete curves/wheels/
HSL functionality are development requirements, not manual tests to be marked off.

## Reproducible physical A/V sync protocol

Generate the stimulus outside Git with the app environment:

```sh
python scripts/create_av_sync_fixture.py /absolute/local/path/av-sync.mov --seconds 300
```

The 60 FPS video flashes white for one frame at every integer second; PCM audio
starts a 10 ms / 1 kHz click at that same source time. The adjacent JSON describes
nominal events and explicitly marks physical QA NOT RUN. The generator refuses
existing outputs. Automated tests verify all 180 frames and PCM intervals of a
three-second fixture; this establishes stimulus integrity only.

On each actual Windows/macOS machine:
1. Record OS, CPU/GPU, build SHA, display refresh, audio output/device and sample
   rate. Use the same display/audio route for calibration and app playback.
2. Import the fixture, play composited preview, and capture display plus speaker
   output with an external high-frame-rate camera/microphone or calibrated
   photodiode/audio interface. Screen recording alone misses physical latency.
3. Measure `audio click onset - visual flash onset` at seconds 5, 150 and 295.
   Report raw and capture-path-corrected offsets in ms, measurement uncertainty,
   and drift `offset(295)-offset(5)`. Do not assume capture latency is zero.
4. Repeat after seeking to 140 seconds and after pause/resume. Export through
   CPU and available GPU profiles and repeat playback of the exports separately.
5. Suggested product acceptance gate: corrected absolute offset <= 50 ms and
   drift <= 20 ms over five minutes, with no audible gaps. This is a proposed
   gate, not a measured result or blanket certification.

| Build / OS / device | Route / capture calibration | Start / middle / end ms | Seek / resume ms | Drift ms | Evidence | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Not measured | Not measured | Not measured | Not measured | Not measured | None | NOT RUN |
