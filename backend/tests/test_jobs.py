import json
from pathlib import Path

from app.jobs import jobs


def test_update_accepts_positional_progress_and_message():
    job_id = jobs.create("test", {})
    jobs.update(job_id, 42, "halfway")
    job = jobs.get(job_id)
    assert job["progress"] == 42
    assert job["message"] == "halfway"


def test_health_reports_package_version():
    from fastapi.testclient import TestClient
    from app.main import app

    version = json.loads((Path(__file__).resolve().parents[2] / "package.json").read_text())["version"]
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"X-AI-Clipper-Token": "aifreeclip-test-token"})
    assert response.status_code == 200
    assert response.json()["version"] == version
