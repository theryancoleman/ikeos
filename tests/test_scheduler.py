import json
import pytest
from pathlib import Path


@pytest.fixture
def sched_vault(tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    return tmp_path


def _hk_dir(vault) -> Path:
    return vault / "projects" / "claude-config" / "housekeeping"


# ── get_config ──

def test_get_config_returns_defaults_when_no_file(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import get_config
    config = get_config()
    assert config["enabled"] is False
    assert config["day_of_week"] == "sun"
    assert config["hour"] == 3
    assert config["minute"] == 7
    assert config["last_triggered"] is None


def test_get_config_reads_existing_file(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    schedule_file = _hk_dir(sched_vault) / "schedule.json"
    schedule_file.write_text(json.dumps({
        "enabled": True, "day_of_week": "mon", "hour": 4, "minute": 15,
        "last_triggered": "2026-06-16T04:15:00"
    }))
    from app.services.scheduler import get_config
    config = get_config()
    assert config["enabled"] is True
    assert config["day_of_week"] == "mon"
    assert config["hour"] == 4
    assert config["minute"] == 15
    assert config["last_triggered"] == "2026-06-16T04:15:00"


def test_get_config_fills_missing_keys_with_defaults(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    schedule_file = _hk_dir(sched_vault) / "schedule.json"
    schedule_file.write_text(json.dumps({"enabled": True}))
    from app.services.scheduler import get_config
    config = get_config()
    assert config["enabled"] is True
    assert config["day_of_week"] == "sun"
    assert config["hour"] == 3


# ── update_config ──

def test_update_config_writes_merged_fields(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config
    result = update_config({"hour": 5, "minute": 30})
    assert result["hour"] == 5
    assert result["minute"] == 30
    assert result["day_of_week"] == "sun"  # default preserved
    # file was written
    written = json.loads((_hk_dir(sched_vault) / "schedule.json").read_text())
    assert written["hour"] == 5
    assert written["minute"] == 30


def test_update_config_rejects_invalid_day_of_week(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config
    with pytest.raises(ValueError, match="day_of_week"):
        update_config({"day_of_week": "xyz"})


def test_update_config_rejects_invalid_hour(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config
    with pytest.raises(ValueError, match="hour"):
        update_config({"hour": 24})


def test_update_config_rejects_invalid_minute(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config
    with pytest.raises(ValueError, match="minute"):
        update_config({"minute": 60})


from unittest.mock import patch, MagicMock
from app.services.session_client import SessionResult


# ── trigger_now ──

def test_trigger_now_returns_session_id_on_success(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    ok_result = SessionResult(session_id="sess-abc")
    with patch("app.services.scheduler.run_scheduled_housekeeping", return_value=ok_result):
        from app.services.scheduler import trigger_now
        result = trigger_now()
    assert result == "sess-abc"


def test_trigger_now_updates_last_triggered_in_config(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    ok_result = SessionResult(session_id="sess-ts")
    with patch("app.services.scheduler.run_scheduled_housekeeping", return_value=ok_result):
        from app.services.scheduler import trigger_now, get_config
        trigger_now()
    config = get_config()
    assert config["last_triggered"] is not None
    assert "T" in config["last_triggered"]


def test_trigger_now_returns_none_on_failure(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    err_result = SessionResult(session_id="", error="Session manager unreachable")
    with patch("app.services.scheduler.run_scheduled_housekeeping", return_value=err_result):
        from app.services.scheduler import trigger_now
        result = trigger_now()
    assert result is None


# ── _job capability gate ──

def test_job_skips_trigger_when_capability_disabled(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    # No capabilities.json → disabled by default
    with patch("app.services.scheduler.trigger_now") as mock_trigger:
        from app.services.scheduler import _job
        _job()
    mock_trigger.assert_not_called()


def test_job_calls_trigger_when_capability_enabled(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    cap_file = _hk_dir(sched_vault) / "capabilities.json"
    import json as _json
    cap_file.write_text(_json.dumps({"housekeeping_scheduler": {"enabled": True}}))
    with patch("app.services.scheduler.trigger_now") as mock_trigger:
        from app.services.scheduler import _job
        _job()
    mock_trigger.assert_called_once()


# ── start() multi-worker guard ──

def test_start_skips_when_scheduler_already_running(sched_vault, monkeypatch):
    """Second call to start() does not replace the running scheduler."""
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    import app.services.scheduler as sched_mod

    mock_sched = MagicMock()
    mock_sched.running = True
    original = sched_mod._scheduler
    sched_mod._scheduler = mock_sched
    try:
        fake_app = MagicMock()
        fake_app.config = {}
        from app.services.scheduler import start
        start(fake_app)
        assert sched_mod._scheduler is mock_sched
    finally:
        sched_mod._scheduler = original


def test_start_logs_warning_when_already_running(sched_vault, monkeypatch, caplog):
    """Second call to start() logs a warning about the duplicate start."""
    import logging
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    import app.services.scheduler as sched_mod

    mock_sched = MagicMock()
    mock_sched.running = True
    original = sched_mod._scheduler
    sched_mod._scheduler = mock_sched
    try:
        fake_app = MagicMock()
        fake_app.config = {}
        with caplog.at_level(logging.WARNING, logger="app.services.scheduler"):
            from app.services.scheduler import start
            start(fake_app)
        assert "already running" in caplog.text.lower()
    finally:
        sched_mod._scheduler = original


# ── leader election lock ──

def test_acquire_leader_lock_only_one_of_two_concurrent_attempts_succeeds(tmp_path):
    """Simulates two gunicorn workers racing for the lock file: only the
    first non-blocking flock attempt should succeed."""
    from app.services.scheduler import _acquire_leader_lock

    lock_path = tmp_path / "scheduler.lock"
    worker_a = _acquire_leader_lock(lock_path)
    worker_b = _acquire_leader_lock(lock_path)
    try:
        assert worker_a is not None
        assert worker_b is None
    finally:
        if worker_a is not None:
            worker_a.close()
        if worker_b is not None:
            worker_b.close()


def test_acquire_leader_lock_releases_on_close(tmp_path):
    """Once the leader's fd is closed (process exit/crash), a new worker
    can win the lock."""
    from app.services.scheduler import _acquire_leader_lock

    lock_path = tmp_path / "scheduler.lock"
    worker_a = _acquire_leader_lock(lock_path)
    assert worker_a is not None
    worker_a.close()

    worker_b = _acquire_leader_lock(lock_path)
    try:
        assert worker_b is not None
    finally:
        if worker_b is not None:
            worker_b.close()


# ── next_run consistency across workers ──

def test_next_run_consistent_after_reschedule_regardless_of_worker(sched_vault, monkeypatch):
    """After update_config() runs on one 'worker' (no live scheduler here,
    simulating a non-leader), get_config_with_next_run() — as served by any
    worker's GET handler — must report the same, correct next_run."""
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config, get_config_with_next_run

    update_config({"enabled": True, "day_of_week": "mon", "hour": 4, "minute": 30})

    first = get_config_with_next_run()
    second = get_config_with_next_run()
    assert first["next_run"] is not None
    assert first["next_run"] == second["next_run"]

    from datetime import datetime
    next_run_dt = datetime.fromisoformat(first["next_run"])
    assert next_run_dt.weekday() == 0  # Monday
    assert next_run_dt.hour == 4
    assert next_run_dt.minute == 30


def test_next_run_none_when_disabled(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config, get_config_with_next_run

    update_config({"enabled": False, "day_of_week": "mon", "hour": 4, "minute": 30})
    assert get_config_with_next_run()["next_run"] is None


# ── trigger_now works regardless of leader election ──

def test_trigger_now_works_when_scheduler_is_none(sched_vault, monkeypatch):
    """Simulates a non-leader worker (no live APScheduler instance) still
    being able to serve 'Run Now' by calling trigger_now() directly."""
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    import app.services.scheduler as sched_mod

    original = sched_mod._scheduler
    sched_mod._scheduler = None
    try:
        ok_result = SessionResult(session_id="sess-non-leader")
        with patch("app.services.scheduler.run_scheduled_housekeeping", return_value=ok_result):
            from app.services.scheduler import trigger_now
            result = trigger_now()
        assert result == "sess-non-leader"
    finally:
        sched_mod._scheduler = original
