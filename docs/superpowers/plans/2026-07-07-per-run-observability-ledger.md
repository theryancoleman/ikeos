# Per-Run Observability Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record per-task outcomes (name, result, error) in each `housekeeping.run` metrics event so failed tasks are visible in the UI without grepping container logs.

**Architecture:** The housekeeping skill already tracks per-task outcomes during Phase 5/6 — it just doesn't include them in the Phase 7 heartbeat PATCH. We extend the Phase 7 payload to include a `task_results` list, pass it through the capture route into the metrics event, and render it as expandable rows in the Recent Runs table. `task_results` is transient run data: it flows skill → API → metrics JSONL but never touches the vault file (the vault allowlist already blocks it).

**Tech Stack:** Python 3.11, Flask, Jinja2, vanilla HTML (`<details>`/`<summary>` for collapsible rows), pytest

---

### Task 1: Extend `patch_housekeeping()` to include task_results in the run event

**Files:**
- Modify: `app/routes/capture.py` (the `patch_housekeeping` route, around line 195–204)
- Test: `tests/test_capture.py` (add after `test_patch_housekeeping_heartbeat`, ~line 806)

The `task_results` field is extracted from `fields` in the route and passed directly into the `housekeeping.run` event. It is NOT added to `_HOUSEKEEPING_ALLOWED_FIELDS` — the vault allowlist already silently ignores it, which is the correct behaviour (run detail is ephemeral, not persisted to the vault file).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_capture.py` after `test_patch_housekeeping_heartbeat`:

```python
def test_patch_housekeeping_heartbeat_includes_task_results(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    captured = []
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
        with patch("app.routes.capture.append_event", side_effect=lambda *a, **kw: captured.append((a, kw))):
            resp = client.patch(
                "/entries/housekeeping",
                json={
                    "project": "claude-config",
                    "type": "housekeeping-heartbeat",
                    "filename": "last-run",
                    "fields": {
                        "last_run": "2026-07-07T12:00:00",
                        "tasks_run": "3",
                        "tasks_failed": "1",
                        "tasks_skipped": "1",
                        "task_results": [
                            {"name": "Research cycle", "project": "claude-config", "outcome": "ok"},
                            {"name": "Weak signals", "project": "claude-config", "outcome": "failed", "error": "Judge timeout"},
                            {"name": "Skills audit", "project": "claude-config", "outcome": "skipped"},
                        ],
                    },
                },
                headers={"X-Capture-Token": "test-token-secret"},
            )
    assert resp.status_code == 200
    assert len(captured) == 1
    event_type, payload = captured[0][0]
    assert event_type == "housekeeping.run"
    assert payload["task_results"] == [
        {"name": "Research cycle", "project": "claude-config", "outcome": "ok"},
        {"name": "Weak signals", "project": "claude-config", "outcome": "failed", "error": "Judge timeout"},
        {"name": "Skills audit", "project": "claude-config", "outcome": "skipped"},
    ]


def test_patch_housekeeping_heartbeat_empty_task_results_when_absent(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    captured = []
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
        with patch("app.routes.capture.append_event", side_effect=lambda *a, **kw: captured.append((a, kw))):
            resp = client.patch(
                "/entries/housekeeping",
                json={
                    "project": "claude-config",
                    "type": "housekeeping-heartbeat",
                    "filename": "last-run",
                    "fields": {
                        "last_run": "2026-07-07T12:00:00",
                        "tasks_run": "2",
                        "tasks_failed": "0",
                        "tasks_skipped": "0",
                    },
                },
                headers={"X-Capture-Token": "test-token-secret"},
            )
    assert resp.status_code == 200
    assert len(captured) == 1
    event_type, payload = captured[0][0]
    assert payload["task_results"] == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
docker exec ikeos pytest tests/test_capture.py::test_patch_housekeeping_heartbeat_includes_task_results tests/test_capture.py::test_patch_housekeeping_heartbeat_empty_task_results_when_absent -v
```

Expected: FAIL — `AssertionError` on `payload["task_results"]` (key doesn't exist yet).

- [ ] **Step 3: Extend the route to pass task_results through**

In `app/routes/capture.py`, find this block (around line 195):

```python
    if entry_type == "housekeeping-heartbeat" and "tasks_run" in fields:
        trigger = fields.get("trigger", "scheduled")
        if trigger not in _VALID_TRIGGERS:
            trigger = "scheduled"
        append_event("housekeeping.run", {
            "trigger": trigger,
            "tasks_run": _safe_int(fields.get("tasks_run")),
            "tasks_failed": _safe_int(fields.get("tasks_failed")),
            "tasks_skipped": _safe_int(fields.get("tasks_skipped")),
        })
```

Replace with:

```python
    if entry_type == "housekeeping-heartbeat" and "tasks_run" in fields:
        trigger = fields.get("trigger", "scheduled")
        if trigger not in _VALID_TRIGGERS:
            trigger = "scheduled"
        raw_results = fields.get("task_results")
        task_results = raw_results if isinstance(raw_results, list) else []
        append_event("housekeeping.run", {
            "trigger": trigger,
            "tasks_run": _safe_int(fields.get("tasks_run")),
            "tasks_failed": _safe_int(fields.get("tasks_failed")),
            "tasks_skipped": _safe_int(fields.get("tasks_skipped")),
            "task_results": task_results,
        })
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
docker exec ikeos pytest tests/test_capture.py::test_patch_housekeeping_heartbeat_includes_task_results tests/test_capture.py::test_patch_housekeeping_heartbeat_empty_task_results_when_absent -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
docker exec ikeos pytest tests/ -q
```

Expected: same failure count as before this task (2 pre-existing failures in `test_run_task_*`).

- [ ] **Step 6: Commit**

```bash
git add app/routes/capture.py tests/test_capture.py
git commit -m "feat: include task_results in housekeeping.run metrics event"
```

---

### Task 2: Render per-task breakdown in the Recent Runs table

**Files:**
- Modify: `app/templates/housekeeping.html` (the Recent Runs section, lines 212–238)

No backend changes — `task_results` is already present in the event dicts returned by `read_events_by_type("housekeeping.run")`. Uses native HTML `<details>`/`<summary>` for collapsible rows — no JS required.

- [ ] **Step 1: Replace the Recent Runs table rows**

In `app/templates/housekeeping.html`, replace the `{% for run in recent_runs %}` block (lines 226–234):

```html
        {% for run in recent_runs %}
        <tr>
          <td>{{ (run.timestamp | default("")) | replace("T", " ") | replace("+00:00", "") or "—" }}</td>
          <td>{{ run.trigger | default("—") }}</td>
          <td>{{ run.tasks_run | default("—") }}</td>
          <td class="{{ 'error' if (run.tasks_failed | default(0)) > 0 else '' }}">{{ run.tasks_failed | default("—") }}</td>
          <td>{{ run.tasks_skipped | default("—") }}</td>
        </tr>
        {% endfor %}
```

With:

```html
        {% for run in recent_runs %}
        {% set results = run.task_results | default([]) %}
        <tr>
          <td>{{ (run.timestamp | default("")) | replace("T", " ") | replace("+00:00", "") or "—" }}</td>
          <td>{{ run.trigger | default("—") }}</td>
          <td>{{ run.tasks_run | default("—") }}</td>
          <td class="{{ 'error' if (run.tasks_failed | default(0)) > 0 else '' }}">{{ run.tasks_failed | default("—") }}</td>
          <td>{{ run.tasks_skipped | default("—") }}</td>
        </tr>
        {% if results %}
        <tr>
          <td colspan="5" style="padding:0 0.5rem 0.5rem 1.5rem; border-top:none">
            <details{% if (run.tasks_failed | default(0)) > 0 %} open{% endif %}>
              <summary style="cursor:pointer; color:var(--muted); font-size:0.85rem">
                task detail ({{ results | length }})
              </summary>
              <ul style="margin:0.4rem 0 0 1rem; padding:0; list-style:none; font-size:0.85rem; font-family:monospace">
                {% for t in results %}
                <li class="{{ 'error' if t.outcome == 'failed' else '' }}" style="padding:0.1rem 0">
                  {% if t.outcome == 'ok' %}✓{% elif t.outcome == 'failed' %}✗{% else %}—{% endif %}
                  {{ t.name | default("unknown") }}{% if t.outcome == 'failed' and t.error %} — {{ t.error }}{% endif %}
                </li>
                {% endfor %}
              </ul>
            </details>
          </td>
        </tr>
        {% endif %}
        {% endfor %}
```

- [ ] **Step 2: Rebuild container and verify rendering**

```bash
docker compose up --build -d ikeos
```

Open `http://<ikeos-host>:5009/housekeeping` in a browser. Confirm:
- Runs without `task_results` show the same table as before (no extra row)
- Runs with `task_results` show a collapsible "task detail (N)" row below
- Failed runs auto-expand (`open` attribute)
- ✓/✗/— icons render correctly

- [ ] **Step 3: Commit**

```bash
git add app/templates/housekeeping.html
git commit -m "feat: show per-task breakdown in housekeeping Recent Runs table"
```

---

### Task 3: Extend housekeeping skill Phase 7 to collect and send task_results

**Files:**
- Modify: `adapters/claude-code/skills/housekeeping.md` (Phase 7, the `/tmp/hk_phase7_update.py` script)

The skill already tracks per-task outcomes in Phases 5/6 using local counters (`TASKS_RUN_COUNT`, etc.). This task adds a parallel `TASK_RESULTS` list the agent builds as it processes tasks, then includes it in the Phase 7 PATCH.

No tests — this is a skill/documentation file consumed by an LLM agent, not executable Python.

- [ ] **Step 1: Add task_results collection instructions to Phase 5/6**

In `adapters/claude-code/skills/housekeeping.md`, find the Phase 5 section header (the section that describes running due tasks as subagents and judging results). Add this instruction block at the end of Phase 5's per-task outcome recording instructions (immediately before or after the `tasks_run`/`tasks_failed` counter increment instructions):

```markdown
As you process each task, also maintain a `TASK_RESULTS` list to pass to Phase 7. After each task outcome:

- **Pass:** append `{"name": "<task title>", "project": "<task project>", "outcome": "ok"}`
- **Fail:** append `{"name": "<task title>", "project": "<task project>", "outcome": "failed", "error": "<judge reason>"}`
- **Skip (not due):** append `{"name": "<task title>", "project": "<task project>", "outcome": "skipped"}`
```

- [ ] **Step 2: Extend the Phase 7 update script to include task_results**

In `adapters/claude-code/skills/housekeeping.md`, find the Phase 7 `/tmp/hk_phase7_update.py` script. Replace the script block:

```python
import urllib.request, json, os, datetime

token = os.environ.get("CAPTURE_TOKEN", "")
_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
payload = {
    "project": "claude-config",
    "type": "housekeeping-heartbeat",
    "filename": "last-run.md",
    "fields": {
        "last_run": now,
        "tasks_run": TASKS_RUN_COUNT,
        "tasks_failed": TASKS_FAILED_COUNT,
        "tasks_skipped": TASKS_SKIPPED_COUNT,
    },
}
req = urllib.request.Request(f"{_ikeos_url}/entries/housekeeping", method="PATCH")
req.add_header("X-Capture-Token", token)
req.add_header("Content-Type", "application/json")
req.data = json.dumps(payload).encode()
urllib.request.urlopen(req)
```

With:

```python
import urllib.request, json, os, datetime

token = os.environ.get("CAPTURE_TOKEN", "")
_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
payload = {
    "project": "claude-config",
    "type": "housekeeping-heartbeat",
    "filename": "last-run.md",
    "fields": {
        "last_run": now,
        "tasks_run": TASKS_RUN_COUNT,
        "tasks_failed": TASKS_FAILED_COUNT,
        "tasks_skipped": TASKS_SKIPPED_COUNT,
        "task_results": TASK_RESULTS,
    },
}
req = urllib.request.Request(f"{_ikeos_url}/entries/housekeeping", method="PATCH")
req.add_header("X-Capture-Token", token)
req.add_header("Content-Type", "application/json")
req.data = json.dumps(payload).encode()
urllib.request.urlopen(req)
```

(The agent substitutes `TASKS_RUN_COUNT`, `TASKS_FAILED_COUNT`, `TASKS_SKIPPED_COUNT`, and `TASK_RESULTS` with actual values before running the script.)

- [ ] **Step 3: Update Phase 8 reporting note**

In Phase 8 of the skill, add a note that the Phase 8 console summary and `TASK_RESULTS` should be consistent — if a task shows `✗` in Phase 8, it must have `"outcome": "failed"` in `TASK_RESULTS`.

- [ ] **Step 4: Commit**

```bash
git add adapters/claude-code/skills/housekeeping.md
git commit -m "feat: housekeeping skill Phase 7 reports per-task outcomes in heartbeat payload"
```

---

### Task 4: Close vault entries

- [ ] **Close the note and promote to done**

```bash
CT=$(docker exec ikeos printenv CAPTURE_TOKEN)
curl -s -o /dev/null -w "%{http_code}" -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CT" \
  -d "project=ikeos" -d "type=note" \
  -d "filename=2026-07-03-why-per-run-observability-ledger-for-scheduled-age" -d "status=done"
```

Expected: `200`.
