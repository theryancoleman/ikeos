import pytest
from pathlib import Path
from unittest.mock import patch
import frontmatter as fm


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
