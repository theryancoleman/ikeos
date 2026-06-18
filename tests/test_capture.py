import pytest
import os
import hashlib
from unittest.mock import patch
from app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "bcr-waivers").mkdir(parents=True)
        with app.test_client() as client:
            yield client


@pytest.fixture
def client_no_token(tmp_path):
    """Client fixture with no CAPTURE_TOKEN env var."""
    os.environ.pop("CAPTURE_TOKEN", None)
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
    assert response.location == "/tasks"


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


# ============= Decision type support tests =============

def test_capture_post_decision_creates_file_in_decisions(client, tmp_path):
    """POST /capture with type=decision should create file in vault root decisions/."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        client.post("/capture", data={
            "type": "decision",
            "title": "Use PostgreSQL",
            "body": "Performance reasons",
        })
    files = list((tmp_path / "decisions").glob("*.md"))
    assert len(files) == 1


def test_capture_post_decision_without_project(client, tmp_path):
    """POST /capture with type=decision should work without project field."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.post("/capture", data={
            "type": "decision",
            "title": "Test decision",
            "body": "Some context",
        }, follow_redirects=False)
    assert response.status_code == 302
    assert response.location == "/tasks"


def test_capture_post_decision_with_optional_project(client, tmp_path):
    """POST /capture with type=decision can include optional project field."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        client.post("/capture", data={
            "type": "decision",
            "project": "bcr-waivers",
            "title": "Test decision with project",
            "body": "Context",
        })
    files = list((tmp_path / "decisions").glob("*.md"))
    assert len(files) == 1
    import frontmatter
    post = frontmatter.load(files[0])
    assert post.metadata.get("project") == "bcr-waivers"


def test_capture_post_decision_has_correct_frontmatter(client, tmp_path):
    """Decision entries should have correct initial frontmatter."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        client.post("/capture", data={
            "type": "decision",
            "title": "Use Postgres",
            "body": "For scalability",
        })
    files = list((tmp_path / "decisions").glob("*.md"))
    import frontmatter
    post = frontmatter.load(files[0])
    assert post.metadata["type"] == "decision"
    assert post.metadata["status"] == "proposed"
    assert "status/proposed" in post.metadata["tags"]
    assert post.metadata["title"] == "Use Postgres"


def test_capture_post_decision_body_structure(client, tmp_path):
    """Decision entry body should have Context/Decision/Consequences sections."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        client.post("/capture", data={
            "type": "decision",
            "title": "ADR-001",
            "body": "Scale the database",
        })
    files = list((tmp_path / "decisions").glob("*.md"))
    import frontmatter
    post = frontmatter.load(files[0])
    assert "## Context" in post.content
    assert "## Decision" in post.content
    assert "## Consequences" in post.content


# ============= PATCH /entries endpoint tests =============

def test_patch_entries_requires_token(client, tmp_path):
    """PATCH /entries without token should return 401."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.patch("/entries", json={
            "project": "bcr-waivers",
            "type": "bug",
            "filename": "2026-06-11-test-bug",
            "status": "open",
        })
    assert response.status_code == 401


def test_patch_entries_with_correct_token(client, tmp_path):
    """PATCH /entries with correct token should update status."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        # First create an entry
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "bug",
            "project": "bcr-waivers",
            "title": "Test bug",
            "body": "Description",
            "severity": "medium",
        })
        # Now update its status
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "bug",
                "filename": slug,
                "status": "open",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 200
    data = response.get_json()
    assert "Status updated" in data.get("message", "")


def test_patch_entries_wrong_token_returns_401(client, tmp_path):
    """PATCH /entries with wrong token should return 401."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "bug",
                "filename": "test",
                "status": "open",
            },
            headers={"X-Capture-Token": "wrong-token"}
        )
    assert response.status_code == 401


def test_patch_entries_missing_token_env_returns_503(client_no_token, tmp_path):
    """PATCH /entries without CAPTURE_TOKEN env should return 503."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client_no_token.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "bug",
                "filename": "test",
                "status": "open",
            },
            headers={"X-Capture-Token": "any-token"}
        )
    assert response.status_code == 503


def test_patch_entries_form_data(client, tmp_path):
    """PATCH /entries should accept form data in addition to JSON."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "idea",
            "project": "bcr-waivers",
            "title": "Test idea",
            "body": "Description",
            "priority": "high",
            "effort": "small",
        })
        response = client.patch("/entries",
            data={
                "project": "bcr-waivers",
                "type": "idea",
                "filename": slug,
                "status": "in-progress",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 200


def test_patch_entries_invalid_status(client, tmp_path):
    """PATCH /entries with invalid status should return 400."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "note",
            "project": "bcr-waivers",
            "title": "Test note",
            "body": "Description",
        })
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "note",
                "filename": slug,
                "status": "not-a-valid-status",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 400


def test_patch_entries_missing_entry(client, tmp_path):
    """PATCH /entries for non-existent entry should return 404."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "bug",
                "filename": "nonexistent-slug",
                "status": "open",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 404


def test_patch_entries_invalid_type(client, tmp_path):
    """PATCH /entries with invalid type should return 400."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "invalid-type",
                "filename": "test",
                "status": "open",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 400


def test_patch_entries_path_traversal_rejection(client, tmp_path):
    """PATCH /entries should reject filenames with path traversal patterns."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "bug",
                "filename": "../../etc/passwd",
                "status": "open",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 400


def test_patch_entries_path_traversal_double_dot(client, tmp_path):
    """PATCH /entries should reject filenames with .. patterns."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "bug",
                "filename": "test..md",
                "status": "open",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 400


def test_patch_entries_status_tag_updated(client, tmp_path):
    """PATCH /entries should update the status/* tag correctly."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import write_entry, read_entry
        slug = write_entry({
            "type": "bug",
            "project": "bcr-waivers",
            "title": "Test bug",
            "body": "Description",
            "severity": "medium",
        })
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "bug",
                "filename": slug,
                "status": "done",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
        assert response.status_code == 200
        entry = read_entry("bcr-waivers", slug)
        assert entry["status"] == "done"
        assert "status/done" in entry["tags"]
        assert "status/new" not in entry["tags"]


def test_patch_entries_body_byte_identical(client, tmp_path):
    """PATCH /entries should preserve body content exactly (byte-identical)."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "note",
            "project": "bcr-waivers",
            "title": "Test note",
            "body": "Original body with special chars: éàü\nMultiple lines\n  Indentation",
        })
        # Get original file content's body hash
        note_path = tmp_path / "projects" / "bcr-waivers" / "notes" / f"{slug}.md"
        import frontmatter
        original_post = frontmatter.load(note_path)
        original_body = original_post.content

        # Update status
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "note",
                "filename": slug,
                "status": "done",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
        assert response.status_code == 200

        # Verify body is unchanged
        updated_post = frontmatter.load(note_path)
        assert updated_post.content == original_body


def test_patch_entries_updated_field_added(client, tmp_path):
    """PATCH /entries should add/update the 'updated' field."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import write_entry, read_entry
        slug = write_entry({
            "type": "bug",
            "project": "bcr-waivers",
            "title": "Test bug",
            "body": "Description",
            "severity": "medium",
        })
        response = client.patch("/entries",
            json={
                "project": "bcr-waivers",
                "type": "bug",
                "filename": slug,
                "status": "open",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
        assert response.status_code == 200
        entry = read_entry("bcr-waivers", slug)
        assert "updated" in entry


def test_patch_entries_decision_type(client, tmp_path):
    """PATCH /entries should support decision type with decision/* tags."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import write_entry, read_entry
        slug = write_entry({
            "type": "decision",
            "title": "Use PostgreSQL",
            "body": "For scalability",
        })
        response = client.patch("/entries",
            json={
                "type": "decision",
                "filename": slug,
                "status": "accepted",
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 200


def test_patch_entries_decision_valid_statuses(client, tmp_path):
    """PATCH /entries for decisions should only accept valid decision statuses."""
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "decision",
            "title": "Use PostgreSQL",
            "body": "For scalability",
        })
        # Try to set invalid status for decision type
        response = client.patch("/entries",
            json={
                "type": "decision",
                "filename": slug,
                "status": "open",  # This is task status, not decision status
            },
            headers={"X-Capture-Token": "test-token-secret"}
        )
    assert response.status_code == 400  # Invalid status for decision lifecycle


def test_capture_json_note(client, mocker):
    mock_write = mocker.patch("app.routes.capture.write_entry")
    resp = client.post(
        "/capture/json",
        json={"type": "note", "project": "bcr-waivers", "title": "Test note"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    call_data = mock_write.call_args[0][0]
    assert call_data["type"] == "note"
    assert call_data["project"] == "bcr-waivers"
    assert call_data["title"] == "Test note"


def test_capture_json_missing_title_returns_400(client):
    resp = client.post(
        "/capture/json",
        json={"type": "note", "project": "bcr-waivers"},
    )
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_capture_json_missing_project_returns_400(client):
    resp = client.post(
        "/capture/json",
        json={"type": "note", "title": "Test"},
    )
    assert resp.status_code == 400


def test_capture_json_invalid_type_returns_400(client):
    resp = client.post(
        "/capture/json",
        json={"type": "decision", "project": "bcr-waivers", "title": "Test"},
    )
    assert resp.status_code == 400


def test_capture_json_idea_includes_priority_effort(client, mocker):
    mock_write = mocker.patch("app.routes.capture.write_entry")
    resp = client.post(
        "/capture/json",
        json={
            "type": "idea",
            "project": "bcr-waivers",
            "title": "Test idea",
            "priority": "high",
            "effort": "low",
        },
    )
    assert resp.status_code == 200
    call_data = mock_write.call_args[0][0]
    assert call_data["priority"] == "high"
    assert call_data["effort"] == "low"


# ============= Umbrella component tests =============

def test_capture_form_includes_components_for_umbrella(client, tmp_path, monkeypatch):
    """Form context includes component list for projects with components."""
    import yaml
    from pathlib import Path
    from unittest.mock import patch

    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.dump({"ikeos": {"name": "IkeOS", "components": ["voice-bridge"]}}))

    import app.services.umbrella as u
    import app.services.vault as v
    u._registry = None
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "ikeos").mkdir(parents=True)

    with patch("app.services.umbrella._REGISTRY_PATH", reg):
        u._registry = None
        resp = client.get("/capture?project=ikeos")

    assert resp.status_code == 200
    assert b"voice-bridge" in resp.data


def test_capture_submit_stores_component(client, tmp_path, monkeypatch):
    """POST /capture with component stores component field in vault entry."""
    import yaml
    from pathlib import Path
    from unittest.mock import patch
    import frontmatter as fm_lib

    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.dump({"ikeos": {"name": "IkeOS", "components": ["voice-bridge"]}}))

    import app.services.umbrella as u
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "ikeos").mkdir(parents=True)

    with patch("app.services.umbrella._REGISTRY_PATH", reg):
        u._registry = None
        resp = client.post("/capture", data={
            "type": "note",
            "project": "ikeos",
            "component": "voice-bridge",
            "title": "Test note",
            "body": "Body",
        }, follow_redirects=True)

    assert resp.status_code == 200
    files = list((tmp_path / "projects" / "ikeos" / "notes").glob("*.md"))
    assert len(files) == 1
    post = fm_lib.load(files[0])
    assert post.metadata.get("component") == "voice-bridge"


def test_capture_json_stores_component(client, tmp_path, monkeypatch):
    """POST /capture/json with component stores component field."""
    import frontmatter as fm_lib
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "ikeos").mkdir(parents=True)

    resp = client.post("/capture/json", json={
        "type": "note",
        "project": "ikeos",
        "component": "voice-bridge",
        "title": "JSON note",
        "body": "Body",
    })
    assert resp.status_code == 200

    files = list((tmp_path / "projects" / "ikeos" / "notes").glob("*.md"))
    assert len(files) == 1
    post = fm_lib.load(files[0])
    assert post.metadata.get("component") == "voice-bridge"


# ============= grill-me type support tests =============

def test_patch_entries_accepts_grill_me_type(client, tmp_path, monkeypatch):
    """PATCH /entries should accept grill-me type."""
    import app.services.vault as vault_mod
    monkeypatch.setattr(vault_mod, "VAULT_PATH", tmp_path)
    vault_mod._invalidate_cache()
    grill_dir = tmp_path / "projects" / "bcr-waivers" / "grill-me"
    grill_dir.mkdir(parents=True)
    (grill_dir / "2026-06-14-test-grill.md").write_text(
        "---\ntype: grill-me\ntitle: Test Grill\nproject: bcr-waivers\nstatus: new\n"
        "created: 2026-06-14T10:00:00\ntags: [grill-me, status/new]\n---\n## Description\ntest\n"
    )
    resp = client.patch(
        "/entries",
        json={"project": "bcr-waivers", "type": "grill-me", "filename": "2026-06-14-test-grill", "status": "open"},
        headers={"X-Capture-Token": "test-token-secret"},
    )
    assert resp.status_code == 200


def test_capture_json_accepts_grill_me_type(client, tmp_path, monkeypatch):
    """POST /capture/json should accept grill-me type."""
    import app.services.vault as vault_mod
    monkeypatch.setattr(vault_mod, "VAULT_PATH", tmp_path)
    vault_mod._invalidate_cache()
    (tmp_path / "projects" / "bcr-waivers").mkdir(parents=True, exist_ok=True)
    resp = client.post(
        "/capture/json",
        json={"type": "grill-me", "project": "bcr-waivers", "title": "Half baked"},
    )
    assert resp.status_code == 200
    files = list((tmp_path / "projects" / "bcr-waivers" / "grill-me").glob("*.md"))
    assert len(files) == 1


# ============= housekeeping-task capture_json tests =============

def test_capture_json_housekeeping_task(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    resp = client.post("/capture/json", json={
        "type": "housekeeping-task",
        "project": "claude-config",
        "title": "Prune vault",
        "interval": "weekly",
        "success_definition": "Old entries pruned.",
    })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    files = list((tmp_path / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    assert len(files) == 1


def test_capture_json_housekeeping_task_missing_title(client):
    resp = client.post("/capture/json", json={
        "type": "housekeeping-task",
        "project": "claude-config",
        "interval": "weekly",
        "success_definition": "Done.",
    })
    assert resp.status_code == 400


def test_capture_json_housekeeping_task_missing_project(client):
    resp = client.post("/capture/json", json={
        "type": "housekeeping-task",
        "title": "Test",
        "interval": "weekly",
        "success_definition": "Done.",
    })
    assert resp.status_code == 400


def test_capture_json_housekeeping_task_defaults_interval_to_weekly(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    resp = client.post("/capture/json", json={
        "type": "housekeeping-task",
        "project": "claude-config",
        "title": "Prune vault",
        "success_definition": "Done.",
        # interval omitted — should default to weekly
    })
    assert resp.status_code == 200
    files = list((tmp_path / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    import frontmatter as fm
    post = fm.load(files[0])
    assert post.metadata["interval"] == "weekly"


def test_capture_json_housekeeping_heartbeat(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    resp = client.post("/capture/json", json={
        "type": "housekeeping-heartbeat",
        "project": "claude-config",
        "title": "Housekeeping Last Run",
    })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    heartbeat = tmp_path / "projects" / "claude-config" / "housekeeping" / "last-run.md"
    assert heartbeat.exists()


# ============= PATCH /entries/housekeeping tests =============

def test_patch_housekeeping_requires_token(client, tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch("/entries/housekeeping", json={
            "project": "claude-config",
            "type": "housekeeping-task",
            "filename": "test",
            "fields": {"enabled": "false"},
        })
    assert resp.status_code == 401


def test_patch_housekeeping_task_enabled(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Test task",
            "body": "",
            "interval": "weekly",
            "success_definition": "Done.",
        })
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": slug, "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 200
    assert "Updated" in resp.get_json().get("message", "")


def test_patch_housekeeping_heartbeat(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-heartbeat",
                  "filename": "last-run",
                  "fields": {"last_run": "2026-06-17T12:00:00", "tasks_run": "5",
                              "tasks_failed": "1", "tasks_skipped": "2"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 200


def test_patch_housekeeping_invalid_type_returns_400(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "bug",
                  "filename": "test", "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400


def test_patch_housekeeping_missing_entry_returns_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "nonexistent", "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 404


def test_patch_housekeeping_path_traversal_returns_400(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "../../etc/passwd", "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400


def test_patch_housekeeping_requires_json_body(client, tmp_path, monkeypatch):
    """PATCH /entries/housekeeping rejects form data — JSON body only."""
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            data={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "test", "enabled": "false"},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400


def test_patch_housekeeping_wrong_token_returns_401(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "test", "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "wrong-token"},
        )
    assert resp.status_code == 401


def test_patch_housekeeping_empty_fields_returns_400(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "test", "fields": {}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400


def test_patch_housekeeping_malformed_json_returns_400(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            data=b"{not valid json",
            content_type="application/json",
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400
