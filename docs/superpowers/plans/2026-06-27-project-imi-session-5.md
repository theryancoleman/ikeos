# Project 'Imi Session 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the three items deferred from Session 4: add `experiment` as a first-class vault entry type, instrument the first metrics write path (`housekeeping.trigger` event), and formally resolve the housekeeping permission-prompt bug by creating the cross-project fix note and documenting the decision.

**Architecture:** Task 1 threads `experiment` through the full vault stack — constants → write/read/update functions → capture route → capture form. Task 2 creates a thin `metrics.py` service and wires it into the housekeeping scheduler trigger. Task 3 closes the IkeOS side of the housekeeping permission bug by documenting the fix decision and creating the cross-project capture API entry for claude-config. No database, no new dependencies.

**Tech Stack:** Python 3.11, Flask, python-frontmatter, pytest, Docker

---

## Scope Note

These three tasks are independent — they can be executed in any order. Each task produces a working, testable increment on its own. The verification contract at the bottom applies to all three together.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/services/vault_cache.py` | Add `"experiment"` to VALID_TYPES, TYPE_FOLDERS, TYPE_TAGS; add EXPERIMENT_STATUSES constant |
| Modify | `app/services/vault_entries.py` | Handle experiment fields in `write_entry()`; add `"experiments"` to `read_entry()` and `update_entry_status()` folder scans; handle experiment status in `update_entry_status_generic()` |
| Modify | `app/routes/capture.py` | Add `"experiment"` to `PATCH /entries` valid types and `POST /capture/json` valid types; extract experiment fields in `capture_submit()` and `capture_json()` |
| Modify | `app/templates/capture.html` | Add Experiment radio button and conditional experiment-fields section |
| Create | `app/services/metrics.py` | `append_event(event_type, payload)` — writes JSON-lines to METRICS_PATH |
| Modify | `app/services/scheduler.py` | Call `metrics.append_event("housekeeping.trigger", ...)` inside `trigger_now()` |
| Modify | `docker-compose.yml` | Add `METRICS_PATH=/metrics/events.jsonl` environment override |
| Modify | `.env.example` | Add `METRICS_PATH` placeholder |
| Modify | `tests/test_vault_entries.py` | Add experiment write and status-update tests |
| Modify | `tests/test_capture.py` | Add experiment `capture_json` test |
| Create | `tests/test_metrics.py` | Unit tests for `append_event()` |
| Modify | `.claude/DECISIONS.md` | Document experiment status lifecycle and housekeeping bug fix decision |

---

## Critical reading before starting

- `app/services/vault_cache.py` — understand VALID_TYPES, TYPE_FOLDERS, TYPE_TAGS constants
- `app/services/vault_entries.py` — read `write_entry()`, `read_entry()`, `update_entry_status()`, `update_entry_status_generic()` in full before touching them
- `app/routes/capture.py` — understand `capture_submit()`, `capture_json()`, and `patch_entries()` before modifying
- `app/templates/capture.html` — understand the `conditional hidden` pattern and JS `updateFields()` before adding experiment fields
- `docs/experiment-framework.md` — the canonical spec for what an experiment entry looks like

---

## Task 1: Add `experiment` as a first-class vault entry type

**Files:**
- Modify: `app/services/vault_cache.py`
- Modify: `app/services/vault_entries.py`
- Modify: `app/routes/capture.py`
- Modify: `app/templates/capture.html`
- Modify: `tests/test_vault_entries.py`
- Modify: `tests/test_capture.py`

### Step 1: Write failing tests for experiment write and status update

In `tests/test_vault_entries.py`, add these tests after the existing ones:

```python
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
```

- [x] **Step 2: Run failing tests**

```bash
docker exec ikeos pytest tests/test_vault_entries.py::test_write_entry_experiment_creates_in_experiments_folder tests/test_vault_entries.py::test_write_entry_experiment_sets_status_running tests/test_vault_entries.py::test_update_entry_status_generic_experiment_complete -v 2>&1 | tail -15
```

Expected: 3 FAILED — `"experiment"` not in VALID_TYPES / no experiments folder logic.

- [x] **Step 3: Update `vault_cache.py` — add experiment constants**

Apply these four changes to `app/services/vault_cache.py`:

```python
# VALID_TYPES — add "experiment"
VALID_TYPES = {
    "note", "idea", "bug", "decision",
    "grill-me", "housekeeping-task", "housekeeping-heartbeat", "experiment",
}

# TYPE_FOLDERS — add "experiment"
TYPE_FOLDERS = {
    "note": "notes", "idea": "ideas", "bug": "bugs",
    "grill-me": "grill-me", "experiment": "experiments",
}

# TYPE_TAGS — add "experiment"
TYPE_TAGS = {
    "note": "documentation",
    "idea": "enhancement",
    "bug": "bug",
    "decision": "decision",
    "grill-me": "grill-me",
    "experiment": "experiment",
}

# New constant — add after DECISION_STATUSES
EXPERIMENT_STATUSES = {"running", "complete", "abandoned"}
```

- [x] **Step 4: Update `vault_entries.py` — four changes**

**Change A:** In `write_entry()`, add the experiment case alongside the existing `if entry_type == "idea":` / `elif entry_type == "bug":` block. Find this section and add the new elif:

```python
        if entry_type == "idea":
            metadata["priority"] = data.get("priority", "medium")
            metadata["effort"] = data.get("effort", "medium")
            why = data.get("why", "").strip()
            if why:
                metadata["why"] = why
        elif entry_type == "bug":
            metadata["severity"] = data.get("severity", "medium")
        elif entry_type == "experiment":
            metadata["status"] = "running"
            metadata["hypothesis"] = data.get("hypothesis", "")
            metadata["expected_outcome"] = data.get("expected_outcome", "")
            metadata["measurement"] = data.get("measurement", "")
            metadata["success_criteria"] = data.get("success_criteria", "")
            metadata["timebox"] = data.get("timebox", "")
            metadata["result"] = ""
            metadata["decision"] = ""
```

Also update the `tags` list in `write_entry()` — the `status/new` tag is set before the type-specific block. For experiments, the initial status is `running`, not `new`. Find this line:

```python
        tags = [type_tag, project, "status/new"]
```

And change it to:

```python
        initial_status = "running" if entry_type == "experiment" else "new"
        tags = [type_tag, project, f"status/{initial_status}"]
```

Also update `metadata["status"]` which is set to `"new"` before the type block:

```python
        metadata = {
            "type": entry_type,
            "title": title,
            "project": project,
            "status": "new",     # ← change this line
```

Change to:

```python
        metadata = {
            "type": entry_type,
            "title": title,
            "project": project,
            "status": "running" if entry_type == "experiment" else "new",
```

**Change B:** In `read_entry()`, add `"experiments"` to the folder scan:

```python
def read_entry(project: str, slug: str) -> dict | None:
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for folder in ("bugs", "ideas", "notes", "grill-me", "experiments"):
```

**Change C:** In `update_entry_status()`, add `"experiments"` to the folder scan:

```python
def update_entry_status(project: str, slug: str, new_status: str) -> bool:
    if new_status not in _vc.VALID_STATUSES:
        return False
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for folder in ("bugs", "ideas", "notes", "grill-me", "experiments"):
```

**Change D:** In `update_entry_status_generic()`, add experiment branch and add `"experiment"` to `folder_map`. Find the `else:` block that checks `VALID_STATUSES` and the `folder_map` dict:

```python
    else:
        if new_status not in _vc.VALID_STATUSES:
            return False
        if not project:
            return False
        folder_map = {"bug": "bugs", "idea": "ideas", "note": "notes", "grill-me": "grill-me"}
        folder = folder_map.get(entry_type)
        if folder is None:
            return False
        base_path = _vc.VAULT_PATH / "projects" / project / folder
```

Replace with:

```python
    elif entry_type == "experiment":
        if new_status not in _vc.EXPERIMENT_STATUSES:
            return False
        if not project:
            return False
        base_path = _vc.VAULT_PATH / "projects" / project / "experiments"
    else:
        if new_status not in _vc.VALID_STATUSES:
            return False
        if not project:
            return False
        folder_map = {
            "bug": "bugs", "idea": "ideas", "note": "notes",
            "grill-me": "grill-me",
        }
        folder = folder_map.get(entry_type)
        if folder is None:
            return False
        base_path = _vc.VAULT_PATH / "projects" / project / folder
```

- [x] **Step 5: Run tests — must all pass**

```bash
docker exec ikeos pytest tests/test_vault_entries.py -v 2>&1 | tail -20
```

Expected: all PASSED (existing + 3 new).

- [x] **Step 6: Update `capture.py` — three locations**

**Location A:** `patch_entries()` — line 107: add `"experiment"` to the valid types tuple:

```python
    if entry_type not in ("bug", "idea", "note", "decision", "grill-me", "experiment"):
        return jsonify({"error": "Invalid entry type"}), 400

    valid_statuses = (
        ("proposed", "accepted", "rejected", "superseded") if entry_type == "decision"
        else ("running", "complete", "abandoned") if entry_type == "experiment"
        else ("new", "open", "in-progress", "done", "deferred")
    )
```

**Location B:** `capture_submit()` — add experiment field extraction after the `elif entry_type == "bug":` block:

```python
    elif entry_type == "bug":
        data["severity"] = request.form.get("severity", "medium")
        data["steps"] = request.form.get("steps", "")
    elif entry_type == "experiment":
        data["hypothesis"] = request.form.get("hypothesis", "").strip()
        data["expected_outcome"] = request.form.get("expected_outcome", "").strip()
        data["measurement"] = request.form.get("measurement", "").strip()
        data["success_criteria"] = request.form.get("success_criteria", "").strip()
        data["timebox"] = request.form.get("timebox", "").strip()
```

**Location C:** `capture_json()` — update the valid-types check and add experiment field extraction:

```python
    if entry_type not in ("note", "idea", "bug", "grill-me", "housekeeping-task", "housekeeping-heartbeat", "experiment"):
        return jsonify({"error": "type must be note, idea, bug, grill-me, housekeeping-task, housekeeping-heartbeat, or experiment"}), 400
```

Add after the `elif entry_type == "housekeeping-task":` block:

```python
    elif entry_type == "experiment":
        data["hypothesis"] = req.get("hypothesis", "")
        data["expected_outcome"] = req.get("expected_outcome", "")
        data["measurement"] = req.get("measurement", "")
        data["success_criteria"] = req.get("success_criteria", "")
        data["timebox"] = req.get("timebox", "")
```

- [x] **Step 7: Write capture_json experiment test**

In `tests/test_capture.py`, add after the existing capture_json tests:

```python
def test_capture_json_experiment(client, tmp_vault):
    resp = client.post("/capture/json", json={
        "type": "experiment",
        "project": "testproject",
        "title": "Cache Experiment",
        "body": "Testing cache",
        "hypothesis": "Caching will be faster",
        "expected_outcome": "Sub-50ms reads",
        "measurement": "Response time",
        "success_criteria": "< 50ms",
        "timebox": "one session",
    })
    assert resp.status_code == 200
    files = list((tmp_vault / "projects" / "testproject" / "experiments").glob("*.md"))
    assert len(files) == 1
    import frontmatter as fm
    post = fm.load(files[0])
    assert post.metadata["type"] == "experiment"
    assert post.metadata["status"] == "running"
    assert post.metadata["hypothesis"] == "Caching will be faster"
    assert post.metadata["timebox"] == "one session"
```

- [x] **Step 8: Run capture test**

```bash
docker exec ikeos pytest tests/test_capture.py::test_capture_json_experiment -v 2>&1 | tail -10
```

Expected: PASSED.

- [x] **Step 9: Update `capture.html` — add Experiment radio and conditional fields**

**Add the Experiment radio button** in the `type-radios` div, after the grill-me radio:

```html
      <label class="type-radio-label"><input type="radio" name="type" id="type-grill-me" value="grill-me"> Grill Me</label>
      <label class="type-radio-label"><input type="radio" name="type" id="type-experiment" value="experiment"> Experiment</label>
```

**Add the experiment-fields section** after the `<div id="bug-fields"...>` closing `</div>`:

```html
  <div id="experiment-fields" class="conditional hidden">
    <div class="ike-field">
      <label class="ike-eyebrow" for="hypothesis">Hypothesis</label>
      <input id="hypothesis" name="hypothesis" type="text" placeholder="If we do X, then Y will happen">
    </div>
    <div class="ike-field">
      <label class="ike-eyebrow" for="expected_outcome">Expected Outcome</label>
      <input id="expected_outcome" name="expected_outcome" type="text" placeholder="Specific, measurable result if hypothesis is correct">
    </div>
    <div class="ike-field">
      <label class="ike-eyebrow" for="measurement">Measurement</label>
      <input id="measurement" name="measurement" type="text" placeholder="How will we know — what will we observe">
    </div>
    <div class="ike-field">
      <label class="ike-eyebrow" for="success_criteria">Success Criteria</label>
      <input id="success_criteria" name="success_criteria" type="text" placeholder="The threshold that counts as success">
    </div>
    <div class="ike-field">
      <label class="ike-eyebrow" for="timebox">Timebox</label>
      <input id="timebox" name="timebox" type="text" placeholder="e.g. one session, 1 week">
    </div>
  </div>
```

**Update the `updateFields()` JS function** to show/hide the experiment fields alongside idea and bug:

```javascript
function updateFields(type) {
  document.getElementById('idea-fields').classList.add('hidden');
  document.getElementById('bug-fields').classList.add('hidden');
  document.getElementById('experiment-fields').classList.add('hidden');
  if (type === 'idea') document.getElementById('idea-fields').classList.remove('hidden');
  if (type === 'bug') document.getElementById('bug-fields').classList.remove('hidden');
  if (type === 'experiment') document.getElementById('experiment-fields').classList.remove('hidden');
}
```

- [x] **Step 10: Run the full test suite**

```bash
docker exec ikeos pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass, 0 failures.

- [x] **Step 11: Rebuild and smoke test capture form**

```bash
docker.exe compose up --build -d ikeos 2>&1 | tail -3
sleep 3
curl -s http://localhost:5009/health
```

Open `http://localhost:5009/capture` in a browser. Verify the "Experiment" radio button appears and selecting it shows the hypothesis/expected_outcome/measurement/success_criteria/timebox fields.

- [x] **Step 12: Commit**

```bash
git add app/services/vault_cache.py app/services/vault_entries.py \
        app/routes/capture.py app/templates/capture.html \
        tests/test_vault_entries.py tests/test_capture.py
git commit -m "feat: add experiment as a first-class vault entry type

Experiments track engineering bets with hypothesis, expected_outcome,
measurement, success_criteria, and timebox fields. Status lifecycle
is running → complete | abandoned (separate from standard new/open/done).
Wired into write_entry, read_entry, update_entry_status_generic,
capture form, capture_json, and PATCH /entries. Vault folder: experiments/."
```

---

## Task 2: Metrics service and housekeeping trigger event

**Files:**
- Create: `app/services/metrics.py`
- Modify: `app/services/scheduler.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Create: `tests/test_metrics.py`

### Step 1: Write failing tests for metrics.append_event()

Create `tests/test_metrics.py`:

```python
import json
import pytest
from pathlib import Path


def test_append_event_creates_file(tmp_path, monkeypatch):
    metrics_path = tmp_path / "events.jsonl"
    import app.services.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    result = metrics_mod.append_event("test.event", {"project": "myproj"})
    assert result is True
    assert metrics_path.exists()


def test_append_event_writes_valid_json(tmp_path, monkeypatch):
    metrics_path = tmp_path / "events.jsonl"
    import app.services.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    metrics_mod.append_event("test.event", {"project": "myproj", "x": 1})
    line = metrics_path.read_text().strip()
    event = json.loads(line)
    assert event["event"] == "test.event"
    assert event["project"] == "myproj"
    assert event["x"] == 1
    assert "timestamp" in event


def test_append_event_creates_nested_parent_dir(tmp_path, monkeypatch):
    metrics_path = tmp_path / "nested" / "dir" / "events.jsonl"
    import app.services.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    metrics_mod.append_event("test.event", {})
    assert metrics_path.exists()


def test_append_event_multiple_events_newline_delimited(tmp_path, monkeypatch):
    metrics_path = tmp_path / "events.jsonl"
    import app.services.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    metrics_mod.append_event("first", {"n": 1})
    metrics_mod.append_event("second", {"n": 2})
    lines = [l for l in metrics_path.read_text().splitlines() if l]
    assert len(lines) == 2
    events = [json.loads(l) for l in lines]
    assert events[0]["event"] == "first"
    assert events[1]["event"] == "second"


def test_append_event_returns_false_when_path_unwritable(tmp_path, monkeypatch):
    import app.services.metrics as metrics_mod
    # Point at an impossible path (a file used as a directory)
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a dir")
    metrics_path = blocker / "events.jsonl"
    monkeypatch.setattr(metrics_mod, "METRICS_PATH", metrics_path)
    result = metrics_mod.append_event("test.event", {})
    assert result is False
```

- [x] **Step 2: Run to confirm failure**

```bash
docker exec ikeos pytest tests/test_metrics.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'app.services.metrics'`

- [x] **Step 3: Create `app/services/metrics.py`**

```python
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

METRICS_PATH = Path(os.environ.get("METRICS_PATH", "/metrics/events.jsonl"))


def append_event(event_type: str, payload: dict) -> bool:
    """Append a JSON-lines event to METRICS_PATH. Returns False on write failure."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event_type,
        **payload,
    }
    try:
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(METRICS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        return True
    except OSError:
        logger.warning("Failed to write metrics event %s to %s", event_type, METRICS_PATH)
        return False
```

- [x] **Step 4: Run tests — must all pass**

```bash
docker exec ikeos pytest tests/test_metrics.py -v 2>&1 | tail -10
```

Expected: 5 PASSED.

- [x] **Step 5: Wire `housekeeping.trigger` event into `scheduler.py`**

In `app/services/scheduler.py`, find `trigger_now()`. After the `_schedule_command(...)` call and `_write_config(config)` call, add the metrics event emission. The full updated `trigger_now()`:

```python
def trigger_now() -> str | None:
    now = datetime.now()
    session_name = f"housekeeping-{now.strftime('%Y%m%d')}"
    sm_url = os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")
    project_dir = os.environ.get("HOUSEKEEPING_PROJECT_DIR", "/mnt/c/Server/claude-config")
    try:
        create_resp = requests.post(
            f"{sm_url}/sessions",
            json={"name": session_name, "project": "claude-config", "project_dir": project_dir},
            timeout=5,
        )
        if not create_resp.ok:
            logger.error("Failed to create housekeeping session: %s", create_resp.status_code)
            return None
        session_id = create_resp.json().get("id")
        if not session_id:
            logger.error("No session ID returned from session manager")
            return None
    except (requests.RequestException, OSError):
        logger.exception("Housekeeping trigger failed")
        return None

    _schedule_command(sm_url, session_id, "/housekeeping — run in scheduled mode")
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

- [x] **Step 6: Run the full test suite to confirm no regressions**

```bash
docker exec ikeos pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass.

- [x] **Step 7: Update `docker-compose.yml` — add METRICS_PATH**

In `docker-compose.yml`, find the `environment:` section (currently only `VAULT_PATH=/vault`) and add `METRICS_PATH`:

```yaml
    environment:
      - VAULT_PATH=/vault
      - METRICS_PATH=/metrics/events.jsonl
```

Also add the metrics volume mount alongside the vault mount:

```yaml
    volumes:
      - ${VAULT_PATH}:/vault:rw
      - ${METRICS_PATH_HOST}:/metrics:rw
      - ${CLAUDE_VERSION_PATH}:/claude-config/VERSION:ro
```

Wait — a file mount needs the host path of the **directory**, not the file. The cleanest approach is to mount the metrics directory rather than the file. Use a new `METRICS_PATH_HOST` env var for the host directory:

```yaml
    environment:
      - VAULT_PATH=/vault
      - METRICS_PATH=/metrics/events.jsonl
    volumes:
      - ${VAULT_PATH}:/vault:rw
      - ${METRICS_PATH_HOST}:/metrics:rw
      - ${CLAUDE_VERSION_PATH}:/claude-config/VERSION:ro
```

- [x] **Step 8: Update `.env.example`**

Add after the existing `VAULT_PATH` line:

```
# Host directory for metrics events (events.jsonl written here by the app)
METRICS_PATH_HOST=/path/to/.claude/metrics
```

- [x] **Step 9: Update your `.env` with the real path**

```bash
echo 'METRICS_PATH_HOST=C:\Users\ServerAdmin\.claude\metrics' >> /mnt/c/Server/projects/ikeos/.env
```

(The `.env` is gitignored — this is safe.)

- [x] **Step 10: Rebuild and verify metrics path works**

```bash
docker.exe compose up --build -d ikeos 2>&1 | tail -3
sleep 3
docker exec ikeos env | grep METRICS_PATH
```

Expected: `METRICS_PATH=/metrics/events.jsonl`

- [x] **Step 11: Commit**

```bash
git add app/services/metrics.py tests/test_metrics.py \
        app/services/scheduler.py \
        docker-compose.yml .env.example
git commit -m "feat: add metrics service and emit housekeeping.trigger events

Creates app/services/metrics.py with append_event() that writes
JSON-lines to METRICS_PATH (default /metrics/events.jsonl).
Wires housekeeping.trigger event into scheduler.trigger_now() so
every scheduled and manual housekeeping dispatch is recorded.
Adds METRICS_PATH_HOST volume mount to docker-compose for host
filesystem persistence."
```

---

## Task 3: Housekeeping permission bug — resolution and cross-project note

**Files:**
- Modify: `.claude/DECISIONS.md`

The root cause of the housekeeping permission bug (vault 2026-06-21) is that subagents dispatched by the `/housekeeping` skill in Claude Code inherit the session's permission context, which prompts for Bash commands not in the allowlist. This is not fixable from the IkeOS app — IkeOS dispatches the session, but permission grants are controlled by `claude-config/global/settings.json` (which governs what Bash commands are auto-approved in Claude Code sessions).

The IkeOS-side improvement from Task 2 (metrics) gives us observability. This task documents the fix decision and creates the actionable cross-project note.

- [x] **Step 1: Update bug status to `in-progress` (if not already)**

Verify the bug status:

```bash
grep "status:" /mnt/c/Server/obsidian-vault/projects/ikeos/bugs/2026-06-21-housekeeping-scheduled-runs-stall-on-bash-permissi.md
```

If status is already `in-progress`, no change needed. If it's `new` or `open`, patch it:

```bash
curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=bug" \
  -d "filename=2026-06-21-housekeeping-scheduled-runs-stall-on-bash-permissi" \
  -d "status=in-progress"
```

- [x] **Step 2: Create cross-project vault entry for claude-config allowlist fix**

The actionable fix is: add `Bash(python3 *)` and `Bash(python *)` to the allowlist in `claude-config/global/settings.json` so that Python-based housekeeping tasks (like vault-schema-check) run without prompts in unattended sessions.

```bash
curl -s -o /dev/null -X POST http://localhost:5009/capture \
  -d "type=idea" \
  -d "project=claude-config" \
  -d "title=Add Python Bash allowlist entries for housekeeping subagents" \
  -d "priority=high" \
  -d "body=Housekeeping scheduled runs stall on Bash permission prompts when subagents try to run Python scanners (e.g. vault-schema-check runs python3 to scan frontmatter). Fix: add Bash(python3 *) and Bash(python *) to the allowlist in claude-config/global/settings.json (or the scoped equivalent for the claude-config project context). This unblocks unattended housekeeping operation. Cross-project dependency from ikeos bug 2026-06-21. Reference: ikeos/docs/imi-audit.md item 10."
```

Verify the entry was created:

```bash
ls /mnt/c/Server/obsidian-vault/projects/claude-config/ideas/ | grep "python"
```

Expected: a new `*.md` file for this idea.

- [x] **Step 3: Append housekeeping fix decision to `.claude/DECISIONS.md`**

Read `.claude/DECISIONS.md` first to see the current last entry, then append:

```markdown
## 2026-06-27: Experiment entry type uses separate status lifecycle

Experiments use `running → complete | abandoned` rather than the standard `new → open → in-progress → done | deferred`. Added `EXPERIMENT_STATUSES` constant to `vault_cache.py` and branched `update_entry_status_generic()` to validate against the right set per type. The PATCH /entries endpoint mirrors this branch. Standard status fields (`new`, `open`, etc.) were not extended — experiment statuses are isolated to prevent contaminating the triage flow (which looks for `status: new`).

## 2026-06-27: Housekeeping permission bug fix deferred to claude-config

The root cause of vault bug 2026-06-21 (subagents stalling on Bash permission prompts in unattended housekeeping sessions) is not fixable from the IkeOS app layer. IkeOS dispatches a Claude Code session; permission grants are governed by `claude-config/global/settings.json`. The chosen fix: add `Bash(python3 *)` and `Bash(python *)` to the allowlist in `claude-config/global/settings.json`, scoped to the claude-config project context. An idea entry has been created in the claude-config vault project tracking this work. IkeOS side: the `housekeeping.trigger` metrics event (Task 2, Session 5) provides the observability needed to detect failed or stalled runs.
```

- [x] **Step 4: Commit**

```bash
git add .claude/DECISIONS.md
git commit -m "docs: document experiment status lifecycle and housekeeping fix decision

Records two decisions: experiment entries use a separate
running/complete/abandoned lifecycle (not the standard vault statuses);
housekeeping permission bug is a claude-config allowlist fix, not an
IkeOS app change. Cross-project note created in claude-config vault."
```

---

## Task 4: Session 5 'Imi Output

At the conclusion of every 'Imi session, produce the 8-section output directly to the user (do not commit it as a file).

- [x] **Step 1: Produce Session 5 output**

Answer each heading:

**Executive Summary** — What was accomplished? What did we learn?

**Files Changed** — Every file modified or created, one-line description.

**Architectural Decisions** — New entries added to DECISIONS.md.

**Public Release Progress** — Which open audit items are now resolved?

**Technical Debt** — What shortcuts were taken deliberately?

**Lessons Learned** — What was surprising or non-obvious?

**Platform Health Observations** — What is in good shape? What is fragile?

**Highest ROI Next Task** — One sentence: what should Session 6 start with?

---

## Verification Contract

Session 5 is done when:

- [x] `docker exec ikeos pytest tests/ -q` shows 0 failures, and the new experiment and metrics tests are included in the count
- [x] `curl -s -X POST http://localhost:5009/capture/json -H "Content-Type: application/json" -d '{"type":"experiment","project":"ikeos","title":"Test","body":"","hypothesis":"H","expected_outcome":"O","measurement":"M","success_criteria":"S","timebox":"1 week"}' | python3 -m json.tool` returns `{"ok": true}`
- [x] An `experiments/` folder is created in the vault under the ikeos project after the above capture
- [x] `docker exec ikeos python -c "from app.services.metrics import append_event; print(append_event('test', {'x':1}))"` prints `True`
- [x] A `housekeeping.trigger` event is appended to events.jsonl when the housekeeping trigger endpoint is called
- [x] A cross-project idea exists in `claude-config` vault for the Python allowlist fix
- [x] DECISIONS.md has entries for experiment status lifecycle and housekeeping fix approach
- [x] `curl -s http://localhost:5009/health` returns `ok`
