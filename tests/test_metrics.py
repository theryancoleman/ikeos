import json
import pytest
from pathlib import Path


def test_append_event_creates_file(tmp_path, monkeypatch):
    metrics_path = tmp_path / "events.jsonl"
    import app.services.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    result = metrics_mod.append_event("test.event", {"project": "myproj"})
    assert result is True
    assert metrics_path.exists()


def test_append_event_writes_valid_json(tmp_path, monkeypatch):
    metrics_path = tmp_path / "events.jsonl"
    import app.services.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    metrics_mod.append_event("test.event", {"project": "myproj", "x": 1})
    line = metrics_path.read_text().strip()
    event = json.loads(line)
    assert event["event"] == "test.event"
    assert event["project"] == "myproj"
    assert event["x"] == 1
    assert "timestamp" in event


def test_append_event_creates_nested_parent_dir(tmp_path, monkeypatch):
    metrics_path = tmp_path / "nested" / "dir" / "events.jsonl"
    import app.services.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    metrics_mod.append_event("test.event", {})
    assert metrics_path.exists()


def test_append_event_multiple_events_newline_delimited(tmp_path, monkeypatch):
    metrics_path = tmp_path / "events.jsonl"
    import app.services.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    metrics_mod.append_event("first", {"n": 1})
    metrics_mod.append_event("second", {"n": 2})
    lines = [l for l in metrics_path.read_text().splitlines() if l]
    assert len(lines) == 2
    events = [json.loads(l) for l in lines]
    assert events[0]["event"] == "first"
    assert events[1]["event"] == "second"


def test_append_event_returns_false_when_path_unwritable(tmp_path, monkeypatch):
    import app.services.metrics as metrics_mod
    # Point at an impossible path (a file used as a directory)
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a dir")
    metrics_path = blocker / "events.jsonl"
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    result = metrics_mod.append_event("test.event", {})
    assert result is False
