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


# ── get_vault_graph ──────────────────────────────────────────────────────────

def _make_entry(path, slug, type_, status, project, body="", urgency=None):
    """Helper: write a minimal vault entry file."""
    tags = [type_, project, f"status/{status}"]
    if urgency:
        tags.append(f"urgency/{urgency}")
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{slug}.md").write_text(
        f"---\ntype: {type_}\ntitle: {slug}\nproject: {project}\n"
        f"status: {status}\ncreated: 2026-01-01T10:00:00\n"
        f"updated: 2026-01-01T10:00:00\ntags: {tags}\n---\n"
        f"## Description\n{body}\n"
    )


def test_get_vault_graph_returns_structure(tmp_path):
    bugs = tmp_path / "projects" / "proj-a" / "bugs"
    _make_entry(bugs, "2026-01-01-bug-one", "bug", "open", "proj-a")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    assert set(result.keys()) == {"nodes", "links", "health"}
    assert set(result["health"].keys()) == {"untriaged", "stale", "broken_links"}
    assert len(result["nodes"]) == 1
    node = result["nodes"][0]
    assert node["id"] == "2026-01-01-bug-one"
    assert node["type"] == "bug"
    assert node["project"] == "proj-a"


def test_get_vault_graph_detects_wikilinks(tmp_path):
    bugs = tmp_path / "projects" / "proj-a" / "bugs"
    notes = tmp_path / "projects" / "proj-a" / "notes"
    _make_entry(bugs, "2026-01-01-bug-a", "bug", "open", "proj-a",
                body="See [[2026-01-01-note-b]]")
    _make_entry(notes, "2026-01-01-note-b", "note", "open", "proj-a")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    assert len(result["links"]) == 1
    assert result["links"][0]["source"] == "2026-01-01-bug-a"
    assert result["links"][0]["target"] == "2026-01-01-note-b"


def test_get_vault_graph_detects_broken_links(tmp_path):
    notes = tmp_path / "projects" / "proj-a" / "notes"
    _make_entry(notes, "2026-01-01-note-x", "note", "open", "proj-a",
                body="See [[nonexistent-slug]]")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    broken = result["health"]["broken_links"]
    assert len(broken) == 1
    assert broken[0]["broken_ref"] == "nonexistent-slug"
    assert broken[0]["source_slug"] == "2026-01-01-note-x"
    assert len(result["links"]) == 0


def test_get_vault_graph_detects_untriaged(tmp_path):
    notes = tmp_path / "projects" / "proj-a" / "notes"
    _make_entry(notes, "2026-01-01-untriaged", "note", "new", "proj-a")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    untriaged = result["health"]["untriaged"]
    assert len(untriaged) == 1
    assert untriaged[0]["slug"] == "2026-01-01-untriaged"


def test_get_vault_graph_detects_stale(tmp_path):
    notes = tmp_path / "projects" / "proj-a" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    # updated 500 days ago — definitely stale
    (notes / "2026-01-01-old.md").write_text(
        "---\ntype: note\ntitle: Old Note\nproject: proj-a\n"
        "status: open\ncreated: 2024-08-15T10:00:00\n"
        "updated: 2024-08-15T10:00:00\ntags: [documentation]\n---\n"
        "## Description\nContent\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    stale = result["health"]["stale"]
    assert len(stale) == 1
    assert stale[0]["days_stale"] >= 30


def test_get_vault_graph_node_urgency_from_tag(tmp_path):
    bugs = tmp_path / "projects" / "proj-a" / "bugs"
    _make_entry(bugs, "2026-01-01-high-bug", "bug", "open", "proj-a", urgency="high")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    node = next(n for n in result["nodes"] if n["id"] == "2026-01-01-high-bug")
    assert node["urgency"] == "high"


def test_get_vault_graph_node_urgency_fallback_to_severity(tmp_path):
    notes = tmp_path / "projects" / "proj-a" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    # Entry with severity field but no urgency/* tag
    (notes / "2026-01-01-sev-note.md").write_text(
        "---\ntype: note\ntitle: Severity Note\nproject: proj-a\n"
        "status: open\nseverity: critical\ncreated: 2026-01-01T10:00:00\n"
        "updated: 2026-01-01T10:00:00\ntags: [documentation]\n---\n"
        "## Description\nContent\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    node = next(n for n in result["nodes"] if n["id"] == "2026-01-01-sev-note")
    assert node["urgency"] == "critical"


def test_read_hub_pages_caches_result_on_second_call(tmp_path):
    proj_dir = tmp_path / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    hub_file = proj_dir / "MyProject.md"
    hub_file.write_text(
        "---\ntype: hub\ntitle: My Project\nproject: myproject\n---\n"
    )

    from app.services import vault as vault_mod

    vault_mod._invalidate_cache()

    with patch.object(vault_mod, "VAULT_PATH", tmp_path):
        result1 = vault_mod._read_hub_pages()
        ts_after_first = vault_mod._hub_pages_cache_ts
        result2 = vault_mod._read_hub_pages()
        ts_after_second = vault_mod._hub_pages_cache_ts

    assert len(result1) == 1
    assert result1[0]["title"] == "My Project"
    assert result1 == result2
    assert ts_after_first == ts_after_second  # cache was hit, timestamp unchanged
    assert vault_mod._hub_pages_cache is not None


# ── component / umbrella ─────────────────────────────────────────────────────

def test_write_entry_with_component_sets_component_tag(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({
            "type": "bug", "project": "ikeos", "title": "Boot crash",
            "body": "It breaks", "severity": "high",
            "component": "voice-bridge",
        })
    files = list((vault / "projects" / "ikeos" / "bugs").glob("*.md"))
    assert len(files) == 1
    post = fm.load(files[0])
    assert post.metadata.get("component") == "voice-bridge"
    assert "component/voice-bridge" in post.metadata["tags"]


def test_write_entry_with_component_appends_wikilink(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({
            "type": "note", "project": "ikeos", "title": "Arch notes",
            "body": "Details here.", "component": "voice-bridge",
        })
    files = list((vault / "projects" / "ikeos" / "notes").glob("*.md"))
    post = fm.load(files[0])
    assert "[[IkeOS]]" in post.content


def test_write_entry_without_component_no_wikilink(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({
            "type": "note", "project": "ikeos", "title": "Standalone",
            "body": "No component.", "domains": [],
        })
    files = list((vault / "projects" / "ikeos" / "notes").glob("*.md"))
    post = fm.load(files[0])
    assert "[[ikeos]]" not in post.content


def test_read_entries_filters_by_component(vault):
    (vault / "projects" / "ikeos" / "bugs").mkdir(parents=True)
    (vault / "projects" / "ikeos" / "bugs" / "2026-06-13-bug-a.md").write_text(
        "---\ntype: bug\ntitle: Bug A\nproject: ikeos\ncomponent: voice-bridge\n"
        "status: new\ncreated: 2026-06-13T10:00:00\ntags: [bug]\n---\n## Description\nA\n"
    )
    (vault / "projects" / "ikeos" / "bugs" / "2026-06-13-bug-b.md").write_text(
        "---\ntype: bug\ntitle: Bug B\nproject: ikeos\ncomponent: display\n"
        "status: new\ncreated: 2026-06-13T11:00:00\ntags: [bug]\n---\n## Description\nB\n"
    )
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import read_entries, _invalidate_cache
        _invalidate_cache()
        entries = read_entries(project="ikeos", component="voice-bridge")
    assert len(entries) == 1
    assert entries[0]["title"] == "Bug A"


# ── hub pages and graph integration ─────────────────────────────────────────

def test_write_hub_page_creates_file(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_hub_page
        write_hub_page("ikeos", "IkeOS", ["voice-bridge", "display"])
    hub = vault / "projects" / "ikeos" / "IkeOS.md"
    assert hub.exists()
    post = fm.load(hub)
    assert post.metadata["type"] == "hub"
    assert post.metadata["project"] == "ikeos"
    assert "[[voice-bridge]]" in post.content
    assert "[[display]]" in post.content


def test_write_hub_page_no_components(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_hub_page
        write_hub_page("wayvr", "Wayvr", [])
    hub = vault / "projects" / "wayvr" / "Wayvr.md"
    assert hub.exists()


def test_write_component_stub_creates_file(vault):
    (vault / "projects" / "ikeos").mkdir(parents=True)
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_component_stub
        write_component_stub("ikeos", "voice-bridge")
    stub = vault / "projects" / "ikeos" / "components" / "voice-bridge.md"
    assert stub.exists()
    post = fm.load(stub)
    assert post.metadata["type"] == "component"
    assert "[[IkeOS]]" in post.content


def test_get_vault_graph_includes_hub_nodes(tmp_path):
    (tmp_path / "projects" / "ikeos").mkdir(parents=True)
    hub = tmp_path / "projects" / "ikeos" / "ikeos.md"
    hub.write_text(
        "---\ntype: hub\nproject: ikeos\ntitle: IkeOS\ntags: [hub]\n---\n"
        "Components: [[voice-bridge]]\n"
    )
    # Also write a stub so the wikilink resolves
    (tmp_path / "projects" / "ikeos" / "components").mkdir()
    stub = tmp_path / "projects" / "ikeos" / "components" / "voice-bridge.md"
    stub.write_text(
        "---\ntype: component\nproject: ikeos\ntitle: voice-bridge\ntags: [component]\n---\n"
        "[[ikeos]]\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    node_ids = {n["id"] for n in result["nodes"]}
    assert "ikeos" in node_ids
    assert "voice-bridge" in node_ids


def test_get_vault_graph_wikilink_resolves_to_hub(tmp_path):
    # Entry with [[ikeos]] wikilink should create a link to the hub node
    (tmp_path / "projects" / "ikeos" / "bugs").mkdir(parents=True)
    (tmp_path / "projects" / "ikeos" / "bugs" / "2026-06-13-crash.md").write_text(
        "---\ntype: bug\ntitle: Crash\nproject: ikeos\ncomponent: voice-bridge\n"
        "status: new\ncreated: 2026-06-13T10:00:00\ntags: [bug]\n---\n"
        "## Description\nBroke.\n\n---\n[[ikeos]]\n"
    )
    (tmp_path / "projects" / "ikeos").mkdir(exist_ok=True)
    (tmp_path / "projects" / "ikeos" / "ikeos.md").write_text(
        "---\ntype: hub\nproject: ikeos\ntitle: IkeOS\ntags: [hub]\n---\nHub page.\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    link_targets = {lnk["target"] for lnk in result["links"]}
    assert "ikeos" in link_targets
    assert not any(bl["broken_ref"] == "ikeos" for bl in result["health"]["broken_links"])


def test_write_entry_creates_grill_me_in_correct_folder(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({"type": "grill-me", "project": "bcr-waivers", "title": "Half baked idea", "body": "Not sure yet"})

    files = list((vault / "projects" / "bcr-waivers" / "grill-me").glob("*.md"))
    assert len(files) == 1
    import frontmatter as fm
    post = fm.load(files[0])
    assert post.metadata["type"] == "grill-me"
    assert post.metadata["status"] == "new"


def test_read_entries_includes_grill_me_folder(vault):
    grill_dir = vault / "projects" / "bcr-waivers" / "grill-me"
    grill_dir.mkdir(parents=True)
    (grill_dir / "2026-06-14-half-formed.md").write_text(
        "---\ntype: grill-me\ntitle: Half formed\nproject: bcr-waivers\nstatus: new\n"
        "created: 2026-06-14T10:00:00\ntags: [grill-me]\n---\n## Description\nNeeds work\n"
    )
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import read_entries, _invalidate_cache
        _invalidate_cache()
        entries = read_entries(project="bcr-waivers")
    assert any(e["type"] == "grill-me" for e in entries)


def test_update_entry_status_generic_grill_me(vault):
    grill_dir = vault / "projects" / "bcr-waivers" / "grill-me"
    grill_dir.mkdir(parents=True)
    (grill_dir / "2026-06-14-test.md").write_text(
        "---\ntype: grill-me\ntitle: Test\nproject: bcr-waivers\nstatus: new\n"
        "created: 2026-06-14T10:00:00\ntags: [grill-me, status/new]\n---\n## Description\ntest\n"
    )
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_entry_status_generic
        result = update_entry_status_generic("grill-me", "bcr-waivers", "2026-06-14-test", "open")
    assert result is True
    import frontmatter as fm
    post = fm.load(grill_dir / "2026-06-14-test.md")
    assert post.metadata["status"] == "open"


# ============= housekeeping-task write tests =============

def test_write_entry_housekeeping_task_creates_file_in_housekeeping_folder(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Prune stale entries",
            "body": "Run the pruner.",
            "interval": "weekly",
            "success_definition": "No entries older than 90 days remain.",
        })
    files = list((vault / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    assert len(files) == 1
    assert slug in files[0].name


def test_write_entry_housekeeping_task_frontmatter(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Prune vault",
            "body": "",
            "interval": "monthly",
            "success_definition": "Done.",
        })
    files = list((vault / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["type"] == "housekeeping-task"
    assert post.metadata["interval"] == "monthly"
    assert post.metadata["enabled"] == "true"
    assert post.metadata["last_run"] == "null"
    assert post.metadata["last_error"] == "null"
    assert post.metadata["consecutive_failures"] == "0"
    assert post.metadata["title"] == "Prune vault"
    assert post.metadata["project"] == "claude-config"
    assert post.metadata["success_definition"] == "Done."
    assert "created" in post.metadata
    assert "housekeeping-task" in post.metadata["tags"]
    assert "status/enabled" in post.metadata["tags"]
    assert "claude-config" in post.metadata["tags"]


def test_write_entry_housekeeping_task_defaults_interval_to_weekly(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Test",
            "body": "",
            "success_definition": "Done.",
            # interval omitted — should default to weekly
        })
    files = list((vault / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["interval"] == "weekly"


# ============= housekeeping-heartbeat write tests =============

def test_write_entry_housekeeping_heartbeat_creates_last_run_md(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "housekeeping-heartbeat",
            "project": "claude-config",
            "title": "Housekeeping Last Run",
        })
    heartbeat = vault / "projects" / "claude-config" / "housekeeping" / "last-run.md"
    assert heartbeat.exists()
    assert slug == "last-run"


def test_write_entry_housekeeping_heartbeat_frontmatter(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({
            "type": "housekeeping-heartbeat",
            "project": "claude-config",
            "title": "Housekeeping Last Run",
        })
    post = fm.load(vault / "projects" / "claude-config" / "housekeeping" / "last-run.md")
    assert post.metadata["type"] == "housekeeping-heartbeat"
    assert post.metadata["last_run"] == "null"
    assert post.metadata["tasks_run"] == "0"
    assert post.metadata["tasks_failed"] == "0"
    assert post.metadata["tasks_skipped"] == "0"


def test_write_entry_housekeeping_heartbeat_is_singleton(vault):
    """Writing heartbeat twice overwrites, never duplicates."""
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
    files = list((vault / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    assert len(files) == 1


# ============= update_housekeeping_fields tests =============

def test_update_housekeeping_fields_task_enabled_toggle(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry, update_housekeeping_fields
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Test task",
            "body": "",
            "interval": "weekly",
            "success_definition": "Done.",
        })
        result = update_housekeeping_fields(
            "housekeeping-task", "claude-config", slug, {"enabled": "false"}
        )
        assert result is True
        post = fm.load(vault / "projects" / "claude-config" / "housekeeping" / f"{slug}.md")
        assert post.metadata["enabled"] == "false"


def test_update_housekeeping_fields_heartbeat(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry, update_housekeeping_fields
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
        result = update_housekeeping_fields(
            "housekeeping-heartbeat", "claude-config", "last-run",
            {"last_run": "2026-06-17T12:00:00", "tasks_run": "3",
             "tasks_failed": "0", "tasks_skipped": "1"},
        )
        assert result is True
        post = fm.load(vault / "projects" / "claude-config" / "housekeeping" / "last-run.md")
        assert post.metadata["last_run"] == "2026-06-17T12:00:00"
        assert post.metadata["tasks_run"] == "3"
        assert post.metadata["tasks_skipped"] == "1"


def test_update_housekeeping_fields_ignores_disallowed_fields(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry, update_housekeeping_fields
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Original",
            "body": "",
            "interval": "weekly",
            "success_definition": "Done.",
        })
        # title is not in the allowed set — should be silently ignored
        result = update_housekeeping_fields(
            "housekeeping-task", "claude-config", slug,
            {"title": "HACKED", "enabled": "false"},
        )
        assert result is True
        post = fm.load(vault / "projects" / "claude-config" / "housekeeping" / f"{slug}.md")
        assert post.metadata["title"] == "Original"
        assert post.metadata["enabled"] == "false"


def test_update_housekeeping_fields_invalid_type_returns_false(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_housekeeping_fields
        result = update_housekeeping_fields("bug", "claude-config", "any", {"last_run": "2026-06-17"})
        assert result is False


def test_update_housekeeping_fields_missing_file_returns_false(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import update_housekeeping_fields
        result = update_housekeeping_fields(
            "housekeeping-task", "claude-config", "nonexistent", {"enabled": "false"}
        )
        assert result is False


def test_update_housekeeping_fields_path_traversal_returns_false(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_housekeeping_fields
        result = update_housekeeping_fields(
            "housekeeping-task", "claude-config", "../../etc/passwd", {"enabled": "false"}
        )
        assert result is False


def test_update_housekeeping_fields_project_traversal_returns_false(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_housekeeping_fields
        result = update_housekeeping_fields(
            "housekeeping-task", "../../etc", "some-task", {"enabled": "false"}
        )
        assert result is False


def test_update_housekeeping_fields_all_disallowed_fields_returns_false(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_housekeeping_fields
        # title is not in the allowed set for housekeeping-task
        result = update_housekeeping_fields(
            "housekeeping-task", "claude-config", "some-task", {"title": "HACKED"}
        )
        assert result is False


def test_write_idea_includes_why_when_provided(tmp_vault):
    data = {
        "type": "idea",
        "project": "testproject",
        "title": "Add dark mode",
        "body": "Users want it",
        "priority": "medium",
        "effort": "small",
        "domains": [],
        "why": "Users on mobile at night complained about eye strain in the survey",
    }
    slug = write_entry(data)
    import frontmatter
    post_file = tmp_vault / "projects" / "testproject" / "ideas" / f"{slug}.md"
    post = frontmatter.load(post_file)
    assert post.metadata.get("why") == "Users on mobile at night complained about eye strain in the survey"


def test_write_idea_omits_why_when_empty(tmp_vault):
    data = {
        "type": "idea",
        "project": "testproject",
        "title": "Another feature",
        "body": "",
        "priority": "low",
        "effort": "small",
        "domains": [],
        "why": "",
    }
    slug = write_entry(data)
    import frontmatter
    post_file = tmp_vault / "projects" / "testproject" / "ideas" / f"{slug}.md"
    post = frontmatter.load(post_file)
    assert "why" not in post.metadata


def test_write_idea_omits_why_when_missing(tmp_vault):
    data = {
        "type": "idea",
        "project": "testproject",
        "title": "Yet another",
        "body": "",
        "priority": "low",
        "effort": "small",
        "domains": [],
    }
    slug = write_entry(data)
    import frontmatter
    post_file = tmp_vault / "projects" / "testproject" / "ideas" / f"{slug}.md"
    post = frontmatter.load(post_file)
    assert "why" not in post.metadata
