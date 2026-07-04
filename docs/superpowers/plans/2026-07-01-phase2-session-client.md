# Phase 2 Session Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralise all IkeOS→session-manager HTTP calls into `app/services/session_client.py` so every call site gets consistent error handling, typed return values, and automatic `session.created` metric emission.

**Architecture:** A new `session_client.py` service provides a single `create_session()` function returning a `SessionResult` dataclass. Four call sites in `scheduler.py` and `housekeeping.py` are migrated to use it; the `requests` import is removed from `scheduler.py` (no longer needed there). All test mock targets shift from `app.routes.housekeeping.requests.post` / `app.services.scheduler.requests.post` to `app.services.session_client.requests.post`.

**Tech Stack:** Python 3.11, dataclasses, requests, pytest, Docker (`docker exec ikeos pytest`)

---

## File Map

| Action | File |
|---|---|
| **Create** | `app/services/session_client.py` |
| **Create** | `tests/test_session_client.py` |
| **Modify** | `app/services/scheduler.py` — migrate `trigger_now()`, remove top-level `import requests` |
| **Modify** | `app/routes/housekeeping.py` — add import, migrate `run_task()`, `blog_draft_publish()`, `blog_draft_rewrite()` |
| **Modify** | `tests/test_scheduler.py` — update mock targets in `trigger_now` tests |
| **Modify** | `tests/test_housekeeping.py` — update mock targets in `run_task` tests, add publish/rewrite session tests |

---

## Task 1: Create `session_client.py` + tests

**Files:**
- Create: `app/services/session_client.py`
- Create: `tests/test_session_client.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_session_client.py`:

```python
import pytest
import requests as req_lib
from unittest.mock import MagicMock, patch


def test_create_session_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "abc"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event"):
            from app.services.session_client import create_session
            result = create_session(name="test", project="proj", project_dir="/tmp")
    assert result.ok is True
    assert result.session_id == "abc"
    assert result.already_running is False


def test_create_session_409_returns_already_running(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 409
    mock_resp.json.return_value = {"session": {"id": "existing"}}
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event") as mock_emit:
            from app.services.session_client import create_session
            result = create_session(name="test", project="proj", project_dir="/tmp")
    assert result.already_running is True
    assert result.session_id == "existing"
    assert result.ok is True
    mock_emit.assert_not_called()


def test_create_session_non_ok_returns_error(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 500
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event") as mock_emit:
            from app.services.session_client import create_session
            result = create_session(name="test", project="proj", project_dir="/tmp")
    assert result.ok is False
    assert "500" in result.error
    mock_emit.assert_not_called()


def test_create_session_timeout_returns_error(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.post",
               side_effect=req_lib.RequestException("timeout")):
        from app.services.session_client import create_session
        result = create_session(name="test", project="proj", project_dir="/tmp")
    assert result.ok is False
    assert "unreachable" in result.error


def test_create_session_emits_metric_on_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "metric-sess"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event") as mock_emit:
            from app.services.session_client import create_session
            create_session(name="myname", project="myproj", project_dir="/tmp")
    mock_emit.assert_called_once_with(
        "session.created",
        {"session_id": "metric-sess", "name": "myname", "project": "myproj"},
    )


def test_create_session_no_metric_on_failure(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 503
    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event") as mock_emit:
            from app.services.session_client import create_session
            create_session(name="test", project="proj", project_dir="/tmp")
    mock_emit.assert_not_called()
```

- [x] **Step 2: Run tests to verify they fail**

```bash
docker exec ikeos pytest tests/test_session_client.py -v
```

Expected: all 6 FAIL with `ModuleNotFoundError` or `ImportError` (file doesn't exist yet)

- [x] **Step 3: Create `app/services/session_client.py`**

```python
import logging
import os
from dataclasses import dataclass

import requests

from app.services.metrics import append_event

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    session_id: str
    already_running: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def create_session(
    *,
    name: str,
    project: str,
    project_dir: str,
    initial_command: str | None = None,
) -> SessionResult:
    sm_url = os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")
    try:
        response = requests.post(
            f"{sm_url}/sessions",
            json={
                "name": name,
                "project": project,
                "project_dir": project_dir,
                "initial_command": initial_command,
            },
            timeout=5,
        )
    except requests.RequestException:
        return SessionResult(session_id="", error="Session manager unreachable")

    if response.status_code == 409:
        existing_id = response.json().get("session", {}).get("id", "")
        return SessionResult(session_id=existing_id, already_running=True)

    if not response.ok:
        return SessionResult(
            session_id="", error=f"Session manager returned {response.status_code}"
        )

    session_id = response.json().get("id", "")
    try:
        append_event(
            "session.created",
            {"session_id": session_id, "name": name, "project": project},
        )
    except Exception:
        logger.warning("Failed to emit session.created metric for session %s", session_id)

    return SessionResult(session_id=session_id)
```

- [x] **Step 4: Run tests to verify they pass**

```bash
docker exec ikeos pytest tests/test_session_client.py -v
```

Expected: all 6 PASS

- [x] **Step 5: Run full test suite to verify no regressions**

```bash
docker exec ikeos pytest -v
```

Expected: all existing tests still PASS

- [x] **Step 6: Commit**

```bash
git add app/services/session_client.py tests/test_session_client.py
git commit -m "feat: add session_client service with SessionResult dataclass"
```

---

## Task 2: Migrate `trigger_now()` in `scheduler.py` + update tests

**Files:**
- Modify: `app/services/scheduler.py`
- Modify: `tests/test_scheduler.py`

- [x] **Step 1: Update the trigger_now tests before touching the implementation**

In `tests/test_scheduler.py`, replace every occurrence of `patch("app.services.scheduler.requests.post", ...)` with `patch("app.services.session_client.requests.post", ...)`.

Also add `mock_resp.status_code = 200` to any mock that sets `.ok = True` (needed by create_session's status_code check).

Here is the complete replacement for all `trigger_now` tests (lines 97–205 of the current file):

```python
# ── trigger_now ──

def test_trigger_now_creates_session_and_sends_command(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.status_code = 200
    mock_create.json.return_value = {"id": "sess-abc"}

    with patch("app.services.session_client.requests.post", return_value=mock_create) as mock_post:
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result == "sess-abc"
    assert mock_post.call_count == 1
    call = mock_post.call_args_list[0]
    assert call[0][0] == "http://mock-sm/sessions"
    body = call[1]["json"]
    assert body["initial_command"] == "/housekeeping — run in scheduled mode"


def test_trigger_now_session_name_starts_with_housekeeping(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.status_code = 200
    mock_create.json.return_value = {"id": "sess-xyz"}

    with patch("app.services.session_client.requests.post",
               return_value=mock_create) as mock_post:
        from app.services.scheduler import trigger_now
        trigger_now()

    first_body = mock_post.call_args_list[0][1]["json"]
    assert first_body["name"].startswith("housekeeping-")
    suffix = first_body["name"].removeprefix("housekeeping-")
    assert len(suffix) == 8
    assert suffix.isdigit()


def test_trigger_now_returns_none_on_request_error(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    import requests as req_mod
    with patch("app.services.session_client.requests.post",
               side_effect=req_mod.RequestException("timeout")):
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result is None


def test_trigger_now_returns_none_when_session_create_fails(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = False
    mock_create.status_code = 503

    with patch("app.services.session_client.requests.post",
               return_value=mock_create):
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result is None


def test_trigger_now_returns_session_id_on_success(sched_vault, monkeypatch):
    """trigger_now returns the session ID once the session is created and
    last_triggered is persisted to the schedule config."""
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.status_code = 200
    mock_create.json.return_value = {"id": "sess-fail-cmd"}

    with patch("app.services.session_client.requests.post", return_value=mock_create):
        from app.services.scheduler import trigger_now, get_config
        result = trigger_now()

    assert result == "sess-fail-cmd"
    config = get_config()
    assert config["last_triggered"] is not None


def test_trigger_now_updates_last_triggered_in_config(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.status_code = 200
    mock_create.json.return_value = {"id": "sess-ts"}

    with patch("app.services.session_client.requests.post",
               return_value=mock_create):
        from app.services.scheduler import trigger_now, get_config
        trigger_now()

    config = get_config()
    assert config["last_triggered"] is not None
    assert "T" in config["last_triggered"]  # ISO datetime
```

- [x] **Step 2: Run tests to verify the updated tests now FAIL (before impl change)**

```bash
docker exec ikeos pytest tests/test_scheduler.py -v -k "trigger_now"
```

Expected: these tests FAIL because `scheduler.py` still uses `requests.post` directly (wrong mock target)

- [x] **Step 3: Migrate `trigger_now()` in `app/services/scheduler.py`**

At the top of the file, replace:

```python
import requests
```

with:

```python
from app.services.session_client import create_session
```

(The `requests` import is no longer needed — no other function in scheduler.py uses it.)

Replace the entire `trigger_now()` function body's HTTP section:

```python
def trigger_now() -> str | None:
    now = datetime.now()
    session_name = f"housekeeping-{now.strftime('%Y%m%d')}"
    project_dir = os.environ.get("HOUSEKEEPING_PROJECT_DIR", "/mnt/c/Server/claude-config")
    result = create_session(
        name=session_name,
        project="claude-config",
        project_dir=project_dir,
        initial_command="/housekeeping — run in scheduled mode",
    )
    if not result.ok:
        logger.error("Failed to create housekeeping session: %s", result.error)
        return None
    session_id = result.session_id
    config = get_config()
    config["last_triggered"] = now.isoformat(timespec="seconds")
    try:
        _write_config(config)
    except OSError:
        logger.exception("Failed to write last_triggered after scheduling housekeeping session")

    from app.services.metrics import append_event
    append_event("housekeeping.trigger", {
        "trigger": "scheduled" if _scheduler else "manual",
        "session_id": session_id,
        "project": "claude-config",
    })

    return session_id
```

(Removed: `sm_url` local variable, `requests.post(...)` block, `except (requests.RequestException, OSError)` handler, `if not session_id` check.)

- [x] **Step 4: Run tests to verify they pass**

```bash
docker exec ikeos pytest tests/test_scheduler.py -v
```

Expected: all PASS

- [x] **Step 5: Run full test suite**

```bash
docker exec ikeos pytest -v
```

Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add app/services/scheduler.py tests/test_scheduler.py
git commit -m "refactor: migrate trigger_now() to session_client.create_session()"
```

---

## Task 3: Migrate `run_task()` in `housekeeping.py` + update tests

**Files:**
- Modify: `app/routes/housekeeping.py`
- Modify: `tests/test_housekeeping.py`

- [x] **Step 1: Update the run_task tests before touching the implementation**

In `tests/test_housekeeping.py`, replace `test_run_task_creates_session` and `test_run_task_session_manager_unreachable`:

```python
def test_run_task_creates_session(client):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "session-abc123"}

    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event"):
            resp = client.post("/housekeeping/tasks/2026-06-17-test-task/run")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["session_id"] == "session-abc123"


def test_run_task_session_manager_unreachable(client):
    import requests as req_lib
    with patch("app.services.session_client.requests.post",
               side_effect=req_lib.RequestException("timeout")):
        resp = client.post("/housekeeping/tasks/2026-06-17-test-task/run")
    assert resp.status_code == 502
```

- [x] **Step 2: Run the updated tests to verify they FAIL**

```bash
docker exec ikeos pytest tests/test_housekeeping.py::test_run_task_creates_session tests/test_housekeeping.py::test_run_task_session_manager_unreachable -v
```

Expected: FAIL (housekeeping.py still uses `requests.post` directly)

- [x] **Step 3: Add the import to `app/routes/housekeeping.py`**

After the existing imports, add:

```python
from app.services.session_client import create_session
```

(Add it after the `from app.services.capabilities import get_capabilities, update_capability` line.)

- [x] **Step 4: Replace `run_task()` body in `app/routes/housekeeping.py`**

Replace the entire `run_task` function:

```python
@bp.route("/housekeeping/tasks/<filename>/run", methods=["POST"])
def run_task(filename: str):
    import re as _re
    session_name = f"housekeeping-{filename}"
    slug = _re.sub(r"^\d{4}-\d{2}-\d{2}-", "", filename)
    command = f"/housekeeping run {slug}"
    result = create_session(
        name=session_name,
        project="claude-config",
        project_dir=HOUSEKEEPING_PROJECT_DIR,
        initial_command=command,
    )
    if result.already_running:
        return jsonify({"ok": True, "session_id": result.session_id, "already_running": True}), 200
    if not result.ok:
        return jsonify({"error": "Failed to create session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200
```

- [x] **Step 5: Run the updated tests to verify they pass**

```bash
docker exec ikeos pytest tests/test_housekeeping.py::test_run_task_creates_session tests/test_housekeeping.py::test_run_task_session_manager_unreachable -v
```

Expected: both PASS

- [x] **Step 6: Run full test suite**

```bash
docker exec ikeos pytest -v
```

Expected: all PASS

- [x] **Step 7: Commit**

```bash
git add app/routes/housekeeping.py tests/test_housekeeping.py
git commit -m "refactor: migrate run_task() to session_client.create_session()"
```

---

## Task 4: Migrate `blog_draft_publish()` + add test

**Files:**
- Modify: `app/routes/housekeeping.py`
- Modify: `tests/test_housekeeping.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_housekeeping.py`:

```python
def test_blog_draft_publish_creates_session(client, tmp_path, monkeypatch):
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    monkeypatch.setattr(hk_mod, "AIOS_BLOG_POSTS_DIR", str(tmp_path))
    monkeypatch.setattr(hk_mod, "AIOS_BLOG_PROJECT_DIR", "/srv/blog")
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("# Draft")

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "pub-sess-1"}

    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event"):
            resp = client.post(
                "/housekeeping/blog-draft/publish",
                headers={"X-Capture-Token": "tok"},
            )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["session_id"] == "pub-sess-1"
```

- [x] **Step 2: Run test to verify it fails**

```bash
docker exec ikeos pytest tests/test_housekeeping.py::test_blog_draft_publish_creates_session -v
```

Expected: FAIL (publish still uses `requests.post` directly)

- [x] **Step 3: Replace `blog_draft_publish()` body in `app/routes/housekeeping.py`**

Replace the entire `blog_draft_publish` function:

```python
@bp.route("/housekeeping/blog-draft/publish", methods=["POST"])
def blog_draft_publish():
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    draft, bluesky = _blog_draft_paths()
    if not draft:
        return jsonify({"error": "No draft found"}), 404
    if not AIOS_BLOG_PROJECT_DIR:
        return jsonify({"error": "AIOS_BLOG_PROJECT_DIR not configured"}), 503
    bluesky_file = bluesky.name if bluesky else ""
    command = (
        f"Run `bash deploy.sh content/posts/{draft.name}` in {AIOS_BLOG_PROJECT_DIR}. "
        f"The Bluesky companion text is in content/posts/{bluesky_file}. "
        "Build the Hugo site, deploy via rsync, and post to Bluesky."
    )
    result = create_session(
        name=f"blog-publish-{draft.stem[:30]}",
        project="aios-blog",
        project_dir=AIOS_BLOG_PROJECT_DIR,
        initial_command=command,
    )
    if not result.ok:
        return jsonify({"error": "Failed to create publish session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200
```

- [x] **Step 4: Run test to verify it passes**

```bash
docker exec ikeos pytest tests/test_housekeeping.py::test_blog_draft_publish_creates_session -v
```

Expected: PASS

- [x] **Step 5: Run full test suite**

```bash
docker exec ikeos pytest -v
```

Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add app/routes/housekeeping.py tests/test_housekeeping.py
git commit -m "refactor: migrate blog_draft_publish() to session_client.create_session()"
```

---

## Task 5: Migrate `blog_draft_rewrite()` + add tests

**Files:**
- Modify: `app/routes/housekeeping.py`
- Modify: `tests/test_housekeeping.py`

- [x] **Step 1: Write the failing tests**

Add to `tests/test_housekeeping.py`:

```python
def test_blog_draft_rewrite_creates_session(client, tmp_path, monkeypatch):
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    monkeypatch.setattr(hk_mod, "AIOS_BLOG_POSTS_DIR", str(tmp_path))
    monkeypatch.setattr(hk_mod, "AIOS_BLOG_PROJECT_DIR", "/srv/blog")
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("# Draft")

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "rw-sess-1"}

    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event"):
            resp = client.post(
                "/housekeeping/blog-draft/rewrite",
                data={"feedback": "make it shorter"},
                headers={"X-Capture-Token": "tok"},
            )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["session_id"] == "rw-sess-1"


def test_blog_draft_rewrite_409_sends_command_to_running_session(client, tmp_path, monkeypatch):
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    monkeypatch.setattr(hk_mod, "AIOS_BLOG_POSTS_DIR", str(tmp_path))
    monkeypatch.setattr(hk_mod, "AIOS_BLOG_PROJECT_DIR", "/srv/blog")
    monkeypatch.setattr(hk_mod, "SESSION_MANAGER_URL", "http://mock-sm")
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("# Draft")

    # create_session returns already_running=True (409 path)
    from app.services.session_client import SessionResult
    with patch("app.routes.housekeeping.create_session",
               return_value=SessionResult(session_id="existing-rw", already_running=True)):
        # command POST to the running session
        cmd_mock = MagicMock()
        cmd_mock.ok = True
        with patch("app.routes.housekeeping.requests.post", return_value=cmd_mock):
            resp = client.post(
                "/housekeeping/blog-draft/rewrite",
                data={"feedback": "different angle"},
                headers={"X-Capture-Token": "tok"},
            )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["session_id"] == "existing-rw"
```

- [x] **Step 2: Run tests to verify they fail**

```bash
docker exec ikeos pytest tests/test_housekeeping.py::test_blog_draft_rewrite_creates_session tests/test_housekeeping.py::test_blog_draft_rewrite_409_sends_command_to_running_session -v
```

Expected: both FAIL (rewrite still uses `requests.post` directly)

- [x] **Step 3: Replace `blog_draft_rewrite()` body in `app/routes/housekeeping.py`**

Replace the entire `blog_draft_rewrite` function:

```python
@bp.route("/housekeeping/blog-draft/rewrite", methods=["POST"])
def blog_draft_rewrite():
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    draft, _ = _blog_draft_paths()
    if not draft:
        return jsonify({"error": "No draft found"}), 404
    if not AIOS_BLOG_PROJECT_DIR:
        return jsonify({"error": "AIOS_BLOG_PROJECT_DIR not configured"}), 503
    feedback = request.form.get("feedback", "").strip()
    if not feedback:
        return jsonify({"error": "Feedback is required"}), 400
    command = (
        f"Rewrite the blog draft at content/posts/{draft.name} based on this feedback: "
        f"{feedback} — keep the same frontmatter, voice, and section structure from the /blog skill. "
        "Overwrite the file in place when done."
    )
    result = create_session(
        name=f"blog-rewrite-{draft.stem[:30]}",
        project="aios-blog",
        project_dir=AIOS_BLOG_PROJECT_DIR,
        initial_command=command,
    )
    if result.already_running:
        try:
            cmd_resp = requests.post(
                f"{SESSION_MANAGER_URL}/sessions/{result.session_id}/command",
                json={"command": command, "escape_first": True},
                timeout=5,
            )
            if not cmd_resp.ok:
                return jsonify({"error": "Rewrite session running but failed to send command"}), 502
        except requests.RequestException:
            return jsonify({"error": "Session manager unreachable"}), 502
        return jsonify({"ok": True, "session_id": result.session_id}), 200
    if not result.ok:
        return jsonify({"error": "Failed to create rewrite session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200
```

- [x] **Step 4: Run tests to verify they pass**

```bash
docker exec ikeos pytest tests/test_housekeeping.py::test_blog_draft_rewrite_creates_session tests/test_housekeeping.py::test_blog_draft_rewrite_409_sends_command_to_running_session -v
```

Expected: both PASS

- [x] **Step 5: Run full test suite**

```bash
docker exec ikeos pytest -v
```

Expected: all PASS

- [x] **Step 6: Rebuild container and verify the app starts**

```bash
docker.exe compose up --build -d ikeos
docker.exe compose logs ikeos --tail=20
```

Expected: container starts cleanly, no import errors in logs

- [x] **Step 7: Commit**

```bash
git add app/routes/housekeeping.py tests/test_housekeeping.py
git commit -m "refactor: migrate blog_draft_rewrite() to session_client.create_session()"
```

---

## Self-Review

**Spec coverage:**
- `SessionResult` dataclass with `session_id`, `already_running`, `error`, `ok` → Task 1 ✓
- `create_session()` keyword-only args → Task 1 ✓
- 409 path → `already_running=True` → Task 1 ✓
- Non-ok → `error="Session manager returned {status}"` → Task 1 ✓
- Timeout/ConnectionError → `error="Session manager unreachable"` → Task 1 ✓
- `session.created` metric on success, not on 409 or error → Task 1 ✓
- `scheduler.py trigger_now()` migrated, `requests` import removed → Task 2 ✓
- `housekeeping.py run_task()` migrated, 409 handled → Task 3 ✓
- `housekeeping.py blog_draft_publish()` migrated → Task 4 ✓
- `housekeeping.py blog_draft_rewrite()` migrated, 409 branch preserved in route → Task 5 ✓
- All 6 `test_session_client.py` tests → Task 1 ✓
- Mock target updates in `test_scheduler.py` → Task 2 ✓
- Mock target updates in `test_housekeeping.py` for `run_task` → Task 3 ✓
- New publish/rewrite session tests → Tasks 4 & 5 ✓
- `SESSION_MANAGER_URL` read at call time (not module-level) in session_client → Task 1 ✓
- `requests` import stays in `housekeeping.py` (used by proxy and other routes) → preserved ✓

**Type consistency:** `SessionResult` defined in Task 1, used in Tasks 2–5. `create_session` signature stable throughout. Task 5 test imports `SessionResult` from `app.services.session_client` — matches Task 1 definition. ✓
