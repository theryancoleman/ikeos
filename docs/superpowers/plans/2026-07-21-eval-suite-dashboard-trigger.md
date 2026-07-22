# Eval Suite Dashboard Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.
>
> **Scope note (read before executing):** The source vault entry asked for "trigger on demand and/or schedule periodic runs." This plan implements **on-demand trigger + results display only**. Building a second cron job means either duplicating scheduler.py's leader-election/APScheduler machinery or generalizing it to support multiple named jobs — a real design decision, not a mechanical add, and disproportionate to an explicitly "not urgent" idea whose current ad hoc `sync.sh` trigger is functional. Recurring scheduling is listed under Explicitly Out of Scope with a concrete follow-up path. Flag to the user if they wanted the scheduling half in this pass.

**Goal:** A dashboard page where the user can trigger a claude-config eval suite run on demand and see the last run's pass/fail/score/regression results, instead of only a terminal report.

**Architecture:** Reuses the exact pattern `run_platform_review()`/`weekly_review.html` already establish for "spawn a Claude Code session to do work, show a button + status": `app/services/driver.py` gains `run_eval_suite()`, which spawns a session via the existing session-manager (no new runtime, no Claude CLI installed in the ikeos container — the eval suite runs as a Claude Code session on the host, exactly like housekeeping does). A new read-only Docker volume mount exposes `claude-config/evals/last_run.json` and `baselines.json` to the ikeos container so the dashboard can read results without touching transcripts. A new capability flag (`eval_suite_trigger`, default off) gates the trigger button, matching `weekly_platform_review`'s existing convention.

**Tech Stack:** Flask (routes + Jinja2 templates), the existing session-manager HTTP contract, Docker Compose volume mounts.

---

## File Structure

- Modify: `docker-compose.yml` — mount `claude-config/evals` read-only.
- Modify: `.env.example` — no new env var needed (reuses `CLAUDE_CONFIG_PATH`), but add a comment noting the new mount.
- Modify: `app/services/capabilities.py` — add `eval_suite_trigger` to `DEFAULT_CAPABILITIES`.
- Modify: `app/services/driver.py` — add `run_eval_suite(model=None)`.
- Create: `app/services/eval_results.py` — reads `/claude-config/evals/last_run.json` and `baselines.json`, computes per-case pass/fail/delta.
- Create: `app/routes/evals.py` — new Blueprint: `GET /evals` (page), `POST /evals/run` (trigger), `GET /evals/session-status` (poll).
- Modify: `app/__init__.py` (or wherever blueprints are registered — check `app/routes/housekeeping.py`'s registration site) — register the new blueprint.
- Create: `app/templates/evals.html` — results table + trigger button, modeled on `weekly_review.html`.
- Modify: `app/templates/housekeeping.html` — add a capability toggle row for `eval_suite_trigger` and a nav link to `/evals`, matching the existing `weekly_platform_review` toggle row.
- Create: `tests/test_eval_results.py`
- Create: `tests/test_evals_routes.py`
- Modify: `tests/test_driver.py` — test for `run_eval_suite()`.

---

## Task 1: Docker mount for evals results

**Files:**
- Modify: `docker-compose.yml`

- [x] **Step 1: Add the read-only evals mount**

In `docker-compose.yml`, find:

```yaml
      - ${CLAUDE_CONFIG_PATH:-/tmp/ikeos-no-claude-config}/library:/claude-config/library:ro
```

Add immediately after it:

```yaml
      - ${CLAUDE_CONFIG_PATH:-/tmp/ikeos-no-claude-config}/evals:/claude-config/evals:ro
```

- [x] **Step 2: Rebuild and verify the mount**

```bash
cd /mnt/c/Server/projects/ikeos && docker.exe compose up --build -d
docker.exe exec ikeos ls /claude-config/evals/
```

Expected: lists `last_run.json`, `baselines.json`, `runner.py`, etc. (If it lists nothing or errors, `CLAUDE_CONFIG_PATH` isn't set in `.env` — confirm it's set to `/mnt/c/Server/claude-config` or the Windows-format equivalent before continuing.)

- [x] **Step 3: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add docker-compose.yml
git commit -m "feat: mount claude-config/evals read-only for the eval-suite dashboard"
```

---

## Task 2: `eval_results.py` — read and interpret last_run.json / baselines.json

**Files:**
- Create: `app/services/eval_results.py`
- Create: `tests/test_eval_results.py`

- [x] **Step 1: Write the failing tests**

```bash
cat > /mnt/c/Server/projects/ikeos/tests/test_eval_results.py << 'EOF'
import json

from app.services import eval_results


def test_read_last_run_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_results, "_last_run_path", lambda: tmp_path / "last_run.json")
    assert eval_results.read_last_run() is None


def test_read_last_run_parses_results(tmp_path, monkeypatch):
    last_run = tmp_path / "last_run.json"
    last_run.write_text(json.dumps({
        "timestamp": "2026-07-21T13:49:31",
        "results": [
            {"id": "case_a", "name": "Case A", "score": 9.2, "reasoning": "Good."},
            {"id": "case_b", "name": "Case B", "score": 3.0, "reasoning": "Weak."},
        ],
    }))
    monkeypatch.setattr(eval_results, "_last_run_path", lambda: last_run)
    data = eval_results.read_last_run()
    assert data["timestamp"] == "2026-07-21T13:49:31"
    assert len(data["results"]) == 2


def test_read_last_run_annotates_baseline_delta(tmp_path, monkeypatch):
    last_run = tmp_path / "last_run.json"
    baselines = tmp_path / "baselines.json"
    last_run.write_text(json.dumps({
        "timestamp": "2026-07-21T13:49:31",
        "results": [{"id": "case_a", "name": "Case A", "score": 9.2, "reasoning": "Good."}],
    }))
    baselines.write_text(json.dumps({"case_a": {"score": 8.0, "model": "x", "date": "2026-05-13"}}))
    monkeypatch.setattr(eval_results, "_last_run_path", lambda: last_run)
    monkeypatch.setattr(eval_results, "_baselines_path", lambda: baselines)
    data = eval_results.read_last_run()
    case = next(r for r in data["results"] if r["id"] == "case_a")
    assert case["baseline_score"] == 8.0
    assert round(case["delta"], 1) == 1.2


def test_read_last_run_missing_baseline_has_null_delta(tmp_path, monkeypatch):
    last_run = tmp_path / "last_run.json"
    baselines = tmp_path / "baselines.json"
    last_run.write_text(json.dumps({
        "timestamp": "2026-07-21T13:49:31",
        "results": [{"id": "new_case", "name": "New Case", "score": 5.0, "reasoning": "N/A"}],
    }))
    baselines.write_text(json.dumps({}))
    monkeypatch.setattr(eval_results, "_last_run_path", lambda: last_run)
    monkeypatch.setattr(eval_results, "_baselines_path", lambda: baselines)
    data = eval_results.read_last_run()
    case = data["results"][0]
    assert case["baseline_score"] is None
    assert case["delta"] is None
EOF
```

- [x] **Step 2: Run tests to verify they fail**

Run: `docker.exe exec ikeos pytest tests/test_eval_results.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.eval_results'`

- [x] **Step 3: Write the module**

```bash
cat > /mnt/c/Server/projects/ikeos/app/services/eval_results.py << 'EOF'
"""Read the claude-config eval suite's results — no execution here, read-only."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_EVALS_MOUNT = Path("/claude-config/evals")


def _last_run_path() -> Path:
    return _EVALS_MOUNT / "last_run.json"


def _baselines_path() -> Path:
    return _EVALS_MOUNT / "baselines.json"


def read_last_run() -> dict | None:
    """Read last_run.json, annotating each result with its baseline score and delta.

    Returns None if last_run.json doesn't exist (no run yet, or the mount is
    absent — degrades gracefully rather than raising).
    """
    path = _last_run_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read %s", path)
        return None

    baselines = {}
    baselines_path = _baselines_path()
    if baselines_path.exists():
        try:
            baselines = json.loads(baselines_path.read_text())
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read %s", baselines_path)

    for result in data.get("results", []):
        baseline = baselines.get(result["id"])
        baseline_score = baseline["score"] if baseline else None
        result["baseline_score"] = baseline_score
        result["delta"] = (result["score"] - baseline_score) if baseline_score is not None else None

    return data
EOF
```

- [x] **Step 4: Run tests to verify they pass**

Run: `docker.exe exec ikeos pytest tests/test_eval_results.py -v`
Expected: all 4 tests pass

- [x] **Step 5: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/services/eval_results.py tests/test_eval_results.py
git commit -m "feat: add eval_results service to read claude-config eval suite output"
```

---

## Task 3: `run_eval_suite()` in driver.py

**Files:**
- Modify: `app/services/driver.py`
- Modify: `tests/test_driver.py`

- [x] **Step 1: Write the failing test**

Find the existing test file `tests/test_driver.py` and add (matching its existing mocking pattern for `create_session` — check the top of the file for how it patches `app.services.driver.create_session` and reuse that same style):

```python
def test_run_eval_suite_spawns_session(mocker):
    mock_create = mocker.patch("app.services.driver.create_session")
    mock_create.return_value = mocker.Mock(session_id="abc123", already_running=False, ok=True)
    from app.services.driver import run_eval_suite
    result = run_eval_suite()
    assert result.session_id == "abc123"
    kwargs = mock_create.call_args.kwargs
    assert kwargs["project_dir"] == "/mnt/c/Server/claude-config"
    assert "evals/runner.py" in kwargs["initial_command"]
    assert kwargs["name"] == "eval-suite-run"
```

- [x] **Step 2: Run test to verify it fails**

Run: `docker.exe exec ikeos pytest tests/test_driver.py -k run_eval_suite -v`
Expected: FAIL — `ImportError: cannot import name 'run_eval_suite'`

- [x] **Step 3: Add the function to `driver.py`**

Add after `run_platform_review()`:

```python
def run_eval_suite(model: str | None = None) -> SessionResult:
    return create_session(
        name="eval-suite-run",
        project=project_slug(),
        project_dir=_housekeeping_project_dir(),
        initial_command=(
            "Run `python3 evals/runner.py --notify` and report the pass/fail/regression "
            "summary when it finishes."
        ),
        model=model,
    )
```

(Uses `_housekeeping_project_dir()` since the eval suite lives in the same claude-config checkout housekeeping already targets — no new project-dir env var needed.)

- [x] **Step 4: Run test to verify it passes**

Run: `docker.exe exec ikeos pytest tests/test_driver.py -v`
Expected: all tests pass, no regressions in existing driver tests

- [x] **Step 5: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/services/driver.py tests/test_driver.py
git commit -m "feat: add run_eval_suite() to driver"
```

---

## Task 4: Capability flag

**Files:**
- Modify: `app/services/capabilities.py`

- [x] **Step 1: Add the capability**

In `DEFAULT_CAPABILITIES`, after the `weekly_platform_review` entry, add:

```python
    "eval_suite_trigger": {
        "enabled": False,
        "enabled_by": None,
        "enabled_at": None,
        "description": "On-demand claude-config eval suite runs from the dashboard",
    },
```

- [x] **Step 2: Verify existing capability tests still pass**

Run: `docker.exe exec ikeos pytest tests/test_capabilities.py -v`
Expected: all pass (adding a dict entry shouldn't break anything, but confirm)

- [x] **Step 3: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/services/capabilities.py
git commit -m "feat: add eval_suite_trigger capability flag (default off)"
```

---

## Task 5: Routes

**Files:**
- Create: `app/routes/evals.py`
- Create: `tests/test_evals_routes.py`
- Modify: the app factory / blueprint registration site (find it via `grep -rn "register_blueprint" app/`)

- [x] **Step 1: Find the blueprint registration site**

Run: `grep -rn "register_blueprint" /mnt/c/Server/projects/ikeos/app/`

Note the exact file and how `housekeeping.bp` is registered — the new blueprint follows the identical pattern.

- [x] **Step 2: Write the failing tests**

```bash
cat > /mnt/c/Server/projects/ikeos/tests/test_evals_routes.py << 'EOF'
import pytest

from app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_evals_page_renders(client, mocker):
    mocker.patch("app.routes.evals.read_last_run", return_value=None)
    resp = client.get("/evals")
    assert resp.status_code == 200


def test_run_requires_capability_enabled(client, mocker):
    mocker.patch("app.routes.evals.is_enabled", return_value=False)
    resp = client.post("/evals/run", headers={"X-Capture-Token": "test-token"})
    assert resp.status_code == 403


def test_run_triggers_session_when_enabled(client, mocker):
    mocker.patch("app.routes.evals.is_enabled", return_value=True)
    mock_result = mocker.Mock(session_id="abc123", already_running=False, ok=True)
    mocker.patch("app.routes.evals.run_eval_suite", return_value=mock_result)
    resp = client.post("/evals/run", headers={"X-Capture-Token": "test-token"})
    assert resp.status_code == 200
    assert resp.get_json()["session_id"] == "abc123"


def test_run_requires_capture_token(client):
    resp = client.post("/evals/run")
    assert resp.status_code == 401
EOF
```

(Adjust the `create_app` import and the capture-token fixture setup to match whatever pattern `tests/conftest.py` already establishes for other route tests — check `tests/test_housekeeping.py`'s fixtures first and reuse them rather than inventing a new one.)

- [x] **Step 3: Run tests to verify they fail**

Run: `docker.exe exec ikeos pytest tests/test_evals_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routes.evals'`

- [x] **Step 4: Write the routes module**

```bash
cat > /mnt/c/Server/projects/ikeos/app/routes/evals.py << 'EOF'
import os

from flask import Blueprint, jsonify, render_template

from app.routes.auth import require_capture_token
from app.services.capabilities import get_capabilities, is_enabled
from app.services.driver import run_eval_suite
from app.services.eval_results import read_last_run
from app.services.session_client import get_session_status

bp = Blueprint("evals", __name__)

CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "")


@bp.route("/evals")
def index():
    last_run = read_last_run()
    return render_template(
        "evals.html",
        last_run=last_run,
        capabilities=get_capabilities(),
        capture_token=CAPTURE_TOKEN,
    )


@bp.route("/evals/run", methods=["POST"])
@require_capture_token
def run():
    if not is_enabled("eval_suite_trigger"):
        return jsonify({"error": "eval_suite_trigger capability is disabled"}), 403
    result = run_eval_suite()
    if result.already_running:
        return jsonify({"ok": True, "session_id": result.session_id, "already_running": True}), 200
    if not result.ok:
        return jsonify({"error": "Failed to start eval suite session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/evals/session-status")
def session_status():
    from flask import request
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        return jsonify({"active": False}), 200
    data = get_session_status(session_id)
    if data is None:
        return jsonify({"active": False})
    return jsonify({"active": data.get("status") == "active"})
EOF
```

Register the blueprint in the app factory found in Step 1, following the exact same line pattern used for `housekeeping.bp` (e.g. `app.register_blueprint(evals.bp)` alongside `app.register_blueprint(housekeeping.bp)`, with a matching import line added at the top of that file).

- [x] **Step 5: Run tests to verify they pass**

Run: `docker.exe exec ikeos pytest tests/test_evals_routes.py -v`
Expected: all 4 pass (Task 6 creates `evals.html`, required for `test_evals_page_renders` — if Task 5 is executed before Task 6, this one test fails on a `TemplateNotFound` error; that's expected and resolves once Task 6 lands. Run the full test again after Task 6.)

- [x] **Step 6: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/routes/evals.py tests/test_evals_routes.py
git commit -m "feat: add /evals routes for on-demand eval suite trigger and results"
```

(Also `git add` the blueprint-registration file changed in Step 4 — include it in this same commit.)

---

## Task 6: `evals.html` template

**Files:**
- Create: `app/templates/evals.html`

- [x] **Step 1: Write the template**

```bash
cat > /mnt/c/Server/projects/ikeos/app/templates/evals.html << 'EOF'
{% extends "base.html" %}
{% block title %}Eval Suite{% endblock %}

{% block content %}
<div class="settings-page">

  <header class="page-header">
    <span class="ike-eyebrow">Housekeeping</span>
    <h1>Eval Suite</h1>
    <p class="page-subtitle">
      claude-config's agent/command eval suite &mdash; pass/fail/regression results from the last run.
    </p>
  </header>

  <div style="display:flex; gap:10px; align-items:center; margin-bottom:20px;">
    <a href="{{ url_for('housekeeping.index') }}" class="pill">&larr; Housekeeping</a>
    {% if capabilities.eval_suite_trigger.enabled %}
    <button class="pill pill-primary" id="run-evals-btn" onclick="runEvals(this)">
      Run Eval Suite
    </button>
    <span id="run-evals-msg" style="font-size:0.85rem; color:var(--color-muted);"></span>
    {% else %}
    <span class="pill pill--muted">Enable capability to run</span>
    {% endif %}
  </div>

  {% if last_run %}
  <section>
    <div class="ike-eyebrow">Last run: {{ last_run.timestamp }}</div>
    <div class="hk-schedule-card" style="overflow-x:auto;">
      <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
        <thead>
          <tr>
            <th style="text-align:left; padding:6px;">Case</th>
            <th style="text-align:right; padding:6px;">Score</th>
            <th style="text-align:right; padding:6px;">Baseline</th>
            <th style="text-align:right; padding:6px;">Delta</th>
          </tr>
        </thead>
        <tbody>
          {% for r in last_run.results %}
          <tr>
            <td style="padding:6px;">{{ r.name }}</td>
            <td style="text-align:right; padding:6px;">{{ r.score }}</td>
            <td style="text-align:right; padding:6px;">{{ r.baseline_score if r.baseline_score is not none else '—' }}</td>
            <td style="text-align:right; padding:6px;
                       color: {{ 'var(--color-danger, #c0392b)' if r.delta is not none and r.delta < 0 else 'inherit' }};">
              {{ '%+.1f'|format(r.delta) if r.delta is not none else '—' }}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </section>
  {% else %}
  <div class="hk-widget">
    <p class="hk-status hk-status-pending">No eval run found yet.</p>
    {% if not capabilities.eval_suite_trigger.enabled %}
    <p style="font-size:0.9rem; color:var(--color-muted);">
      Enable the <strong>Eval Suite Trigger</strong> capability on the
      <a href="{{ url_for('housekeeping.index') }}">Housekeeping page</a> to run the first eval.
    </p>
    {% endif %}
  </div>
  {% endif %}

</div>

<script>
const _captureToken = {{ capture_token | tojson }};

async function runEvals(btn) {
  const msg = document.getElementById('run-evals-msg');
  btn.disabled = true;
  btn.textContent = 'Starting…';
  msg.textContent = '';
  try {
    const resp = await fetch('/evals/run', {
      method: 'POST',
      headers: {'X-Capture-Token': _captureToken},
    });
    const data = await resp.json();
    if (!resp.ok) {
      btn.textContent = 'Run Eval Suite';
      btn.disabled = false;
      msg.textContent = data.error || 'Error starting eval run.';
    } else if (data.already_running) {
      btn.textContent = 'Already running';
      msg.textContent = `Session: ${data.session_id}`;
    } else {
      btn.textContent = 'Running…';
      msg.textContent = `Session started: ${data.session_id}. Each case takes 10-30s via the claude CLI — reload this page in a few minutes for results.`;
    }
  } catch (e) {
    btn.textContent = 'Run Eval Suite';
    btn.disabled = false;
    msg.textContent = 'Network error.';
  }
}
</script>
{% endblock %}
EOF
```

- [x] **Step 2: Run the full route test file again (now that the template exists)**

Run: `docker.exe exec ikeos pytest tests/test_evals_routes.py -v`
Expected: all 4 pass

- [x] **Step 3: Add the capability toggle row to `housekeeping.html`**

Run: `grep -n "weekly_platform_review" /mnt/c/Server/projects/ikeos/app/templates/housekeeping.html`

Find the existing toggle row markup for `weekly_platform_review` in the capabilities section and duplicate it immediately below, substituting `eval_suite_trigger` for the capability name, "Eval Suite Trigger" for the label, and its description text. Also add a nav pill linking to `{{ url_for('evals.index') }}` next to wherever the "Weekly Platform Review" nav link lives in the same file.

- [x] **Step 4: Manual smoke test**

```bash
cd /mnt/c/Server/projects/ikeos && docker.exe compose up --build -d
```

In a browser, visit the ikeos dashboard, navigate to Housekeeping, enable "Eval Suite Trigger," navigate to the new Eval Suite page, click "Run Eval Suite," and confirm a session starts (check `docker.exe exec ikeos curl -s http://host.docker.internal:5010/sessions` or the Sessions tab in the UI for a new `eval-suite-run` session).

- [x] **Step 5: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/templates/evals.html app/templates/housekeeping.html
git commit -m "feat: add eval suite results page and housekeeping nav/toggle entry"
```

---

## Explicitly Out of Scope

- **Recurring scheduling.** Per the scope note at the top of this plan — extending `scheduler.py`'s leader-election/APScheduler machinery to support a second named cron job is a real design decision (parameterize by job name vs. duplicate the module vs. a generic job registry) that deserves its own plan once there's a concrete cadence in mind (the vault entry didn't specify one). Follow-up: a new vault idea, "Generalize scheduler.py to support multiple named housekeeping-style jobs," scoped separately.
- **Long-poll or websocket status updates.** The `session-status` route exists for future use but `evals.html` doesn't poll it yet — the user reloads the page manually, matching `weekly_review.html`'s current (also non-polling) behavior. Add polling later if manual reload proves annoying in practice.
- **Timeout handling for a hung eval run.** The spawned Claude Code session runs the eval suite same as any other driver-spawned session — if it hangs, it's visible and killable from the existing Sessions tab like any other session. No new session-manager-level timeout logic is added specifically for this task.
