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
