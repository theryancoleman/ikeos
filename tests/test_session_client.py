import pytest
import requests as req_lib
from unittest.mock import MagicMock, patch

from app.services.session_client import SessionResult, create_session


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
