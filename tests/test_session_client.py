import pytest
import requests as req_lib
from unittest.mock import MagicMock, patch

from app.services.session_client import (
    SessionResult,
    create_session,
    get_session_status,
    send_command,
    session_manager_url,
)


def test_create_session_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "abc"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event"):
            result = create_session(name="test", project="proj", project_dir="/tmp")
    assert result.ok is True
    assert result.session_id == "abc"
    assert result.already_running is False


def test_create_session_409_returns_already_running(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 409
    mock_resp.json.return_value = {"session": {"id": "existing"}}
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event") as mock_emit:
            result = create_session(name="test", project="proj", project_dir="/tmp")
    assert result.already_running is True
    assert result.session_id == "existing"
    assert result.ok is True
    mock_emit.assert_not_called()


def test_create_session_non_ok_returns_error(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 500
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event") as mock_emit:
            result = create_session(name="test", project="proj", project_dir="/tmp")
    assert result.ok is False
    assert "500" in result.error
    mock_emit.assert_not_called()


def test_create_session_timeout_returns_error(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.post",
               side_effect=req_lib.RequestException("timeout")):
        result = create_session(name="test", project="proj", project_dir="/tmp")
    assert result.ok is False
    assert "unreachable" in result.error


def test_create_session_emits_metric_on_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "metric-sess"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event") as mock_emit:
            create_session(name="myname", project="myproj", project_dir="/tmp")
    mock_emit.assert_called_once_with(
        "session.created",
        {"session_id": "metric-sess", "name": "myname", "project": "myproj"},
    )


def test_create_session_no_metric_on_failure(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 503
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event") as mock_emit:
            create_session(name="test", project="proj", project_dir="/tmp")
    mock_emit.assert_not_called()


def test_session_manager_url_default(monkeypatch):
    monkeypatch.delenv("SESSION_MANAGER_URL", raising=False)
    assert session_manager_url() == "http://host.docker.internal:5010"


def test_session_manager_url_env_override(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://custom:9999")
    assert session_manager_url() == "http://custom:9999"


def test_create_session_omits_model_when_none(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "abc"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp) as mock_post:
        with patch("app.services.session_client.append_event"):
            create_session(name="t", project="p", project_dir="/tmp")
    assert "model" not in mock_post.call_args.kwargs["json"]


def test_create_session_passes_model_when_set(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "abc"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp) as mock_post:
        with patch("app.services.session_client.append_event"):
            create_session(name="t", project="p", project_dir="/tmp", model="claude-fable-5")
    assert mock_post.call_args.kwargs["json"]["model"] == "claude-fable-5"


def test_send_command_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    with patch("app.services.session_client.requests.post", return_value=mock_resp) as mock_post:
        assert send_command("sess1", "hello", escape_first=True) is True
    assert mock_post.call_args.args[0] == "http://mock-sm/sessions/sess1/command"
    assert mock_post.call_args.kwargs["json"] == {"command": "hello", "escape_first": True}


def test_send_command_unreachable_returns_false(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.post",
               side_effect=req_lib.RequestException("boom")):
        assert send_command("sess1", "hello") is False


def test_get_session_status_found(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    # GET /sessions on the real session-manager returns a list of session
    # dicts (see session-manager app.py: get_sessions() -> jsonify(refreshed)
    # where refreshed is a list), not a single dict.
    mock_resp.json.return_value = [
        {"id": "other", "status": "idle"},
        {"id": "s1", "status": "active"},
    ]
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        assert get_session_status("s1") == {"id": "s1", "status": "active"}


def test_get_session_status_not_in_list(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"id": "other", "status": "idle"}]
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        assert get_session_status("s1") is None


def test_get_session_status_missing_or_down(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        assert get_session_status("nope") is None
    with patch("app.services.session_client.requests.get",
               side_effect=req_lib.RequestException("down")):
        assert get_session_status("s1") is None


from app.services.session_client import list_active_session_names


def test_list_active_session_names_filters_by_prefix_and_status(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = [
        {"name": "housekeeping-20260721", "status": "active"},
        {"name": "housekeeping-20260714", "status": "idle"},
        {"name": "blog-publish-abc", "status": "active"},
    ]
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        names = list_active_session_names("housekeeping-")
    assert names == ["housekeeping-20260721"]


def test_list_active_session_names_empty_when_none_match(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = [{"name": "blog-publish-abc", "status": "active"}]
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        assert list_active_session_names("housekeeping-") == []


def test_list_active_session_names_empty_when_unreachable(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.get",
               side_effect=req_lib.RequestException("down")):
        assert list_active_session_names("housekeeping-") == []
