import pytest
from unittest.mock import patch
import frontmatter as fm
import app.services.vault_cache as _vc


@pytest.fixture(autouse=True)
def reset_cache():
    _vc._invalidate_cache()
    yield
    _vc._invalidate_cache()


def _write_task(path, filename, enabled="true", last_run="null", failures="0", interval="weekly", project="myproj"):
    task = fm.Post(
        "## Instructions\nDo the thing.\n",
        title="Test Task",
        type="housekeeping-task",
        project=project,
        interval=interval,
        enabled=enabled,
        success_definition="",
        last_run=last_run,
        last_error="null",
        consecutive_failures=failures,
        created="2026-01-01T00:00:00",
        tags=["housekeeping-task", "myproj", "status/enabled"],
    )
    path.mkdir(parents=True, exist_ok=True)
    (path / filename).write_text(fm.dumps(task))


def test_read_housekeeping_tasks_returns_list(tmp_path):
    hk_dir = tmp_path / "projects" / "myproj" / "housekeeping"
    _write_task(hk_dir, "2026-01-01-test.md")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import read_housekeeping_tasks
        result = read_housekeeping_tasks("myproj")
    assert len(result) == 1
    assert result[0]["title"] == "Test Task"


def test_compute_task_status_due_when_never_run(tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import _compute_task_status
        status = _compute_task_status({"enabled": "true", "last_run": "null", "interval": "weekly"})
    assert status == "due"


def test_compute_task_status_disabled(tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import _compute_task_status
        status = _compute_task_status({"enabled": "false", "last_run": "null", "interval": "weekly"})
    assert status == "disabled"


def test_compute_task_status_ok_when_consecutive_failures_is_int_zero(tmp_path):
    """PATCH sets consecutive_failures as int 0; must not be treated as error."""
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import _compute_task_status
        status = _compute_task_status({
            "enabled": "true",
            "last_run": "2026-06-28",
            "interval": "weekly",
            "consecutive_failures": 0,
        })
    assert status == "ok"


def test_read_housekeeping_tasks_scans_all_projects(tmp_path):
    """No project arg returns tasks from every project's housekeeping folder."""
    hk_a = tmp_path / "projects" / "proj-a" / "housekeeping"
    hk_b = tmp_path / "projects" / "proj-b" / "housekeeping"
    _write_task(hk_a, "2026-01-01-task-a.md", project="proj-a")
    _write_task(hk_b, "2026-01-02-task-b.md", project="proj-b")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import read_housekeeping_tasks
        result = read_housekeeping_tasks()
    assert len(result) == 2
    projects = {t["project"] for t in result}
    assert projects == {"proj-a", "proj-b"}


def test_update_housekeeping_fields_updates_last_run(tmp_path):
    hk_dir = tmp_path / "projects" / "myproj" / "housekeeping"
    _write_task(hk_dir, "2026-01-01-test.md")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import update_housekeeping_fields
        result = update_housekeeping_fields(
            "housekeeping-task", "myproj", "2026-01-01-test",
            {"last_run": "2026-06-27T10:00:00"},
        )
    assert result is True
    post = fm.load(hk_dir / "2026-01-01-test.md")
    assert post.metadata["last_run"] == "2026-06-27T10:00:00"


def test_delete_housekeeping_task_removes_file(tmp_path):
    hk_dir = tmp_path / "projects" / "myproj" / "housekeeping"
    _write_task(hk_dir, "2026-01-01-test.md")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import delete_housekeeping_task
        result = delete_housekeeping_task("myproj", "2026-01-01-test")
    assert result is True
    assert not (hk_dir / "2026-01-01-test.md").exists()
