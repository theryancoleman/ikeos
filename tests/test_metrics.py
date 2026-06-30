import json
import pytest
from pathlib import Path
from unittest.mock import patch


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


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


def test_metrics_view_returns_200(client):
    with patch("app.services.metrics.METRICS_PATH", Path("/nonexistent/events.jsonl")):
        resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_view_shows_events(client, tmp_path):
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps({"event": "housekeeping.trigger", "timestamp": "2026-06-30T03:07:00+00:00",
                    "session_id": "abc123", "project": "claude-config", "trigger": "scheduled"}) + "\n" +
        json.dumps({"event": "housekeeping.trigger", "timestamp": "2026-06-29T03:07:00+00:00",
                    "session_id": "def456", "project": "claude-config", "trigger": "scheduled"}) + "\n"
    )
    with patch("app.services.metrics.METRICS_PATH", events_file):
        resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.data.decode()
    assert "housekeeping.trigger" in data
    assert "abc123" in data


def test_metrics_view_empty_when_no_file(client, tmp_path):
    with patch("app.services.metrics.METRICS_PATH", tmp_path / "missing.jsonl"):
        resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_event_post_requires_auth(client):
    resp = client.post("/metrics/event",
                       json={"event": "test.event", "session_id": "x"},
                       content_type="application/json")
    assert resp.status_code in (401, 503)


def test_metrics_event_post_appends_event(client, tmp_path, monkeypatch):
    import app.routes.agents as agents_mod
    monkeypatch.setattr(agents_mod, "CAPTURE_TOKEN", "tok")
    events_file = tmp_path / "events.jsonl"
    with patch("app.services.metrics.METRICS_PATH", events_file):
        resp = client.post(
            "/metrics/event",
            json={"event": "agent.session_start", "session_id": "s1"},
            content_type="application/json",
            headers={"X-Capture-Token": "tok"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    lines = events_file.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "agent.session_start"
    assert "timestamp" in record
