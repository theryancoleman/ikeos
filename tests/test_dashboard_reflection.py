import pytest
from unittest.mock import patch
from app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token")
    app = create_app({"TESTING": True})
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        with app.test_client() as c:
            yield c


def test_dashboard_shows_reflection_health_widget(tmp_path, client):
    """When get_reflection_health() returns data, the dashboard renders the widget."""
    mock_health = {
        "active_signals": 4,
        "pending_promotion": 1,
        "acceptance_rate": 0.75,
        "last_snapshot_week": "2026-W27",
        "abrupt_endings": 2,
    }

    with patch("app.routes.browse.get_reflection_health", return_value=mock_health), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        resp = client.get("/tasks")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Reflection Health" in body
    assert "Active signals" in body
    assert ">4<" in body        # active_signals value between tags
    assert "75%" in body        # acceptance_rate rendered as percentage
    assert "2026-W27" in body   # last_snapshot_week


def test_dashboard_handles_missing_reflection_health(tmp_path, client):
    """When get_reflection_health() returns None, the dashboard renders without error."""
    with patch("app.routes.browse.get_reflection_health", return_value=None), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        resp = client.get("/tasks")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Reflection Health" not in body
