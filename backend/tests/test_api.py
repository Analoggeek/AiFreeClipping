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
