# Bugs + 'Imi Gate + Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three known bugs (blog-draft auth gap, session concurrency, test failures), complete the remaining 'Imi Level B gate items (umbrella_registry.yaml cleanup, stale naming), and wire Phase 0 metrics observability (events.jsonl write paths complete + `/metrics` read view).

**Architecture:** Five independent task groups. Tasks 1–3 are bug fixes in two separate codebases (ikeos app + session manager service). Tasks 4–5 are repo hygiene. Task 6 is a new Flask route + template. Each task is self-contained and commits independently. Tasks 1, 4, 5, 6 are in `/mnt/c/Server/projects/ikeos`. Tasks 2–3 are in `/mnt/c/Server/claude-config/services/session-manager`.

**Tech Stack:** Python 3.11, Flask, Jinja2, pytest, threading, git

---

## File Map

| Task | Action | File |
|------|--------|------|
| 1 | Modify | `app/routes/housekeeping.py` |
| 1 | Modify | `app/templates/blog_draft.html` |
| 1 | Modify | `tests/test_housekeeping.py` |
| 2 | Modify | `sessions.py` (session-manager) |
| 2 | Modify | `tests/test_sessions.py` (session-manager) |
| 3 | Modify | `tests/test_app.py` (session-manager) |
| 4 | Modify | `.gitignore` |
| 4 | Create | `umbrella_registry.yaml.example` |
| 5 | Verify only | `README.md`, `CLAUDE.md`, `.claude/DECISIONS.md`, `.env.example` |
| 6 | Modify | `app/routes/agents.py` (or new `app/routes/metrics.py`) |
| 6 | Create | `app/templates/metrics.html` |
| 6 | Modify | `app/__init__.py` |
| 6 | Modify | `tests/test_metrics.py` |

---

## Task 1: Blog-draft auth guard

**Context:** `/housekeeping/blog-draft/save`, `/publish`, and `/rewrite` are mutation endpoints that spawn Claude sessions or write files. They are missing the `_check_auth()` guard that every other mutation endpoint in `housekeeping.py` has (see `delete_task` line 175, `patch_schedule` line 379). The `blog_draft.html` template also calls these via `fetch()` without an auth header.

**Files:**
- Modify: `app/routes/housekeeping.py:236–325`
- Modify: `app/templates/blog_draft.html:66–218`
- Modify: `tests/test_housekeeping.py`

- [ ] **Step 1: Write failing tests for auth guard**

Add to `tests/test_housekeeping.py`. Place after the existing housekeeping tests. The `client` fixture is defined in `tests/conftest.py` and uses `create_app({"TESTING": True})`.

```python
# ── blog-draft auth guard ──

def test_blog_draft_save_rejects_missing_token(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "secret-token")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    draft = tmp_path / "2026-06-30-weekly-draft.md"
    draft.write_text("# Hello")
    resp = client.post("/housekeeping/blog-draft/save",
                       data={"content": "new", "bluesky_text": ""})
    assert resp.status_code == 401


def test_blog_draft_save_rejects_wrong_token(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "secret-token")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    draft = tmp_path / "2026-06-30-weekly-draft.md"
    draft.write_text("# Hello")
    resp = client.post("/housekeeping/blog-draft/save",
                       data={"content": "new", "bluesky_text": ""},
                       headers={"X-Capture-Token": "wrong"})
    assert resp.status_code == 401


def test_blog_draft_save_accepts_correct_token(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "secret-token")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    draft = tmp_path / "2026-06-30-weekly-draft.md"
    draft.write_text("# Hello")
    resp = client.post("/housekeeping/blog-draft/save",
                       data={"content": "updated", "bluesky_text": ""},
                       headers={"X-Capture-Token": "secret-token"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_blog_draft_publish_rejects_missing_token(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "secret-token")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-06-30-weekly-draft.md").write_text("# Hello")
    resp = client.post("/housekeeping/blog-draft/publish")
    assert resp.status_code == 401


def test_blog_draft_rewrite_rejects_missing_token(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "secret-token")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-06-30-weekly-draft.md").write_text("# Hello")
    resp = client.post("/housekeeping/blog-draft/rewrite",
                       data={"feedback": "make it better"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
docker exec ikeos pytest tests/test_housekeeping.py -k "blog_draft_save_rejects or blog_draft_publish_rejects or blog_draft_rewrite_rejects or blog_draft_save_accepts" -v
```

Expected: 5 FAILED (401 not returned yet — routes execute without auth).

- [ ] **Step 3: Add `_check_auth()` to the three routes in `housekeeping.py`**

In `blog_draft_save` (line 236), add at the top of the function body:

```python
@bp.route("/housekeeping/blog-draft/save", methods=["POST"])
def blog_draft_save():
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    draft, bluesky = _blog_draft_paths()
    # ... rest of function unchanged
```

In `blog_draft_publish` (line 252), add at the top:

```python
@bp.route("/housekeeping/blog-draft/publish", methods=["POST"])
def blog_draft_publish():
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    draft, bluesky = _blog_draft_paths()
    # ... rest of function unchanged
```

In `blog_draft_rewrite` (line 283), add at the top:

```python
@bp.route("/housekeeping/blog-draft/rewrite", methods=["POST"])
def blog_draft_rewrite():
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    draft, _ = _blog_draft_paths()
    # ... rest of function unchanged
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
docker exec ikeos pytest tests/test_housekeeping.py -k "blog_draft_save_rejects or blog_draft_publish_rejects or blog_draft_rewrite_rejects or blog_draft_save_accepts" -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Pass `capture_token` to `blog_draft.html` template**

In `blog_draft_editor()` (around line 222), add `capture_token` to the render call:

```python
@bp.route("/housekeeping/blog-draft")
def blog_draft_editor():
    draft, bluesky = _blog_draft_paths()
    if not draft:
        return render_template("housekeeping.html", **_housekeeping_context(), no_draft=True)
    return render_template(
        "blog_draft.html",
        filename=draft.name,
        content=draft.read_text(encoding="utf-8"),
        bluesky_text=(bluesky.read_text(encoding="utf-8") if bluesky else ""),
        bluesky_filename=(bluesky.name if bluesky else ""),
        capture_token=CAPTURE_TOKEN,
    )
```

- [ ] **Step 6: Add token to fetch calls in `blog_draft.html`**

At the top of the `<script>` block (after existing variable declarations, around line 73), add:

```javascript
const _captureToken = {{ capture_token | tojson }};
```

Then update the three `fetch()` calls to include the header:

**Save** (around line 99):
```javascript
const resp = await fetch('/housekeeping/blog-draft/save', {
  method: 'POST',
  body,
  headers: { 'X-Capture-Token': _captureToken },
});
```

**Publish** (around line 115):
```javascript
const resp = await fetch('/housekeeping/blog-draft/publish', {
  method: 'POST',
  headers: { 'X-Capture-Token': _captureToken },
});
```

**Rewrite** (around line 204):
```javascript
const resp = await fetch('/housekeeping/blog-draft/rewrite', {
  method: 'POST',
  body,
  headers: { 'X-Capture-Token': _captureToken },
});
```

- [ ] **Step 7: Rebuild and run full housekeeping test suite**

```bash
docker.exe compose up --build -d ikeos && docker exec ikeos pytest tests/test_housekeeping.py -v
```

Expected: all tests PASSED.

- [ ] **Step 8: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/routes/housekeeping.py app/templates/blog_draft.html tests/test_housekeeping.py
git -C /mnt/c/Server/projects/ikeos commit -m "fix: add _check_auth() guard to blog-draft mutation endpoints

/save, /publish, and /rewrite were missing the auth gate that
delete_task and patch_schedule already have. These endpoints spawn
Claude sessions or write files — they should require the capture token.
blog_draft.html updated to pass X-Capture-Token in all fetch calls."
```

---

## Task 2: sessions.py concurrent write safety

**Context:** `sessions.py` in the session manager reads/writes a sessions list to `~/.claude-sessions.json` with no threading lock. `create_session`, `update_session`, and `remove_session` all do read-modify-write. Two concurrent `POST /sessions` requests can both read the same initial state, both append/modify, then one's `_save()` overwrites the other's. Fix: module-level `threading.Lock` held across the full read-modify-write in each write function.

**Working directory for Tasks 2–3:** `/mnt/c/Server/claude-config/services/session-manager`

**Files:**
- Modify: `sessions.py`
- Modify: `tests/test_sessions.py`

- [ ] **Step 1: Write a failing test for concurrent write safety**

Add to `tests/test_sessions.py`:

```python
import threading

def test_concurrent_create_sessions_both_persist():
    """Both sessions must be saved when created concurrently."""
    results = []
    def create():
        s = create_session(f"session-{threading.current_thread().name}", "proj", "/dir")
        results.append(s["id"])

    threads = [threading.Thread(target=create, name=f"t{i}") for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    saved = list_sessions()
    assert len(saved) == 5, f"Expected 5 sessions, got {len(saved)}"
    assert len(set(results)) == 5, "Duplicate session IDs created"
```

- [ ] **Step 2: Run test to confirm it is flaky or failing**

```bash
cd /mnt/c/Server/claude-config/services/session-manager && python -m pytest tests/test_sessions.py::test_concurrent_create_sessions_both_persist -v --count=10 2>/dev/null || python -m pytest tests/test_sessions.py::test_concurrent_create_sessions_both_persist -v
```

Expected: intermittent failure or consistent failure showing <5 sessions saved.

- [ ] **Step 3: Add threading.Lock to `sessions.py`**

Replace the entire content of `sessions.py` with:

```python
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

SESSIONS_FILE = Path.home() / ".claude-sessions.json"

_lock = threading.Lock()


def _load() -> list[dict]:
    if not SESSIONS_FILE.exists():
        return []
    return json.loads(SESSIONS_FILE.read_text())


def _save(sessions: list[dict]) -> None:
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))


def list_sessions() -> list[dict]:
    with _lock:
        return _load()


def get_session(session_id: str) -> dict | None:
    with _lock:
        return next((s for s in _load() if s["id"] == session_id), None)


def create_session(name: str, project: str, project_dir: str,
                   remote_control: bool = False, ephemeral: bool = False) -> dict:
    session = {
        "id": str(uuid.uuid4()),
        "name": name,
        "project": project,
        "project_dir": project_dir,
        "remote_control": remote_control,
        "remote_control_confirmed": False,
        "autonomous_mode": False,
        "ephemeral": ephemeral,
        "status": "active",
        "tmux_session": name,
        "started_at": datetime.utcnow().isoformat(),
        "message_count": 0,
        "compaction_detected": False,
        "last_pane_check": None,
    }
    with _lock:
        sessions = _load()
        sessions.append(session)
        _save(sessions)
    return session


def update_session(session_id: str, **kwargs) -> dict | None:
    with _lock:
        sessions = _load()
        for s in sessions:
            if s["id"] == session_id:
                s.update(kwargs)
                _save(sessions)
                return s
    return None


def remove_session(session_id: str) -> bool:
    with _lock:
        sessions = _load()
        new_sessions = [s for s in sessions if s["id"] != session_id]
        if len(new_sessions) == len(sessions):
            return False
        _save(new_sessions)
    return True
```

- [ ] **Step 4: Run the concurrent test to confirm it passes**

```bash
cd /mnt/c/Server/claude-config/services/session-manager && python -m pytest tests/test_sessions.py::test_concurrent_create_sessions_both_persist -v
```

Expected: PASSED.

- [ ] **Step 5: Run the full sessions test suite to check for regressions**

```bash
cd /mnt/c/Server/claude-config/services/session-manager && python -m pytest tests/test_sessions.py -v
```

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git -C /mnt/c/Server/claude-config add services/session-manager/sessions.py services/session-manager/tests/test_sessions.py
git -C /mnt/c/Server/claude-config commit -m "fix: add threading.Lock to sessions.py read-modify-write operations

Concurrent POST /sessions requests could race on _load()/_save()
producing lost writes. Module-level _lock now held across the full
read-modify-write in create_session, update_session, and remove_session.
list_sessions and get_session also locked for read consistency."
```

---

## Task 3: Fix session manager test_app.py failures

**Context:** 14 tests in `tests/test_app.py` were failing before this session. Root causes per the vault bug:
1. Docker command format: tests assert `["docker", "restart", "traefik"]` but `app.py` now uses `["bash", "-c", "docker.exe restart traefik"]` (changed to support docker.exe on WSL2).
2. Response shape mismatches in some tests.

The strategy: run the tests, read the actual failures, fix assertions to match current behavior. Do not change `app.py` behavior — the tests must match what the code does.

**Files:**
- Modify: `tests/test_app.py`

- [ ] **Step 1: Run the failing tests and capture output**

```bash
cd /mnt/c/Server/claude-config/services/session-manager && python -m pytest tests/test_app.py -v 2>&1 | tee /tmp/test_failures.txt | tail -60
```

Expected: approximately 14 FAILED. Read each failure message carefully — the actual assertion error text tells you what the code returned vs. what the test expected.

- [ ] **Step 2: Fix `test_container_restart` assertion**

The code at `app.py:389` calls:
```python
subprocess.run(["bash", "-c", f"docker.exe restart {name}"], capture_output=True, text=True, timeout=30)
```

Update `test_container_restart` to assert the new form:

```python
def test_container_restart(client, mocker):
    run_mock = mocker.patch("app.subprocess.run")
    run_mock.return_value = MagicMock(returncode=0, stderr="")
    resp = client.post("/infrastructure/containers/traefik/restart")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    run_mock.assert_called_once_with(
        ["bash", "-c", "docker.exe restart traefik"],
        capture_output=True, text=True, timeout=30
    )
```

- [ ] **Step 3: Fix `test_container_stop` assertion**

The code at `app.py:400` calls `["bash", "-c", f"docker.exe stop {name}"]`:

```python
def test_container_stop(client, mocker):
    run_mock = mocker.patch("app.subprocess.run")
    run_mock.return_value = MagicMock(returncode=0, stderr="")
    resp = client.post("/infrastructure/containers/traefik/stop")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    run_mock.assert_called_once_with(
        ["bash", "-c", "docker.exe stop traefik"],
        capture_output=True, text=True, timeout=30
    )
```

- [ ] **Step 4: Fix `test_container_start` assertion**

The code at `app.py:409` calls `["bash", "-c", f"docker.exe start {name}"]`:

```python
def test_container_start(client, mocker):
    run_mock = mocker.patch("app.subprocess.run")
    run_mock.return_value = MagicMock(returncode=0, stderr="")
    resp = client.post("/infrastructure/containers/traefik/start")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    run_mock.assert_called_once_with(
        ["bash", "-c", "docker.exe start traefik"],
        capture_output=True, text=True, timeout=30
    )
```

- [ ] **Step 5: Fix remaining failures from Step 1 output**

For each remaining failure in `/tmp/test_failures.txt`, apply the same principle: read the actual response the code returns and update the test assertion to match. Do NOT change `app.py` to match old tests — the tests are wrong, not the code.

Common patterns to look for:
- `KeyError` in tests: the response shape changed (e.g., a key was removed or renamed). Update the assert to use the new key.
- `IndexError`: the test assumed a list position that no longer exists. Check the actual response.
- `AssertionError` on status codes: the endpoint now returns a different code for valid reasons.

After fixing each failure, note the change and rationale as a comment in the test.

- [ ] **Step 6: Run the full test_app.py suite**

```bash
cd /mnt/c/Server/claude-config/services/session-manager && python -m pytest tests/test_app.py -v
```

Expected: 0 FAILED.

- [ ] **Step 7: Run the complete session manager test suite**

```bash
cd /mnt/c/Server/claude-config/services/session-manager && python -m pytest tests/ -v
```

Expected: 0 FAILED across all test files.

- [ ] **Step 8: Commit**

```bash
git -C /mnt/c/Server/claude-config add services/session-manager/tests/test_app.py
git -C /mnt/c/Server/claude-config commit -m "fix: update test_app.py assertions to match docker.exe shell pattern

Container restart/stop/start tests expected ['docker', 'cmd', name]
but app.py now uses ['bash', '-c', 'docker.exe cmd name'] to work
in WSL2 non-interactive shells where docker is not aliased.
Additional response-shape mismatches fixed to match current behavior."
```

---

## Task 4: Gitignore umbrella_registry.yaml

**Context:** `umbrella_registry.yaml` contains personal project topology (Windows paths like `C:\Server\projects\...`, private project names like `rcade`, `worldwardle`). It should be gitignored with a documented example. This is the last 'Imi Level B blocker — it's what a stranger sees when they clone IkeOS today.

**Working directory:** `/mnt/c/Server/projects/ikeos`

**Files:**
- Modify: `.gitignore`
- Create: `umbrella_registry.yaml.example`

- [ ] **Step 1: Confirm `umbrella_registry.yaml` is currently tracked**

```bash
git -C /mnt/c/Server/projects/ikeos ls-files umbrella_registry.yaml
```

Expected: outputs `umbrella_registry.yaml` (it is tracked).

- [ ] **Step 2: Add to `.gitignore`**

Open `.gitignore` and add these lines in the "App secrets" section (after `.env`):

```gitignore
# Personal project config — use umbrella_registry.yaml.example as a template
umbrella_registry.yaml
```

- [ ] **Step 3: Create `umbrella_registry.yaml.example`**

Create the file at `/mnt/c/Server/projects/ikeos/umbrella_registry.yaml.example`:

```yaml
# umbrella_registry.yaml
# Maps umbrella project slugs to their component sub-projects.
#
# Components listed here are hidden from the top-level project picker
# and captured under the umbrella's vault folder instead.
#
# Flat projects (components: []) appear as normal projects with no component picker.
# codebases: absolute paths to the relevant project directories on disk.
#            On Windows/WSL2, use Windows-style paths (C:\...).
#
# Copy this file to umbrella_registry.yaml and edit to match your setup.

# Example: a platform with multiple sub-projects
my-platform:
  name: My Platform
  codebases:
    - /home/user/projects/my-platform
  components:
    - my-platform-api
    - my-platform-ui

# Example: a standalone project with no components
my-standalone-project:
  name: My Standalone Project
  codebases:
    - /home/user/projects/my-standalone-project
  components: []
```

- [ ] **Step 4: Untrack the personal file from git**

```bash
git -C /mnt/c/Server/projects/ikeos rm --cached umbrella_registry.yaml
```

Expected: `rm 'umbrella_registry.yaml'`

- [ ] **Step 5: Verify gitignore took effect**

```bash
git -C /mnt/c/Server/projects/ikeos status umbrella_registry.yaml
```

Expected: `umbrella_registry.yaml` is listed as untracked but ignored — it should NOT appear in `git status` output (ignored files are hidden). If it appears as untracked (not ignored), the gitignore rule may not have propagated — run `git check-ignore -v umbrella_registry.yaml` to debug.

- [ ] **Step 6: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add .gitignore umbrella_registry.yaml.example
git -C /mnt/c/Server/projects/ikeos commit -m "chore: gitignore umbrella_registry.yaml, add documented example

Personal project topology (Windows paths, private project names)
should not be visible in the public repo. umbrella_registry.yaml.example
documents the format for contributors. Closes the last 'Imi Level B
blocker."
```

---

## Task 5: Verify no stale "Obsidian Capture" naming

**Context:** The 'Imi audit flagged naming inconsistency. Session 2 renamed the primary surfaces but some files may still contain the old name. This is a verification-only task — read the output and fix any hits.

**Working directory:** `/mnt/c/Server/projects/ikeos`

- [ ] **Step 1: Search for stale naming in committed files**

```bash
git -C /mnt/c/Server/projects/ikeos grep -i "obsidian.capture\|obsidian_capture" -- '*.md' '*.py' '*.html' '*.yaml' '*.yml' '*.txt' '*.json' '.gitignore' '.env.example'
```

Expected: zero matches. If any are found, go to Step 2. If none, skip to Step 3.

- [ ] **Step 2: Fix any matches found**

For each match:
- If in a user-facing string (README, CLAUDE.md, DECISIONS.md header, template, route docstring): change to "IkeOS"
- If in a code identifier (variable name, vault project slug): these can remain as-is — the slug `obsidian-capture` is a historical vault identifier that isn't user-facing
- If in a comment describing old behavior: update to reflect current name

- [ ] **Step 3: Verify DECISIONS.md header**

```bash
head -1 /mnt/c/Server/projects/ikeos/.claude/DECISIONS.md
```

Expected: `# Architectural Decisions — IkeOS`

If it still says "Obsidian Capture", fix it:

```bash
# Do NOT use sed directly — use the Edit tool to change line 1
```

Use the Edit tool: old_string = `# Architectural Decisions — Obsidian Capture`, new_string = `# Architectural Decisions — IkeOS`.

- [ ] **Step 4: Commit if any changes were made**

```bash
git -C /mnt/c/Server/projects/ikeos add -A
git -C /mnt/c/Server/projects/ikeos commit -m "chore: remove remaining stale 'Obsidian Capture' naming

Final naming pass from 'Imi Session 2 audit. All user-facing
strings now say IkeOS. Vault slug obsidian-capture retained as
a historical identifier in code."
```

If no changes were needed, skip the commit and note "Naming already clean."

---

## Task 6: Phase 0 — /metrics view

**Context:** `housekeeping.trigger` is already wired in `scheduler.py` (lines 147–152). The gap is: there is no way to read events.jsonl from the IkeOS UI. This task adds:
1. A `GET /metrics` route that reads the last 50 events from events.jsonl and renders a timeline
2. A `POST /metrics/event` endpoint (protected by CAPTURE_TOKEN) so external services (session manager) can append events without needing the metrics volume mounted
3. A basic `metrics.html` template

**Note:** `POST /metrics/event` is the mechanism by which the session manager will later log `agent.session_start` and `agent.session_end`. Wiring the session manager to call it is **out of scope for this task** — that is Phase 0.5. This task only adds the IkeOS-side endpoints.

**Files:**
- Modify: `app/routes/agents.py` — add `/metrics` and `/metrics/event` routes
- Create: `app/templates/metrics.html`
- Modify: `app/__init__.py` — add nav entry if needed
- Modify: `tests/test_metrics.py` — extend with new route tests

- [ ] **Step 1: Check existing test_metrics.py to understand current coverage**

```bash
cat /mnt/c/Server/projects/ikeos/tests/test_metrics.py
```

Read the file. Understand what `append_event` tests already exist. Add new tests only for the Flask routes.

- [ ] **Step 2: Write failing tests for `GET /metrics`**

Add to `tests/test_metrics.py`. These tests use the `client` fixture from `conftest.py`.

```python
import json
from pathlib import Path
from unittest.mock import patch


def test_metrics_view_returns_200(client):
    with patch("app.services.metrics.METRICS_PATH", Path("/nonexistent/events.jsonl")):
        resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_view_shows_events(client, tmp_path):
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps({"event": "housekeeping.trigger", "timestamp": "2026-06-30T03:07:00+00:00",
                    "session_id": "abc123", "project": "claude-config", "trigger": "scheduled"}) + "\n" +
        json.dumps({"event": "housekeeping.trigger", "timestamp": "2026-06-29T03:07:00+00:00",
                    "session_id": "def456", "project": "claude-config", "trigger": "scheduled"}) + "\n"
    )
    with patch("app.services.metrics.METRICS_PATH", events_file):
        resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.data.decode()
    assert "housekeeping.trigger" in data
    assert "abc123" in data


def test_metrics_view_empty_when_no_file(client, tmp_path):
    with patch("app.services.metrics.METRICS_PATH", tmp_path / "missing.jsonl"):
        resp = client.get("/metrics")
    assert resp.status_code == 200
    # Page renders without error; no events shown


def test_metrics_event_post_requires_auth(client):
    resp = client.post("/metrics/event",
                       json={"event": "test.event", "session_id": "x"},
                       content_type="application/json")
    assert resp.status_code in (401, 503)


def test_metrics_event_post_appends_event(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    events_file = tmp_path / "events.jsonl"
    with patch("app.services.metrics.METRICS_PATH", events_file):
        resp = client.post(
            "/metrics/event",
            json={"event": "agent.session_start", "session_id": "s1"},
            content_type="application/json",
            headers={"X-Capture-Token": "tok"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    lines = events_file.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "agent.session_start"
    assert "timestamp" in record
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
docker exec ikeos pytest tests/test_metrics.py -k "metrics_view or metrics_event" -v
```

Expected: FAILED (routes don't exist yet).

- [ ] **Step 4: Add `read_events()` to `app/services/metrics.py`**

Add this function at the end of `app/services/metrics.py`. It reads `METRICS_PATH` at call-time so tests can patch `app.services.metrics.METRICS_PATH` correctly.

```python
import json as _json_mod


def read_events(limit: int = 50) -> list[dict]:
    """Return up to `limit` most-recent events from METRICS_PATH, newest first."""
    if not METRICS_PATH.exists():
        return []
    try:
        lines = METRICS_PATH.read_text(encoding="utf-8").strip().splitlines()
        events = []
        for line in reversed(lines[-limit:]):
            try:
                events.append(_json_mod.loads(line))
            except _json_mod.JSONDecodeError:
                pass
        return events
    except OSError:
        return []
```

- [ ] **Step 5: Add routes to `agents.py`**

Add the following to `app/routes/agents.py`. Check the top of the file for existing imports before adding. `CAPTURE_TOKEN` may already be defined; do not redefine it.

```python
from app.services.metrics import append_event, read_events

CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "")  # skip if already defined


@bp.route("/metrics")
def metrics_view():
    events = read_events(limit=50)
    return render_template("metrics.html", events=events)


@bp.route("/metrics/event", methods=["POST"])
def metrics_event():
    if not CAPTURE_TOKEN:
        return jsonify({"error": "Service unavailable"}), 503
    if request.headers.get("X-Capture-Token", "") != CAPTURE_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = request.get_json(silent=True) or {}
    event_type = data.pop("event", None)
    if not event_type:
        return jsonify({"error": "event field required"}), 400
    ok = append_event(event_type, data)
    if not ok:
        return jsonify({"error": "Failed to write event"}), 500
    return jsonify({"ok": True}), 200
```

Add any missing imports to the top of `agents.py`:
- `import os` — likely already present
- `from flask import ... jsonify, request` — add any missing names
- `from app.services.metrics import append_event, read_events` — new import

**Important:** If `CAPTURE_TOKEN` is already defined at module level in `agents.py`, do not redefine it — check first with `grep -n "CAPTURE_TOKEN" app/routes/agents.py`.

- [ ] **Step 6: Create `app/templates/metrics.html`**

```html
{% extends "base.html" %}
{% block title %}Metrics{% endblock %}

{% block content %}
<div class="settings-page">
  <header class="page-header">
    <span class="ike-eyebrow">Platform</span>
    <h1>Metrics</h1>
    <p class="page-subtitle">Last {{ events|length }} events from events.jsonl</p>
  </header>

  {% if not events %}
  <div class="empty-state">
    <p>No events recorded yet. Events appear here when housekeeping sessions run.</p>
  </div>
  {% else %}
  <table class="settings-list metrics-table">
    <thead>
      <tr>
        <th>Time</th>
        <th>Event</th>
        <th>Details</th>
      </tr>
    </thead>
    <tbody>
    {% for ev in events %}
      <tr class="settings-row metrics-row">
        <td class="metrics-ts">{{ ev.timestamp | replace('T', ' ') | replace('+00:00', '') }}</td>
        <td><span class="pill pill--{{ ev.event.split('.')[0] }}">{{ ev.event }}</span></td>
        <td class="metrics-detail">
          {% for k, v in ev.items() %}
            {% if k not in ('event', 'timestamp') %}
              <span class="metrics-kv"><span class="metrics-key">{{ k }}</span>: {{ v }}</span>
            {% endif %}
          {% endfor %}
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 7: Add `/metrics` to the nav in `base.html`**

Find the nav in `app/templates/base.html`. Add a Metrics link in the appropriate nav section (near Housekeeping or at the end of the main nav items):

```html
<a href="{{ url_for('agents.metrics_view') }}" class="nav-link{% if request.endpoint == 'agents.metrics_view' %} active{% endif %}">Metrics</a>
```

If the nav uses a list structure, follow the existing pattern exactly.

- [ ] **Step 8: Run the metrics tests**

```bash
docker.exe compose up --build -d ikeos && docker exec ikeos pytest tests/test_metrics.py -v
```

Expected: all PASSED.

- [ ] **Step 9: Smoke test in browser context**

```bash
curl -sf http://localhost:5009/metrics | grep -c "Metrics"
```

Expected: output `1` or higher (page renders with the Metrics heading).

- [ ] **Step 10: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/routes/agents.py app/templates/metrics.html app/templates/base.html tests/test_metrics.py
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add /metrics view and /metrics/event endpoint for Phase 0 observability

GET /metrics reads the last 50 events from events.jsonl and renders
a timeline. POST /metrics/event (token-protected) lets external
services (session manager, housekeeping sessions) append events
without needing the metrics volume mounted. housekeeping.trigger
was already wired in scheduler.py; this closes the read-back gap."
```

---

## Verification Contract

This plan is done when:

- [ ] `docker exec ikeos pytest tests/test_housekeeping.py -v` — 0 FAILED, auth guard tests passing
- [ ] `cd /mnt/c/Server/claude-config/services/session-manager && python -m pytest tests/ -v` — 0 FAILED across all session manager tests
- [ ] `docker exec ikeos pytest tests/test_metrics.py -v` — 0 FAILED
- [ ] `docker exec ikeos pytest` — full IkeOS suite 0 FAILED
- [ ] `git -C /mnt/c/Server/projects/ikeos ls-files umbrella_registry.yaml` — empty output (not tracked)
- [ ] `curl -sf http://localhost:5009/metrics` — returns HTTP 200 with Metrics heading
- [ ] `curl -sf http://localhost:5009/housekeeping/blog-draft/save -X POST` — returns 401 (no token)
- [ ] All commits on main with conventional commit messages
