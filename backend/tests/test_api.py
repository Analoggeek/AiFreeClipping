import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_needs_token():
    assert client.get("/api/health").status_code == 401


def test_health_and_capabilities():
    token = open(os.path.expanduser("~/.AiFreeClipping/.api_token"), encoding="utf-8").read()
    headers = {"X-AI-Clipper-Token": token}
    health = client.get("/api/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["ok"] is True
    caps = client.get("/api/system/capabilities", headers=headers)
    assert caps.status_code == 200
    assert "ffmpeg" in caps.json()


def test_hardware_endpoint_reports_workers():
    token = open(os.path.expanduser("~/.AiFreeClipping/.api_token"), encoding="utf-8").read()
    headers = {"X-AI-Clipper-Token": token}
    response = client.get("/api/system/hardware", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["workers"] >= 1
    assert body["cpu_count"] >= 1
    assert "gpu" in body


def test_apply_effects_to_multiple_clips():
    token = open(os.path.expanduser("~/.AiFreeClipping/.api_token"), encoding="utf-8").read()
    headers = {"X-AI-Clipper-Token": token}
    response = client.post(
        "/api/clips/apply-effects",
        headers=headers,
        json={"clip_ids": ["missing-clip"], "effects": {"aspect": "9:16"}},
    )
    assert response.status_code == 200
    assert response.json()["changed"] == 0
