from unittest.mock import patch

import pytest

from app.services.session_client import SessionResult


@pytest.fixture(autouse=True)
def enable_council_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.capabilities._capabilities_path", return_value=tmp_path / "capabilities.json"):
        from app.services.capabilities import update_capability
        update_capability("council_pipeline", True, actor="test")
        yield


def _write_item(tmp_path, project="claude-config", slug="2026-08-18-test-item"):
    from app.services.vault import write_entry
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / project).mkdir(parents=True, exist_ok=True)
        return write_entry({
            "type": "council-item", "project": project,
            "title": "Test item", "body": "Body", "match_slug": "test-item",
        })


def test_discuss_requires_token(client, tmp_path):
    resp = client.post("/council/some-slug/discuss")
    assert resp.status_code == 401


def test_discuss_spawns_session_and_sets_in_discussion(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes.council.project_slug", lambda: "claude-config")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        slug = _write_item(tmp_path)
        with patch("app.services.driver.run_council_discuss", return_value=SessionResult(session_id="s1")) as mock_run:
            resp = client.post(f"/council/{slug}/discuss", headers={"X-Capture-Token": "test-token-secret"})
    assert resp.status_code == 200
    assert resp.get_json()["session_id"] == "s1"
    mock_run.assert_called_once_with(slug)


def test_approve_spawns_action_session(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes.council.project_slug", lambda: "claude-config")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        slug = _write_item(tmp_path)
        with patch("app.services.driver.run_council_action", return_value=SessionResult(session_id="s2")) as mock_run:
            resp = client.post(f"/council/{slug}/approve", headers={"X-Capture-Token": "test-token-secret"})
    assert resp.status_code == 200
    assert resp.get_json()["session_id"] == "s2"
    mock_run.assert_called_once_with(slug)


def test_decline_flips_status_without_spawning_session(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes.council.project_slug", lambda: "claude-config")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        slug = _write_item(tmp_path)
        resp = client.post(f"/council/{slug}/decline", headers={"X-Capture-Token": "test-token-secret"})
    assert resp.status_code == 200


def test_approve_returns_403_when_capability_disabled(client, tmp_path):
    from app.services.capabilities import update_capability
    with patch("app.services.capabilities._capabilities_path", return_value=tmp_path / "caps.json"):
        update_capability("council_pipeline", False, actor="test")
        resp = client.post("/council/some-slug/approve", headers={"X-Capture-Token": "test-token-secret"})
    assert resp.status_code == 403
