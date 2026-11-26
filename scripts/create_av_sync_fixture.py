"""Create a reproducible flash/click stimulus, not a physical-device QA result.

Run with the application's Python environment. First frame of every second is
white; a 10 ms 1 kHz tone starts on that exact second. PCM avoids AAC priming.
"""

from pathlib import Path
import argparse
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipos.core.ffmpeg import require_ffmpeg


def create(output, seconds=300):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    if type(seconds) is not int or not 3 <= seconds <= 3600:
        raise ValueError("Duration must be 3–3600 seconds")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_ffmpeg(),
        "-hide_banner",
        "-nostdin",
        "-n",
        "-f",
        "lavfi",
        "-i",
        f"color=black:s=640x360:r=60:d={seconds},drawbox=color=white:t=fill:enable='eq(mod(n,60),0)'",
        "-f",
        "lavfi",
        "-i",
        f"aevalsrc=0.5*sin(2*PI*1000*t)*lt(mod(t\\,1)\\,0.01):s=48000:d={seconds}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "pcm_s16le",
        "-t",
        str(seconds),
        str(output),
    ]
    subprocess.run(
        command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    manifest = {
        "stimulus": str(output),
        "duration_seconds": seconds,
        "fps": 60,
        "sample_rate": 48000,
        "event_seconds": list(range(seconds)),
        "event_duration_audio_ms": 10,
        "physical_qa_status": "NOT RUN",
        "note": "Nominal simultaneous source events do not establish speaker/display sync. Measure captured events and capture-path calibration.",
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        type=Path,
        help="New .mov output; existing files are never overwritten",
    )
    parser.add_argument("--seconds", type=int, default=300)
    args = parser.parse_args()
    if args.output.suffix.lower() != ".mov":
        parser.error("Use .mov for PCM audio stimulus")
    print(create(args.output, args.seconds))
