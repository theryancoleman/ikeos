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
    mock_create.json.return_value = {"id": "sess-abc"}

    mock_cmd = MagicMock()
    mock_cmd.ok = True

    with patch("app.services.scheduler.requests.post",
               side_effect=[mock_create, mock_cmd]) as mock_post:
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result == "sess-abc"
    assert mock_post.call_count == 2
    # first call: POST /sessions
    first_url = mock_post.call_args_list[0][0][0]
    assert first_url == "http://mock-sm/sessions"
    # second call: POST /sessions/sess-abc/command
    second_url = mock_post.call_args_list[1][0][0]
    assert second_url == "http://mock-sm/sessions/sess-abc/command"
    second_body = mock_post.call_args_list[1][1]["json"]
    assert second_body["command"] == "/housekeeping — run in scheduled mode"


def test_trigger_now_session_name_starts_with_housekeeping(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.json.return_value = {"id": "sess-xyz"}
    mock_cmd = MagicMock()
    mock_cmd.ok = True

    with patch("app.services.scheduler.requests.post",
               side_effect=[mock_create, mock_cmd]) as mock_post:
        from app.services.scheduler import trigger_now
        trigger_now()

    first_body = mock_post.call_args_list[0][1]["json"]
    assert first_body["name"].startswith("housekeeping-")
    # name format: housekeeping-YYYYMMDD (8-digit date suffix)
    suffix = first_body["name"].removeprefix("housekeeping-")
    assert len(suffix) == 8
    assert suffix.isdigit()


def test_trigger_now_returns_none_on_request_error(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    import requests as req_mod
    with patch("app.services.scheduler.requests.post",
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

    with patch("app.services.scheduler.requests.post",
               return_value=mock_create):
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result is None


def test_trigger_now_returns_none_when_command_send_fails(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.json.return_value = {"id": "sess-fail-cmd"}

    mock_cmd = MagicMock()
    mock_cmd.ok = False
    mock_cmd.status_code = 500

    with patch("app.services.scheduler.requests.post",
               side_effect=[mock_create, mock_cmd]):
        from app.services.scheduler import trigger_now, get_config
        result = trigger_now()

    assert result is None
    # last_triggered must NOT be written when command fails
    config = get_config()
    assert config["last_triggered"] is None


def test_trigger_now_updates_last_triggered_in_config(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.json.return_value = {"id": "sess-ts"}
    mock_cmd = MagicMock()
    mock_cmd.ok = True

    with patch("app.services.scheduler.requests.post",
               side_effect=[mock_create, mock_cmd]):
        from app.services.scheduler import trigger_now, get_config
        trigger_now()

    config = get_config()
    assert config["last_triggered"] is not None
    assert "T" in config["last_triggered"]  # ISO datetime
