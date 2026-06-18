import pytest
import requests
from pathlib import Path
from unittest.mock import patch, MagicMock
from unittest.mock import patch as mock_patch
from datetime import datetime, timedelta


@pytest.fixture
def hk_vault(tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    return tmp_path


def _write_task(folder, filename, interval="weekly", enabled="true",
                last_run="null", consecutive_failures="0"):
    (folder / filename).write_text(
        f"---\n"
        f"type: housekeeping-task\n"
        f"title: {filename}\n"
        f"project: claude-config\n"
        f"interval: {interval}\n"
        f"enabled: '{enabled}'\n"
        f"last_run: '{last_run}'\n"
        f"last_error: 'null'\n"
        f"consecutive_failures: '{consecutive_failures}'\n"
        f"---\n"
    )


def _write_heartbeat(folder, last_run="null", tasks_run="0",
                     tasks_failed="0", tasks_skipped="0"):
    (folder / "last-run.md").write_text(
        f"---\n"
        f"type: housekeeping-heartbeat\n"
        f"last_run: '{last_run}'\n"
        f"tasks_run: '{tasks_run}'\n"
        f"tasks_failed: '{tasks_failed}'\n"
        f"tasks_skipped: '{tasks_skipped}'\n"
        f"---\n"
    )


# ── read_housekeeping_tasks ──

def test_read_housekeeping_tasks_empty_when_no_folder(tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import read_housekeeping_tasks
        assert read_housekeeping_tasks("claude-config") == []


def test_read_housekeeping_tasks_returns_tasks(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    _write_task(folder, "2026-06-17-prune-vault.md")
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_tasks
        tasks = read_housekeeping_tasks("claude-config")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "2026-06-17-prune-vault.md"
    assert tasks[0]["filename"] == "2026-06-17-prune-vault"
    assert "status" in tasks[0]
    assert "next_run" in tasks[0]


def test_read_housekeeping_tasks_skips_heartbeat(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    _write_heartbeat(folder)
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_tasks
        tasks = read_housekeeping_tasks("claude-config")
    assert tasks == []


def test_read_housekeeping_tasks_skips_non_task_types(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    (folder / "other.md").write_text(
        "---\ntype: idea\ntitle: Other\nproject: claude-config\n---\n"
    )
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_tasks
        tasks = read_housekeeping_tasks("claude-config")
    assert tasks == []


# ── read_housekeeping_heartbeat ──

def test_read_housekeeping_heartbeat_missing_file_returns_defaults(tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import read_housekeeping_heartbeat
        hb = read_housekeeping_heartbeat("claude-config")
    assert hb["last_run"] is None
    assert hb["tasks_run"] == "0"
    assert hb["tasks_failed"] == "0"
    assert hb["tasks_skipped"] == "0"


def test_read_housekeeping_heartbeat_reads_file(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    _write_heartbeat(folder, last_run="2026-06-14T12:00:00",
                     tasks_run="5", tasks_failed="1", tasks_skipped="2")
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_heartbeat
        hb = read_housekeeping_heartbeat("claude-config")
    assert hb["last_run"] == "2026-06-14T12:00:00"
    assert hb["tasks_run"] == "5"
    assert hb["tasks_failed"] == "1"
    assert hb["tasks_skipped"] == "2"


def test_read_housekeeping_heartbeat_null_string_becomes_none(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    _write_heartbeat(folder, last_run="null")
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_heartbeat
        hb = read_housekeeping_heartbeat("claude-config")
    assert hb["last_run"] is None


# ── _compute_task_status ──

def test_compute_task_status_disabled():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        task = {"enabled": "false", "consecutive_failures": "0",
                "last_run": "null", "interval": "weekly"}
        assert _compute_task_status(task) == "disabled"


def test_compute_task_status_error():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        task = {"enabled": "true", "consecutive_failures": "2",
                "last_run": "2026-06-16T12:00:00", "interval": "weekly"}
        assert _compute_task_status(task) == "error"


def test_compute_task_status_uninitialized_monthly():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": "null", "interval": "monthly"}
        assert _compute_task_status(task) == "uninitialized"


def test_compute_task_status_due_weekly_no_last_run():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": "null", "interval": "weekly"}
        assert _compute_task_status(task) == "due"


def test_compute_task_status_due():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        last_run = (datetime.now() - timedelta(days=7)).isoformat()
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": last_run, "interval": "weekly"}
        assert _compute_task_status(task) == "due"


def test_compute_task_status_overdue():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        last_run = (datetime.now() - timedelta(days=12)).isoformat()
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": last_run, "interval": "weekly"}
        assert _compute_task_status(task) == "overdue"


def test_compute_task_status_ok():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        last_run = (datetime.now() - timedelta(days=2)).isoformat()
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": last_run, "interval": "weekly"}
        assert _compute_task_status(task) == "ok"


# ── _compute_next_run ──

def test_compute_next_run_null_returns_none():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_next_run
        task = {"last_run": "null", "interval": "weekly"}
        assert _compute_next_run(task) is None


def test_compute_next_run_weekly():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_next_run
        task = {"last_run": "2026-06-10T12:00:00", "interval": "weekly"}
        result = _compute_next_run(task)
        assert result == "2026-06-16"  # 2026-06-10 + 6 days


# ── Route tests ──

def test_housekeeping_index_renders(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"Housekeeping" in resp.data


def test_housekeeping_index_shows_tasks(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    folder = tmp_path / "projects" / "claude-config" / "housekeeping"
    folder.mkdir(parents=True)
    _write_task(folder, "2026-06-17-prune-vault.md")
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"2026-06-17-prune-vault" in resp.data


def test_housekeeping_index_empty_state(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"No tasks" in resp.data


# ── Write route tests ──

def test_create_task_success(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"ok": True}

    with mock_patch("app.routes.housekeeping.requests.post", return_value=mock_resp):
        resp = client.post("/housekeeping/tasks", data={
            "title": "Prune old entries",
            "interval": "weekly",
            "success_definition": "All entries older than 90 days removed.",
        })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_create_task_missing_title_returns_400(client):
    resp = client.post("/housekeeping/tasks", data={
        "interval": "weekly",
        "success_definition": "Done.",
    })
    assert resp.status_code == 400


def test_create_task_missing_success_definition_returns_400(client):
    resp = client.post("/housekeeping/tasks", data={
        "title": "Test task",
        "interval": "weekly",
    })
    assert resp.status_code == 400


def test_toggle_task_disables(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    folder = tmp_path / "projects" / "claude-config" / "housekeeping"
    folder.mkdir(parents=True)
    _write_task(folder, "2026-06-17-test-task.md", enabled="true")

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"message": "Updated"}

    with mock_patch("app.routes.housekeeping.requests.patch", return_value=mock_resp):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/toggle")
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] == "false"


def test_toggle_task_enables(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    folder = tmp_path / "projects" / "claude-config" / "housekeeping"
    folder.mkdir(parents=True)
    _write_task(folder, "2026-06-17-test-task.md", enabled="false")

    mock_resp = MagicMock()
    mock_resp.ok = True

    with mock_patch("app.routes.housekeeping.requests.patch", return_value=mock_resp):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/toggle")
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] == "true"


def test_toggle_task_not_found_returns_404(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)
    resp = client.post("/housekeeping/tasks/nonexistent-task/toggle")
    assert resp.status_code == 404


def test_reset_task_success(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    mock_resp = MagicMock()
    mock_resp.ok = True

    with mock_patch("app.routes.housekeeping.requests.patch", return_value=mock_resp):
        resp = client.post("/housekeeping/tasks/2026-06-17-some-task/reset")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_run_task_creates_session(client):
    create_mock = MagicMock()
    create_mock.ok = True
    create_mock.json.return_value = {"id": "session-abc123"}

    cmd_mock = MagicMock()
    cmd_mock.ok = True

    with mock_patch("app.routes.housekeeping.requests.post",
                    side_effect=[create_mock, cmd_mock]):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/run")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["session_id"] == "session-abc123"


def test_run_task_session_manager_unreachable(client):
    with mock_patch("app.routes.housekeeping.requests.post",
                    side_effect=requests.RequestException("timeout")):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/run")
    assert resp.status_code == 502
