# tests/test_reflection.py
import json
import datetime
import pytest
from pathlib import Path
from unittest.mock import patch
from app.services.reflection import get_reflection_health, get_weak_signals, _ABRUPT_PATTERN


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


# ── get_weak_signals ──

def test_get_weak_signals_not_configured(tmp_path):
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path / "nonexistent")):
        result = get_weak_signals()
    assert result is None


def test_get_weak_signals_missing_file(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_weak_signals()
    assert result is None


def test_get_weak_signals_empty_list(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    _write_signals(lib / "weak-signals.json", [])
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_weak_signals()
    assert result == []


def test_get_weak_signals_computes_prune_and_threshold(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    today = datetime.date.today()
    fresh = today.isoformat()                                    # 0 days since, occurrences 1
    near_prune = (today - datetime.timedelta(days=44)).isoformat()  # 1 day left, occurrences 1
    overdue = (today - datetime.timedelta(days=50)).isoformat()     # past window, occurrences 1

    _write_signals(lib / "weak-signals.json", [
        {"category": "friction-point", "skill_referenced": None, "pattern": "fresh, 1 occ",
         "occurrences": 1, "first_seen": fresh, "last_seen": fresh},
        {"category": "skill-gap", "skill_referenced": "debugging", "pattern": "approaching threshold",
         "occurrences": 2, "first_seen": fresh, "last_seen": fresh},
        {"category": "rule-gap", "skill_referenced": None, "pattern": "at threshold",
         "occurrences": 3, "first_seen": fresh, "last_seen": fresh},
        {"category": "friction-point", "skill_referenced": None, "pattern": "near prune window",
         "occurrences": 1, "first_seen": near_prune, "last_seen": near_prune},
        {"category": "friction-point", "skill_referenced": None, "pattern": "overdue for prune",
         "occurrences": 1, "first_seen": overdue, "last_seen": overdue},
    ])

    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_weak_signals()

    assert result is not None
    assert len(result) == 5

    # Sorted by occurrences descending: "at threshold" (3) first
    assert result[0]["pattern"] == "at threshold"
    assert result[0]["at_threshold"] is True
    assert result[0]["approaching_threshold"] is False

    approaching = next(s for s in result if s["pattern"] == "approaching threshold")
    assert approaching["at_threshold"] is False
    assert approaching["approaching_threshold"] is True

    fresh_signal = next(s for s in result if s["pattern"] == "fresh, 1 occ")
    assert fresh_signal["days_until_prune"] == 45
    assert fresh_signal["at_threshold"] is False
    assert fresh_signal["approaching_threshold"] is False

    near_prune_signal = next(s for s in result if s["pattern"] == "near prune window")
    assert near_prune_signal["days_until_prune"] == 1

    overdue_signal = next(s for s in result if s["pattern"] == "overdue for prune")
    assert overdue_signal["days_until_prune"] == -5


def test_get_weak_signals_invalid_last_seen_date(tmp_path):
    """A malformed last_seen date must not crash; days_until_prune is None."""
    lib = tmp_path / "library"
    lib.mkdir()
    _write_signals(lib / "weak-signals.json", [
        {"category": "friction-point", "skill_referenced": None, "pattern": "bad date",
         "occurrences": 1, "first_seen": "not-a-date", "last_seen": "not-a-date"},
    ])
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_weak_signals()

    assert result is not None
    assert result[0]["days_until_prune"] is None


def test_get_weak_signals_malformed_json_returns_none(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    (lib / "weak-signals.json").write_text("not json", encoding="utf-8")
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_weak_signals()
    assert result is None
