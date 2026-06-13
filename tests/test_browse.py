import pytest
import os
from unittest.mock import patch
from app import create_app
from app.services.vault import write_entry, read_entry, write_project_meta, _read_project_meta, _invalidate_cache


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


@pytest.fixture
def vault_with_projects(tmp_path):
    for slug, name in [("alpha", "Alpha Project"), ("beta", "Beta Project")]:
        d = tmp_path / "projects" / slug
        d.mkdir(parents=True)
        (d / "project.md").write_text(
            f"---\nname: {name}\ndescription: \nhidden: false\n---\n"
        )
    return tmp_path


@pytest.fixture
def settings_client(vault_with_projects):
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.vault.VAULT_PATH", vault_with_projects):
        with app.test_client() as c:
            yield c, vault_with_projects


def test_settings_page_renders(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        resp = client.get("/settings")
    assert resp.status_code == 200
    assert b"Alpha Project" in resp.data
    assert b"Beta Project" in resp.data


def test_settings_page_shows_slugs(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        resp = client.get("/settings")
    assert b"alpha" in resp.data
    assert b"beta" in resp.data


def test_update_project_settings_redirects(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        resp = client.post(
            "/projects/alpha/settings",
            data={"name": "Alpha Renamed", "description": "A desc", "hidden": ""},
            follow_redirects=False,
        )
    assert resp.status_code == 302


def test_update_project_settings_persists(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        client.post(
            "/projects/alpha/settings",
            data={"name": "Alpha Renamed", "description": "A new desc", "hidden": ""},
        )
        _invalidate_cache()
        meta = _read_project_meta("alpha")
    assert meta["name"] == "Alpha Renamed"
    assert meta["description"] == "A new desc"
    assert meta["hidden"] is False


def test_update_project_settings_hidden_toggle(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        client.post(
            "/projects/alpha/settings",
            data={"name": "Alpha", "description": "", "hidden": "on"},
        )
        _invalidate_cache()
        meta = _read_project_meta("alpha")
    assert meta["hidden"] is True


# ── Graph routes ──────────────────────────────────────────────────────────────

@pytest.fixture
def graph_vault(tmp_path):
    notes_dir = tmp_path / "projects" / "proj-a" / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "2026-01-01-test-note.md").write_text(
        "---\ntype: note\ntitle: Test Note\nproject: proj-a\n"
        "status: open\ncreated: 2026-01-01T10:00:00\n"
        "updated: 2026-01-01T10:00:00\ntags: [documentation]\n---\n"
        "## Description\nContent\n"
    )
    return tmp_path


@pytest.fixture
def graph_client(graph_vault):
    from app.services.vault import _invalidate_cache
    _invalidate_cache()
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.vault.VAULT_PATH", graph_vault):
        with app.test_client() as client:
            yield client


def test_graph_page_renders(graph_client):
    response = graph_client.get("/graph")
    assert response.status_code == 200
    assert b"Graph" in response.data


def test_api_graph_returns_json(graph_client):
    from app.services.vault import _invalidate_cache
    _invalidate_cache()
    response = graph_client.get("/api/graph")
    assert response.status_code == 200
    data = response.get_json()
    assert "nodes" in data
    assert "links" in data
    assert "health" in data
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "2026-01-01-test-note"
    assert data["nodes"][0]["project"] == "proj-a"


def test_project_page_filters_by_component(client, tmp_path, monkeypatch):
    """?component= param filters entries to that component only."""
    import yaml
    from unittest.mock import patch

    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.dump({"ikeos": {"name": "IkeOS", "components": ["voice-bridge", "display"]}}))

    import app.services.umbrella as u
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "ikeos").mkdir(parents=True)

    bugs_dir = tmp_path / "projects" / "ikeos" / "bugs"
    bugs_dir.mkdir(parents=True)
    (bugs_dir / "2026-06-13-bug-a.md").write_text(
        "---\ntype: bug\ntitle: VB Bug\nproject: ikeos\ncomponent: voice-bridge\n"
        "status: new\ncreated: 2026-06-13T10:00:00\ntags: [bug]\n---\n## Description\nA\n"
    )
    (bugs_dir / "2026-06-13-bug-b.md").write_text(
        "---\ntype: bug\ntitle: Display Bug\nproject: ikeos\ncomponent: display\n"
        "status: new\ncreated: 2026-06-13T11:00:00\ntags: [bug]\n---\n## Description\nB\n"
    )

    with patch("app.services.umbrella._REGISTRY_PATH", reg):
        u._registry = None
        resp = client.get("/projects/ikeos?component=voice-bridge")

    assert resp.status_code == 200
    assert b"VB Bug" in resp.data
    assert b"Display Bug" not in resp.data


def test_project_page_shows_component_pills_for_umbrella(client, tmp_path, monkeypatch):
    """Project page renders component pill links when components are defined."""
    import yaml
    from unittest.mock import patch

    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.dump({"ikeos": {"name": "IkeOS", "components": ["voice-bridge"]}}))

    import app.services.umbrella as u
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "ikeos").mkdir(parents=True)

    with patch("app.services.umbrella._REGISTRY_PATH", reg):
        u._registry = None
        resp = client.get("/projects/ikeos")

    assert resp.status_code == 200
    assert b"voice-bridge" in resp.data
