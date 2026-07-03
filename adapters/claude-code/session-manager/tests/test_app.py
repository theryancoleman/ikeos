import pytest
import json
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# First call returns False (session not yet alive during create), then True for all
# subsequent calls (session is running). Tests that need a "stopped" session reset
# has_session to return_value=False after creation rather than using this constant.
_HAS_SESSION_SIDE_EFFECT = [False] + [True] * 20


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("sessions.SESSIONS_FILE", tmp_path / "sessions.json")
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_get_sessions_empty(client, mocker):
    mocker.patch("app.has_session", return_value=False)
    mocker.patch("app.capture_pane", return_value="")
    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_create_session(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=False)
    mocker.patch("app.threading.Thread")
    resp = client.post("/sessions", json={
        "name": "test-session",
        "project": "my-proj",
        "project_dir": "/mnt/c/Server/projects/my-proj",
        "remote_control": False,
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "test-session"
    assert data["status"] == "active"


def test_create_session_with_remote_control(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=False)
    mocker.patch("app.threading.Thread")
    resp = client.post("/sessions", json={
        "name": "rc-session",
        "project": "proj",
        "project_dir": "/dir",
        "remote_control": True,
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["remote_control"] is True


def test_create_session_rc_dialog_dismissed(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=False)
    mocker.patch("app.threading.Thread")
    resp = client.post("/sessions", json={
        "name": "rc-session", "project": "proj", "project_dir": "/dir",
        "remote_control": True,
    })
    assert resp.status_code == 201


def test_create_session_startup_thread_spawned(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=False)
    mock_thread = mocker.patch("app.threading.Thread")
    client.post("/sessions", json={
        "name": "startup-test",
        "project": "proj",
        "project_dir": "/dir",
    })
    mock_thread.assert_called_once()
    kwargs = mock_thread.call_args.kwargs
    assert kwargs["daemon"] is True
    assert kwargs["target"].__name__ == "_run_session_startup"


def test_create_session_with_initial_command_sets_ephemeral(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=False)
    mocker.patch("app.threading.Thread")
    resp = client.post("/sessions", json={
        "name": "hk-session",
        "project": "claude-config",
        "project_dir": "/dir",
        "initial_command": "/housekeeping — run in scheduled mode",
    })
    assert resp.status_code == 201
    assert resp.get_json()["ephemeral"] is True


def test_create_session_without_initial_command_not_ephemeral(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=False)
    mocker.patch("app.threading.Thread")
    resp = client.post("/sessions", json={
        "name": "normal-session",
        "project": "proj",
        "project_dir": "/dir",
    })
    assert resp.status_code == 201
    assert resp.get_json()["ephemeral"] is False


def test_stop_session(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    mocker.patch("app.kill_session")
    create_resp = client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False
    })
    sid = create_resp.get_json()["id"]
    resp = client.delete(f"/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_stop_session_404(client):
    resp = client.delete("/sessions/nonexistent")
    assert resp.status_code == 404


def test_toggle_remote_control(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False
    })
    sid = create_resp.get_json()["id"]
    mocker.patch("app.send_command")
    mocker.patch("app.time.sleep")
    mocker.patch("app.capture_pane", return_value="Remote control enabled\n")
    resp = client.patch(f"/sessions/{sid}/remote_control")
    assert resp.status_code == 200
    assert resp.get_json()["remote_control"] is True
    assert resp.get_json()["remote_control_confirmed"] is True


def test_send_command_clear_resets_counters(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False
    })
    from sessions import list_sessions, update_session
    sid = create_resp.get_json()["id"]
    update_session(sid, message_count=30, compaction_detected=True)
    mocker.patch("app.send_command")
    resp = client.post(f"/sessions/{sid}/command", json={"command": "/clear"})
    assert resp.status_code == 200
    from sessions import get_session
    s = get_session(sid)
    assert s["message_count"] == 0
    assert s["compaction_detected"] is False


def test_refresh_sets_activity(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="✻ Razzmatazzing… (1s)\n")
    client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False,
    })
    resp = client.get("/sessions")
    assert resp.get_json()[0]["activity"] == "thinking"


def test_refresh_reinjects_auto_on_compaction(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False,
    })
    from sessions import list_sessions, update_session
    sid = create_resp.get_json()["id"]
    update_session(sid, autonomous_mode=True, compaction_detected=False)

    send_mock = mocker.patch("app.send_command")
    mocker.patch("app.capture_pane", return_value="Your context has been compacted")

    resp = client.get("/sessions")
    assert resp.status_code == 200
    send_mock.assert_called_once_with("s1", "/auto")

    from sessions import get_session
    s = get_session(sid)
    assert s["compaction_detected"] is True


def test_refresh_no_reinject_if_already_compacted(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False,
    })
    from sessions import list_sessions, update_session
    sid = create_resp.get_json()["id"]
    update_session(sid, autonomous_mode=True, compaction_detected=True)

    send_mock = mocker.patch("app.send_command")
    mocker.patch("app.capture_pane", return_value="Your context has been compacted")

    client.get("/sessions")
    send_mock.assert_not_called()


def test_refresh_no_reinject_if_autonomous_mode_off(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False,
    })
    from sessions import list_sessions, update_session
    sid = create_resp.get_json()["id"]
    update_session(sid, autonomous_mode=False, compaction_detected=False)

    send_mock = mocker.patch("app.send_command")
    mocker.patch("app.capture_pane", return_value="Your context has been compacted")

    client.get("/sessions")
    send_mock.assert_not_called()


def test_toggle_autonomous_mode_on(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False,
    })
    sid = create_resp.get_json()["id"]

    send_mock = mocker.patch("app.send_command")
    resp = client.patch(f"/sessions/{sid}/autonomous_mode")
    assert resp.status_code == 200
    assert resp.get_json()["autonomous_mode"] is True
    send_mock.assert_called_once_with("s1", "/auto")


def test_toggle_autonomous_mode_off(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "s1", "project": "p", "project_dir": "/d", "remote_control": False,
    })
    from sessions import list_sessions, update_session
    sid = create_resp.get_json()["id"]
    update_session(sid, autonomous_mode=True)

    send_mock = mocker.patch("app.send_command")
    resp = client.patch(f"/sessions/{sid}/autonomous_mode")
    assert resp.status_code == 200
    assert resp.get_json()["autonomous_mode"] is False
    send_mock.assert_not_called()


def test_toggle_autonomous_mode_404(client):
    resp = client.patch("/sessions/nonexistent/autonomous_mode")
    assert resp.status_code == 404


def test_get_pane_not_found(client):
    resp = client.get("/sessions/nonexistent-id/pane")
    assert resp.status_code == 404


def test_get_pane_stopped_session(client, mocker):
    mocker.patch("app.launch_session")
    mock_has = mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "pane-stopped", "project": "proj",
        "project_dir": "/dir", "remote_control": False,
    })
    sid = create_resp.get_json()["id"]
    mock_has.side_effect = [False] * 20
    resp = client.get(f"/sessions/{sid}/pane")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["active"] is False
    assert data["lines"] == []


def test_get_pane_active_session(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="alpha\nbeta\ngamma")
    create_resp = client.post("/sessions", json={
        "name": "pane-active", "project": "proj",
        "project_dir": "/dir", "remote_control": False,
    })
    sid = create_resp.get_json()["id"]
    resp = client.get(f"/sessions/{sid}/pane")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["active"] is True
    assert data["lines"] == ["alpha", "beta", "gamma"]


def test_get_pane_truncates_to_40_lines(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    fifty_lines = "\n".join(f"line{i}" for i in range(50))
    mocker.patch("app.capture_pane", return_value=fifty_lines)
    create_resp = client.post("/sessions", json={
        "name": "pane-trunc", "project": "proj",
        "project_dir": "/dir", "remote_control": False,
    })
    sid = create_resp.get_json()["id"]
    resp = client.get(f"/sessions/{sid}/pane")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["lines"]) == 40
    assert data["lines"][0] == "line10"
    assert data["lines"][-1] == "line49"


def test_rename_session(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.capture_pane", return_value="")
    mocker.patch("app.threading.Timer")
    create_resp = client.post("/sessions", json={
        "name": "old-name", "project": "p", "project_dir": "/d", "remote_control": False,
    })
    sid = create_resp.get_json()["id"]

    send_mock = mocker.patch("app.send_command")
    resp = client.post(f"/sessions/{sid}/rename", json={"name": "new-name"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "new-name"
    send_mock.assert_called_once_with("old-name", "/rename new-name")


def test_rename_session_stopped_skips_send(client, mocker):
    # Deliberately uses return_value=False (not _HAS_SESSION_SIDE_EFFECT) to simulate
    # a session that is stopped: has_session always returns False, so the app never
    # considers the session alive and the rename should skip sending the /rename command.
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=False)
    mocker.patch("app.capture_pane", return_value="")
    mocker.patch("app.threading.Timer")
    client.post("/sessions", json={
        "name": "old-name", "project": "p", "project_dir": "/d", "remote_control": False,
    })
    from sessions import list_sessions
    sid = list_sessions()[0]["id"]

    send_mock = mocker.patch("app.send_command")
    resp = client.post(f"/sessions/{sid}/rename", json={"name": "new-name"})
    assert resp.status_code == 200
    send_mock.assert_not_called()


def test_rename_session_404(client):
    resp = client.post("/sessions/nonexistent/rename", json={"name": "x"})
    assert resp.status_code == 404


def test_get_infrastructure(client, mocker):
    mocker.patch("app._list_docker_containers", return_value=[
        {"Names": "traefik", "Image": "traefik:v2.10", "Status": "Up 2 days", "State": "running", "Ports": "0.0.0.0:80->80/tcp"},
    ])
    mocker.patch("app._check_machines", return_value=[
        {"name": "home-server", "host": "192.168.1.100", "reachable": True},
    ])
    resp = client.get("/infrastructure")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["containers"]) == 1
    assert data["containers"][0]["Names"] == "traefik"
    assert len(data["machines"]) == 1
    assert data["machines"][0]["reachable"] is True


def test_container_restart(client, mocker):
    run_mock = mocker.patch("app.subprocess.run")
    run_mock.return_value = MagicMock(returncode=0, stderr="")
    resp = client.post("/infrastructure/containers/traefik/restart")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    run_mock.assert_called_once_with(
        ["bash", "-c", "docker.exe restart traefik"],
        capture_output=True, text=True, timeout=30
    )


def test_container_restart_rejects_invalid_name(client):
    resp = client.post("/infrastructure/containers/../etc/restart")
    assert resp.status_code in (400, 404)


def test_container_stop(client, mocker):
    run_mock = mocker.patch("app.subprocess.run")
    run_mock.return_value = MagicMock(returncode=0, stderr="")
    resp = client.post("/infrastructure/containers/traefik/stop")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_container_start(client, mocker):
    run_mock = mocker.patch("app.subprocess.run")
    run_mock.return_value = MagicMock(returncode=0, stderr="")
    resp = client.post("/infrastructure/containers/traefik/start")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_send_slash_command_always_uses_thread_via_send_prompt(client, mocker):
    """The /command endpoint always dispatches via a thread with send_prompt now."""
    import sessions
    s = sessions.create_session("thread-test", "proj", "/dir")
    session_id = s["id"]

    mocker.patch("app.has_session", return_value=True)
    mocker.patch("app.capture_pane", return_value="")
    mock_thread = mocker.patch("app.threading.Thread")

    resp = client.post(f"/sessions/{session_id}/command",
                       json={"command": "/triage"})
    assert resp.status_code == 200
    mock_thread.assert_called_once()
    assert mock_thread.call_args.kwargs["daemon"] is True


def test_create_session_fires_metric_event(client, mocker):
    """agent.session_start fires when a session is created."""
    mock_has = mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.launch_session")
    mocker.patch("app.threading.Thread")
    metric_mock = mocker.patch("app._post_metric")
    resp = client.post("/sessions", json={
        "name": "test-session", "project": "myproject",
        "project_dir": "/dir",
    })
    assert resp.status_code == 201
    metric_mock.assert_called_once_with(
        "agent.session_start",
        {"session_id": resp.get_json()["id"], "project": "myproject", "name": "test-session"},
    )


def test_remove_session_fires_metric_event(client, mocker):
    """agent.session_end fires when a session is explicitly removed."""
    mock_has = mocker.patch("app.has_session", side_effect=_HAS_SESSION_SIDE_EFFECT)
    mocker.patch("app.launch_session")
    mocker.patch("app.threading.Thread")
    metric_mock = mocker.patch("app._post_metric")
    create_resp = client.post("/sessions", json={
        "name": "test-session", "project": "myproject",
        "project_dir": "/dir",
    })
    sid = create_resp.get_json()["id"]
    metric_mock.reset_mock()

    mocker.patch("app.kill_session")
    mock_has.side_effect = [True] + [False] * 20
    resp = client.delete(f"/sessions/{sid}/remove")
    assert resp.status_code == 200
    metric_mock.assert_called_once_with(
        "agent.session_end",
        {"session_id": sid, "project": "myproject", "name": "test-session"},
    )


def test_wait_for_completion_removes_session_when_idle_after_working(mocker):
    import app as app_module
    mocker.patch("app.time.sleep")
    # Phase 1: deadline=0+300=300; loop check monotonic=5 < 300, so inside loop
    # Phase 1: activity="working" → break out of phase 1
    # Phase 2: deadline=5+7200; loop check monotonic=10 < 7205, so inside loop
    # Phase 2: activity="idle" → kill + remove
    mocker.patch("app.time.monotonic", side_effect=[0.0, 5.0, 5.0, 10.0])
    mocker.patch("app.has_session", return_value=True)
    mocker.patch("app.capture_pane", return_value="pane")
    mocker.patch("app.parse_activity", side_effect=["working", "idle"])
    mock_kill = mocker.patch("app.kill_session")
    mock_remove = mocker.patch("app.remove_session")

    app_module._wait_for_completion_and_remove("hk-session", "session-id-123")

    mock_kill.assert_called_once_with("hk-session")
    mock_remove.assert_called_once_with("session-id-123")
