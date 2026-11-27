"""Regressions for stale media selections in clip discovery."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.db import db, dumps, now, uid
import app.main as main_module
from app.main import app

client = TestClient(app)
HEADERS = {"X-AI-Clipper-Token": "aifreeclip-test-token"}


def _wait_for_job(job_id: str) -> dict:
    for _ in range(200):
        response = client.get(f"/api/jobs/{job_id}", headers=HEADERS)
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"done", "error", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Job did not finish: {job_id}")


def test_proposal_with_only_deleted_media_fails_with_a_refresh_hint():
    response = client.post("/api/clips/propose", headers=HEADERS, json={
        "media_ids": [uid("deleted_media_")], "count": 1,
        "min_duration": 5, "max_duration": 5, "use_llm": False,
    })
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    try:
        job = _wait_for_job(job_id)
        assert job["status"] == "error"
        assert job["error"] == "None of the selected videos are available in the library. Refresh and select a video again."
    finally:
        db.delete("jobs", "id", job_id)


def test_proposal_skips_deleted_media_and_finishes_with_available_sources(tmp_path, monkeypatch):
    media_id = uid("live_media_")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic source")
    db.insert("media", {
        "id": media_id, "title": "Available source", "path": str(source), "source_url": None,
        "duration": 10, "width": 640, "height": 360, "thumbnail": None,
        "playlist_id": None, "metadata": "{}", "created_at": now(),
    })

    async def fake_transcribe(*_args, **_kwargs):
        return {"segments": [], "text": ""}

    async def fake_vision(*_args, **_kwargs):
        return {
            "timeline": [], "crop_path": [], "region_key": "[]",
            "reframe_version": main_module.vision.REFRAME_VERSION,
        }

    monkeypatch.setattr(main_module, "transcribe", fake_transcribe)
    monkeypatch.setattr(main_module.vision, "analyze", fake_vision)
    missing_id = uid("deleted_media_")
    response = client.post("/api/clips/propose", headers=HEADERS, json={
        "media_ids": [missing_id, media_id, media_id], "count": 1,
        "min_duration": 5, "max_duration": 5, "use_llm": False,
    })
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    try:
        job = _wait_for_job(job_id)
        assert job["status"] == "done", job
        assert job["result"]["clips"]
        assert job["result"]["warnings"] == [
            "1 selected video(s) were no longer in the library and were skipped."
        ]
        assert all(clip["media_id"] == media_id for clip in job["result"]["clips"])
    finally:
        db.execute("DELETE FROM analyses WHERE media_id=?", (media_id,))
        db.execute("DELETE FROM clips WHERE media_id=?", (media_id,))
        db.delete("media", "id", media_id)
        db.delete("jobs", "id", job_id)
