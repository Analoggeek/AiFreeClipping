"""Regressions for responsive batch rendering and incremental Auto Edit output."""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import db, dumps, now, uid
import app.main as main_module
from app.main import app
from app.services import render

client = TestClient(app)
HEADERS = {"X-AI-Clipper-Token": "aifreeclip-test-token"}


def _wait_for_job(job_id: str, test_client: TestClient = client) -> dict:
    for _ in range(300):
        response = test_client.get(f"/api/jobs/{job_id}", headers=HEADERS)
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"done", "error", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Job did not finish: {job}")


def test_render_budget_reserves_cpu_and_honors_requested_worker_limit():
    assert main_module._render_budget(70, {"cpu_count": 8, "workers": 4}) == (3, 2)
    assert main_module._render_budget(70, {"cpu_count": 10, "workers": 1}) == (1, 8)
    assert main_module._render_budget(1, {"cpu_count": 1, "workers": 4}) == (1, 1)


def test_ffmpeg_clip_threads_use_the_auto_edit_budget():
    args = render.build_clip_args(
        "/tmp/source.mp4", 0, 2, "/tmp/output.mp4",
        {"aspect": "9:16", "resolution": "720p", "render_threads": 2, "sfx": []},
    )
    assert args[args.index("-threads") + 1] == "2"
    assert args[args.index("-filter_threads") + 1] == "2"
    assert args[args.index("-filter_complex_threads") + 1] == "2"


def test_blur_fill_runs_at_quarter_resolution_before_upscaling():
    args = render.build_clip_args(
        "/tmp/source.mp4", 0, 2, "/tmp/output.mp4",
        {"aspect": "9:16", "resolution": "1080p", "blur_background": True, "sfx": []},
    )
    graph = args[args.index("-filter_complex") + 1]
    assert "[bg]scale=270:480" in graph
    assert "gblur=sigma=6" in graph
    assert "scale=1080:1920:flags=bilinear[bgb]" in graph
    assert "[fg]scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos" in graph


def test_auto_edit_exposes_completed_outputs_and_continues_after_a_render_failure(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic source")
    media_id = uid("m_render_perf_")
    first_id, second_id, third_id = (uid("c_render_perf_") for _ in range(3))
    missing_media_id = uid("m_render_perf_missing_")
    db.insert("media", {
        "id": media_id, "title": "Render performance source", "path": str(source),
        "source_url": None, "duration": 8, "width": 640, "height": 360,
        "thumbnail": None, "playlist_id": None, "metadata": "{}", "created_at": now(),
    })
    clip_sources = ((first_id, media_id), (second_id, media_id), (third_id, missing_media_id))
    for index, (clip_id, clip_media_id) in enumerate(clip_sources):
        db.insert("clips", {
            "id": clip_id, "project_id": None, "media_id": clip_media_id,
            "start": index * 2, "end": index * 2 + 2, "score": 80 - index,
            "title": f"Performance clip {index + 1}", "reason": "test",
            "status": "proposed", "output": None, "metadata": dumps({}),
            "created_at": now(),
        })

    second_render_started = threading.Event()
    allow_second_render_to_fail = threading.Event()
    jobs_to_delete: list[str] = []

    async def fake_render(_media, _start, _end, output, options, on_progress=None):
        assert options["render_threads"] == 1
        if first_id in output:
            if on_progress:
                on_progress(50, "Rendering test clip")
            return output
        second_render_started.set()
        await asyncio.to_thread(allow_second_render_to_fail.wait, 5)
        raise RuntimeError("simulated FFmpeg failure")

    monkeypatch.setattr(main_module, "hardware_info", lambda: {"cpu_count": 1, "workers": 1, "encoder": "test"})
    monkeypatch.setattr(main_module, "configured_watermark_path", lambda: None)
    monkeypatch.setattr(render, "render_clip", fake_render)
    monkeypatch.setattr(render, "export_path", lambda name: str(tmp_path / f"{name}.mp4"))

    try:
        with TestClient(app) as test_client:
            response = test_client.post("/api/auto-edit", headers=HEADERS, json={
                "clip_ids": [first_id, second_id, third_id], "sound_effects": False, "stickers": False,
                "blur_background": False,
            })
            assert response.status_code == 200
            job_id = response.json()["job_id"]
            jobs_to_delete.append(job_id)

            assert second_render_started.wait(3), "the second render did not start"
            partial = test_client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
            assert partial["status"] == "running", partial
            assert partial["result"]["partial"] is True
            assert partial["result"]["completed"] == 1
            assert [item["clip_id"] for item in partial["result"]["outputs"]] == [first_id]
            assert [item["clip_id"] for item in partial["result"]["edits"]] == [first_id]

            allow_second_render_to_fail.set()
            final = _wait_for_job(job_id, test_client)
            assert final["status"] == "done", final
            assert final["result"]["partial"] is False
            assert final["result"]["total"] == 3
            assert final["result"]["count"] == 1
            assert len(final["result"]["warnings"]) == 2
            assert any("simulated FFmpeg failure" in warning for warning in final["result"]["warnings"])
            assert any(missing_media_id in warning for warning in final["result"]["warnings"])
            assert final["result"]["completed"] == 1
            rendered = db.loads(db.one("SELECT * FROM clips WHERE id=?", (first_id,)), "metadata")
            failed = db.loads(db.one("SELECT * FROM clips WHERE id=?", (second_id,)), "metadata")
            assert rendered["output"] and rendered["status"] == "auto_edited"
            assert failed["output"] is None and failed["status"] == "proposed"
    finally:
        allow_second_render_to_fail.set()
        for job_id in jobs_to_delete:
            db.delete("jobs", "id", job_id)
        db.delete("clips", "id", first_id)
        db.delete("clips", "id", second_id)
        db.delete("clips", "id", third_id)
        db.delete("media", "id", media_id)
