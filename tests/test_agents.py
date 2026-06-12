import pytest
from unittest.mock import patch, MagicMock


MOCK_SESSION = {
    "id": "abc123",
    "name": "test-session",
    "project": "bcr-waivers",
    "project_dir": "/mnt/c/Server/projects/bcr-waivers",
    "remote_control": False,
    "remote_control_confirmed": False,
    "autonomous_mode": False,
    "status": "active",
    "tmux_session": "test-session",
    "started_at": "2026-06-03T10:00:00",
    "message_count": 5,
    "compaction_detected": False,
    "health": "fresh",
    "last_pane_check": None,
}


def _mock_response(data, status=200):
    m = MagicMock()
    m.json.return_value = data
    m.status_code = status
    return m


def test_agents_page_renders(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert b"test-session" in resp.data


def test_agents_page_handles_manager_down(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 side_effect=Exception("connection refused"))
    resp = client.get("/agents")
    assert resp.status_code == 200  # page still renders, empty session list


def test_list_sessions_proxy(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/agents/sessions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["name"] == "test-session"


def test_create_session_proxy(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response(MOCK_SESSION, 201))
    resp = client.post("/agents/sessions", json={
        "name": "test-session",
        "project": "bcr-waivers",
        "project_dir": "/mnt/c/Server/projects/bcr-waivers",
        "remote_control": False,
    })
    assert resp.status_code == 201


def test_stop_session_proxy(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response({"ok": True}))
    resp = client.delete("/agents/sessions/abc123")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_send_command_proxy(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response({"ok": True}))
    resp = client.post("/agents/sessions/abc123/command",
                       json={"command": "/clear"})
    assert resp.status_code == 200


def test_toggle_autonomous_mode_proxy(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response({**MOCK_SESSION, "autonomous_mode": True}))
    resp = client.patch("/agents/sessions/abc123/autonomous_mode")
    assert resp.status_code == 200
    assert resp.get_json()["autonomous_mode"] is True


def test_home_page_renders(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Sessions" in resp.data


def test_home_page_has_capture_column(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/")
    assert b"cap-project" in resp.data


def test_agents_page_no_capture_column(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert b"cap-project" not in resp.data


def test_rename_session_proxy(client, mocker):
    updated = {**MOCK_SESSION, "name": "new-name"}
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response(updated))
    resp = client.post("/agents/sessions/abc123/rename", json={"name": "new-name"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "new-name"


MOCK_INFRA = {
    "containers": [
        {"Names": "traefik", "Image": "traefik:v2.10", "Status": "Up 2 days",
         "State": "running", "Ports": "0.0.0.0:80->80/tcp"},
    ],
    "machines": [
        {"name": "home-server", "host": "192.168.1.77", "reachable": True},
        {"name": "cottage", "host": "100.74.204.42", "reachable": False},
    ],
}


def test_infrastructure_page_renders(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response(MOCK_INFRA))
    resp = client.get("/status")
    assert resp.status_code == 200
    assert b"traefik" in resp.data
    assert b"home-server" in resp.data


def test_infrastructure_page_handles_manager_down(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 side_effect=Exception("connection refused"))
    resp = client.get("/status")
    assert resp.status_code == 200  # renders empty


def test_container_restart_proxy(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response({"ok": True}))
    resp = client.post("/infrastructure/containers/traefik/restart")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_nav_has_hamburger_button(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert b"nav-hamburger" in resp.data
    assert b"nav-links" in resp.data
