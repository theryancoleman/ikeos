import pytest
from pathlib import Path
from unittest.mock import patch
import frontmatter as fm
from app.services.vault import write_entry, read_entry, write_project_meta


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "projects" / "bcr-waivers").mkdir(parents=True)
    (tmp_path / "projects" / "worldwardle").mkdir(parents=True)
    return tmp_path


def test_get_projects_returns_sorted_list(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import get_projects
        assert get_projects() == ["bcr-waivers", "worldwardle"]


def test_get_projects_empty_when_no_projects_dir(tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_projects
        assert get_projects() == []


def test_write_entry_creates_file_in_correct_folder(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({"type": "note", "project": "bcr-waivers", "title": "Test note", "body": "Body text"})

    files = list((vault / "projects" / "bcr-waivers" / "notes").glob("*.md"))
    assert len(files) == 1


def test_write_entry_sets_status_new(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({"type": "note", "project": "bcr-waivers", "title": "Test", "body": ""})

    files = list((vault / "projects" / "bcr-waivers" / "notes").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["status"] == "new"


def test_write_entry_includes_bug_fields(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({
            "type": "bug", "project": "bcr-waivers",
            "title": "Crash", "body": "It crashes",
            "severity": "high", "steps": "1. Do thing\n2. Crash"
        })

    files = list((vault / "projects" / "bcr-waivers" / "bugs").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["severity"] == "high"
    assert "Steps to reproduce" in post.content


def test_write_entry_includes_idea_fields(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({
            "type": "idea", "project": "bcr-waivers",
            "title": "Better login", "body": "Description",
            "priority": "high", "effort": "small"
        })

    files = list((vault / "projects" / "bcr-waivers" / "ideas").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["priority"] == "high"
    assert post.metadata["effort"] == "small"


def test_read_entries_returns_newest_first(vault):
    (vault / "projects" / "bcr-waivers" / "notes").mkdir(parents=True)
    older = vault / "projects" / "bcr-waivers" / "notes" / "2026-05-25-old.md"
    newer = vault / "projects" / "bcr-waivers" / "notes" / "2026-05-26-new.md"
    older.write_text("---\ntype: note\ntitle: Old\nproject: bcr-waivers\nstatus: new\ncreated: 2026-05-25T10:00:00\ntags: [note]\n---\n## Description\nOld\n")
    newer.write_text("---\ntype: note\ntitle: New\nproject: bcr-waivers\nstatus: new\ncreated: 2026-05-26T10:00:00\ntags: [note]\n---\n## Description\nNew\n")

    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import read_entries
        entries = read_entries()
    assert entries[0]["title"] == "New"
    assert entries[1]["title"] == "Old"


def test_read_entries_filters_by_status(vault):
    (vault / "projects" / "bcr-waivers" / "notes").mkdir(parents=True)
    (vault / "projects" / "bcr-waivers" / "notes" / "2026-05-26-done.md").write_text(
        "---\ntype: note\ntitle: Done\nproject: bcr-waivers\nstatus: done\ncreated: 2026-05-26T10:00:00\ntags: [note]\n---\n## Description\nDone\n"
    )
    (vault / "projects" / "bcr-waivers" / "notes" / "2026-05-26-new.md").write_text(
        "---\ntype: note\ntitle: New\nproject: bcr-waivers\nstatus: new\ncreated: 2026-05-26T11:00:00\ntags: [note]\n---\n## Description\nNew\n"
    )

    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import read_entries
        entries = read_entries(status_filter=["new"])
    assert len(entries) == 1
    assert entries[0]["title"] == "New"


def test_read_entry_returns_correct_entry(vault):
    (vault / "projects" / "bcr-waivers" / "bugs").mkdir(parents=True)
    (vault / "projects" / "bcr-waivers" / "bugs" / "2026-05-26-crash.md").write_text(
        "---\ntype: bug\ntitle: Crash\nproject: bcr-waivers\nstatus: new\nseverity: high\ncreated: 2026-05-26T10:00:00\ntags: [bug]\n---\n## Description\nIt crashes\n"
    )

    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import read_entry
        entry = read_entry("bcr-waivers", "2026-05-26-crash")
    assert entry["title"] == "Crash"
    assert entry["severity"] == "high"


def test_read_entry_returns_none_for_missing(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import read_entry
        assert read_entry("bcr-waivers", "nonexistent") is None


def test_update_entry_status_changes_status_and_tag(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_entry_status
        slug = write_entry({
            "type": "idea", "project": "bcr-waivers", "title": "My idea",
            "body": "body", "priority": "medium", "effort": "medium",
        })
        result = update_entry_status("bcr-waivers", slug, "open")
        assert result is True
        entry = read_entry("bcr-waivers", slug)
        assert entry["status"] == "open"
        assert "status/open" in entry["tags"]
        assert "status/new" not in entry["tags"]


def test_update_entry_status_returns_false_for_missing_entry(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_entry_status
        result = update_entry_status("bcr-waivers", "no-such-slug", "open")
        assert result is False


def test_update_entry_status_returns_false_for_invalid_status(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry, update_entry_status, read_entry
        slug = write_entry({
            "type": "idea", "project": "bcr-waivers", "title": "My idea",
            "body": "body", "priority": "medium", "effort": "medium",
        })
        result = update_entry_status("bcr-waivers", slug, "not-a-real-status")
        assert result is False
        entry = read_entry("bcr-waivers", slug)
        assert entry["status"] == "new"  # unchanged


def test_read_project_meta_returns_description(tmp_path):
    proj = tmp_path / "projects" / "my-project"
    proj.mkdir(parents=True)
    (proj / "project.md").write_text(
        "---\nname: My Project\ndescription: A test project\nhidden: false\n---\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import _read_project_meta
        meta = _read_project_meta("my-project")
    assert meta["description"] == "A test project"


def test_read_project_meta_description_defaults_to_empty(tmp_path):
    proj = tmp_path / "projects" / "my-project"
    proj.mkdir(parents=True)
    (proj / "project.md").write_text("---\nname: My Project\nhidden: false\n---\n")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import _read_project_meta
        meta = _read_project_meta("my-project")
    assert meta["description"] == ""


def test_write_project_meta_creates_project_md(tmp_path):
    proj = tmp_path / "projects" / "my-project"
    proj.mkdir(parents=True)
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        result = write_project_meta("my-project", "My Project", "A description", False)
    assert result is True
    meta_file = proj / "project.md"
    assert meta_file.exists()
    post = fm.load(meta_file)
    assert post.metadata["name"] == "My Project"
    assert post.metadata["description"] == "A description"
    assert post.metadata["hidden"] is False


def test_write_project_meta_updates_existing(tmp_path):
    proj = tmp_path / "projects" / "my-project"
    proj.mkdir(parents=True)
    (proj / "project.md").write_text("---\nname: Old Name\nhidden: false\n---\n")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        write_project_meta("my-project", "New Name", "Updated desc", True)
        from app.services.vault import _read_project_meta
        meta = _read_project_meta("my-project")
    assert meta["name"] == "New Name"
    assert meta["description"] == "Updated desc"
    assert meta["hidden"] is True


def test_write_project_meta_returns_false_for_missing_slug(tmp_path):
    (tmp_path / "projects").mkdir(parents=True)
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        result = write_project_meta("nonexistent", "Name", "", False)
    assert result is False


def test_get_projects_with_meta_includes_hidden_when_requested(tmp_path):
    for slug, name, hidden in [("visible", "Visible", False), ("hidden-one", "Hidden", True)]:
        d = tmp_path / "projects" / slug
        d.mkdir(parents=True)
        (d / "project.md").write_text(
            f"---\nname: {name}\nhidden: {str(hidden).lower()}\n---\n"
        )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_projects_with_meta
        visible_only = get_projects_with_meta(include_hidden=False)
        all_projects = get_projects_with_meta(include_hidden=True)
    assert len(visible_only) == 1
    assert visible_only[0]["slug"] == "visible"
    assert len(all_projects) == 2
