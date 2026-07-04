import json
import pytest
from unittest.mock import patch, MagicMock
from app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token")
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_patch_housekeeping_heartbeat_emits_run_event(tmp_path, client, monkeypatch):
    """A heartbeat PATCH with run stats appends a housekeeping.run event."""
    vault = tmp_path / "housekeeping"
    vault.mkdir()
    (vault / "last-run.md").write_text(
        "---\nlast_run: ''\ntasks_run: ''\ntasks_failed: ''\ntasks_skipped: ''\n---\n",
        encoding="utf-8",
    )

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

    emitted = []

    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.capture.append_event", side_effect=lambda *a, **k: emitted.append((a, k)) or True):
        # Create the housekeeping directory structure for ikeos
        (tmp_path / "projects" / "ikeos" / "housekeeping").mkdir(parents=True, exist_ok=True)
        from app.services.vault import write_entry
        write_entry({
            "type": "housekeeping-heartbeat",
            "project": "ikeos",
            "title": "Last Run",
        })

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


def test_patch_housekeeping_task_does_not_emit_run_event(tmp_path, client, monkeypatch):
    """A task-level PATCH (not heartbeat) must NOT emit a housekeeping.run event."""
    token = "test-token"

    emitted = []

    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.capture.append_event", side_effect=lambda *a, **k: emitted.append((a, k)) or True):
        # Create the housekeeping directory structure for ikeos
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
