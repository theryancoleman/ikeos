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


# ── trigger_now ──

def test_trigger_now_creates_session_and_sends_command(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.status_code = 200
    mock_create.json.return_value = {"id": "sess-abc"}

    with patch("app.services.session_client.requests.post", return_value=mock_create) as mock_post:
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result == "sess-abc"
    assert mock_post.call_count == 1
    call = mock_post.call_args_list[0]
    assert call[0][0] == "http://mock-sm/sessions"
    body = call[1]["json"]
    assert body["initial_command"] == "/housekeeping — run in scheduled mode"


def test_trigger_now_session_name_starts_with_housekeeping(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.status_code = 200
    mock_create.json.return_value = {"id": "sess-xyz"}

    with patch("app.services.session_client.requests.post",
               return_value=mock_create) as mock_post:
        from app.services.scheduler import trigger_now
        trigger_now()

    first_body = mock_post.call_args_list[0][1]["json"]
    assert first_body["name"].startswith("housekeeping-")
    suffix = first_body["name"].removeprefix("housekeeping-")
    assert len(suffix) == 8
    assert suffix.isdigit()


def test_trigger_now_returns_none_on_request_error(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    import requests as req_mod
    with patch("app.services.session_client.requests.post",
               side_effect=req_mod.RequestException("timeout")):
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result is None


def test_trigger_now_returns_none_when_session_create_fails(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = False
    mock_create.status_code = 503

    with patch("app.services.session_client.requests.post",
               return_value=mock_create):
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result is None


def test_trigger_now_returns_session_id_on_success(sched_vault, monkeypatch):
    """trigger_now returns the session ID once the session is created and
    last_triggered is persisted to the schedule config."""
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.status_code = 200
    mock_create.json.return_value = {"id": "sess-fail-cmd"}

    with patch("app.services.session_client.requests.post", return_value=mock_create):
        from app.services.scheduler import trigger_now, get_config
        result = trigger_now()

    assert result == "sess-fail-cmd"
    config = get_config()
    assert config["last_triggered"] is not None


def test_trigger_now_updates_last_triggered_in_config(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.status_code = 200
    mock_create.json.return_value = {"id": "sess-ts"}

    with patch("app.services.session_client.requests.post",
               return_value=mock_create):
        from app.services.scheduler import trigger_now, get_config
        trigger_now()

    config = get_config()
    assert config["last_triggered"] is not None
    assert "T" in config["last_triggered"]  # ISO datetime


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
