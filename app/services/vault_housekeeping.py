"""Housekeeping vault functions — read/write housekeeping task entries."""

import logging
from datetime import datetime, timedelta

import frontmatter

import app.services.vault_cache as _vc

logger = logging.getLogger(__name__)

_HOUSEKEEPING_ALLOWED_FIELDS: dict[str, set[str]] = {
    "housekeeping-task": {"enabled", "last_run", "last_error", "consecutive_failures", "success_definition"},
    "housekeeping-heartbeat": {"last_run", "tasks_run", "tasks_failed", "tasks_skipped"},
}

_INTERVAL_THRESHOLDS: dict[str, int] = {
    "weekly": 6,
    "monthly": 27,
    "quarterly": 83,
    "annually": 364,
}


def update_housekeeping_fields(
    entry_type: str,
    project: str,
    filename: str,
    fields: dict,
) -> bool:
    """Overwrite allowed runtime fields on a housekeeping vault entry."""
    allowed = _HOUSEKEEPING_ALLOWED_FIELDS.get(entry_type)
    if allowed is None:
        return False

    if ".." in filename or "/" in filename or "\\" in filename:
        return False

    if ".." in project or "/" in project or "\\" in project:
        return False

    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    fname = filename if filename.endswith(".md") else f"{filename}.md"
    filepath = _vc.VAULT_PATH / "projects" / project / "housekeeping" / fname
    if not filepath.exists():
        return False

    temp_filepath = filepath.with_suffix(".tmp")
    try:
        post = frontmatter.load(filepath)
        for k, v in updates.items():
            post.metadata[k] = v
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        temp_filepath.replace(filepath)
        _vc._invalidate_cache()
        return True
    except Exception:
        logger.exception(
            "Failed to update housekeeping fields for %s/%s/%s",
            entry_type, project, filename,
        )
        temp_filepath.unlink(missing_ok=True)
        return False


def _compute_task_status(task: dict) -> str:
    if task.get("enabled") != "true":
        return "disabled"
    if task.get("consecutive_failures", "0") != "0":
        return "error"
    last_run = task.get("last_run", "null")
    if last_run == "null" or last_run is None:
        return "due" if task.get("interval") == "weekly" else "uninitialized"
    threshold = _INTERVAL_THRESHOLDS.get(task.get("interval", "weekly"), 6)
    try:
        last_run_dt = datetime.fromisoformat(last_run) if isinstance(last_run, str) else last_run
        days_since = (datetime.now() - last_run_dt.replace(tzinfo=None)).days
        if days_since >= threshold + 3:
            return "overdue"
        if days_since >= threshold:
            return "due"
        return "ok"
    except (ValueError, TypeError):
        return "unknown"


def _compute_next_run(task: dict) -> str | None:
    last_run = task.get("last_run", "null")
    if last_run == "null" or last_run is None:
        return None
    threshold = _INTERVAL_THRESHOLDS.get(task.get("interval", "weekly"), 6)
    try:
        last_run_dt = datetime.fromisoformat(last_run) if isinstance(last_run, str) else last_run
        return (last_run_dt.replace(tzinfo=None) + timedelta(days=threshold)).date().isoformat()
    except (ValueError, TypeError):
        return None


def read_housekeeping_tasks(project: str) -> list[dict]:
    """Read all housekeeping-task entries. Uncached — state changes frequently."""
    folder = _vc.VAULT_PATH / "projects" / project / "housekeeping"
    if not folder.exists():
        return []
    tasks = []
    for filepath in sorted(folder.glob("*.md")):
        if filepath.name == "last-run.md":
            continue
        try:
            post = frontmatter.load(filepath)
            if post.metadata.get("type") != "housekeeping-task":
                continue
            task = dict(post.metadata)
            task["filename"] = filepath.stem
            task["status"] = _compute_task_status(task)
            task["next_run"] = _compute_next_run(task)
            tasks.append(task)
        except Exception as e:
            logger.warning("Failed to parse housekeeping task %s: %s", filepath, e)
            continue
    return tasks


def read_housekeeping_heartbeat(project: str) -> dict:
    """Read the housekeeping heartbeat singleton. Returns safe defaults if missing."""
    _safe: dict = {
        "last_run": None,
        "tasks_run": "0",
        "tasks_failed": "0",
        "tasks_skipped": "0",
    }
    filepath = _vc.VAULT_PATH / "projects" / project / "housekeeping" / "last-run.md"
    if not filepath.exists():
        return _safe.copy()
    try:
        post = frontmatter.load(filepath)
        data = dict(post.metadata)
        if data.get("last_run") in ("null", None, ""):
            data["last_run"] = None
        return {**_safe, **data}
    except Exception:
        return _safe.copy()


def delete_housekeeping_task(project: str, filename: str) -> bool:
    """Delete a housekeeping task file. Returns True if deleted, False if not found."""
    folder = _vc.VAULT_PATH / "projects" / project / "housekeeping"
    filepath = folder / f"{filename}.md"
    if not filepath.exists():
        return False
    if filepath.name == "last-run.md":
        return False
    try:
        post = frontmatter.load(filepath)
        if post.metadata.get("type") != "housekeeping-task":
            return False
    except Exception:
        return False
    filepath.unlink()
    return True
