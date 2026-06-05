import pytest
import os
from unittest.mock import patch
from app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "bcr-waivers").mkdir(parents=True)
        with app.test_client() as client:
            yield client


def test_capture_get_returns_200(client):
    response = client.get("/capture")
    assert response.status_code == 200


def test_capture_get_contains_form(client):
    response = client.get("/capture")
    assert b"<form" in response.data


def test_capture_post_redirects_to_dashboard(client):
    response = client.post("/capture", data={
        "type": "note",
        "project": "bcr-waivers",
        "title": "Test note",
        "body": "Some content",
    })
    assert response.status_code == 302
    assert response.location == "/"


def test_capture_post_creates_file(client, tmp_path):
    client.post("/capture", data={
        "type": "note",
        "project": "bcr-waivers",
        "title": "Test note",
        "body": "Content",
    })
    files = list((tmp_path / "projects" / "bcr-waivers" / "notes").glob("*.md"))
    assert len(files) == 1


def test_capture_form_preselects_project_from_query_param(client):
    response = client.get("/capture?project=bcr-waivers")
    assert response.status_code == 200
    assert b'value="bcr-waivers" selected' in response.data


def test_capture_submit_stay_redirects_back_to_capture(client, tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.post(
            "/capture",
            data={
                "type": "note",
                "project": "bcr-waivers",
                "title": "Quick note",
                "body": "",
                "stay": "1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["Location"]
        assert "/capture" in location
        assert "project=bcr-waivers" in location


def test_capture_submit_without_stay_redirects_to_dashboard(client, tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.post(
            "/capture",
            data={
                "type": "note",
                "project": "bcr-waivers",
                "title": "Quick note",
                "body": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["Location"]
        assert "/capture" not in location


def test_style_css_contains_codemirror_cursor_rule(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert b"CodeMirror-cursor" in response.data


def test_capture_form_contains_stay_persistence_js(client):
    response = client.get("/capture")
    assert b"captureStay" in response.data
