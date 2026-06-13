import pytest
from pathlib import Path
from unittest.mock import patch
import frontmatter as fm
import yaml


def _make_entry(path, slug, type_, project, status="new", component=None):
    path.mkdir(parents=True, exist_ok=True)
    content = "## Description\nBody.\n"
    meta = {
        "type": type_, "title": slug, "project": project,
        "status": status, "created": "2026-06-01T10:00:00",
        "tags": [type_, project, f"status/{status}"],
    }
    if component:
        meta["component"] = component
    post = fm.Post(content, **meta)
    (path / f"{slug}.md").write_text(fm.dumps(post))


def _write_registry(tmp_path, data):
    reg = tmp_path / "umbrella_registry.yaml"
    reg.write_text(yaml.dump(data))
    return reg


def test_collect_component_entries(tmp_path):
    bugs = tmp_path / "projects" / "claude-code" / "bugs"
    _make_entry(bugs, "2026-06-01-test-bug", "bug", "claude-code")
    _make_entry(bugs, "2026-06-01-other-bug", "bug", "claude-code")

    from scripts.migrate_to_umbrella import collect_component_entries
    entries = collect_component_entries(tmp_path, "claude-code")
    assert len(entries) == 2
    slugs = {e["slug"] for e in entries}
    assert "2026-06-01-test-bug" in slugs


def test_migrate_entry_writes_to_umbrella_folder(tmp_path):
    bugs = tmp_path / "projects" / "claude-code" / "bugs"
    _make_entry(bugs, "2026-06-01-test-bug", "bug", "claude-code")
    src = bugs / "2026-06-01-test-bug.md"

    from scripts.migrate_to_umbrella import migrate_entry
    migrate_entry(tmp_path, src, "bug", "claude-code", "claude-config", apply=True)

    dest = tmp_path / "projects" / "claude-config" / "bugs" / "2026-06-01-test-bug.md"
    assert dest.exists()
    assert not src.exists()

    post = fm.load(dest)
    assert post.metadata["project"] == "claude-config"
    assert post.metadata["component"] == "claude-code"
    assert "component/claude-code" in post.metadata["tags"]
    assert "[[claude-config]]" in post.content


def test_migrate_entry_dry_run_does_not_move(tmp_path):
    bugs = tmp_path / "projects" / "claude-code" / "bugs"
    _make_entry(bugs, "2026-06-01-test-bug", "bug", "claude-code")
    src = bugs / "2026-06-01-test-bug.md"

    from scripts.migrate_to_umbrella import migrate_entry
    migrate_entry(tmp_path, src, "bug", "claude-code", "claude-config", apply=False)

    assert src.exists()
    dest = tmp_path / "projects" / "claude-config" / "bugs" / "2026-06-01-test-bug.md"
    assert not dest.exists()


def test_hide_component_project(tmp_path):
    proj = tmp_path / "projects" / "claude-code"
    proj.mkdir(parents=True)
    (proj / "project.md").write_text("---\nname: Claude Code\nhidden: false\n---\n")

    from scripts.migrate_to_umbrella import hide_component_project
    hide_component_project(tmp_path, "claude-code", apply=True)

    post = fm.load(proj / "project.md")
    assert post.metadata["hidden"] is True
