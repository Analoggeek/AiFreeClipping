"""Real independent timeline-window exports; injected failures are labelled."""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from tests.test_multitrack import media
from clipos.video.multitrack import MultitrackProject
from clipos.video.studio_batch import plan_batch, run_batch
from clipos.video.multitrack_render import export_project
from clipos.core.ffmpeg import probe


def assembly(media):
    project = MultitrackProject(width=160, height=90, fps=10)
    project.import_media(media[0], queue_clip_id=1)
    project.import_media(media[1], at=2, queue_clip_id=2)
    project.add_caption("Actual caption layer", 2, 0.8)
    return project


def test_actual_batch_windows_dimensions_audio_manifest_and_no_overwrite(
    media, tmp_path
):
    p = assembly(media)
    jobs = plan_batch(p, {1, 2}, tmp_path, "Studio")
    manifest = tmp_path / "manifest.json"
    run_batch(p, jobs, encoder="cpu", manifest=manifest)
    assert [j.status for j in jobs] == ["completed", "completed"]
    for job in jobs:
        info = probe(job.output)
        assert (info.video.width, info.video.height) == (160, 90)
        assert info.has_audio and abs(info.duration - 2) < 0.2
    from tests.test_crop_config import decode

    first = decode(jobs[0].output)
    second = decode(jobs[1].output)
    assert first[5, 5, 2] > first[5, 5, 0] + 100  # red first clip, BGR decoder
    assert (
        second[5, 5, 0] > second[5, 5, 2] + 100
    )  # blue second window, not wrong source
    assert [j["status"] for j in json.loads(manifest.read_text())["jobs"]] == [
        "completed",
        "completed",
    ]
    with pytest.raises(ValueError, match="already exists"):
        plan_batch(p, {1, 2}, tmp_path, "Studio")


def test_one_missing_source_fails_only_its_window_and_retry_recovers(media, tmp_path):
    p = assembly(media)
    jobs = plan_batch(p, {1, 2}, tmp_path, "Recover")
    original = media[0].read_bytes()
    media[0].unlink()
    run_batch(p, jobs, encoder="cpu")
    assert jobs[0].status == "failed" and jobs[1].status == "completed"
    good_stat = Path(jobs[1].output).stat().st_mtime_ns
    media[0].write_bytes(original)
    run_batch(p, jobs, encoder="cpu", retry=True)
    assert all(j.status == "completed" for j in jobs)
    assert Path(jobs[1].output).stat().st_mtime_ns == good_stat


def test_cancel_and_publish_race_never_overwrite_existing_file(media, tmp_path):
    p = assembly(media)
    jobs = plan_batch(p, {1, 2}, tmp_path, "Cancel")
    run_batch(p, jobs, cancelled=lambda: True)
    assert all(j.status == "cancelled" for j in jobs)
    assert not any(Path(j.output).exists() for j in jobs)
    jobs = plan_batch(p, {1}, tmp_path, "Race")

    def concurrent_publish(*args, **kwargs):
        result = export_project(*args, **kwargs)
        Path(jobs[0].output).write_bytes(b"other application output")
        return result

    with patch(
        "clipos.video.studio_batch.export_project", side_effect=concurrent_publish
    ):
        run_batch(p, jobs, encoder="cpu")
    assert jobs[0].status == "failed"
    assert Path(jobs[0].output).read_bytes() == b"other application output"
    assert not list(tmp_path.glob(".clipos-batch-*"))
