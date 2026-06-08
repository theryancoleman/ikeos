import pytest
import frontmatter as fm
from pathlib import Path


@pytest.fixture
def fake_vault(tmp_path):
    entries = [
        ("worldwardle", "bugs",  "Score bug",    "open",        "2026-01-01T00:00:00", "bug",  {"severity": "high"}),
        ("worldwardle", "ideas", "New feature",  "in-progress", "2026-05-01T00:00:00", "idea", {"priority": "medium"}),
        ("spotify-beatport", "ideas", "BPM filter", "done",     "2026-06-01T00:00:00", "idea", {"priority": "low"}),
        ("spotify-beatport", "notes", "Setup note", "open",     "2026-03-01T00:00:00", "note", {}),
    ]
    for project, folder, title, status, created, entry_type, extra in entries:
        d = tmp_path / "projects" / project / folder
        d.mkdir(parents=True, exist_ok=True)
        metadata = {
            "title": title,
            "status": status,
            "created": created,
            "project": project,
            "type": entry_type,
            "tags": [entry_type, project, f"status/{status}"],
            **extra,
        }
        post = fm.Post(f"## Description\nBody\n", **metadata)
        slug = f"2026-01-01-{title.lower().replace(' ', '-')}"
        (d / f"{slug}.md").write_text(fm.dumps(post))
    return tmp_path


def test_load_vault_returns_all_project_entries(fake_vault):
    from vault_cli import load_vault
    _vault, entries, warnings = load_vault(str(fake_vault))
    assert len(entries) == 4
    assert warnings == []


def test_load_vault_entries_have_required_keys(fake_vault):
    from vault_cli import load_vault
    _vault, entries, _warnings = load_vault(str(fake_vault))
    for entry in entries:
        assert "_note" in entry
        assert "_project" in entry
        assert "_folder" in entry


def test_load_vault_missing_path_exits(tmp_path):
    from vault_cli import load_vault
    with pytest.raises(SystemExit):
        load_vault(str(tmp_path / "does-not-exist"))


def test_projects_cmd_counts_by_status(fake_vault, capsys):
    from vault_cli import load_vault, projects_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    projects_cmd(entries, plain=True)
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    # Header + 2 projects
    assert len(lines) == 3
    # worldwardle: 1 open, 1 in-progress
    ww = next(l for l in lines if l.startswith("worldwardle"))
    cols = ww.split("\t")
    assert cols[0] == "worldwardle"
    assert cols[2] == "1"   # open
    assert cols[3] == "1"   # in-progress


def test_projects_cmd_empty_vault(tmp_path, capsys):
    from vault_cli import load_vault, projects_cmd
    _vault, entries, _warnings = load_vault(str(tmp_path))
    projects_cmd(entries, plain=True)
    out = capsys.readouterr().out
    assert "Nothing found." in out


def test_status_cmd_shows_open_and_in_progress(fake_vault, capsys):
    from vault_cli import load_vault, status_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    status_cmd(entries, project_filter=None, plain=True)
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    # Header + 3 entries (1 open bug, 1 in-progress idea, 1 open note) — not the done idea
    data_lines = [l for l in lines if not l.startswith("Project")]
    assert len(data_lines) == 3


def test_status_cmd_project_filter(fake_vault, capsys):
    from vault_cli import load_vault, status_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    status_cmd(entries, project_filter="worldwardle", plain=True)
    out = capsys.readouterr().out
    lines = [l for l in out.strip().splitlines() if not l.startswith("Project")]
    assert len(lines) == 2
    assert all("worldwardle" in l for l in lines)


def test_status_cmd_sorted_oldest_first(fake_vault, capsys):
    from vault_cli import load_vault, status_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    status_cmd(entries, project_filter=None, plain=True)
    out = capsys.readouterr().out
    lines = [l for l in out.strip().splitlines() if not l.startswith("Project")]
    # Score bug created 2026-01-01 should appear before New feature (2026-05-01)
    titles = [l.split("\t")[2] for l in lines]
    assert titles.index("Score bug") < titles.index("New feature")


def test_status_cmd_no_results(fake_vault, capsys):
    from vault_cli import load_vault, status_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    status_cmd(entries, project_filter="nonexistent-project", plain=True)
    out = capsys.readouterr().out
    assert "Nothing found." in out


def test_find_cmd_filter_by_status(fake_vault, capsys):
    from vault_cli import load_vault, find_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    find_cmd(entries, {"status": "done", "project": None, "type": None, "tag": None}, plain=True)
    out = capsys.readouterr().out
    lines = [l for l in out.strip().splitlines() if not l.startswith("Project")]
    assert len(lines) == 1
    assert "BPM filter" in lines[0]


def test_find_cmd_filter_by_type(fake_vault, capsys):
    from vault_cli import load_vault, find_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    find_cmd(entries, {"status": None, "project": None, "type": "bug", "tag": None}, plain=True)
    out = capsys.readouterr().out
    lines = [l for l in out.strip().splitlines() if not l.startswith("Project")]
    assert len(lines) == 1
    assert "Score bug" in lines[0]


def test_find_cmd_filter_by_tag(fake_vault, capsys):
    from vault_cli import load_vault, find_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    find_cmd(entries, {"status": None, "project": None, "type": None, "tag": "status/done"}, plain=True)
    out = capsys.readouterr().out
    lines = [l for l in out.strip().splitlines() if not l.startswith("Project")]
    assert len(lines) == 1
    assert "BPM filter" in lines[0]


def test_find_cmd_filters_are_anded(fake_vault, capsys):
    from vault_cli import load_vault, find_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    # open AND worldwardle → 1 result (Score bug; New feature is in-progress)
    find_cmd(entries, {"status": "open", "project": "worldwardle", "type": None, "tag": None}, plain=True)
    out = capsys.readouterr().out
    lines = [l for l in out.strip().splitlines() if not l.startswith("Project")]
    assert len(lines) == 1
    assert "Score bug" in lines[0]


def test_find_cmd_no_results(fake_vault, capsys):
    from vault_cli import load_vault, find_cmd
    _vault, entries, _warnings = load_vault(str(fake_vault))
    find_cmd(entries, {"status": "new", "project": None, "type": None, "tag": None}, plain=True)
    out = capsys.readouterr().out
    assert "Nothing found." in out


def test_audit_cmd_detects_schema_violation(tmp_path, capsys):
    # Entry missing required 'title' field
    d = tmp_path / "projects" / "test-proj" / "notes"
    d.mkdir(parents=True)
    (d / "2026-01-01-no-title.md").write_text(
        "---\nstatus: open\nproject: test-proj\ntype: note\ncreated: '2026-01-01T00:00:00'\ntags:\n- note\n---\n## Description\nMissing title\n"
    )
    from vault_cli import load_vault, audit_cmd
    vault, entries, _warnings = load_vault(str(tmp_path))
    audit_cmd(vault, entries, project_filter=None, plain=True)
    out = capsys.readouterr().out
    assert "2026-01-01-no-title" in out


def test_audit_cmd_detects_stale_open_items(tmp_path, capsys):
    d = tmp_path / "projects" / "test-proj" / "ideas"
    d.mkdir(parents=True)
    (d / "2026-01-01-old-idea.md").write_text(
        "---\ntitle: Old idea\nstatus: open\nproject: test-proj\ntype: idea\ncreated: '2020-01-01T00:00:00'\ntags:\n- enhancement\n- test-proj\n- status/open\n---\n## Description\nVery old\n"
    )
    from vault_cli import load_vault, audit_cmd
    vault, entries, _warnings = load_vault(str(tmp_path))
    audit_cmd(vault, entries, project_filter=None, plain=True)
    out = capsys.readouterr().out
    assert "Old idea" in out


def test_audit_cmd_project_filter(fake_vault, capsys):
    from vault_cli import load_vault, audit_cmd
    vault, entries, _warnings = load_vault(str(fake_vault))
    audit_cmd(vault, entries, project_filter="worldwardle", plain=True)
    out = capsys.readouterr().out
    # spotify-beatport entries should not appear in output
    assert "spotify-beatport" not in out
