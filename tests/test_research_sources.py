import pytest
import requests as req_lib
from unittest.mock import MagicMock, patch

from app.services.session_client import (
    ResearchSourceResult,
    ResearchSourcesResult,
    add_research_source,
    list_research_sources,
    toggle_research_source,
)


# ── service: session_client research-source functions ──

def test_list_research_sources_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"sources": [{"url": "https://a.com", "label": "A", "id": "abc"}]}
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        result = list_research_sources()
    assert result.ok is True
    assert result.sources == [{"url": "https://a.com", "label": "A", "id": "abc"}]


def test_list_research_sources_unreachable(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.get",
               side_effect=req_lib.RequestException("boom")):
        result = list_research_sources()
    assert result.ok is False
    assert "unreachable" in result.error


def test_list_research_sources_non_ok(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 500
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        result = list_research_sources()
    assert result.ok is False
    assert "500" in result.error


def test_add_research_source_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"url": "https://a.com", "label": "A", "id": "abc"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp) as mock_post:
        result = add_research_source(url="https://a.com", label="A")
    assert result.ok is True
    assert result.source["id"] == "abc"
    assert mock_post.call_args.kwargs["json"] == {"url": "https://a.com", "label": "A"}


def test_add_research_source_conflict(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 409
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        result = add_research_source(url="https://a.com", label="A")
    assert result.ok is False
    assert "already exists" in result.error


def test_add_research_source_unreachable(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.post",
               side_effect=req_lib.RequestException("boom")):
        result = add_research_source(url="https://a.com", label="A")
    assert result.ok is False
    assert "unreachable" in result.error


def test_toggle_research_source_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"url": "https://a.com", "label": "A", "id": "abc", "blacklisted": True}
    with patch("app.services.session_client.requests.patch", return_value=mock_resp) as mock_patch:
        result = toggle_research_source("abc")
    assert result.ok is True
    assert result.source["blacklisted"] is True
    assert mock_patch.call_args.args[0] == "http://mock-sm/research-sources/abc"


def test_toggle_research_source_not_found(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    with patch("app.services.session_client.requests.patch", return_value=mock_resp):
        result = toggle_research_source("nope")
    assert result.ok is False
    assert "not found" in result.error


def test_toggle_research_source_unreachable(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.patch",
               side_effect=req_lib.RequestException("boom")):
        result = toggle_research_source("abc")
    assert result.ok is False
    assert "unreachable" in result.error


# ── route: GET /research-sources ──

def test_page_renders_with_mocked_source_list(client):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "sources": [
            {
                "url": "https://example.com/blog",
                "label": "Example Blog",
                "status": "active",
                "blacklisted": False,
                "last_fetched": "2026-07-10",
                "entries_generated": 3,
                "added": "2026-06-01",
                "id": "abc123",
            }
        ]
    }
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        resp = client.get("/research-sources")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Example Blog" in body
    assert "https://example.com/blog" in body
    assert "Active" in body


def test_page_shows_blocked_status_from_blacklisted_field(client):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "sources": [
            {
                "url": "https://blocked.com",
                "label": "Blocked Source",
                "status": "active",
                "blacklisted": True,
                "last_fetched": None,
                "entries_generated": 0,
                "added": "2026-06-01",
                "id": "def456",
            }
        ]
    }
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        resp = client.get("/research-sources")
    body = resp.data.decode()
    assert "Blocked" in body
    assert "Unblock" in body


def test_page_service_unreachable_renders_gracefully(client):
    with patch("app.services.session_client.requests.get",
               side_effect=req_lib.RequestException("boom")):
        resp = client.get("/research-sources")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Can&#39;t reach the research-source management service." in body or \
        "Can't reach the research-source management service." in body


# ── route: POST /research-sources ──

def test_add_source_form_submission_calls_post(client):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"url": "https://new.com", "label": "New", "id": "xyz"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp) as mock_post:
        resp = client.post("/research-sources", data={"url": "https://new.com", "label": "New"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["ok"] is True
    assert mock_post.call_args.kwargs["json"] == {"url": "https://new.com", "label": "New"}


def test_add_source_missing_fields_returns_400(client):
    resp = client.post("/research-sources", data={"url": "", "label": ""})
    assert resp.status_code == 400


def test_add_source_unreachable_returns_502(client):
    with patch("app.services.session_client.requests.post",
               side_effect=req_lib.RequestException("boom")):
        resp = client.post("/research-sources", data={"url": "https://new.com", "label": "New"})
    assert resp.status_code == 502


# ── route: POST /research-sources/<id>/toggle ──

def test_toggle_button_calls_patch(client):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"url": "https://a.com", "label": "A", "id": "abc", "blacklisted": True}
    with patch("app.services.session_client.requests.patch", return_value=mock_resp) as mock_patch:
        resp = client.post("/research-sources/abc/toggle")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert mock_patch.call_args.args[0] == "http://host.docker.internal:5010/research-sources/abc"


def test_toggle_not_found_returns_404(client):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    with patch("app.services.session_client.requests.patch", return_value=mock_resp):
        resp = client.post("/research-sources/nope/toggle")
    assert resp.status_code == 404


def test_toggle_unreachable_returns_502(client):
    with patch("app.services.session_client.requests.patch",
               side_effect=req_lib.RequestException("boom")):
        resp = client.post("/research-sources/abc/toggle")
    assert resp.status_code == 502
