import pytest
import os
from unittest.mock import patch
from app import create_app
from app.services.vault import write_entry, read_entry


@pytest.fixture
def vault(tmp_path):
    proj = tmp_path / "projects" / "bcr-waivers" / "notes"
    proj.mkdir(parents=True)
    (proj / "2026-05-26-test-note.md").write_text(
        "---\ntype: note\ntitle: Test note\nproject: bcr-waivers\n"
        "status: new\ncreated: 2026-05-26T10:00:00\ntags: [note]\n---\n"
        "## Description\nContent\n"
    )
    return tmp_path


@pytest.fixture
def client(vault):
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.vault.VAULT_PATH", vault):
        with app.test_client() as client:
            yield client


def test_tasks_page_renders(client):
    response = client.get("/tasks")
    assert response.status_code == 200


def test_tasks_page_shows_entry_title(client):
    response = client.get("/tasks")
    assert b"Test note" in response.data


def test_project_view_returns_200(client):
    response = client.get("/projects/bcr-waivers")
    assert response.status_code == 200


def test_project_view_shows_entry(client):
    response = client.get("/projects/bcr-waivers")
    assert b"Test note" in response.data


def test_entry_view_returns_200(client):
    response = client.get("/projects/bcr-waivers/2026-05-26-test-note")
    assert response.status_code == 200


def test_entry_view_shows_content(client):
    response = client.get("/projects/bcr-waivers/2026-05-26-test-note")
    assert b"Test note" in response.data


def test_entry_view_404_for_missing(client):
    response = client.get("/projects/bcr-waivers/nonexistent")
    assert response.status_code == 404


def test_post_update_status_redirects(client, vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        slug = write_entry({
            "type": "idea", "project": "bcr-waivers", "title": "Update me",
            "body": "", "priority": "medium", "effort": "medium",
        })
        response = client.post(
            f"/projects/bcr-waivers/{slug}/status",
            data={"status": "open"},
            follow_redirects=False,
        )
        assert response.status_code == 302


def test_post_update_status_persists_to_vault(client, vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        slug = write_entry({
            "type": "idea", "project": "bcr-waivers", "title": "Update me",
            "body": "", "priority": "medium", "effort": "medium",
        })
        client.post(
            f"/projects/bcr-waivers/{slug}/status",
            data={"status": "done"},
        )
        entry = read_entry("bcr-waivers", slug)
        assert entry["status"] == "done"
