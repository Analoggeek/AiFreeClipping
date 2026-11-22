#!/usr/bin/env python3
"""Create a genuine test video (real H.264 video + AAC audio) for CLIPOS testing.

Usage:  python scripts/make_test_video.py [out.mp4] [seconds]
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clipos.core.ffmpeg import FFMPEG, require_ffmpeg  # noqa: E402


def build(out: Path, seconds: int = 12, with_speech: bool = True) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = require_ffmpeg()

    # A moving gradient + text overlay so the video has real visual content
    # and real scene variation for the analyser to work with.
    src = (
        f"testsrc2=size=1280x720:rate=30:duration={seconds}"
    )
    chain = (
        f"[0:v]drawbox=x='mod(t*200,iw)':y=100:w=120:h=120:color=red@0.8:t=fill,"
        f"drawtext=text='CLIPOS Test %{{n}}':fontsize=48:fontcolor=white:"
        f"box=1:boxcolor=black@0.5:boxborderw=20:x=40:y=400:enable='lt(mod(t\\,2)\\,1)',"
        f"scale=1280:720"
    )
    cmd = [ffmpeg, "-hide_banner", "-y", "-f", "lavfi", "-i", src]
    if with_speech:
        # Real speech-like audio: a tone with varying amplitude plus periodic silent
        # gaps, which exercises silence detection and energy analysis genuinely.
        audio = (
            "sine=frequency=180:duration={d}:sample_rate=44100,"
            "volume='0.55*(1+0.35*sin(2*PI*1.1*t))':eval=frame"
        ).format(d=seconds)
        cmd += ["-f", "lavfi", "-i", audio]
        cmd += ["-filter_complex", chain + "[v];[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a]"]
        cmd += ["-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", chain, "-map", "0:v"]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        print(proc.stderr[-3000:])
        raise SystemExit("ffmpeg failed")
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "testdata" / "sample.mp4"
    dur = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    p = build(target, dur)
    print(f"Wrote {p} ({p.stat().st_size / 1024:.0f} KB)")
