import pytest
from unittest.mock import patch
from app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token")
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _capture_emitted():
    """Return (emitted list, side_effect fn) for patching append_event."""
    emitted = []

    def _side_effect(*a, **k):
        emitted.append((a, k))
        return True

    return emitted, _side_effect


def test_patch_housekeeping_heartbeat_emits_run_event(tmp_path, client):
    """A heartbeat PATCH with run stats appends a housekeeping.run event."""
    token = "test-token"
    payload = {
        "project": "ikeos",
        "type": "housekeeping-heartbeat",
        "filename": "last-run.md",
        "fields": {
            "last_run": "2026-07-04T12:00:00",
            "tasks_run": "4",
            "tasks_failed": "1",
            "tasks_skipped": "0",
        },
    }

    emitted, side_effect = _capture_emitted()

    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.capture.append_event", side_effect=side_effect):
        (tmp_path / "projects" / "ikeos" / "housekeeping").mkdir(parents=True, exist_ok=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "ikeos", "title": "Last Run"})

        resp = client.patch(
            "/entries/housekeeping",
            json=payload,
            headers={"X-Capture-Token": token},
        )

    assert resp.status_code == 200
    assert len(emitted) == 1
    event_type, event_payload = emitted[0][0]
    assert event_type == "housekeeping.run"
    assert event_payload["tasks_run"] == 4
    assert event_payload["tasks_failed"] == 1
    assert event_payload["tasks_skipped"] == 0
    assert event_payload["trigger"] == "scheduled"


def test_patch_housekeeping_heartbeat_non_numeric_fields_emit_zeros(tmp_path, client):
    """Non-numeric tasks_run/failed/skipped values are safely coerced to 0."""
    token = "test-token"
    payload = {
        "project": "ikeos",
        "type": "housekeeping-heartbeat",
        "filename": "last-run.md",
        "fields": {
            "last_run": "2026-07-04T12:00:00",
            "tasks_run": "N/A",
            "tasks_failed": "abc",
            "tasks_skipped": None,
        },
    }

    emitted, side_effect = _capture_emitted()

    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.capture.append_event", side_effect=side_effect):
        (tmp_path / "projects" / "ikeos" / "housekeeping").mkdir(parents=True, exist_ok=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "ikeos", "title": "Last Run"})

        resp = client.patch(
            "/entries/housekeeping",
            json=payload,
            headers={"X-Capture-Token": token},
        )

    assert resp.status_code == 200
    assert len(emitted) == 1
    _, event_payload = emitted[0][0]
    assert event_payload["tasks_run"] == 0
    assert event_payload["tasks_failed"] == 0
    assert event_payload["tasks_skipped"] == 0


def test_patch_housekeeping_heartbeat_invalid_trigger_coerced(tmp_path, client):
    """An unknown trigger value is coerced to 'scheduled'."""
    token = "test-token"
    payload = {
        "project": "ikeos",
        "type": "housekeeping-heartbeat",
        "filename": "last-run.md",
        "fields": {
            "last_run": "2026-07-04T12:00:00",
            "tasks_run": "2",
            "trigger": "INVALID_TRIGGER",
        },
    }

    emitted, side_effect = _capture_emitted()

    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.capture.append_event", side_effect=side_effect):
        (tmp_path / "projects" / "ikeos" / "housekeeping").mkdir(parents=True, exist_ok=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "ikeos", "title": "Last Run"})

        resp = client.patch(
            "/entries/housekeeping",
            json=payload,
            headers={"X-Capture-Token": token},
        )

    assert resp.status_code == 200
    _, event_payload = emitted[0][0]
    assert event_payload["trigger"] == "scheduled"


def test_patch_housekeeping_task_does_not_emit_run_event(tmp_path, client):
    """A task-level PATCH (not heartbeat) must NOT emit a housekeeping.run event."""
    token = "test-token"
    emitted, side_effect = _capture_emitted()

    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.capture.append_event", side_effect=side_effect):
        (tmp_path / "projects" / "ikeos" / "housekeeping").mkdir(parents=True, exist_ok=True)
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "ikeos",
            "title": "My task",
            "interval": "weekly",
            "success_definition": "Done",
        })

        payload = {
            "project": "ikeos",
            "type": "housekeeping-task",
            "filename": slug,
            "fields": {"last_run": "2026-07-04T12:00:00", "consecutive_failures": 0},
        }

        resp = client.patch(
            "/entries/housekeeping",
            json=payload,
            headers={"X-Capture-Token": token},
        )

    assert resp.status_code == 200
    assert len(emitted) == 0


def test_housekeeping_page_renders_recent_runs_without_error(tmp_path, monkeypatch):
    """GET /housekeeping with a non-empty metrics file must render without UndefinedError."""
    import json
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps({"event": "housekeeping.run", "tasks_run": 2, "tasks_failed": 1,
                    "tasks_skipped": 0, "trigger": "manual",
                    "timestamp": "2026-07-04T10:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token")
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.metrics.METRICS_PATH", events_file), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        with app.test_client() as c:
            resp = c.get("/housekeeping")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Recent Runs" in body
    assert "manual" in body
    assert "2026-07-04" in body


def test_housekeeping_context_includes_recent_runs(tmp_path):
    """_housekeeping_context() must include recent_runs list from metrics."""
    import json
    from app.routes.housekeeping import _housekeeping_context

    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps({"event": "housekeeping.run", "tasks_run": 3, "tasks_failed": 0,
                    "tasks_skipped": 0, "trigger": "scheduled",
                    "timestamp": "2026-07-04T10:00:00+00:00"}) + "\n" +
        json.dumps({"event": "session.created", "project": "ikeos",
                    "timestamp": "2026-07-04T09:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    with patch("app.services.metrics.METRICS_PATH", events_file), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.housekeeping.CAPTURE_TOKEN", "tok"), \
         patch("app.routes.housekeeping.get_config_with_next_run", return_value={}), \
         patch("app.routes.housekeeping.latest_draft_name", return_value=None), \
         patch("app.routes.housekeeping.latest_review_name", return_value=None), \
         patch("app.routes.housekeeping.get_capabilities", return_value=[]):
        ctx = _housekeeping_context()

    assert "recent_runs" in ctx
    runs = ctx["recent_runs"]
    assert len(runs) == 1
    assert runs[0]["event"] == "housekeeping.run"
    assert runs[0]["tasks_run"] == 3
