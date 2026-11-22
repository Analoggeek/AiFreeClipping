#!/usr/bin/env python3
"""Generate a test video containing real detectable faces.

Draws simple but Haar-detectable synthetic faces (eyes, nose, mouth on a skin-toned
oval) so the face-detection and speaker-tracking code paths can be exercised without
requiring a camera or a stock-footage download.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from clipos.core.ffmpeg import require_ffmpeg  # noqa: E402


def draw_face(frame: np.ndarray, cx: int, cy: int, size: int, skin=(205, 195, 185)) -> None:
    """Draw a face-like shape that Haar cascades reliably detect.

    Haar frontal-face cascades key on the classic light-forehead / dark-eyes /
    dark-mouth pattern, so those three regions are rendered with high contrast.
    """
    h, w = frame.shape[:2]
    rx = int(size * 0.40)
    ry = int(size * 0.50)
    # Neck / shoulders
    cv2.ellipse(frame, (cx, cy + int(ry * 1.5)), (int(rx * 1.7), int(ry * 0.75)),
                0, 0, 360, (85, 95, 120), -1)
    # Face oval
    cv2.ellipse(frame, (cx, cy), (rx, ry), 0, 0, 360, skin, -1)
    # Hair / forehead band (dark, above eyes)
    cv2.ellipse(frame, (cx, cy - int(ry * 0.50)), (rx, int(ry * 0.52)), 0, 180, 360,
                (45, 42, 48), -1)
    # Eye sockets: dark region with a bright sclera inside
    eye_dx = int(rx * 0.44)
    eye_r = max(4, int(size * 0.085))
    eye_y = cy - int(ry * 0.15)
    for sx in (-eye_dx, eye_dx):
        cv2.ellipse(frame, (cx + sx, eye_y), (int(eye_r * 1.5), int(eye_r * 1.1)),
                    0, 0, 360, (70, 62, 58), -1)
        cv2.circle(frame, (cx + sx, eye_y), eye_r, (250, 250, 250), -1)
        cv2.circle(frame, (cx + sx, eye_y), max(2, eye_r // 2), (30, 28, 26), -1)
        # eyebrow
        cv2.line(frame, (cx + sx - int(eye_r * 1.4), eye_y - int(ry * 0.28)),
                 (cx + sx + int(eye_r * 1.4), eye_y - int(ry * 0.26)), (40, 36, 34), 3)
    # Nose bridge shadow
    cv2.line(frame, (cx + int(rx * 0.05), eye_y + int(ry * 0.10)),
             (cx - int(rx * 0.10), cy + int(ry * 0.28)), (165, 150, 140), 3)
    # Dark mouth
    cv2.ellipse(frame, (cx, cy + int(ry * 0.48)), (int(rx * 0.50), int(ry * 0.22)),
                0, 0, 180, (95, 62, 68), 3)
    cv2.line(frame, (cx - int(rx * 0.48), cy + int(ry * 0.48)),
             (cx + int(rx * 0.48), cy + int(ry * 0.48)), (95, 62, 68), 2)


def build(out: Path, seconds: int = 14, width: int = 1280, height: int = 720, fps: int = 30):
    """Render frames with OpenCV and pipe rawvideo straight into ffmpeg.

    Piping raw frames avoids depending on any intermediate container/codec support
    in the local ffmpeg build.

    The audio track imitates speech: alternating loud bursts (the "talking" parts)
    separated by quiet pauses, with the loud section following whichever person is
    on screen.  That gives the audio analysis real energy/silence structure and lets
    the speaker-tracking and clip-scoring code paths work on meaningful data.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    n = seconds * fps
    ffmpeg = require_ffmpeg()

    # Build a speech-like waveform in numpy: 160 Hz voice fundamental + a formant
    # overtone, gated into bursts with short gaps, at 44.1 kHz.
    sr = 44100
    total = sr * seconds
    t = np.arange(total, dtype=np.float32) / sr
    voice = (0.55 * np.sin(2 * np.pi * 160.0 * t)
             + 0.28 * np.sin(2 * np.pi * 320.0 * t)
             + 0.16 * np.sin(2 * np.pi * 480.0 * t))
    gate = np.zeros(total, dtype=np.float32)
    # Two-second "sentences" separated by 0.7 s pauses.
    step = int(2.0 * sr)
    gap = int(0.7 * sr)
    pos = 0
    while pos < total:
        end = min(total, pos + step)
        # Fade the edges so bursts do not click.
        fade = min(int(0.05 * sr), (end - pos) // 2)
        seg = gate[pos:end]
        seg[:] = 1.0
        if fade > 0:
            seg[:fade] = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            seg[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
        pos = end + gap
    wave = (voice * gate * 0.55).astype(np.float32)
    pcm = np.int16(np.clip(wave, -1.0, 1.0) * 32767)

    # Write the speech-like audio to a temporary WAV file and feed it to ffmpeg
    # as a second file input.  Using a file instead of a second pipe avoids the
    # classic two-pipe deadlock and keeps the command portable.
    import wave

    audio_path = out.with_suffix(".wav")
    with wave.open(str(audio_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "pipe:0",
        "-i", str(audio_path),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    vw = proc.stdin

    for i in range(n):
        t = i / fps
        frame = np.full((height, width, 3), 70, dtype=np.uint8)
        # Background gradient so frames are not static
        grad = np.linspace(40, 110, width, dtype=np.uint8)
        frame[:, :, 0] = grad[None, :]
        frame[:, :, 1] = grad[None, :] // 2

        # Two "speakers": A on the left (primary), B on the right.
        # They alternate which one is speaking/leaning in, like a podcast.
        speaker = "A" if (t // 3.5) % 2 == 0 else "B"
        ax, bx = int(width * 0.28), int(width * 0.72)
        a_size = 150 + int(28 * np.sin(t * 1.7))
        b_size = 150 + int(28 * np.sin(t * 1.4 + 1.2))
        if speaker == "A":
            b_size = int(b_size * 0.82)
        else:
            a_size = int(a_size * 0.82)
        draw_face(frame, ax, int(height * 0.40), a_size, skin=(205, 193, 180))
        draw_face(frame, bx, int(height * 0.40), b_size, skin=(185, 168, 152))

        # Scene change: flash a coloured band every ~7 seconds (real cut trigger)
        if int(t) % 7 == 0 and (t % 1.0) < 0.05:
            frame[:] = (30, 30, 30)
        cv2.putText(frame, f"t={t:05.2f}", (24, 60), cv2.FONT_HERSHEY_SIMPLEX,
                    1.1, (255, 255, 255), 2)
        vw.write(frame.tobytes())

    vw.close()
    stderr = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        print(stderr[-1500:])
        raise SystemExit("ffmpeg encode failed")
    audio_path.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "testdata" / "faces.mp4"
    dur = int(sys.argv[2]) if len(sys.argv) > 2 else 14
    p = build(target, dur)
    print(f"Wrote {p} ({p.stat().st_size / 1024:.0f} KB)")
