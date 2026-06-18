# IkeOS Housekeeping Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a housekeeping task management page to IkeOS and a heartbeat status widget on the dashboard, backed by direct vault reads and obsidian-capture API proxying for writes.

**Architecture:** New vault service functions read the `housekeeping/` folder directly (uncached). A new `housekeeping` Flask blueprint handles all routes at `/housekeeping`. The dashboard (`dashboard.html`) gets a heartbeat widget in its sidebar. The nav gains a top-level Housekeeping link.

**Tech Stack:** Python 3.11, Flask, python-frontmatter, pytest, Vanilla JS (fetch-based actions), IkeOS design system CSS

**Spec:** `docs/superpowers/specs/2026-06-17-housekeeping-design.md`

**Prerequisite:** obsidian-capture Plan 1 (`2026-06-17-housekeeping-extensions.md`) must be complete before Tasks 5 onward will work end-to-end. Tasks 1–4 (vault service + template) can be implemented and tested independently.

---

## Files

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/services/vault.py` | Add `read_housekeeping_tasks()`, `read_housekeeping_heartbeat()`, `_compute_task_status()`, `_compute_next_run()` |
| Create | `app/routes/housekeeping.py` | Blueprint: GET index, POST create/toggle/reset/run |
| Create | `app/templates/housekeeping.html` | Task management table + add-task form |
| Modify | `app/static/style.css` | Status pills + dashboard widget styles |
| Modify | `app/routes/browse.py` | Pass `housekeeping_heartbeat` + `hk_status` + `hk_age` to `/tasks` template |
| Modify | `app/templates/dashboard.html` | Add heartbeat widget in sidebar |
| Modify | `app/templates/base.html` | Add Housekeeping nav link |
| Modify | `app/__init__.py` | Register housekeeping blueprint |
| Create | `tests/test_housekeeping.py` | Tests for vault functions and routes |

---

### Task 1: vault — read_housekeeping_tasks and read_housekeeping_heartbeat

**Files:**
- Modify: `tests/test_housekeeping.py` (create)
- Modify: `app/services/vault.py`

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_housekeeping.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta


@pytest.fixture
def hk_vault(tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    return tmp_path


def _write_task(folder, filename, interval="weekly", enabled="true",
                last_run="null", consecutive_failures="0"):
    (folder / filename).write_text(
        f"---\n"
        f"type: housekeeping-task\n"
        f"title: {filename}\n"
        f"project: claude-config\n"
        f"interval: {interval}\n"
        f"enabled: '{enabled}'\n"
        f"last_run: '{last_run}'\n"
        f"last_error: 'null'\n"
        f"consecutive_failures: '{consecutive_failures}'\n"
        f"---\n"
    )


def _write_heartbeat(folder, last_run="null", tasks_run="0",
                     tasks_failed="0", tasks_skipped="0"):
    (folder / "last-run.md").write_text(
        f"---\n"
        f"type: housekeeping-heartbeat\n"
        f"last_run: '{last_run}'\n"
        f"tasks_run: '{tasks_run}'\n"
        f"tasks_failed: '{tasks_failed}'\n"
        f"tasks_skipped: '{tasks_skipped}'\n"
        f"---\n"
    )


# ── read_housekeeping_tasks ──

def test_read_housekeeping_tasks_empty_when_no_folder(tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import read_housekeeping_tasks
        assert read_housekeeping_tasks("claude-config") == []


def test_read_housekeeping_tasks_returns_tasks(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    _write_task(folder, "2026-06-17-prune-vault.md")
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_tasks
        tasks = read_housekeeping_tasks("claude-config")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "2026-06-17-prune-vault.md"
    assert tasks[0]["filename"] == "2026-06-17-prune-vault"
    assert "status" in tasks[0]
    assert "next_run" in tasks[0]


def test_read_housekeeping_tasks_skips_heartbeat(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    _write_heartbeat(folder)
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_tasks
        tasks = read_housekeeping_tasks("claude-config")
    assert tasks == []


def test_read_housekeeping_tasks_skips_non_task_types(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    (folder / "other.md").write_text(
        "---\ntype: idea\ntitle: Other\nproject: claude-config\n---\n"
    )
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_tasks
        tasks = read_housekeeping_tasks("claude-config")
    assert tasks == []


# ── read_housekeeping_heartbeat ──

def test_read_housekeeping_heartbeat_missing_file_returns_defaults(tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import read_housekeeping_heartbeat
        hb = read_housekeeping_heartbeat("claude-config")
    assert hb["last_run"] is None
    assert hb["tasks_run"] == "0"
    assert hb["tasks_failed"] == "0"
    assert hb["tasks_skipped"] == "0"


def test_read_housekeeping_heartbeat_reads_file(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    _write_heartbeat(folder, last_run="2026-06-14T12:00:00",
                     tasks_run="5", tasks_failed="1", tasks_skipped="2")
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_heartbeat
        hb = read_housekeeping_heartbeat("claude-config")
    assert hb["last_run"] == "2026-06-14T12:00:00"
    assert hb["tasks_run"] == "5"
    assert hb["tasks_failed"] == "1"
    assert hb["tasks_skipped"] == "2"


def test_read_housekeeping_heartbeat_null_string_becomes_none(hk_vault):
    folder = hk_vault / "projects" / "claude-config" / "housekeeping"
    _write_heartbeat(folder, last_run="null")
    with patch("app.services.vault.VAULT_PATH", hk_vault):
        from app.services.vault import read_housekeeping_heartbeat
        hb = read_housekeeping_heartbeat("claude-config")
    assert hb["last_run"] is None


# ── _compute_task_status ──

def test_compute_task_status_disabled():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        task = {"enabled": "false", "consecutive_failures": "0",
                "last_run": "null", "interval": "weekly"}
        assert _compute_task_status(task) == "disabled"


def test_compute_task_status_error():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        task = {"enabled": "true", "consecutive_failures": "2",
                "last_run": "2026-06-16T12:00:00", "interval": "weekly"}
        assert _compute_task_status(task) == "error"


def test_compute_task_status_uninitialized_monthly():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": "null", "interval": "monthly"}
        assert _compute_task_status(task) == "uninitialized"


def test_compute_task_status_due_weekly_no_last_run():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": "null", "interval": "weekly"}
        assert _compute_task_status(task) == "due"


def test_compute_task_status_due():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        last_run = (datetime.now() - timedelta(days=7)).isoformat()
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": last_run, "interval": "weekly"}
        assert _compute_task_status(task) == "due"


def test_compute_task_status_overdue():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        last_run = (datetime.now() - timedelta(days=12)).isoformat()
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": last_run, "interval": "weekly"}
        assert _compute_task_status(task) == "overdue"


def test_compute_task_status_ok():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_task_status
        last_run = (datetime.now() - timedelta(days=2)).isoformat()
        task = {"enabled": "true", "consecutive_failures": "0",
                "last_run": last_run, "interval": "weekly"}
        assert _compute_task_status(task) == "ok"


# ── _compute_next_run ──

def test_compute_next_run_null_returns_none():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_next_run
        task = {"last_run": "null", "interval": "weekly"}
        assert _compute_next_run(task) is None


def test_compute_next_run_weekly():
    with patch("app.services.vault.VAULT_PATH", Path("/tmp")):
        from app.services.vault import _compute_next_run
        task = {"last_run": "2026-06-10T12:00:00", "interval": "weekly"}
        result = _compute_next_run(task)
        assert result == "2026-06-16"  # 2026-06-10 + 6 days
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /mnt/c/Server/projects/ikeos
docker.exe compose exec obsidian-capture pytest tests/test_housekeeping.py -v 2>/dev/null || \
python3 -m pytest tests/test_housekeeping.py -v
```

Expected: FAIL with `ImportError` (functions not defined)

- [ ] **Step 1.3: Add vault functions to `app/services/vault.py`**

Add `timedelta` to the existing datetime import at the top of vault.py:

```python
from datetime import datetime, timedelta, timezone
```

Add these functions at the end of `app/services/vault.py`:

```python
# ── Housekeeping ──────────────────────────────────────────────────────────────

_INTERVAL_THRESHOLDS: dict[str, int] = {
    "weekly": 6,
    "monthly": 27,
    "quarterly": 83,
    "annually": 364,
}


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
    folder = VAULT_PATH / "projects" / project / "housekeeping"
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
        except Exception:
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
    filepath = VAULT_PATH / "projects" / project / "housekeeping" / "last-run.md"
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
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_housekeeping.py -v
```

Expected: All pass

- [ ] **Step 1.5: Commit**

```bash
git add app/services/vault.py tests/test_housekeeping.py
git commit -m "feat: add read_housekeeping_tasks and read_housekeeping_heartbeat to vault service"
```

---

### Task 2: housekeeping blueprint — GET /housekeeping

**Files:**
- Modify: `tests/test_housekeeping.py`
- Create: `app/routes/housekeeping.py`
- Modify: `app/__init__.py`

- [ ] **Step 2.1: Write the failing tests**

Append to `tests/test_housekeeping.py`:

```python
# ── Route tests ──

def test_housekeeping_index_renders(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"Housekeeping" in resp.data


def test_housekeeping_index_shows_tasks(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    folder = tmp_path / "projects" / "claude-config" / "housekeeping"
    folder.mkdir(parents=True)
    _write_task(folder, "2026-06-17-prune-vault.md")
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"2026-06-17-prune-vault" in resp.data


def test_housekeeping_index_empty_state(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"No tasks" in resp.data
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_housekeeping.py -k "index" -v
```

Expected: FAIL with 404 (route doesn't exist)

- [ ] **Step 2.3: Create `app/routes/housekeeping.py`**

```python
import os
import requests
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify

bp = Blueprint("housekeeping", __name__)

CAPTURE_URL = os.environ.get("CAPTURE_URL", "http://host.docker.internal:5009")
CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "")
SESSION_MANAGER_URL = "http://host.docker.internal:5010"


def _capture_headers() -> dict:
    return {"X-Capture-Token": CAPTURE_TOKEN}


def _age_str(last_run: str | None) -> str:
    if not last_run or last_run == "null":
        return "Never"
    try:
        dt = datetime.fromisoformat(last_run)
        days = (datetime.now() - dt.replace(tzinfo=None)).days
        if days == 0:
            return "Today"
        if days == 1:
            return "Yesterday"
        return f"{days} days ago"
    except (ValueError, TypeError):
        return "Unknown"


def _widget_status(heartbeat: dict) -> str:
    last_run = heartbeat.get("last_run")
    if not last_run:
        return "overdue"
    try:
        dt = datetime.fromisoformat(last_run)
        if (datetime.now() - dt.replace(tzinfo=None)).days > 9:
            return "overdue"
    except (ValueError, TypeError):
        return "overdue"
    if heartbeat.get("tasks_failed", "0") != "0":
        return "failed"
    return "ok"


@bp.route("/housekeeping")
def index():
    from app.services.vault import read_housekeeping_tasks, read_housekeeping_heartbeat
    tasks = read_housekeeping_tasks("claude-config")
    heartbeat = read_housekeeping_heartbeat("claude-config")
    return render_template(
        "housekeeping.html",
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
    )
```

- [ ] **Step 2.4: Register the blueprint in `app/__init__.py`**

Add to the imports and register call:

```python
from app.routes.housekeeping import bp as housekeeping_bp
app.register_blueprint(housekeeping_bp)
```

- [ ] **Step 2.5: Create minimal `app/templates/housekeeping.html`** (full template in Task 4)

```html
{% extends "base.html" %}
{% block title %}Housekeeping{% endblock %}

{% block content %}
<div class="settings-page">
  <header class="page-header">
    <span class="ike-eyebrow">System</span>
    <h1>Housekeeping</h1>
  </header>
  {% if tasks %}
    {% for task in tasks %}
      <p>{{ task.filename }}</p>
    {% endfor %}
  {% else %}
    <p class="empty">No tasks defined yet.</p>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2.6: Run tests to verify they pass**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_housekeeping.py -k "index" -v
```

Expected: PASS

- [ ] **Step 2.7: Commit**

```bash
git add app/routes/housekeeping.py app/__init__.py app/templates/housekeeping.html tests/test_housekeeping.py
git commit -m "feat: add housekeeping blueprint with GET /housekeeping"
```

---

### Task 3: housekeeping blueprint — write routes

**Files:**
- Modify: `tests/test_housekeeping.py`
- Modify: `app/routes/housekeeping.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_housekeeping.py`:

```python
from unittest.mock import patch as mock_patch, MagicMock


def test_create_task_success(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"ok": True}

    with mock_patch("app.routes.housekeeping.requests.post", return_value=mock_resp):
        resp = client.post("/housekeeping/tasks", data={
            "title": "Prune old entries",
            "interval": "weekly",
            "success_definition": "All entries older than 90 days removed.",
        })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_create_task_missing_title_returns_400(client):
    resp = client.post("/housekeeping/tasks", data={
        "interval": "weekly",
        "success_definition": "Done.",
    })
    assert resp.status_code == 400


def test_create_task_missing_success_definition_returns_400(client):
    resp = client.post("/housekeeping/tasks", data={
        "title": "Test task",
        "interval": "weekly",
    })
    assert resp.status_code == 400


def test_toggle_task_disables(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    folder = tmp_path / "projects" / "claude-config" / "housekeeping"
    folder.mkdir(parents=True)
    _write_task(folder, "2026-06-17-test-task.md", enabled="true")

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"message": "Updated"}

    with mock_patch("app.routes.housekeeping.requests.patch", return_value=mock_resp):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/toggle")
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] == "false"


def test_toggle_task_enables(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    folder = tmp_path / "projects" / "claude-config" / "housekeeping"
    folder.mkdir(parents=True)
    _write_task(folder, "2026-06-17-test-task.md", enabled="false")

    mock_resp = MagicMock()
    mock_resp.ok = True

    with mock_patch("app.routes.housekeeping.requests.patch", return_value=mock_resp):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/toggle")
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] == "true"


def test_toggle_task_not_found_returns_404(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)
    resp = client.post("/housekeeping/tasks/nonexistent-task/toggle")
    assert resp.status_code == 404


def test_reset_task_success(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    mock_resp = MagicMock()
    mock_resp.ok = True

    with mock_patch("app.routes.housekeeping.requests.patch", return_value=mock_resp):
        resp = client.post("/housekeeping/tasks/2026-06-17-some-task/reset")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_run_task_creates_session(client):
    create_mock = MagicMock()
    create_mock.ok = True
    create_mock.json.return_value = {"id": "session-abc123"}

    cmd_mock = MagicMock()
    cmd_mock.ok = True

    with mock_patch("app.routes.housekeeping.requests.post",
                    side_effect=[create_mock, cmd_mock]):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/run")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["session_id"] == "session-abc123"


def test_run_task_session_manager_unreachable(client):
    with mock_patch("app.routes.housekeeping.requests.post",
                    side_effect=requests.RequestException("timeout")):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/run")
    assert resp.status_code == 502
```

Also add `import requests` at the top of `tests/test_housekeeping.py`.

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_housekeeping.py -k "create_task or toggle or reset or run_task" -v
```

Expected: FAIL with 404/405

- [ ] **Step 3.3: Add write routes to `app/routes/housekeeping.py`**

Add these routes to the existing blueprint file (after the `index` route):

```python
@bp.route("/housekeeping/tasks", methods=["POST"])
def create_task():
    title = request.form.get("title", "").strip()
    interval = request.form.get("interval", "weekly")
    success_definition = request.form.get("success_definition", "").strip()

    if not title or not success_definition:
        return jsonify({"error": "title and success_definition are required"}), 400
    if interval not in ("weekly", "monthly", "quarterly", "annually"):
        return jsonify({"error": "invalid interval"}), 400

    try:
        resp = requests.post(
            f"{CAPTURE_URL}/capture/json",
            json={
                "type": "housekeeping-task",
                "project": "claude-config",
                "title": title,
                "interval": interval,
                "success_definition": success_definition,
            },
            timeout=5,
        )
        if not resp.ok:
            return jsonify({"error": "Failed to create task"}), 502
    except requests.RequestException:
        return jsonify({"error": "obsidian-capture unreachable"}), 502

    return jsonify({"ok": True}), 200


@bp.route("/housekeeping/tasks/<filename>/toggle", methods=["POST"])
def toggle_task(filename: str):
    from app.services.vault import read_housekeeping_tasks
    tasks = read_housekeeping_tasks("claude-config")
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    new_enabled = "false" if task.get("enabled") == "true" else "true"
    try:
        resp = requests.patch(
            f"{CAPTURE_URL}/entries/housekeeping",
            json={
                "project": "claude-config",
                "type": "housekeeping-task",
                "filename": filename,
                "fields": {"enabled": new_enabled},
            },
            headers=_capture_headers(),
            timeout=5,
        )
        if not resp.ok:
            return jsonify({"error": "Failed to update task"}), 502
    except requests.RequestException:
        return jsonify({"error": "obsidian-capture unreachable"}), 502

    return jsonify({"ok": True, "enabled": new_enabled}), 200


@bp.route("/housekeeping/tasks/<filename>/reset", methods=["POST"])
def reset_task(filename: str):
    try:
        resp = requests.patch(
            f"{CAPTURE_URL}/entries/housekeeping",
            json={
                "project": "claude-config",
                "type": "housekeeping-task",
                "filename": filename,
                "fields": {"last_run": "null", "consecutive_failures": "0"},
            },
            headers=_capture_headers(),
            timeout=5,
        )
        if not resp.ok:
            return jsonify({"error": "Failed to reset timer"}), 502
    except requests.RequestException:
        return jsonify({"error": "obsidian-capture unreachable"}), 502

    return jsonify({"ok": True}), 200


@bp.route("/housekeeping/tasks/<filename>/run", methods=["POST"])
def run_task(filename: str):
    session_name = f"housekeeping-{filename}"
    command = f"/housekeeping run in scheduled mode {filename}"
    try:
        create_resp = requests.post(
            f"{SESSION_MANAGER_URL}/sessions",
            json={"name": session_name},
            timeout=5,
        )
        if not create_resp.ok:
            return jsonify({"error": "Failed to create session"}), 502
        session_id = create_resp.json().get("id")
        if not session_id:
            return jsonify({"error": "No session ID returned"}), 502

        cmd_resp = requests.post(
            f"{SESSION_MANAGER_URL}/sessions/{session_id}/command",
            json={"command": command},
            timeout=5,
        )
        if not cmd_resp.ok:
            return jsonify({"error": "Session created but command failed"}), 502
    except requests.RequestException:
        return jsonify({"error": "Session manager unreachable"}), 502

    return jsonify({"ok": True, "session_id": session_id}), 200
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_housekeeping.py -k "create_task or toggle or reset or run_task" -v
```

Expected: PASS

- [ ] **Step 3.5: Run full test suite**

```bash
docker.exe compose exec obsidian-capture pytest tests/ -v
```

Expected: All pass

- [ ] **Step 3.6: Commit**

```bash
git add app/routes/housekeeping.py tests/test_housekeeping.py
git commit -m "feat: add housekeeping write routes — create, toggle, reset, run"
```

---

### Task 4: full housekeeping template + CSS

**Files:**
- Modify: `app/templates/housekeeping.html` (replace the stub)
- Modify: `app/static/style.css`

- [ ] **Step 4.1: Replace `app/templates/housekeeping.html` with the full template**

```html
{% extends "base.html" %}
{% block title %}Housekeeping{% endblock %}

{% block content %}
<div class="settings-page">

  <header class="page-header">
    <span class="ike-eyebrow">System</span>
    <h1>Housekeeping</h1>
    <p class="page-subtitle">Automated maintenance tasks — reads definitions from the claude-config vault.</p>
  </header>

  <section>
    <div class="ike-eyebrow">Tasks <span class="eyebrow-count">/ {{ tasks | length }}</span></div>
    {% if tasks %}
    <div class="hk-table-wrap">
      <table class="hk-table">
        <thead>
          <tr>
            <th class="hk-col-name">Name</th>
            <th class="hk-col-interval">Interval</th>
            <th class="hk-col-status">Status</th>
            <th class="hk-col-date">Last Run</th>
            <th class="hk-col-date">Next Due</th>
            <th class="hk-col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for task in tasks %}
          <tr>
            <td class="hk-name">{{ task.title }}</td>
            <td class="hk-interval">{{ task.interval }}</td>
            <td><span class="hk-pill hk-pill--{{ task.status }}">{{ task.status }}</span></td>
            <td class="hk-date">{{ task.last_run if task.last_run and task.last_run != 'null' else '—' }}</td>
            <td class="hk-date">{{ task.next_run or '—' }}</td>
            <td class="hk-actions">
              <button class="pill"
                      onclick="toggleTask('{{ task.filename | forceescape }}', this)"
                      data-enabled="{{ task.enabled }}">
                {{ 'Disable' if task.enabled == 'true' else 'Enable' }}
              </button>
              <button class="pill"
                      onclick="resetTask('{{ task.filename | forceescape }}', this)">Reset</button>
              <button class="pill pill-primary-filled"
                      onclick="runTask('{{ task.filename | forceescape }}', this)">Run</button>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <p class="empty">No tasks defined yet. Add one below.</p>
    {% endif %}
  </section>

  <section class="hk-add-section">
    <div class="ike-eyebrow">Add Task</div>
    <form class="hk-add-form" id="addTaskForm">
      <div class="hk-form-row">
        <label for="hk-title">Title</label>
        <input type="text" id="hk-title" name="title" required
               placeholder="e.g. Prune stale vault entries">
      </div>
      <div class="hk-form-row">
        <label for="hk-interval">Interval</label>
        <select id="hk-interval" name="interval">
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
          <option value="quarterly">Quarterly</option>
          <option value="annually">Annually</option>
        </select>
      </div>
      <div class="hk-form-row">
        <label for="hk-success">Success Definition</label>
        <textarea id="hk-success" name="success_definition" required rows="3"
                  placeholder="Describe what success looks like — passed to the judge subagent."></textarea>
      </div>
      <div class="hk-form-footer">
        <button type="submit" class="pill pill-primary-filled">Add Task</button>
        <span class="hk-form-msg" id="addTaskMsg"></span>
      </div>
    </form>
  </section>

</div>

<script>
async function toggleTask(filename, btn) {
  btn.disabled = true;
  try {
    const resp = await fetch(`/housekeeping/tasks/${encodeURIComponent(filename)}/toggle`,
                             {method: 'POST'});
    if (resp.ok) {
      location.reload();
    } else {
      btn.disabled = false;
      alert('Failed to toggle task.');
    }
  } catch (e) {
    btn.disabled = false;
  }
}

async function resetTask(filename, btn) {
  btn.disabled = true;
  try {
    const resp = await fetch(`/housekeeping/tasks/${encodeURIComponent(filename)}/reset`,
                             {method: 'POST'});
    if (resp.ok) {
      location.reload();
    } else {
      btn.disabled = false;
      alert('Failed to reset timer.');
    }
  } catch (e) {
    btn.disabled = false;
  }
}

async function runTask(filename, btn) {
  btn.disabled = true;
  btn.textContent = '…';
  try {
    const resp = await fetch(`/housekeeping/tasks/${encodeURIComponent(filename)}/run`,
                             {method: 'POST'});
    if (resp.ok) {
      const data = await resp.json();
      btn.textContent = 'Launched ↗';
      btn.onclick = () => window.location.href = '/agents';
      btn.disabled = false;
    } else {
      btn.textContent = 'Run';
      btn.disabled = false;
      alert('Failed to launch session.');
    }
  } catch (e) {
    btn.textContent = 'Run';
    btn.disabled = false;
  }
}

document.getElementById('addTaskForm').addEventListener('submit', async function(e) {
  e.preventDefault();
  const msg = document.getElementById('addTaskMsg');
  msg.textContent = '';
  const resp = await fetch('/housekeeping/tasks', {
    method: 'POST',
    body: new FormData(e.target),
  });
  if (resp.ok) {
    msg.textContent = 'Task added.';
    e.target.reset();
    setTimeout(() => location.reload(), 800);
  } else {
    const err = await resp.json().catch(() => ({}));
    msg.textContent = err.error || 'Failed to add task.';
  }
});
</script>
{% endblock %}
```

- [ ] **Step 4.2: Add CSS to `app/static/style.css`**

Append to the end of `app/static/style.css`:

```css
/* ── Housekeeping page ──────────────────────────────────────── */

.hk-table-wrap {
  border: 1px solid var(--border-subtle, #1e1e1e);
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
  margin-bottom: var(--space-8, 2rem);
}

.hk-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-body-sm, 0.83rem);
}

.hk-table thead {
  background: var(--bg-surface, #0e0e0e);
  border-bottom: 1px solid var(--border-subtle, #1e1e1e);
}

.hk-table th {
  text-align: left;
  padding: 0.45rem 0.85rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-tertiary, #8B82A4);
}

.hk-table td {
  padding: 0.55rem 0.85rem;
  vertical-align: middle;
  border-bottom: 1px solid var(--border-subtle, #161616);
  color: var(--text-secondary, #C8C0DA);
}

.hk-table tr:last-child td { border-bottom: none; }
.hk-table tr:hover td { background: var(--bg-hover, rgba(124,58,237,0.05)); }

.hk-col-name     { width: 35%; }
.hk-col-interval { width: 10%; }
.hk-col-status   { width: 10%; }
.hk-col-date     { width: 14%; }
.hk-col-actions  { width: 17%; }

.hk-name { color: var(--text-primary, #EDE9F8); font-weight: 500; }
.hk-date { font-size: 0.78rem; color: var(--text-tertiary, #8B82A4); }
.hk-actions { display: flex; gap: 6px; flex-wrap: wrap; }

/* Status pills */
.hk-pill {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 4px;
  line-height: 1.7;
}
.hk-pill--ok           { background: rgba(34,197,94,0.12);  color: #4ADE80; border: 1px solid rgba(34,197,94,0.25); }
.hk-pill--due          { background: rgba(245,158,11,0.12); color: #FCD34D; border: 1px solid rgba(245,158,11,0.25); }
.hk-pill--overdue      { background: rgba(239,68,68,0.12);  color: #F87171; border: 1px solid rgba(239,68,68,0.25); }
.hk-pill--error        { background: rgba(239,68,68,0.12);  color: #F87171; border: 1px solid rgba(239,68,68,0.25); }
.hk-pill--disabled     { background: rgba(139,130,164,0.1); color: #8B82A4; border: 1px solid rgba(139,130,164,0.2); }
.hk-pill--uninitialized{ background: rgba(139,130,164,0.1); color: #8B82A4; border: 1px solid rgba(139,130,164,0.2); }

/* Add task form */
.hk-add-section { margin-top: var(--space-8, 2rem); }

.hk-add-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 1rem);
  max-width: 560px;
  margin-top: var(--space-4, 1rem);
}

.hk-form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hk-form-row label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary, #8B82A4);
}

.hk-form-row input,
.hk-form-row select,
.hk-form-row textarea {
  background: var(--bg-inset, #111);
  border: 1px solid var(--border-subtle, #1e1e1e);
  border-radius: var(--radius-sm, 6px);
  color: var(--text-primary, #EDE9F8);
  padding: 0.45rem 0.65rem;
  font-size: 0.85rem;
  font-family: inherit;
}

.hk-form-row input:focus,
.hk-form-row select:focus,
.hk-form-row textarea:focus {
  outline: none;
  border-color: var(--ike-soft-lavender, #B497FF);
}

.hk-form-row textarea { resize: vertical; }

.hk-form-footer {
  display: flex;
  align-items: center;
  gap: var(--space-3, 0.5rem);
}

.hk-form-msg {
  font-size: 0.8rem;
  color: var(--text-tertiary, #8B82A4);
}

/* ── Dashboard housekeeping widget ──────────────────────────── */

.hk-widget {
  margin-top: var(--space-6, 1.5rem);
  padding: var(--space-4, 1rem);
  background: var(--bg-surface, #0e0e0e);
  border: 1px solid var(--border-subtle, #1e1e1e);
  border-radius: var(--radius-md, 8px);
}

.hk-widget-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3, 0.5rem);
  margin-bottom: 0.35rem;
}

.hk-widget-label {
  font-size: 0.78rem;
  color: var(--text-secondary, #C8C0DA);
}

.hk-widget-age {
  font-size: 0.78rem;
  color: var(--text-tertiary, #8B82A4);
}

.hk-widget-summary {
  font-size: 0.75rem;
  color: var(--text-tertiary, #8B82A4);
  margin-bottom: 0.5rem;
}

.hk-widget-link {
  font-size: 0.78rem;
  color: var(--ike-soft-lavender, #B497FF);
  text-decoration: none;
}

.hk-widget-link:hover { text-decoration: underline; }

/* Widget status pills */
.hk-widget-status {
  display: inline-block;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1.7;
}
.hk-widget-status--ok      { background: rgba(34,197,94,0.12);  color: #4ADE80; border: 1px solid rgba(34,197,94,0.25); }
.hk-widget-status--overdue { background: rgba(245,158,11,0.12); color: #FCD34D; border: 1px solid rgba(245,158,11,0.25); }
.hk-widget-status--failed  { background: rgba(239,68,68,0.12);  color: #F87171; border: 1px solid rgba(239,68,68,0.25); }
```

- [ ] **Step 4.3: Rebuild CSS bundle**

```bash
cd /mnt/c/Server/projects/ikeos
docker.exe compose exec obsidian-capture python3 scripts/bundle_css.py 2>/dev/null || python3 scripts/bundle_css.py
```

- [ ] **Step 4.4: Commit**

```bash
git add app/templates/housekeeping.html app/static/style.css app/static/bundle.css
git commit -m "feat: full housekeeping template and CSS"
```

---

### Task 5: nav link

**Files:**
- Modify: `app/templates/base.html`

- [ ] **Step 5.1: Add Housekeeping nav link to `app/templates/base.html`**

Find the Skills nav link:

```html
<a href="{{ url_for('browse.skills') }}"    class="nav-link {% if request.endpoint == 'browse.skills' %}is-active{% endif %}">Skills</a>
```

Add the Housekeeping link immediately after it:

```html
      <a href="{{ url_for('housekeeping.index') }}" class="nav-link {% if request.endpoint == 'housekeeping.index' %}is-active{% endif %}">Housekeeping</a>
```

- [ ] **Step 5.2: Verify the nav renders**

```bash
docker.exe compose exec obsidian-capture pytest tests/ -v -k "not housekeeping"
```

Expected: All existing tests pass

- [ ] **Step 5.3: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: add Housekeeping nav link"
```

---

### Task 6: dashboard heartbeat widget

**Files:**
- Modify: `app/routes/browse.py`
- Modify: `app/templates/dashboard.html`

- [ ] **Step 6.1: Add heartbeat data to the `/tasks` route in `app/routes/browse.py`**

Find the `tasks()` function. Add the heartbeat read and pass it to the template. The full updated function:

```python
@bp.route("/tasks")
def tasks():
    projects = get_projects_with_meta()
    all_entries = read_entries()

    project_stats = {}
    for p in projects:
        slug = p["slug"]
        p_entries = [e for e in all_entries if e.get("project") == slug]
        active = [e for e in p_entries if e.get("status") in ACTIVE_STATUSES]
        project_stats[slug] = {
            "bugs": len([e for e in active if e.get("type") == "bug"]),
            "ideas": len([e for e in active if e.get("type") == "idea"]),
            "notes": len([e for e in active if e.get("type") == "note"]),
            "new": len([e for e in p_entries if e.get("status") == "new"]),
        }

    in_flight = [e for e in all_entries if e.get("status") == "in-progress"]
    needs_triage = [e for e in all_entries if e.get("status") == "new"]

    from app.services.vault import read_housekeeping_heartbeat
    from app.routes.housekeeping import _age_str, _widget_status
    heartbeat = read_housekeeping_heartbeat("claude-config")

    return render_template(
        "dashboard.html",
        projects=projects,
        project_stats=project_stats,
        in_flight=in_flight,
        needs_triage=needs_triage,
        housekeeping_heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
    )
```

- [ ] **Step 6.2: Add the heartbeat widget to `app/templates/dashboard.html`**

Find the closing `</section>` tag of the projects section in `dashboard-sidebar` (after the project-grid block). Add the widget immediately after it, before `</div><!-- dashboard-sidebar -->`:

```html
    <!-- ── Housekeeping heartbeat widget ── -->
    <section>
      <div class="ike-eyebrow">Housekeeping</div>
      <div class="hk-widget">
        <div class="hk-widget-row">
          <span class="hk-widget-label">Last run: <span class="hk-widget-age">{{ hk_age }}</span></span>
          <span class="hk-widget-status hk-widget-status--{{ hk_status }}">{{ hk_status }}</span>
        </div>
        <div class="hk-widget-summary">
          {{ housekeeping_heartbeat.tasks_run }} run ·
          {{ housekeeping_heartbeat.tasks_failed }} failed ·
          {{ housekeeping_heartbeat.tasks_skipped }} skipped
        </div>
        <a href="{{ url_for('housekeeping.index') }}" class="hk-widget-link">Manage tasks →</a>
      </div>
    </section>
```

- [ ] **Step 6.3: Run the existing browse tests**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_browse.py -v
```

Expected: All pass (the dashboard still renders fine; heartbeat returns safe defaults if vault files don't exist)

- [ ] **Step 6.4: Commit**

```bash
git add app/routes/browse.py app/templates/dashboard.html
git commit -m "feat: add housekeeping heartbeat widget to dashboard"
```

---

### Task 7: rebuild and smoke test

**Files:** None (container operations only)

- [ ] **Step 7.1: Rebuild and restart the IkeOS container**

```bash
cd /mnt/c/Server/projects/ikeos
docker.exe compose up --build -d obsidian-capture
```

Wait ~10 seconds.

- [ ] **Step 7.2: Check container health**

```bash
docker.exe compose ps
curl -s http://homeautomation:5009/health
```

Expected: `ok`

- [ ] **Step 7.3: Smoke test — navigate to Housekeeping page**

Open `http://homeautomation:5009/housekeeping` in a browser.

Expected: Page renders with "No tasks defined yet." (vault files don't exist yet)

- [ ] **Step 7.4: Smoke test — navigate to Dashboard**

Open `http://homeautomation:5009/tasks`.

Expected: Housekeeping widget appears in sidebar showing "Never" and "overdue" status.

- [ ] **Step 7.5: Smoke test — nav link works**

Click Housekeeping in the nav from any page. Expected: navigates to `/housekeeping`, link is highlighted as active.

- [ ] **Step 7.6: Seed the vault (requires obsidian-capture Plan 1 complete)**

Once obsidian-capture Plan 1 is shipped, create the heartbeat singleton and at least one task:

```bash
# Create heartbeat singleton
curl -s -X POST http://localhost:5009/capture/json \
  -H "Content-Type: application/json" \
  -d '{"type":"housekeeping-heartbeat","project":"claude-config","title":"Housekeeping Last Run"}'

# Create first real task (example)
curl -s -X POST http://localhost:5009/capture/json \
  -H "Content-Type: application/json" \
  -d '{"type":"housekeeping-task","project":"claude-config","title":"Review weak signals","interval":"weekly","success_definition":"All signals older than 45 days reviewed and either promoted or cleared."}'
```

Reload the Housekeeping page — task should appear. Reload Dashboard — widget should show real data.
