# tests/test_reflection.py
import json
import datetime
import pytest
from pathlib import Path
from unittest.mock import patch
from app.services.reflection import get_reflection_health, _ABRUPT_PATTERN


def _write_signals(path: Path, signals: list) -> None:
    path.write_text(json.dumps({"signals": signals}), encoding="utf-8")


def _write_metrics(path: Path, snapshots: list) -> None:
    path.write_text(json.dumps({"snapshots": snapshots}), encoding="utf-8")


def test_get_reflection_health_happy_path(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    today = datetime.date.today()
    recent = (today - datetime.timedelta(days=10)).isoformat()
    old = (today - datetime.timedelta(days=50)).isoformat()

    _write_signals(lib / "weak-signals.json", [
        {"pattern": "A", "last_seen": recent, "occurrences": 4},
        {"pattern": "B", "last_seen": recent, "occurrences": 1},
        {"pattern": "C", "last_seen": old, "occurrences": 5},   # outside 45-day window
        {"pattern": _ABRUPT_PATTERN, "last_seen": recent, "occurrences": 3},
    ])
    _write_metrics(lib / "metrics.json", [
        {"week": "2026-W26", "reflection_acceptance_rate": 0.6},
        {"week": "2026-W27", "reflection_acceptance_rate": 0.8},
    ])

    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_reflection_health()

    assert result is not None
    assert result["active_signals"] == 3       # A, B, abrupt (old C excluded)
    assert result["pending_promotion"] == 2    # A (4 occ) + abrupt (3 occ)
    assert result["acceptance_rate"] == pytest.approx(0.8)
    assert result["last_snapshot_week"] == "2026-W27"
    assert result["abrupt_endings"] == 3


def test_get_reflection_health_missing_dir(tmp_path):
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path / "nonexistent")):
        result = get_reflection_health()
    assert result is None


def test_get_reflection_health_missing_files(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    # No files written
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_reflection_health()
    assert result is None


def test_get_reflection_health_no_snapshots(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    today = datetime.date.today()
    recent = (today - datetime.timedelta(days=5)).isoformat()
    _write_signals(lib / "weak-signals.json", [
        {"pattern": "X", "last_seen": recent, "occurrences": 1},
    ])
    _write_metrics(lib / "metrics.json", [])

    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_reflection_health()

    assert result is not None
    assert result["acceptance_rate"] is None
    assert result["last_snapshot_week"] is None
    assert result["abrupt_endings"] == 0


def test_get_reflection_health_abrupt_signal_missing_occurrences_key(tmp_path):
    """Abrupt signal with no 'occurrences' key must not crash (KeyError guard)."""
    lib = tmp_path / "library"
    lib.mkdir()
    today = datetime.date.today()
    recent = (today - datetime.timedelta(days=5)).isoformat()
    _write_signals(lib / "weak-signals.json", [
        {"pattern": _ABRUPT_PATTERN, "last_seen": recent},  # no occurrences key
    ])
    _write_metrics(lib / "metrics.json", [])

    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_reflection_health()

    assert result is not None
    assert result["abrupt_endings"] == 0


def test_get_reflection_health_non_dict_json_returns_none(tmp_path):
    """JSON files with a list root (not a dict) must return None without crashing."""
    lib = tmp_path / "library"
    lib.mkdir()
    (lib / "weak-signals.json").write_text("[1, 2, 3]", encoding="utf-8")
    (lib / "metrics.json").write_text('{"snapshots": []}', encoding="utf-8")

    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_reflection_health()

    assert result is None
