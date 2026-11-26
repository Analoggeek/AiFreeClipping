from pathlib import Path

from app.services.render import build_clip_args, resolution_for, write_ass


def test_resolution_table():
    assert resolution_for("9:16", "1080p") == (1080, 1920)
    assert resolution_for("16:9", "720p") == (1280, 720)


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
