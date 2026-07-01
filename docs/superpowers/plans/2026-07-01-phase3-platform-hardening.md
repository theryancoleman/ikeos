# Phase 3 — Platform Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining 'Imi platform hardening gaps: enforce lowercase project slugs, guard the APScheduler single-worker assumption at startup, and register `weekly_platform_review` as a controlled capability.

**Architecture:** Three independent S-size tasks. Task 1 normalises the `project` parameter at the write boundary (`write_entry`) and at every capture endpoint that builds the `data` dict before calling it. Task 2 adds a startup log that makes the gunicorn-workers-1 assumption explicit and observable. Task 3 extends the existing capability registry pattern to the next autonomous capability.

**Tech Stack:** Python 3.11, Flask, pytest, python-frontmatter, APScheduler

---

### Task 1: Normalize project slugs to lowercase

**Files:**
- Modify: `app/services/vault_entries.py` — `write_entry()` normalises project
- Modify: `app/routes/capture.py` — form POST and `/capture/json` endpoints normalise project
- Test: `tests/test_vault_entries.py`
- Test: `tests/test_capture.py`

- [ ] **Step 1.1: Write the failing test in test_vault_entries.py**

Add at the bottom of `tests/test_vault_entries.py`:

```python
def test_write_entry_normalizes_project_to_lowercase(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch.object(_vc, "VAULT_PATH", tmp_path):
        write_entry({"type": "note", "project": "MyProj", "title": "Mixed case", "body": ""})
    files = list((tmp_path / "projects" / "myproj" / "notes").glob("*.md"))
    assert len(files) == 1, "entry should land in lowercase project dir"
```

- [ ] **Step 1.2: Run it to confirm it fails**

```bash
docker exec ikeos pytest tests/test_vault_entries.py::test_write_entry_normalizes_project_to_lowercase -v
```

Expected: FAIL — the entry lands in `MyProj/notes/` (wrong case directory) or raises FileNotFoundError.

- [ ] **Step 1.3: Implement — normalise project in write_entry()**

In `app/services/vault_entries.py`, after line `project = data.get("project", "")`, add:

```python
project = project.lower().strip()
```

Full context (lines 22–26 become):

```python
def write_entry(data: dict) -> str:
    entry_type = data["type"]
    project = data.get("project", "").lower().strip()
    title = data["title"]
    body = data.get("body", "")
```

- [ ] **Step 1.4: Run test — should pass**

```bash
docker exec ikeos pytest tests/test_vault_entries.py::test_write_entry_normalizes_project_to_lowercase -v
```

Expected: PASS

- [ ] **Step 1.5: Write the failing capture route test**

Add to `tests/test_capture.py`:

```python
def test_capture_post_normalizes_project_slug(client, tmp_path):
    (tmp_path / "projects" / "bcr-waivers").mkdir(parents=True)
    with patch.object(_vc, "VAULT_PATH", tmp_path):
        client.post("/capture", data={
            "type": "note",
            "project": "BCR-Waivers",
            "title": "Mixed case project",
            "body": "test",
        })
    files = list((tmp_path / "projects" / "bcr-waivers" / "notes").glob("*.md"))
    assert len(files) == 1, "should write to lowercase project dir"
```

You will also need to add the following import at the top of `tests/test_capture.py` if not already present:

```python
import app.services.vault_cache as _vc
from unittest.mock import patch
```

- [ ] **Step 1.6: Run it to confirm it fails**

```bash
docker exec ikeos pytest tests/test_capture.py::test_capture_post_normalizes_project_slug -v
```

Expected: FAIL — entry goes to `BCR-Waivers/notes/` because the route doesn't normalise before passing to `write_entry`.

- [ ] **Step 1.7: Implement — normalise in capture form POST**

In `app/routes/capture.py`, the form POST handler sets `project` at lines 57–63. Change:

```python
    else:
        project = request.form["project"]
        if project == "__future__":
            project = request.form.get("future_project_name", "").strip() or "future"
        data["project"] = project
```

to:

```python
    else:
        project = request.form["project"]
        if project == "__future__":
            project = request.form.get("future_project_name", "").strip() or "future"
        data["project"] = project.lower().strip()
```

Also normalise the `/capture/json` endpoint. Find `project = req_data.get("project", "").strip()` (around line 107) and change to:

```python
project = req_data.get("project", "").strip().lower()
```

And the second JSON path around line 186: `project = req.get("project", "")` change to:

```python
project = req.get("project", "").strip().lower()
```

- [ ] **Step 1.8: Run the full vault_entries and capture test suites**

```bash
docker exec ikeos pytest tests/test_vault_entries.py tests/test_capture.py -v
```

Expected: all pass (the new tests and all pre-existing ones).

- [ ] **Step 1.9: Run the full test suite**

```bash
docker exec ikeos pytest tests/ -q
```

Expected: 322+ passed, 0 failed.

- [ ] **Step 1.10: Commit**

```bash
git add app/services/vault_entries.py app/routes/capture.py tests/test_vault_entries.py tests/test_capture.py
git commit -m "fix: normalize project slugs to lowercase at write and capture boundaries"
```

---

### Task 2: APScheduler single-worker startup guard

**Files:**
- Modify: `app/services/scheduler.py` — `start()` logs the workers-1 assumption

The gunicorn `--workers 1` flag is set in the Dockerfile CMD and is the constraint preventing duplicate housekeeping runs. There is no clean way to verify the worker count at runtime from within the app (gunicorn doesn't expose this to the WSGI app). The correct mitigation is a visible startup log that makes the assumption explicit — so any operator who changes the Dockerfile CMD sees it in startup output and knows what they're breaking.

- [ ] **Step 2.1: Add the startup warning to scheduler.start()**

In `app/services/scheduler.py`, in the `start()` function, immediately after `_scheduler.start()`, add:

```python
    logger.warning(
        "APScheduler started — this relies on gunicorn --workers 1. "
        "If workers > 1, the housekeeping job fires multiple times per trigger. "
        "See DECISIONS.md 2026-06-18 for context."
    )
```

Full updated `start()` function:

```python
def start(app) -> None:
    global _scheduler
    if app.config.get("TESTING"):
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    config = get_config()
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _job,
        "cron",
        id="housekeeping",
        day_of_week=config["day_of_week"],
        hour=config["hour"],
        minute=config["minute"],
    )
    _scheduler.start()
    logger.warning(
        "APScheduler started — this relies on gunicorn --workers 1. "
        "If workers > 1, the housekeeping job fires multiple times per trigger. "
        "See DECISIONS.md 2026-06-18 for context."
    )
    if not config.get("enabled"):
        _scheduler.pause_job("housekeeping")
    logger.info(
        "Housekeeping scheduler started (enabled=%s, schedule=%s %s:%s)",
        config.get("enabled"),
        config["day_of_week"],
        config["hour"],
        config["minute"],
    )
```

- [ ] **Step 2.2: Run the scheduler tests**

```bash
docker exec ikeos pytest tests/test_scheduler.py -v
```

Expected: all pass (the log is a warning-level side effect, not observable in unit tests that don't spin up a real scheduler).

- [ ] **Step 2.3: Rebuild and check the startup log**

```bash
docker.exe compose up --build -d ikeos && docker.exe compose logs --tail=30 ikeos
```

Expected: log lines show `APScheduler started — this relies on gunicorn --workers 1.` near startup.

- [ ] **Step 2.4: Commit**

```bash
git add app/services/scheduler.py
git commit -m "fix: log explicit single-worker assumption when APScheduler starts"
```

---

### Task 3: Register weekly_platform_review capability

**Files:**
- Modify: `app/services/capabilities.py` — add `weekly_platform_review` to `DEFAULT_CAPABILITIES`
- Test: `tests/test_capabilities.py`

This is the controls-first extension for the next autonomous capability: the weekly AI engineering platform review routine (DO THIRD in the 'Imi sequence). The capability defaults to `enabled: False`. Until an architect enables it, the capability registry records it as known-but-locked. No routing changes are needed in this task — the capability gate will be checked in the next phase when the review route is built.

- [ ] **Step 3.1: Write the failing test**

Add to `tests/test_capabilities.py`:

```python
def test_weekly_platform_review_capability_exists_and_defaults_to_disabled(tmp_path):
    with patch.object(capabilities, "_capabilities_path", return_value=tmp_path / "capabilities.json"):
        caps = capabilities.get_capabilities()
    assert "weekly_platform_review" in caps
    assert caps["weekly_platform_review"]["enabled"] is False


def test_update_weekly_platform_review_capability(tmp_path):
    caps_file = tmp_path / "capabilities.json"
    with patch.object(capabilities, "_capabilities_path", return_value=caps_file):
        result = capabilities.update_capability("weekly_platform_review", enabled=True, actor="ryan")
    assert result["enabled"] is True
    assert result["enabled_by"] == "ryan"
```

Check the import block at the top of `tests/test_capabilities.py` — it should already import `capabilities` module directly (not via `from ... import`). Confirm and add `from unittest.mock import patch` if not present.

- [ ] **Step 3.2: Run to confirm failure**

```bash
docker exec ikeos pytest tests/test_capabilities.py::test_weekly_platform_review_capability_exists_and_defaults_to_disabled tests/test_capabilities.py::test_update_weekly_platform_review_capability -v
```

Expected: FAIL — `weekly_platform_review` not in `DEFAULT_CAPABILITIES`.

- [ ] **Step 3.3: Add the capability to DEFAULT_CAPABILITIES**

In `app/services/capabilities.py`, extend `DEFAULT_CAPABILITIES`:

```python
DEFAULT_CAPABILITIES: dict = {
    "housekeeping_scheduler": {
        "enabled": False,
        "enabled_by": None,
        "enabled_at": None,
        "description": "Scheduled weekly housekeeping runs via session manager",
    },
    "weekly_platform_review": {
        "enabled": False,
        "enabled_by": None,
        "enabled_at": None,
        "description": "Weekly AI engineering platform review — researches ecosystem developments and scores platform health",
    },
}
```

- [ ] **Step 3.4: Run new tests — should pass**

```bash
docker exec ikeos pytest tests/test_capabilities.py::test_weekly_platform_review_capability_exists_and_defaults_to_disabled tests/test_capabilities.py::test_update_weekly_platform_review_capability -v
```

Expected: PASS

- [ ] **Step 3.5: Run full capabilities test suite**

```bash
docker exec ikeos pytest tests/test_capabilities.py -v
```

Expected: all pass.

- [ ] **Step 3.6: Run full test suite**

```bash
docker exec ikeos pytest tests/ -q
```

Expected: 325+ passed, 0 failed.

- [ ] **Step 3.7: Rebuild container and verify /housekeeping/capabilities lists both capabilities**

```bash
docker.exe compose up --build -d ikeos
curl -s http://localhost:5009/housekeeping/capabilities | python3 -m json.tool
```

Expected: JSON with `housekeeping_scheduler` and `weekly_platform_review`, both `"enabled": false`.

- [ ] **Step 3.8: Commit**

```bash
git add app/services/capabilities.py tests/test_capabilities.py
git commit -m "feat: register weekly_platform_review as a controlled capability"
```

---

## Self-Review

**Spec coverage:**
- Lowercase slug enforcement: covered by Task 1 (write_entry + capture routes + tests).
- APScheduler guard: covered by Task 2 (startup log visible in container output).
- weekly_platform_review capability: covered by Task 3 (registry + tests + API verification).

**Placeholder scan:** No TBDs, no vague steps. All code blocks are complete.

**Type consistency:** No cross-task type references — each task is self-contained.
