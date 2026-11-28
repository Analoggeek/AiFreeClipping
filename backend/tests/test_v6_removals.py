"""v6 regression coverage for retired caption/subtitle and YouTube publishing APIs."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import db, dumps, now, uid
from app.main import ClipPatch, _clean_clip_metadata, app
from app.schemas import AutoEditRequest, DownloadRequest, RenderRequest
from app.services.downloader import _ydl_options

client = TestClient(app)
HEADERS = {"X-AI-Clipper-Token": "aifreeclip-test-token"}


def test_removed_features_are_absent_from_openapi_and_request_schemas():
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/analysis/transcribe" not in paths
    assert "/api/analysis/{media_id}/transcript" not in paths
    assert not any(path.startswith("/api/youtube/") for path in paths)

    assert "subtitles" not in DownloadRequest.model_fields
    assert "captions" not in RenderRequest.model_fields
    assert "caption_style" not in RenderRequest.model_fields
    assert "title" not in RenderRequest.model_fields
    assert "captions" not in AutoEditRequest.model_fields
    assert "caption_style" not in AutoEditRequest.model_fields
    assert "reuse_settings" not in AutoEditRequest.model_fields
    assert "caption" not in ClipPatch.model_fields


def test_youtube_download_remains_supported_without_subtitle_artifacts():
    request = DownloadRequest(url="https://www.youtube.com/watch?v=video-id", mode="single")
    options = _ydl_options(request, Path("/tmp"))
    assert options["format"] == "bestvideo+bestaudio/best"
    assert options["noplaylist"] is True
    assert not any(key.lower().endswith("subtitles") or key.lower().startswith("write") for key in options)


def test_legacy_project_text_tracks_are_removed_but_editable_tracks_survive():
    project_id = uid("v6_project_")
    legacy_timeline = {
        "caption_style": {"preset": "hype"},
        "aspect": "9:16",
        "resolution": "720p",
        "tracks": {
            "video": [{
                "path": "/tmp/source.mp4", "sourceStart": 2, "duration": 4,
                "caption_style": {"preset": "premium"},
                "captions": [{"text": "old overlay", "start": 0, "end": 2}],
                "effects": {
                    "speed": 1.1,
                    "caption_style": {"preset": "hype"},
                    "captions": [{"text": "old effect", "start": 0, "end": 1}],
                    "title": "old title overlay",
                },
            }],
            "captions": [{"text": "legacy track", "start": 0, "end": 1}],
            "stickers": [{"path": "/tmp/sticker.png", "start": 1, "end": 2, "x": 0.5, "y": 0.5}],
            "audio": [{"path": "/tmp/music.wav", "start": 0, "end": 4, "volume": 0.2}],
        },
    }
    db.insert("projects", {
        "id": project_id, "name": "Legacy project", "data": dumps({"timeline": {}}),
        "created_at": now(), "updated_at": now(),
    })
    try:
        response = client.put(
            f"/api/projects/{project_id}", headers=HEADERS,
            json={"timeline": legacy_timeline},
        )
        assert response.status_code == 200
        timeline = response.json()["project"]["timeline"]
        tracks = timeline["tracks"]
        assert set(tracks) == {"video", "stickers", "audio"}
        assert len(tracks["video"]) == len(tracks["stickers"]) == len(tracks["audio"]) == 1
        video = tracks["video"][0]
        assert video["path"] == "/tmp/source.mp4" and video["duration"] == 4
        assert "captions" not in video and "caption_style" not in video
        assert video["effects"] == {"speed": 1.1}
        stored = json.loads(db.one("SELECT data FROM projects WHERE id=?", (project_id,))["data"])
        assert stored["timeline"] == timeline
    finally:
        db.delete("projects", "id", project_id)


def test_legacy_settings_are_hidden_and_cannot_be_set_via_api():
    keys = ("youtube_client_secret", "YOUTUBE_CLIENT_SECRET", "auto_edit_captions")
    previous = {key: db.get_setting(key, "") for key in keys}
    try:
        for key in keys:
            db.set_setting(key, "legacy-value")
        response = client.get("/api/settings", headers=HEADERS)
        assert response.status_code == 200
        assert not any(key in response.json()["values"] for key in keys)

        response = client.put("/api/settings", headers=HEADERS, json={"values": {key: "new-value" for key in keys}})
        assert response.status_code == 200
        assert not any(key in response.json()["values"] for key in keys)
        assert all(db.get_setting(key) == "legacy-value" for key in keys)
    finally:
        for key, value in previous.items():
            db.set_setting(key, value)


def test_legacy_social_copy_is_removed_and_plain_titles_are_retained():
    metadata = {
        "caption": "Old social copy",
        "hook": "You won't believe this",
        "hashtags": ["#Shorts", "#Viral"],
        "title": "A factual clip title",
        "transcript": "The source words remain available for internal context.",
    }
    cleaned = _clean_clip_metadata(metadata)
    assert cleaned == {
        "title": "A factual clip title",
        "transcript": "The source words remain available for internal context.",
    }
