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
