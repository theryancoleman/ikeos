from unittest.mock import MagicMock, patch


def test_evals_page_renders(client):
    with patch("app.routes.evals.read_last_run", return_value=None):
        resp = client.get("/evals")
    assert resp.status_code == 200


def test_run_requires_capability_enabled(client, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    with patch("app.routes.evals.is_enabled", return_value=False):
        resp = client.post("/evals/run", headers={"X-Capture-Token": "tok"})
    assert resp.status_code == 403


def test_run_triggers_session_when_enabled(client, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    mock_result = MagicMock(session_id="abc123", already_running=False, ok=True)
    with patch("app.routes.evals.is_enabled", return_value=True), \
         patch("app.routes.evals.run_eval_suite", return_value=mock_result):
        resp = client.post("/evals/run", headers={"X-Capture-Token": "tok"})
    assert resp.status_code == 200
    assert resp.get_json()["session_id"] == "abc123"


def test_run_requires_capture_token(client, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    resp = client.post("/evals/run")
    assert resp.status_code == 401
