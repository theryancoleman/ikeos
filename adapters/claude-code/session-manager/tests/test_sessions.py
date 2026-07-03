import threading
import pytest
from unittest.mock import patch


@pytest.fixture
def tmp_sessions_file(tmp_path):
    f = tmp_path / "sessions.json"
    return f


@pytest.fixture(autouse=True)
def patch_sessions_file(tmp_sessions_file):
    with patch("sessions.SESSIONS_FILE", tmp_sessions_file):
        yield


from sessions import (
    list_sessions, get_session, create_session, update_session, remove_session
)


def test_list_sessions_empty():
    assert list_sessions() == []


def test_create_session_returns_record():
    s = create_session("test", "my-project", "/home/user/projects/my-project")
    assert s["name"] == "test"
    assert s["project"] == "my-project"
    assert s["status"] == "active"
    assert s["remote_control"] is False
    assert s["remote_control_confirmed"] is False
    assert s["message_count"] == 0
    assert s["compaction_detected"] is False
    assert s["autonomous_mode"] is False
    assert "id" in s
    assert "started_at" in s


def test_create_session_persists():
    create_session("test", "proj", "/dir")
    assert len(list_sessions()) == 1


def test_get_session_returns_none_for_unknown():
    assert get_session("nonexistent") is None


def test_get_session_finds_by_id():
    s = create_session("test", "proj", "/dir")
    found = get_session(s["id"])
    assert found["name"] == "test"


def test_update_session():
    s = create_session("test", "proj", "/dir")
    updated = update_session(s["id"], status="stopped", message_count=5)
    assert updated["status"] == "stopped"
    assert updated["message_count"] == 5


def test_update_session_unknown_returns_none():
    assert update_session("bad-id", status="stopped") is None


def test_remove_session():
    s = create_session("test", "proj", "/dir")
    result = remove_session(s["id"])
    assert result is True
    assert list_sessions() == []


def test_remove_session_unknown_returns_false():
    assert remove_session("bad-id") is False


def test_create_session_ephemeral_defaults_false():
    s = create_session("test", "proj", "/dir")
    assert s["ephemeral"] is False


def test_create_session_ephemeral_true():
    s = create_session("test", "proj", "/dir", ephemeral=True)
    assert s["ephemeral"] is True


def test_concurrent_create_sessions_both_persist():
    """Both sessions must be saved when created concurrently."""
    results = []
    def create():
        s = create_session(f"session-{threading.current_thread().name}", "proj", "/dir")
        results.append(s["id"])

    threads = [threading.Thread(target=create, name=f"t{i}") for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    saved = list_sessions()
    assert len(saved) == 5, f"Expected 5 sessions, got {len(saved)}"
    assert len(set(results)) == 5, "Duplicate session IDs created"
