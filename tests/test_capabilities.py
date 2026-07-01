import json
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def cap_vault(tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    return tmp_path


def _hk_dir(vault) -> Path:
    return vault / "projects" / "claude-config" / "housekeeping"


# ── get_capabilities ──

def test_get_capabilities_returns_defaults_when_no_file(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    caps = caps_mod.get_capabilities()
    assert "housekeeping_scheduler" in caps
    assert caps["housekeeping_scheduler"]["enabled"] is False
    assert caps["housekeeping_scheduler"]["enabled_by"] is None
    assert caps["housekeeping_scheduler"]["enabled_at"] is None


def test_get_capabilities_reads_existing_file(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    cap_file.write_text(json.dumps({
        "housekeeping_scheduler": {
            "enabled": True,
            "enabled_by": "architect",
            "enabled_at": "2026-07-01T10:00:00+00:00",
            "description": "Scheduled weekly housekeeping runs via session manager",
        }
    }))
    import app.services.capabilities as caps_mod
    caps = caps_mod.get_capabilities()
    assert caps["housekeeping_scheduler"]["enabled"] is True
    assert caps["housekeeping_scheduler"]["enabled_by"] == "architect"


def test_get_capabilities_merges_with_defaults_for_missing_keys(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    cap_file.write_text(json.dumps({"housekeeping_scheduler": {"enabled": True}}))
    import app.services.capabilities as caps_mod
    caps = caps_mod.get_capabilities()
    assert caps["housekeeping_scheduler"]["enabled"] is True
    assert "description" in caps["housekeeping_scheduler"]


def test_get_capabilities_returns_defaults_on_corrupt_file(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    cap_file.write_text("not json {{{")
    import app.services.capabilities as caps_mod
    caps = caps_mod.get_capabilities()
    assert caps["housekeeping_scheduler"]["enabled"] is False


# ── is_enabled ──

def test_is_enabled_false_by_default(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    assert caps_mod.is_enabled("housekeeping_scheduler") is False


def test_is_enabled_true_when_file_says_enabled(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    cap_file.write_text(json.dumps({"housekeeping_scheduler": {"enabled": True}}))
    import app.services.capabilities as caps_mod
    assert caps_mod.is_enabled("housekeeping_scheduler") is True


def test_is_enabled_false_for_unknown_capability(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    assert caps_mod.is_enabled("nonexistent_capability") is False


# ── update_capability ──

def test_update_capability_enables_and_writes_file(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with patch("app.services.capabilities.append_event"):
        record = caps_mod.update_capability("housekeeping_scheduler", True)
    assert record["enabled"] is True
    assert record["enabled_by"] == "architect"
    assert record["enabled_at"] is not None
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    assert cap_file.exists()
    saved = json.loads(cap_file.read_text())
    assert saved["housekeeping_scheduler"]["enabled"] is True


def test_update_capability_disable_clears_actor_and_timestamp(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with patch("app.services.capabilities.append_event"):
        caps_mod.update_capability("housekeeping_scheduler", True)
        record = caps_mod.update_capability("housekeeping_scheduler", False)
    assert record["enabled"] is False
    assert record["enabled_by"] is None
    assert record["enabled_at"] is None


def test_update_capability_emits_enabled_event(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with patch("app.services.capabilities.append_event") as mock_emit:
        caps_mod.update_capability("housekeeping_scheduler", True)
    mock_emit.assert_called_once_with(
        "capability.enabled",
        {"capability": "housekeeping_scheduler", "actor": "architect"},
    )


def test_update_capability_emits_disabled_event(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with patch("app.services.capabilities.append_event") as mock_emit:
        caps_mod.update_capability("housekeeping_scheduler", False)
    mock_emit.assert_called_once_with(
        "capability.disabled",
        {"capability": "housekeeping_scheduler", "actor": "architect"},
    )


def test_update_capability_raises_for_unknown_name(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with pytest.raises(ValueError, match="Unknown capability"):
        caps_mod.update_capability("nonexistent", True)
