from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from skyle_ai.api import create_app
from skyle_ai.config import Settings


def test_health_ui_and_system_state(client):
    assert client.get("/health").json()["status"] == "ok"
    page = client.get("/")
    assert page.status_code == 200
    assert "Skyle AI" in page.text
    assert client.get("/static/app.css").status_code == 200
    system = client.get("/api/v1/system").json()
    assert system["llm"]["configured"] is False
    assert system["storage"]["engine"] == "SQLite + FTS5"
    assert system["privacy"].startswith("Uploaded documents remain")


def test_auth_is_optional_but_enforced_when_configured(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / "secure", api_key="local-test-key"))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/system").status_code == 401
        assert client.get("/api/v1/system", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = client.get("/api/v1/system", headers={"Authorization": "Bearer local-test-key"})
        assert ok.status_code == 200
        assert ok.json()["auth_required"] is True


def test_activity_excludes_submitted_text(client):
    secret_phrase = "private diagnostic phrase zq9824"
    response = client.post("/api/v1/analyze/text", json={"text": f"This is a good {secret_phrase}"})
    assert response.status_code == 200
    activity_response = client.get("/api/v1/activity")
    activity = activity_response.text
    assert "private diagnostic phrase" not in activity
    assert "good" not in activity
    assert activity_response.json()["events"][0]["duration_ms"] >= 1


def test_document_size_limit_is_per_file(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "small", max_document_bytes=12)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/documents/upload", files={"files": ("large.txt", b"this file is longer", "text/plain")}
        )
        assert response.status_code == 200
        assert response.json()["results"][0]["status"] == "error"
        assert "limit" in response.json()["results"][0]["error"]


def test_capabilities_disclose_untrained_and_demo_only_areas(client):
    entries = {item["id"]: item for item in client.get("/api/v1/capabilities").json()["capabilities"]}
    assert "not an autonomous multi-agent model" in entries["agents"]["method"]
    assert "unbenchmarked" in entries["nlp"]["method"]
    assert "no local object recognition" in entries["vision"]["method"]
