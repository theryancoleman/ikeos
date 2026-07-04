# Observability Sprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface per-run housekeeping history in the housekeeping UI and add a reflection health widget to the dashboard by wiring the existing-but-idle metrics plumbing to the existing-but-idle claude-config health data.

**Architecture:** Two additive features sharing a single sprint. (1) Housekeeping runs are instrumented by calling `append_event("housekeeping.run", …)` inside `patch_housekeeping()` when a heartbeat PATCH arrives — the event lands in `events.jsonl` and the housekeeping page reads the last 10. (2) A new `app/services/reflection.py` reads `$CLAUDE_CONFIG_DIR/library/weak-signals.json` and `library/metrics.json`, returning a structured dict; the dashboard route calls it and the dashboard template renders a health card.

**Tech Stack:** Flask, Python 3.11+, pytest, Jinja2, JSON-lines (`events.jsonl`), plain JSON files in claude-config.

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `app/services/metrics.py` | Add `read_events_by_type()` helper |
| Modify | `app/routes/capture.py` | Call `append_event()` in `patch_housekeeping()` |
| Modify | `app/routes/housekeeping.py` | Pass recent runs to template context |
| Modify | `app/templates/housekeeping.html` | Render recent-runs table |
| Create | `app/services/reflection.py` | Read weak-signals + metrics from claude-config |
| Modify | `app/routes/browse.py` | Call reflection service in dashboard route |
| Modify | `app/templates/dashboard.html` | Render reflection health card |
| Modify | `tests/test_metrics.py` (or create) | Tests for `read_events_by_type()` |
| Create | `tests/test_housekeeping_instrumentation.py` | Tests for event emission in patch route |
| Create | `tests/test_reflection.py` | Tests for reflection health service |

---

### Task 1: Add `read_events_by_type()` to metrics service

**Files:**
- Modify: `app/services/metrics.py`
- Test: `tests/test_metrics.py` (check if it exists; create if not)

- [ ] **Step 1: Write the failing test**

Check whether `tests/test_metrics.py` exists: `ls /mnt/c/Server/projects/ikeos/tests/test_metrics.py 2>/dev/null || echo missing`

If missing, create it. Either way, add this test:

```python
# tests/test_metrics.py
import json
from pathlib import Path
from unittest.mock import patch
from app.services.metrics import read_events_by_type


def test_read_events_by_type_filters_correctly(tmp_path):
    events_file = tmp_path / "events.jsonl"
    lines = [
        json.dumps({"event": "housekeeping.run", "tasks_run": 3, "timestamp": "2026-07-01T10:00:00+00:00"}),
        json.dumps({"event": "session.created", "project": "ikeos", "timestamp": "2026-07-01T09:00:00+00:00"}),
        json.dumps({"event": "housekeeping.run", "tasks_run": 5, "timestamp": "2026-07-02T10:00:00+00:00"}),
    ]
    events_file.write_text("\n".join(lines), encoding="utf-8")

    with patch("app.services.metrics.METRICS_PATH", events_file):
        result = read_events_by_type("housekeeping.run", limit=10)

    assert len(result) == 2
    assert all(e["event"] == "housekeeping.run" for e in result)
    # newest first
    assert result[0]["tasks_run"] == 5
    assert result[1]["tasks_run"] == 3


def test_read_events_by_type_respects_limit(tmp_path):
    events_file = tmp_path / "events.jsonl"
    lines = [json.dumps({"event": "housekeeping.run", "tasks_run": i, "timestamp": f"2026-07-0{i+1}T00:00:00+00:00"}) for i in range(5)]
    events_file.write_text("\n".join(lines), encoding="utf-8")

    with patch("app.services.metrics.METRICS_PATH", events_file):
        result = read_events_by_type("housekeeping.run", limit=3)

    assert len(result) == 3


def test_read_events_by_type_missing_file(tmp_path):
    with patch("app.services.metrics.METRICS_PATH", tmp_path / "nonexistent.jsonl"):
        result = read_events_by_type("housekeeping.run")
    assert result == []
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
docker exec ikeos pytest tests/test_metrics.py::test_read_events_by_type_filters_correctly -v
```

Expected: `FAILED` — `ImportError: cannot import name 'read_events_by_type'`

- [ ] **Step 3: Add `read_events_by_type()` to `app/services/metrics.py`**

Append after the existing `read_events()` function:

```python
def read_events_by_type(event_type: str, limit: int = 50) -> list[dict]:
    """Return up to `limit` most-recent events matching `event_type`, newest first."""
    all_events = read_events(limit=limit * 10)  # over-fetch to have room to filter
    return [e for e in all_events if e.get("event") == event_type][:limit]
```

- [ ] **Step 4: Run all three tests**

```bash
docker exec ikeos pytest tests/test_metrics.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite to check for regressions**

```bash
docker exec ikeos pytest -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/metrics.py tests/test_metrics.py
git commit -m "feat: add read_events_by_type() helper to metrics service"
```

---

### Task 2: Instrument housekeeping.run events in patch_housekeeping

**Files:**
- Modify: `app/routes/capture.py` (lines 144–179, `patch_housekeeping()`)
- Create: `tests/test_housekeeping_instrumentation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_housekeeping_instrumentation.py
import json
import pytest
from unittest.mock import patch, MagicMock
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_patch_housekeeping_heartbeat_emits_run_event(tmp_path, client):
    """A heartbeat PATCH with run stats appends a housekeeping.run event."""
    vault = tmp_path / "housekeeping"
    vault.mkdir()
    (vault / "last-run.md").write_text(
        "---\nlast_run: ''\ntasks_run: ''\ntasks_failed: ''\ntasks_skipped: ''\n---\n",
        encoding="utf-8",
    )

    token = "test-token"
    payload = {
        "project": "ikeos",
        "type": "housekeeping-heartbeat",
        "filename": "last-run.md",
        "fields": {
            "last_run": "2026-07-04T12:00:00",
            "tasks_run": "4",
            "tasks_failed": "1",
            "tasks_skipped": "0",
        },
    }

    emitted = []

    with patch("app.routes.capture._get_capture_token", return_value=token), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.capture.append_event", side_effect=lambda *a, **k: emitted.append((a, k)) or True):
        resp = client.patch(
            "/entries/housekeeping",
            json=payload,
            headers={"X-Capture-Token": token},
        )

    assert resp.status_code == 200
    assert len(emitted) == 1
    event_type, event_payload = emitted[0][0]
    assert event_type == "housekeeping.run"
    assert event_payload["tasks_run"] == 4
    assert event_payload["tasks_failed"] == 1
    assert event_payload["tasks_skipped"] == 0


def test_patch_housekeeping_task_does_not_emit_run_event(tmp_path, client):
    """A task-level PATCH (not heartbeat) must NOT emit a housekeeping.run event."""
    vault = tmp_path / "housekeeping"
    vault.mkdir()
    (vault / "my-task.md").write_text(
        "---\ntitle: My task\nenabled: 'true'\nlast_run: ''\nconsecutive_failures: 0\n---\n",
        encoding="utf-8",
    )

    token = "test-token"
    payload = {
        "project": "ikeos",
        "type": "housekeeping-task",
        "filename": "my-task.md",
        "fields": {"last_run": "2026-07-04T12:00:00", "consecutive_failures": 0},
    }

    emitted = []

    with patch("app.routes.capture._get_capture_token", return_value=token), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.capture.append_event", side_effect=lambda *a, **k: emitted.append((a, k)) or True):
        resp = client.patch(
            "/entries/housekeeping",
            json=payload,
            headers={"X-Capture-Token": token},
        )

    assert resp.status_code == 200
    assert len(emitted) == 0
```

- [ ] **Step 2: Run to confirm they fail**

```bash
docker exec ikeos pytest tests/test_housekeeping_instrumentation.py -v
```

Expected: `FAILED` — `cannot import name 'append_event'` or the assertion on `emitted` fails.

- [ ] **Step 3: Instrument `patch_housekeeping()` in `app/routes/capture.py`**

Add the import at the top of the file (after the existing imports):

```python
from app.services.metrics import append_event
```

Inside `patch_housekeeping()`, add event emission after the successful `update_housekeeping_fields()` call. Find the block at the end of the function:

```python
    success = update_housekeeping_fields(entry_type, project, filename, fields)
    if not success:
        return jsonify({"error": "Entry not found or no valid fields provided"}), 404

    return jsonify({"message": "Updated"}), 200
```

Replace it with:

```python
    success = update_housekeeping_fields(entry_type, project, filename, fields)
    if not success:
        return jsonify({"error": "Entry not found or no valid fields provided"}), 404

    if entry_type == "housekeeping-heartbeat" and "tasks_run" in fields:
        append_event("housekeeping.run", {
            "trigger": fields.get("trigger", "scheduled"),
            "tasks_run": int(fields.get("tasks_run") or 0),
            "tasks_failed": int(fields.get("tasks_failed") or 0),
            "tasks_skipped": int(fields.get("tasks_skipped") or 0),
        })

    return jsonify({"message": "Updated"}), 200
```

- [ ] **Step 4: Run the tests**

```bash
docker exec ikeos pytest tests/test_housekeeping_instrumentation.py -v
```

Expected: both pass.

- [ ] **Step 5: Run full suite**

```bash
docker exec ikeos pytest -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/routes/capture.py tests/test_housekeeping_instrumentation.py
git commit -m "feat: emit housekeeping.run event when heartbeat PATCH arrives"
```

---

### Task 3: Reflection health service

**Files:**
- Create: `app/services/reflection.py`
- Create: `tests/test_reflection.py`

The service reads two JSON files from `$CLAUDE_CONFIG_DIR/library/`. If the env var is unset or the files are missing, it returns `None` — callers must handle the absent case gracefully.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reflection.py
import json
import datetime
from pathlib import Path
from unittest.mock import patch
from app.services.reflection import get_reflection_health


def _write_signals(path: Path, signals: list) -> None:
    path.write_text(json.dumps({"signals": signals}), encoding="utf-8")


def _write_metrics(path: Path, snapshots: list) -> None:
    path.write_text(json.dumps({"snapshots": snapshots}), encoding="utf-8")


def test_get_reflection_health_happy_path(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    today = datetime.date.today()
    recent = (today - datetime.timedelta(days=10)).isoformat()
    old = (today - datetime.timedelta(days=50)).isoformat()

    _write_signals(lib / "weak-signals.json", [
        {"pattern": "A", "last_seen": recent, "occurrences": 4},
        {"pattern": "B", "last_seen": recent, "occurrences": 1},
        {"pattern": "C", "last_seen": old, "occurrences": 5},   # outside 45-day window
        {"pattern": "Session ended without reflection via /close-session", "last_seen": recent, "occurrences": 3},
    ])
    _write_metrics(lib / "metrics.json", [
        {"week": "2026-W26", "reflection_acceptance_rate": 0.6},
        {"week": "2026-W27", "reflection_acceptance_rate": 0.8},
    ])

    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_reflection_health()

    assert result is not None
    assert result["active_signals"] == 3       # A, B, abrupt (old C excluded)
    assert result["pending_promotion"] == 2    # A (4 occ) + abrupt (3 occ)
    assert result["acceptance_rate"] == pytest.approx(0.8)
    assert result["last_snapshot_week"] == "2026-W27"
    assert result["abrupt_endings"] == 3


def test_get_reflection_health_missing_dir(tmp_path):
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path / "nonexistent")):
        result = get_reflection_health()
    assert result is None


def test_get_reflection_health_missing_files(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    # No files written
    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_reflection_health()
    assert result is None


def test_get_reflection_health_no_snapshots(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    today = datetime.date.today()
    recent = (today - datetime.timedelta(days=5)).isoformat()
    _write_signals(lib / "weak-signals.json", [
        {"pattern": "X", "last_seen": recent, "occurrences": 1},
    ])
    _write_metrics(lib / "metrics.json", {"snapshots": []})

    with patch("app.services.reflection.CLAUDE_CONFIG_DIR", str(tmp_path)):
        result = get_reflection_health()

    assert result is not None
    assert result["acceptance_rate"] is None
    assert result["last_snapshot_week"] is None
    assert result["abrupt_endings"] == 0
```

Add `import pytest` at the top of the test file.

- [ ] **Step 2: Run to confirm failure**

```bash
docker exec ikeos pytest tests/test_reflection.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.services.reflection'`

- [ ] **Step 3: Create `app/services/reflection.py`**

```python
import datetime
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CLAUDE_CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR", "")
_ABRUPT_PATTERN = "Session ended without reflection via /close-session"
_ACTIVE_DAYS = 45
_PROMOTION_THRESHOLD = 3


def get_reflection_health() -> dict | None:
    """Return reflection health metrics from claude-config library files, or None if unavailable."""
    if not CLAUDE_CONFIG_DIR:
        return None
    lib = Path(CLAUDE_CONFIG_DIR) / "library"
    signals_path = lib / "weak-signals.json"
    metrics_path = lib / "metrics.json"
    if not signals_path.exists() or not metrics_path.exists():
        return None

    try:
        sig_data = json.loads(signals_path.read_text(encoding="utf-8"))
        met_data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read reflection health files: %s", exc)
        return None

    cutoff = (datetime.date.today() - datetime.timedelta(days=_ACTIVE_DAYS)).isoformat()
    signals = sig_data.get("signals", [])
    active = [s for s in signals if s.get("last_seen", "") >= cutoff]
    pending = [s for s in active if s.get("occurrences", 0) >= _PROMOTION_THRESHOLD]

    abrupt = next((s for s in signals if s.get("pattern") == _ABRUPT_PATTERN), None)
    abrupt_count = abrupt["occurrences"] if abrupt else 0

    snapshots = met_data.get("snapshots", [])
    latest = snapshots[-1] if snapshots else None
    acceptance_rate = latest.get("reflection_acceptance_rate") if latest else None
    last_week = latest.get("week") if latest else None

    return {
        "active_signals": len(active),
        "pending_promotion": len(pending),
        "acceptance_rate": acceptance_rate,
        "last_snapshot_week": last_week,
        "abrupt_endings": abrupt_count,
    }
```

- [ ] **Step 4: Run the tests**

```bash
docker exec ikeos pytest tests/test_reflection.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
docker exec ikeos pytest -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/reflection.py tests/test_reflection.py
git commit -m "feat: add reflection health service reading claude-config library files"
```

---

### Task 4: Recent runs in housekeeping context and template

**Files:**
- Modify: `app/routes/housekeeping.py` (`_housekeeping_context()`)
- Modify: `app/templates/housekeeping.html`
- Test: extend `tests/test_housekeeping_instrumentation.py` with a context test

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_housekeeping_instrumentation.py`:

```python
def test_housekeeping_context_includes_recent_runs(tmp_path, client):
    """_housekeeping_context() must include recent_runs from metrics."""
    import json
    from unittest.mock import patch
    from app.routes.housekeeping import _housekeeping_context

    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps({"event": "housekeeping.run", "tasks_run": 3, "tasks_failed": 0,
                    "tasks_skipped": 0, "trigger": "scheduled",
                    "timestamp": "2026-07-04T10:00:00+00:00"}) + "\n" +
        json.dumps({"event": "session.created", "project": "ikeos",
                    "timestamp": "2026-07-04T09:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    with patch("app.services.metrics.METRICS_PATH", events_file), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.routes.housekeeping.CAPTURE_TOKEN", "tok"), \
         patch("app.routes.housekeeping.get_config_with_next_run", return_value={}), \
         patch("app.routes.housekeeping.latest_draft_name", return_value=None), \
         patch("app.routes.housekeeping.latest_review_name", return_value=None), \
         patch("app.routes.housekeeping.get_capabilities", return_value=[]):
        ctx = _housekeeping_context()

    assert "recent_runs" in ctx
    runs = ctx["recent_runs"]
    assert len(runs) == 1
    assert runs[0]["event"] == "housekeeping.run"
    assert runs[0]["tasks_run"] == 3
```

- [ ] **Step 2: Run to confirm failure**

```bash
docker exec ikeos pytest tests/test_housekeeping_instrumentation.py::test_housekeeping_context_includes_recent_runs -v
```

Expected: `FAILED` — `KeyError: 'recent_runs'`

- [ ] **Step 3: Add `recent_runs` to `_housekeeping_context()` in `app/routes/housekeeping.py`**

Add the metrics import at the top of the file (with the other service imports):

```python
from app.services.metrics import read_events_by_type
```

In `_housekeeping_context()`, add `recent_runs` to the returned dict:

```python
def _housekeeping_context() -> dict:
    tasks = read_housekeeping_tasks()
    heartbeat = read_housekeeping_heartbeat(project_slug())
    schedule = get_config_with_next_run()
    return dict(
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
        schedule=schedule,
        capture_token=CAPTURE_TOKEN,
        blog_draft=latest_draft_name(),
        weekly_review_file=latest_review_name(),
        capabilities=get_capabilities(),
        recent_runs=read_events_by_type("housekeeping.run", limit=10),
    )
```

- [ ] **Step 4: Run the test**

```bash
docker exec ikeos pytest tests/test_housekeeping_instrumentation.py -v
```

Expected: all pass.

- [ ] **Step 5: Add "Recent Runs" table to `app/templates/housekeeping.html`**

Find the closing section of the tasks table (the `</table>` or section after the task table). Add a new section after the Add Task form:

```html
<!-- Recent Runs -->
{% if recent_runs %}
<section class="card" style="margin-top:1.5rem">
  <h2>Recent Runs</h2>
  <table>
    <thead>
      <tr>
        <th>Time</th>
        <th>Trigger</th>
        <th>Run</th>
        <th>Failed</th>
        <th>Skipped</th>
      </tr>
    </thead>
    <tbody>
      {% for run in recent_runs %}
      <tr>
        <td>{{ run.timestamp | replace("T", " ") | replace("+00:00", "") }}</td>
        <td>{{ run.get("trigger", "—") }}</td>
        <td>{{ run.get("tasks_run", "—") }}</td>
        <td class="{{ 'error' if run.get('tasks_failed', 0) > 0 else '' }}">{{ run.get("tasks_failed", "—") }}</td>
        <td>{{ run.get("tasks_skipped", "—") }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</section>
{% endif %}
```

Find the exact insertion point by searching for the closing tag of the last existing section (the Add Task form) in `app/templates/housekeeping.html` and insert after it.

- [ ] **Step 6: Manual smoke test — verify the UI renders**

```bash
docker exec ikeos python -c "
from app import create_app
app = create_app()
with app.test_client() as c:
    r = c.get('/housekeeping')
    print(r.status_code, 'recent_runs' in r.data.decode())
"
```

Expected: `200 True` (or `200 False` if no events exist yet — that's fine, the `{% if recent_runs %}` guard handles it).

- [ ] **Step 7: Run full suite**

```bash
docker exec ikeos pytest -x -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add app/routes/housekeeping.py app/templates/housekeeping.html tests/test_housekeeping_instrumentation.py
git commit -m "feat: show last 10 housekeeping run events in housekeeping UI"
```

---

### Task 5: Reflection health widget on dashboard

**Files:**
- Modify: `app/routes/browse.py` (`tasks()` route)
- Modify: `app/templates/dashboard.html`
- Create: `tests/test_dashboard_reflection.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_reflection.py
import pytest
from unittest.mock import patch
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_dashboard_passes_reflection_health(tmp_path, client):
    """The /tasks route passes reflection_health to the template."""
    mock_health = {
        "active_signals": 4,
        "pending_promotion": 1,
        "acceptance_rate": 0.75,
        "last_snapshot_week": "2026-W27",
        "abrupt_endings": 2,
    }

    with patch("app.routes.browse.get_reflection_health", return_value=mock_health), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        resp = client.get("/tasks")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "4" in body        # active_signals
    assert "75%" in body or "0.75" in body or "75" in body  # acceptance rate rendered


def test_dashboard_handles_missing_reflection_health(tmp_path, client):
    """When reflection service returns None, the dashboard still loads without error."""
    with patch("app.routes.browse.get_reflection_health", return_value=None), \
         patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        resp = client.get("/tasks")

    assert resp.status_code == 200
```

- [ ] **Step 2: Run to confirm failure**

```bash
docker exec ikeos pytest tests/test_dashboard_reflection.py -v
```

Expected: `FAILED` — either `ImportError` or assertion fails because template doesn't render reflection data.

- [ ] **Step 3: Wire reflection health into the dashboard route in `app/routes/browse.py`**

Add the import after the existing imports:

```python
from app.services.reflection import get_reflection_health
```

In the `tasks()` function, add the call and pass it to the template (insert before `return render_template(...)`):

```python
    reflection_health = get_reflection_health()

    return render_template(
        "dashboard.html",
        projects=projects,
        project_stats=project_stats,
        in_flight=in_flight,
        needs_triage=needs_triage,
        housekeeping_heartbeat=heartbeat,
        hk_age=hk_age,
        hk_status=hk_status,
        blog_draft=blog_draft,
        reflection_health=reflection_health,
    )
```

- [ ] **Step 4: Add reflection health card to `app/templates/dashboard.html`**

Find the existing housekeeping heartbeat widget section (around lines 97–120 per the scout report). Add a new card below it:

```html
<!-- Reflection Health -->
{% if reflection_health %}
<div class="widget-card">
  <h3>Reflection Health</h3>
  <div class="widget-row">
    <span class="label">Active signals (45d)</span>
    <span class="value">{{ reflection_health.active_signals }}</span>
  </div>
  <div class="widget-row">
    <span class="label">Pending promotion</span>
    <span class="value {{ 'warn' if reflection_health.pending_promotion > 0 else '' }}">{{ reflection_health.pending_promotion }}</span>
  </div>
  {% if reflection_health.acceptance_rate is not none %}
  <div class="widget-row">
    <span class="label">Acceptance rate</span>
    <span class="value">{{ (reflection_health.acceptance_rate * 100) | int }}%</span>
  </div>
  {% endif %}
  {% if reflection_health.abrupt_endings > 0 %}
  <div class="widget-row warn">
    <span class="label">Abrupt session endings</span>
    <span class="value">{{ reflection_health.abrupt_endings }}</span>
  </div>
  {% endif %}
  {% if reflection_health.last_snapshot_week %}
  <div class="widget-row muted">
    <span class="label">Last snapshot</span>
    <span class="value">{{ reflection_health.last_snapshot_week }}</span>
  </div>
  {% endif %}
</div>
{% endif %}
```

- [ ] **Step 5: Run the tests**

```bash
docker exec ikeos pytest tests/test_dashboard_reflection.py -v
```

Expected: both pass.

- [ ] **Step 6: Run full suite**

```bash
docker exec ikeos pytest -x -q
```

Expected: all pass.

- [ ] **Step 7: Rebuild and smoke-test in browser**

```bash
docker.exe compose up --build -d ikeos
```

Open `http://localhost:5009/tasks` and verify the reflection health card appears (or is absent if `CLAUDE_CONFIG_DIR` is not set — that's expected and correct).

- [ ] **Step 8: Commit**

```bash
git add app/routes/browse.py app/templates/dashboard.html tests/test_dashboard_reflection.py
git commit -m "feat: add reflection health widget to dashboard"
```

---

## Self-Review

**Spec coverage:**
- ✅ Per-run ledger: events emitted (Task 2), visible in housekeeping UI (Task 4)
- ✅ Reflection health: service reads claude-config files (Task 3), widget on dashboard (Task 5)
- ✅ `read_events_by_type()` helper for reuse (Task 1)
- ✅ `trigger` field captured in events — can distinguish scheduled vs. manual runs
- ℹ️ Token cost and judge verdict are out of scope for this sprint (requires session-manager changes; tracked in vault)

**Placeholder scan:** None found — all code blocks are complete with exact signatures.

**Type consistency:**
- `read_events_by_type()` returns `list[dict]` — consumed as list in `_housekeeping_context()` ✅
- `get_reflection_health()` returns `dict | None` — callers check `if reflection_health` ✅
- `append_event()` signature: `(event_type: str, payload: dict) -> bool` — called correctly in Task 2 ✅
- `recent_runs` key in context dict matches `recent_runs` in template ✅
- `reflection_health` key in render_template matches template variable ✅
