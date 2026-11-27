import asyncio
import subprocess
from pathlib import Path

import pytest

from app.config import ffmpeg_binary
from app.services import render
from app.services.render import _compose_regions, _even_pair, build_clip_args, resolution_for, write_ass
from app.services.utils import probe


def test_resolution_table():
    assert resolution_for("9:16", "1080p") == (1080, 1920)
    assert resolution_for("16:9", "720p") == (1280, 720)


def test_split_ratio_and_outline_are_carried_into_composition_filters():
    assert _even_pair(1920, 0.75) == (1440, 480)
    regions = [
        {"x": 0, "y": 0, "w": 1, "h": 0.58},
        {"x": 0, "y": 0.58, "w": 1, "h": 0.42},
    ]
    filters, result = _compose_regions(
        "0:v", "fps=30", regions, "top-game-bottom-player", 1080, 1920,
        "preview", 0.75, "neon",
    )
    graph = ";".join(filters)
    assert "scale=1080:1440" in graph and "scale=1080:480" in graph
    assert "vstack=inputs=2" in graph
    assert graph.count("drawbox=") == 4
    assert "0x22D3EE@0.34" in graph and "0x22D3EE@0.98" in graph
    assert result == "preview_outline3"


@pytest.mark.parametrize("outline_style", ["none", "clean", "neon", "double"])
def test_split_ratio_and_outline_render_to_playable_video(tmp_path: Path, outline_style: str):
    ffmpeg = ffmpeg_binary()
    available = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
    if "libx264" not in available.stdout:
        pytest.skip("Local FFmpeg does not include the libx264 encoder")
    source = tmp_path / "split-source.mp4"
    output = tmp_path / "split-outline.mp4"
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=12", "-t", "1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True)
    regions = [
        {"x": 0, "y": 0, "w": 1, "h": 0.6},
        {"x": 0, "y": 0.6, "w": 1, "h": 0.4},
    ]
    asyncio.run(render.render_clip(str(source), 0, 1, str(output), {
        "aspect": "9:16", "resolution": "720p", "regions": regions,
        "region_layout": "top-game-bottom-player", "split_ratio": 0.7,
        "outline_style": outline_style, "caption_style": {"preset": "none"},
        "sfx": [], "watermark": False,
    }))
    assert output.stat().st_size > 1000
    info = probe(output)
    assert (info["video_codec"], info["width"], info["height"]) == ("h264", 720, 1280)


def test_clip_command_has_expected_filters(tmp_path: Path):
    music = tmp_path / "music.mp3"
    music.write_bytes(b"")
    sticker = tmp_path / "sticker.png"
    sticker.write_bytes(b"")
    options = {
        "aspect": "9:16", "resolution": "1080p", "music": str(music),
        "sticker": str(sticker), "sfx": ["whoosh"], "captions": [],
        "caption_style": {"preset": "none"}, "watermark_path": None,
    }
    args = build_clip_args("/tmp/input.mp4", 10, 25, "/tmp/out.mp4", options, has_audio=True)
    joined = " ".join(args)
    assert "-i" in args
    assert "trim=start=10.000:end=25.000" in joined
    assert "subtitles" not in joined
    assert "[vout]" in joined and "[aout]" in joined
    assert "amix=inputs=3" in joined  # voice + music + one sfx
    assert "-progress" in args
    assert "shell" not in joined


def test_small_focus_region_is_expanded_to_a_usable_crop():
    options = {
        "aspect": "9:16", "resolution": "1080p", "captions": [],
        "caption_style": {"preset": "none"}, "blur_background": True,
        "region": {"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.1},
    }
    joined = " ".join(build_clip_args("/tmp/input.mp4", 0, 5, "/tmp/out.mp4", options, has_audio=True))
    assert "crop=" in joined
    # Even a tiny marked area must keep at least a quarter of the source frame.
    assert "iw*0.2" in joined or "ih*0.2" in joined or "iw*0.50" in joined


def test_write_ass(tmp_path: Path):
    path = write_ass(
        [{"text": "Hello!", "start": 1.0, "end": 2.0}, {"word": "Go", "start": 2.0, "end": 2.4}],
        {"preset": "hype"}, offset=0, position="bottom",
    )
    content = Path(path).read_text()
    assert "[Script Info]" in content
    assert "Dialogue:" in content and "Hello!" in content and "Go" in content
