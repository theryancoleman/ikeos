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


def test_create_hub_and_stubs_creates_files(tmp_path):
    from scripts.migrate_to_umbrella import create_hub_and_stubs
    umbrella_meta = {"name": "Claude Config", "components": ["claude-code"]}
    create_hub_and_stubs(tmp_path, "claude-config", umbrella_meta, apply=True)

    hub = tmp_path / "projects" / "claude-config" / "claude-config.md"
    assert hub.exists()
    post = fm.load(hub)
    assert post.metadata["type"] == "hub"
    assert post.metadata["project"] == "claude-config"
    assert "[[claude-code]]" in post.content

    stub = tmp_path / "projects" / "claude-config" / "components" / "claude-code.md"
    assert stub.exists()
    post = fm.load(stub)
    assert post.metadata["type"] == "component"
    assert "[[claude-config]]" in post.content


def test_create_hub_and_stubs_skips_existing(tmp_path):
    from scripts.migrate_to_umbrella import create_hub_and_stubs
    umbrella_meta = {"name": "Claude Config", "components": ["claude-code"]}

    # First call creates files
    create_hub_and_stubs(tmp_path, "claude-config", umbrella_meta, apply=True)
    hub = tmp_path / "projects" / "claude-config" / "claude-config.md"
    original_text = hub.read_text()

    # Second call should NOT overwrite
    create_hub_and_stubs(tmp_path, "claude-config", umbrella_meta, apply=True)
    assert hub.read_text() == original_text


def test_migrate_entry_wikilink_idempotent(tmp_path):
    from scripts.migrate_to_umbrella import migrate_entry
    bugs = tmp_path / "projects" / "claude-code" / "bugs"
    _make_entry(bugs, "2026-06-01-test-bug", "bug", "claude-code")
    src = bugs / "2026-06-01-test-bug.md"

    # First migration
    migrate_entry(tmp_path, src, "bug", "claude-code", "claude-config", apply=True)

    dest = tmp_path / "projects" / "claude-config" / "bugs" / "2026-06-01-test-bug.md"
    assert dest.exists()

    # Move back to simulate re-run scenario
    bugs.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(dest, src)

    # Re-run: collision guard should skip
    migrate_entry(tmp_path, src, "bug", "claude-code", "claude-config", apply=True)
    # dest still exists (was skipped), no duplicate wikilink
    post = fm.load(dest)
    assert post.content.count("[[claude-config]]") == 1
