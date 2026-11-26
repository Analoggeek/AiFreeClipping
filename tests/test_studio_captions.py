"""Real extraction/rendering with explicitly injected transcript contract data.

These tests do not certify speech recognition accuracy.
"""

from unittest.mock import patch
import pytest

from tests.test_multitrack import media
from clipos.ai.transcription import Transcript, Segment, Word
from clipos.video.multitrack import MultitrackProject
from clipos.video.studio_captions import (
    generate_timeline_captions,
    append_generated_captions,
)
from clipos.video.multitrack_render import export_project
from clipos.core.ffmpeg import probe, FFmpegCancelled


def test_generation_maps_trim_speed_and_real_word_times_and_renders(media, tmp_path):
    p = MultitrackProject(width=160, height=90, fps=10)
    mid = p.import_media(media[0], at=1)
    lane = p.lanes[0]
    item = lane.items[0]
    p.change_item(lane.id, item.id, linked=True, source_in=0.5, length=1, speed=2)
    transcript = Transcript(
        language="en",
        duration=1,
        text="hello world",
        segments=[
            Segment(
                0,
                0.8,
                "hello world",
                [Word("hello", 0.1, 0.3), Word("world", 0.4, 0.8)],
            )
        ],
    )
    before = p.to_dict()
    with (
        patch("clipos.video.studio_captions.local_model_path", return_value=tmp_path),
        patch(
            "clipos.video.studio_captions.transcribe", return_value=transcript
        ) as speech,
    ):
        result = generate_timeline_captions(p, {mid}, model_size="tiny")
    assert p.to_dict() == before
    assert speech.call_args.kwargs["device"] == "cpu"
    append_generated_captions(p, result)
    cue = p.lanes[-1].items[0]
    assert cue.at == pytest.approx(1.05)
    assert cue.caption_words[1]["s"] == pytest.approx(0.15)
    path = tmp_path / "captioned.mp4"
    export_project(p, path, tmp_path / "work", encoder="cpu")
    assert probe(path).has_audio
    saved = tmp_path / "assembly.json"
    p.save(saved)
    assert MultitrackProject.load(saved).to_dict() == p.to_dict()
    assert p.undo() and p.to_dict() == before


def test_missing_model_and_cancellation_never_modify_project(media, tmp_path):
    p = MultitrackProject(width=160, height=90)
    mid = p.import_media(media[0])
    before = p.to_dict()
    with patch("clipos.video.studio_captions.local_model_path", return_value=None):
        with pytest.raises(RuntimeError, match="AI Models"):
            generate_timeline_captions(p, {mid})
    with patch("clipos.video.studio_captions.local_model_path", return_value=tmp_path):
        with pytest.raises(FFmpegCancelled):
            generate_timeline_captions(p, {mid}, cancelled=lambda: True)
    assert p.to_dict() == before


def test_timed_caption_split_and_validation(tmp_path):
    p = MultitrackProject(width=160, height=90)
    lane, item = p.add_caption("hello world", 0, 2)
    p.change_item(
        lane,
        item,
        caption_words=[
            {"w": "hello", "s": 0.0, "e": 0.8},
            {"w": "world", "s": 1.0, "e": 1.8},
        ],
    )
    p.split(lane, item, 1)
    assert [cue.text for cue in p.lanes[0].items] == ["hello", "world"]
    assert p.lanes[0].items[1].caption_words[0]["s"] == 0
    before = p.to_dict()
    with pytest.raises(ValueError):
        p.change_item(lane, item, caption_words=[{"w": "bad", "s": 0.0, "e": 10.0}])
    assert p.to_dict() == before
