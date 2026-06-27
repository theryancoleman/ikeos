import pytest
from unittest.mock import patch
import frontmatter as fm
import app.services.vault_cache as _vc


@pytest.fixture(autouse=True)
def reset_cache():
    _vc._invalidate_cache()
    yield
    _vc._invalidate_cache()


def test_write_entry_creates_note_in_notes_folder(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({"type": "note", "project": "myproj", "title": "Test note", "body": "Body"})
    files = list((tmp_path / "projects" / "myproj" / "notes").glob("*.md"))
    assert len(files) == 1


def test_write_entry_sets_status_new(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({"type": "note", "project": "myproj", "title": "Test", "body": ""})
    files = list((tmp_path / "projects" / "myproj" / "notes").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["status"] == "new"


def test_write_entry_bug_includes_severity(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({
            "type": "bug", "project": "myproj",
            "title": "Crash", "body": "It crashes", "severity": "high",
        })
    files = list((tmp_path / "projects" / "myproj" / "bugs").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["severity"] == "high"


def test_read_entries_returns_all_types(tmp_path):
    for folder, etype in [("bugs", "bug"), ("notes", "note"), ("ideas", "idea")]:
        d = tmp_path / "projects" / "myproj" / folder
        d.mkdir(parents=True)
        (d / f"2026-01-01-entry.md").write_text(
            f"---\ntype: {etype}\ntitle: T\nproject: myproj\n"
            "status: new\ncreated: 2026-01-01T00:00:00\ntags: []\n---\n## Description\n"
        )
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import read_entries, _invalidate_cache
        _invalidate_cache()
        result = read_entries(project="myproj")
    assert len(result) == 3


def test_update_entry_status_generic_changes_status(tmp_path):
    notes_dir = tmp_path / "projects" / "myproj" / "notes"
    notes_dir.mkdir(parents=True)
    entry = fm.Post(
        "## Description\nbody\n",
        type="note", title="T", project="myproj",
        status="new", created="2026-01-01T00:00:00",
        tags=["documentation", "myproj", "status/new"],
    )
    (notes_dir / "2026-01-01-t.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status_generic
        result = update_entry_status_generic("note", "myproj", "2026-01-01-t", "open")
    assert result is True
    post = fm.load(notes_dir / "2026-01-01-t.md")
    assert post.metadata["status"] == "open"
    assert "status/open" in post.metadata["tags"]


def test_write_entry_experiment_creates_in_experiments_folder(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({
            "type": "experiment",
            "project": "myproj",
            "title": "Cache vs No Cache",
            "body": "Testing the in-process cache.",
            "hypothesis": "If we cache, then reads are faster",
            "expected_outcome": "Sub-50ms warm reads",
            "measurement": "DevTools network timing",
            "success_criteria": "Warm cache < 50ms",
            "timebox": "one session",
        })
    files = list((tmp_path / "projects" / "myproj" / "experiments").glob("*.md"))
    assert len(files) == 1


def test_write_entry_experiment_sets_status_running(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({
            "type": "experiment",
            "project": "myproj",
            "title": "My Experiment",
            "body": "",
            "hypothesis": "H",
            "expected_outcome": "O",
            "measurement": "M",
            "success_criteria": "S",
            "timebox": "1 week",
        })
    files = list((tmp_path / "projects" / "myproj" / "experiments").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["status"] == "running"
    assert post.metadata["hypothesis"] == "H"
    assert post.metadata["timebox"] == "1 week"
    assert post.metadata["result"] == ""
    assert post.metadata["decision"] == ""


def test_read_entry_finds_experiment_by_slug(tmp_path):
    exp_dir = tmp_path / "projects" / "myproj" / "experiments"
    exp_dir.mkdir(parents=True)
    entry = fm.Post(
        "## Context\nbody\n",
        type="experiment", title="My Experiment", project="myproj",
        status="running", created="2026-01-01T00:00:00",
        tags=["experiment", "myproj", "status/running"],
    )
    (exp_dir / "2026-01-01-my-experiment.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import read_entry
        result = read_entry("myproj", "2026-01-01-my-experiment")
    assert result is not None
    assert result["title"] == "My Experiment"
    assert result["status"] == "running"


def test_update_entry_status_generic_experiment_complete(tmp_path):
    exp_dir = tmp_path / "projects" / "myproj" / "experiments"
    exp_dir.mkdir(parents=True)
    entry = fm.Post(
        "## Context\nbody\n",
        type="experiment", title="T", project="myproj",
        status="running", created="2026-01-01T00:00:00",
        tags=["experiment", "myproj", "status/running"],
    )
    (exp_dir / "2026-01-01-t.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status_generic
        result = update_entry_status_generic("experiment", "myproj", "2026-01-01-t", "complete")
    assert result is True
    post = fm.load(exp_dir / "2026-01-01-t.md")
    assert post.metadata["status"] == "complete"
    assert "status/complete" in post.metadata["tags"]


def test_entry_type_config_defines_type_folders_and_tags():
    """TYPE_FOLDERS and TYPE_TAGS must be derived from ENTRY_TYPE_CONFIG — not independent dicts."""
    assert hasattr(_vc, "ENTRY_TYPE_CONFIG"), "ENTRY_TYPE_CONFIG not found in vault_cache"
    assert _vc.TYPE_FOLDERS == {k: v["folder"] for k, v in _vc.ENTRY_TYPE_CONFIG.items()}
    assert _vc.TYPE_TAGS == {k: v["tag"] for k, v in _vc.ENTRY_TYPE_CONFIG.items()}


def test_read_entry_uses_entry_type_config(tmp_path):
    """read_entry must find an entry whose type/folder comes only from ENTRY_TYPE_CONFIG."""
    fake_config = {
        **_vc.ENTRY_TYPE_CONFIG,
        "widget": {
            "folder": "widgets",
            "tag": "widget",
            "initial_status": "new",
            "valid_statuses": _vc.VALID_STATUSES,
        },
    }
    widget_dir = tmp_path / "projects" / "myproj" / "widgets"
    widget_dir.mkdir(parents=True)
    post = fm.Post(
        "body",
        type="widget", title="Widget", project="myproj",
        status="new", created="2026-01-01T00:00:00",
        tags=["widget", "myproj", "status/new"],
    )
    (widget_dir / "2026-01-01-widget.md").write_text(fm.dumps(post))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.services.vault_cache.ENTRY_TYPE_CONFIG", fake_config):
        from app.services.vault_entries import read_entry
        result = read_entry("myproj", "2026-01-01-widget")
    assert result is not None
    assert result["title"] == "Widget"


def test_update_entry_status_generic_uses_entry_type_config(tmp_path):
    """update_entry_status_generic must route to a folder defined only in ENTRY_TYPE_CONFIG."""
    fake_config = {
        **_vc.ENTRY_TYPE_CONFIG,
        "widget": {
            "folder": "widgets",
            "tag": "widget",
            "initial_status": "new",
            "valid_statuses": _vc.VALID_STATUSES,
        },
    }
    widget_dir = tmp_path / "projects" / "myproj" / "widgets"
    widget_dir.mkdir(parents=True)
    post = fm.Post(
        "body",
        type="widget", title="W", project="myproj",
        status="new", created="2026-01-01T00:00:00",
        tags=["widget", "myproj", "status/new"],
    )
    (widget_dir / "2026-01-01-w.md").write_text(fm.dumps(post))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.services.vault_cache.ENTRY_TYPE_CONFIG", fake_config):
        from app.services.vault_entries import update_entry_status_generic
        result = update_entry_status_generic("widget", "myproj", "2026-01-01-w", "done")
    assert result is True
    post = fm.load(widget_dir / "2026-01-01-w.md")
    assert post.metadata["status"] == "done"
    assert "status/done" in post.metadata["tags"]


def test_patch_valid_types_constant_exists_and_is_correct():
    assert hasattr(_vc, "PATCH_VALID_TYPES"), "PATCH_VALID_TYPES not found in vault_cache"
    assert _vc.PATCH_VALID_TYPES == set(_vc.ENTRY_TYPE_CONFIG.keys()) | {"decision"}


def test_capture_json_valid_types_constant_exists_and_is_correct():
    assert hasattr(_vc, "CAPTURE_JSON_VALID_TYPES"), "CAPTURE_JSON_VALID_TYPES not found in vault_cache"
    assert _vc.CAPTURE_JSON_VALID_TYPES == (
        set(_vc.ENTRY_TYPE_CONFIG.keys()) | {"housekeeping-task", "housekeeping-heartbeat"}
    )


def test_update_entry_status_rejects_standard_status_for_experiment(tmp_path):
    """'done' is a valid VALID_STATUS but not a valid experiment status."""
    exp_dir = tmp_path / "projects" / "myproj" / "experiments"
    exp_dir.mkdir(parents=True)
    entry = fm.Post(
        "body",
        type="experiment", title="E", project="myproj",
        status="running", created="2026-01-01T00:00:00",
        tags=["experiment", "myproj", "status/running"],
    )
    (exp_dir / "2026-01-01-e.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status
        result = update_entry_status("myproj", "2026-01-01-e", "done")
    assert result is False, "update_entry_status must reject 'done' for experiments"


def test_update_entry_status_accepts_experiment_status_for_experiment(tmp_path):
    """'complete' is a valid experiment status and must be accepted."""
    exp_dir = tmp_path / "projects" / "myproj" / "experiments"
    exp_dir.mkdir(parents=True)
    entry = fm.Post(
        "body",
        type="experiment", title="E", project="myproj",
        status="running", created="2026-01-01T00:00:00",
        tags=["experiment", "myproj", "status/running"],
    )
    (exp_dir / "2026-01-01-e.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status
        result = update_entry_status("myproj", "2026-01-01-e", "complete")
    assert result is True
    post = fm.load(exp_dir / "2026-01-01-e.md")
    assert post.metadata["status"] == "complete"
    assert "status/complete" in post.metadata["tags"]


def test_update_entry_status_rejects_experiment_status_for_note(tmp_path):
    """'running' is a valid experiment status but not valid for a note."""
    note_dir = tmp_path / "projects" / "myproj" / "notes"
    note_dir.mkdir(parents=True)
    entry = fm.Post(
        "body",
        type="note", title="N", project="myproj",
        status="new", created="2026-01-01T00:00:00",
        tags=["documentation", "myproj", "status/new"],
    )
    (note_dir / "2026-01-01-n.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status
        result = update_entry_status("myproj", "2026-01-01-n", "running")
    assert result is False, "update_entry_status must reject 'running' for notes"
