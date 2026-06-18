# Housekeeping Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-process APScheduler cron to IkeOS that fires weekly, spawns a Claude Code session running `/housekeeping — run in scheduled mode`, and persists schedule config to the vault — configurable from the housekeeping management page.

**Architecture:** A new `app/services/scheduler.py` owns the APScheduler `BackgroundScheduler`, config read/write to `/vault/projects/claude-config/housekeeping/schedule.json`, and the session-spawn job. Two new endpoints (`GET/PATCH /housekeeping/schedule`) expose config to the UI. The housekeeping management page gains a schedule control section above the task table. The scheduler starts inside `create_app()` behind a `TESTING` guard.

**Tech Stack:** Flask, APScheduler>=3.10, pytest, requests, existing session manager API at `SESSION_MANAGER_URL`.

---

## File Map

| File | Change |
|---|---|
| `requirements.txt` | Add `APScheduler>=3.10` |
| `app/services/scheduler.py` | New — config I/O, `trigger_now()`, `start()`, `get_config_with_next_run()` |
| `app/routes/housekeeping.py` | Add `_check_auth()`, `GET/PATCH /housekeeping/schedule`, update `index()` |
| `app/templates/housekeeping.html` | Add Schedule section before task table |
| `app/static/style.css` | Add CSS for schedule section |
| `app/static/bundle.css` | Regenerated via `python3 scripts/bundle_css.py` |
| `app/__init__.py` | Accept optional `config` dict; call `scheduler_svc.start(app)` |
| `tests/conftest.py` | Update `client` fixture to pass `{"TESTING": True}` |
| `tests/test_scheduler.py` | New — unit tests for scheduler service |
| `tests/test_housekeeping.py` | Extend with schedule endpoint tests |

---

### Task 1: Add APScheduler dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependency**

Open `requirements.txt` and add `APScheduler>=3.10` after the `requests` line:

```
flask>=3.0
python-dotenv>=1.0
python-frontmatter>=1.1
gunicorn>=21.2
pytest>=8.0
requests>=2.31
APScheduler>=3.10
obsidiantools==0.11.0
rich>=13.0
```

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: add APScheduler dependency for housekeeping cron"
```

---

### Task 2: Scheduler service — config read/write

**Files:**
- Create: `app/services/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scheduler.py`:

```python
import json
import pytest
from pathlib import Path


@pytest.fixture
def sched_vault(tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    return tmp_path


def _hk_dir(vault) -> Path:
    return vault / "projects" / "claude-config" / "housekeeping"


# ── get_config ──

def test_get_config_returns_defaults_when_no_file(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import get_config
    config = get_config()
    assert config["enabled"] is False
    assert config["day_of_week"] == "sun"
    assert config["hour"] == 3
    assert config["minute"] == 7
    assert config["last_triggered"] is None


def test_get_config_reads_existing_file(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    schedule_file = _hk_dir(sched_vault) / "schedule.json"
    schedule_file.write_text(json.dumps({
        "enabled": True, "day_of_week": "mon", "hour": 4, "minute": 15,
        "last_triggered": "2026-06-16T04:15:00"
    }))
    from app.services.scheduler import get_config
    config = get_config()
    assert config["enabled"] is True
    assert config["day_of_week"] == "mon"
    assert config["hour"] == 4
    assert config["minute"] == 15
    assert config["last_triggered"] == "2026-06-16T04:15:00"


def test_get_config_fills_missing_keys_with_defaults(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    schedule_file = _hk_dir(sched_vault) / "schedule.json"
    schedule_file.write_text(json.dumps({"enabled": True}))
    from app.services.scheduler import get_config
    config = get_config()
    assert config["enabled"] is True
    assert config["day_of_week"] == "sun"
    assert config["hour"] == 3


# ── update_config ──

def test_update_config_writes_merged_fields(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config
    result = update_config({"hour": 5, "minute": 30})
    assert result["hour"] == 5
    assert result["minute"] == 30
    assert result["day_of_week"] == "sun"  # default preserved
    # file was written
    written = json.loads((_hk_dir(sched_vault) / "schedule.json").read_text())
    assert written["hour"] == 5
    assert written["minute"] == 30


def test_update_config_rejects_invalid_day_of_week(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config
    with pytest.raises(ValueError, match="day_of_week"):
        update_config({"day_of_week": "xyz"})


def test_update_config_rejects_invalid_hour(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config
    with pytest.raises(ValueError, match="hour"):
        update_config({"hour": 24})


def test_update_config_rejects_invalid_minute(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config
    with pytest.raises(ValueError, match="minute"):
        update_config({"minute": 60})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker.exe compose exec ikeos pytest tests/test_scheduler.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'app.services.scheduler'`

- [ ] **Step 3: Create scheduler.py with config I/O**

Create `app/services/scheduler.py`:

```python
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_DEFAULTS: dict = {
    "enabled": False,
    "day_of_week": "sun",
    "hour": 3,
    "minute": 7,
    "last_triggered": None,
}

_scheduler = None  # set by start(); None in tests and before startup


def _schedule_path() -> Path:
    vault = Path(os.environ.get("VAULT_PATH", "/vault"))
    return vault / "projects" / "claude-config" / "housekeeping" / "schedule.json"


def _write_config(config: dict) -> None:
    path = _schedule_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(config, f, indent=2)
    tmp.replace(path)


def get_config() -> dict:
    path = _schedule_path()
    if not path.exists():
        return _DEFAULTS.copy()
    try:
        with open(path) as f:
            data = json.load(f)
        return {**_DEFAULTS, **data}
    except Exception:
        logger.exception("Failed to read schedule config from %s", path)
        return _DEFAULTS.copy()


def _validate(fields: dict) -> None:
    if "day_of_week" in fields and fields["day_of_week"] not in _VALID_DAYS:
        raise ValueError(
            f"day_of_week must be one of: {', '.join(sorted(_VALID_DAYS))}"
        )
    if "hour" in fields and not (0 <= int(fields["hour"]) <= 23):
        raise ValueError("hour must be 0–23")
    if "minute" in fields and not (0 <= int(fields["minute"]) <= 59):
        raise ValueError("minute must be 0–59")


def _reschedule(config: dict) -> None:
    if _scheduler is None:
        return
    job = _scheduler.get_job("housekeeping")
    if job is None:
        return
    _scheduler.reschedule_job(
        "housekeeping",
        trigger="cron",
        day_of_week=config["day_of_week"],
        hour=config["hour"],
        minute=config["minute"],
    )
    if config.get("enabled"):
        _scheduler.resume_job("housekeeping")
    else:
        _scheduler.pause_job("housekeeping")


def update_config(fields: dict) -> dict:
    _validate(fields)
    current = get_config()
    allowed = {"enabled", "day_of_week", "hour", "minute"}
    for k, v in fields.items():
        if k in allowed:
            current[k] = v
    _write_config(current)
    _reschedule(current)
    return current


def get_config_with_next_run() -> dict:
    config = get_config()
    config["next_run"] = None
    if config.get("enabled") and _scheduler is not None:
        job = _scheduler.get_job("housekeeping")
        if job and job.next_run_time:
            config["next_run"] = job.next_run_time.isoformat(timespec="seconds")
    return config
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker.exe compose exec ikeos pytest tests/test_scheduler.py -v 2>&1 | head -40
```

Expected: 7 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler service — config read/write"
```

---

### Task 3: Scheduler service — trigger_now()

**Files:**
- Modify: `app/services/scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_scheduler.py`:

```python
from unittest.mock import patch, MagicMock


# ── trigger_now ──

def test_trigger_now_creates_session_and_sends_command(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.json.return_value = {"id": "sess-abc"}

    mock_cmd = MagicMock()
    mock_cmd.ok = True

    with patch("app.services.scheduler.requests.post",
               side_effect=[mock_create, mock_cmd]) as mock_post:
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result == "sess-abc"
    assert mock_post.call_count == 2
    # first call: POST /sessions
    first_url = mock_post.call_args_list[0][0][0]
    assert first_url == "http://mock-sm/sessions"
    # second call: POST /sessions/sess-abc/command
    second_url = mock_post.call_args_list[1][0][0]
    assert second_url == "http://mock-sm/sessions/sess-abc/command"
    second_body = mock_post.call_args_list[1][1]["json"]
    assert second_body["command"] == "/housekeeping — run in scheduled mode"


def test_trigger_now_session_name_starts_with_housekeeping(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.json.return_value = {"id": "sess-xyz"}
    mock_cmd = MagicMock()
    mock_cmd.ok = True

    with patch("app.services.scheduler.requests.post",
               side_effect=[mock_create, mock_cmd]) as mock_post:
        from app.services.scheduler import trigger_now
        trigger_now()

    first_body = mock_post.call_args_list[0][1]["json"]
    assert first_body["name"].startswith("housekeeping-")
    # name format: housekeeping-YYYYMMDD (8-digit date suffix)
    suffix = first_body["name"].removeprefix("housekeeping-")
    assert len(suffix) == 8
    assert suffix.isdigit()


def test_trigger_now_returns_none_on_request_error(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    import requests as req_mod
    with patch("app.services.scheduler.requests.post",
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

    with patch("app.services.scheduler.requests.post",
               return_value=mock_create):
        from app.services.scheduler import trigger_now
        result = trigger_now()

    assert result is None


def test_trigger_now_updates_last_triggered_in_config(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")

    mock_create = MagicMock()
    mock_create.ok = True
    mock_create.json.return_value = {"id": "sess-ts"}
    mock_cmd = MagicMock()
    mock_cmd.ok = True

    with patch("app.services.scheduler.requests.post",
               side_effect=[mock_create, mock_cmd]):
        from app.services.scheduler import trigger_now, get_config
        trigger_now()

    config = get_config()
    assert config["last_triggered"] is not None
    assert "T" in config["last_triggered"]  # ISO datetime
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker.exe compose exec ikeos pytest tests/test_scheduler.py::test_trigger_now_creates_session_and_sends_command -v
```

Expected: `AttributeError` — `trigger_now` not yet defined

- [ ] **Step 3: Add trigger_now() to scheduler.py**

Add these imports at the top of `app/services/scheduler.py` (after existing imports):

```python
from datetime import datetime

import requests
```

Then append `trigger_now()` after `get_config_with_next_run()`:

```python
def trigger_now() -> str | None:
    today = datetime.now().strftime("%Y%m%d")
    session_name = f"housekeeping-{today}"
    sm_url = os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")
    try:
        create_resp = requests.post(
            f"{sm_url}/sessions",
            json={"name": session_name},
            timeout=5,
        )
        if not create_resp.ok:
            logger.error("Failed to create housekeeping session: %s", create_resp.status_code)
            return None
        session_id = create_resp.json().get("id")
        if not session_id:
            logger.error("No session ID returned from session manager")
            return None
        cmd_resp = requests.post(
            f"{sm_url}/sessions/{session_id}/command",
            json={"command": "/housekeeping — run in scheduled mode"},
            timeout=5,
        )
        if not cmd_resp.ok:
            logger.error("Failed to send housekeeping command: %s", cmd_resp.status_code)
            return None
        config = get_config()
        config["last_triggered"] = datetime.now().isoformat(timespec="seconds")
        _write_config(config)
        return session_id
    except requests.RequestException:
        logger.exception("Session manager unreachable during housekeeping trigger")
        return None
```

Note: `—` is the em-dash (—). The command string must be `/housekeeping — run in scheduled mode` with an em-dash, not a hyphen.

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker.exe compose exec ikeos pytest tests/test_scheduler.py -v
```

Expected: 12 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler service — trigger_now() with session manager integration"
```

---

### Task 4: Scheduler service — start() and _job()

**Files:**
- Modify: `app/services/scheduler.py`

No unit tests for `start()` — it requires a running APScheduler and is exercised by the integration smoke test in Task 8.

- [ ] **Step 1: Append start() and _job() to scheduler.py**

Append to the end of `app/services/scheduler.py`:

```python
def _job() -> None:
    logger.info("Housekeeping scheduled trigger firing")
    trigger_now()


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

- [ ] **Step 2: Verify existing tests still pass**

```bash
docker.exe compose exec ikeos pytest tests/test_scheduler.py -v
```

Expected: 12 PASSED (no regressions)

- [ ] **Step 3: Commit**

```bash
git add app/services/scheduler.py
git commit -m "feat: scheduler service — start() with APScheduler BackgroundScheduler"
```

---

### Task 5: GET/PATCH /housekeeping/schedule routes

**Files:**
- Modify: `app/routes/housekeeping.py`
- Modify: `tests/test_housekeeping.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_housekeeping.py`:

```python
# ── GET /housekeeping/schedule ──

def test_get_schedule_returns_config_shape(client, monkeypatch, tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    resp = client.get("/housekeeping/schedule")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "enabled" in data
    assert "day_of_week" in data
    assert "hour" in data
    assert "minute" in data
    assert "last_triggered" in data
    assert "next_run" in data


def test_get_schedule_returns_defaults_when_no_file(client, monkeypatch, tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    resp = client.get("/housekeeping/schedule")
    data = resp.get_json()
    assert data["enabled"] is False
    assert data["day_of_week"] == "sun"
    assert data["next_run"] is None  # scheduler not running in test mode


# ── PATCH /housekeeping/schedule ──

def test_patch_schedule_requires_token(client, monkeypatch):
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "real-token")
    resp = client.patch("/housekeeping/schedule",
                        json={"enabled": True},
                        headers={"X-Capture-Token": "wrong-token"})
    assert resp.status_code == 401


def test_patch_schedule_rejects_non_json_body(client, monkeypatch, tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    resp = client.patch("/housekeeping/schedule",
                        data="not json",
                        headers={"X-Capture-Token": "tok",
                                 "Content-Type": "text/plain"})
    assert resp.status_code == 400


def test_patch_schedule_rejects_invalid_hour(client, monkeypatch, tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    resp = client.patch("/housekeeping/schedule",
                        json={"hour": 25},
                        headers={"X-Capture-Token": "tok"})
    assert resp.status_code == 400
    assert "hour" in resp.get_json()["error"]


def test_patch_schedule_rejects_invalid_day_of_week(client, monkeypatch, tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    resp = client.patch("/housekeeping/schedule",
                        json={"day_of_week": "xyz"},
                        headers={"X-Capture-Token": "tok"})
    assert resp.status_code == 400
    assert "day_of_week" in resp.get_json()["error"]


def test_patch_schedule_updates_and_returns_config(client, monkeypatch, tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    resp = client.patch("/housekeeping/schedule",
                        json={"enabled": False, "hour": 4, "minute": 30, "day_of_week": "mon"},
                        headers={"X-Capture-Token": "tok"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["hour"] == 4
    assert data["minute"] == 30
    assert data["day_of_week"] == "mon"
    assert data["enabled"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker.exe compose exec ikeos pytest tests/test_housekeeping.py::test_get_schedule_returns_config_shape -v
```

Expected: `404` — route doesn't exist yet

- [ ] **Step 3: Add _check_auth(), GET, PATCH, and update index() in housekeeping.py**

In `app/routes/housekeeping.py`, add `_check_auth()` after the existing module-level constants and before the first route:

```python
def _check_auth() -> tuple[bool, int]:
    if not CAPTURE_TOKEN:
        return False, 503
    if request.headers.get("X-Capture-Token", "") != CAPTURE_TOKEN:
        return False, 401
    return True, 200
```

Update `index()` to fetch and pass schedule config:

```python
@bp.route("/housekeeping")
def index():
    from app.services.vault import read_housekeeping_tasks, read_housekeeping_heartbeat
    from app.services.scheduler import get_config_with_next_run
    tasks = read_housekeeping_tasks("claude-config")
    heartbeat = read_housekeeping_heartbeat("claude-config")
    schedule = get_config_with_next_run()
    return render_template(
        "housekeeping.html",
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
        schedule=schedule,
    )
```

Add the two new routes after `run_task()`:

```python
@bp.route("/housekeeping/schedule", methods=["GET"])
def get_schedule():
    from app.services.scheduler import get_config_with_next_run
    return jsonify(get_config_with_next_run()), 200


@bp.route("/housekeeping/schedule", methods=["PATCH"])
def patch_schedule():
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid or empty JSON body"}), 400
    allowed = {"enabled", "day_of_week", "hour", "minute"}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({"error": "No valid fields provided"}), 400
    try:
        from app.services.scheduler import update_config, get_config_with_next_run
        update_config(fields)
        return jsonify(get_config_with_next_run()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker.exe compose exec ikeos pytest tests/test_housekeeping.py -v -k "schedule"
```

Expected: 8 tests PASSED

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
docker.exe compose exec ikeos pytest tests/ -v 2>&1 | tail -20
```

Expected: all existing tests still pass; only pre-existing failures (pytest-mock related) if any.

- [ ] **Step 6: Commit**

```bash
git add app/routes/housekeeping.py tests/test_housekeeping.py
git commit -m "feat: GET/PATCH /housekeeping/schedule endpoints"
```

---

### Task 6: Housekeeping page — Schedule section

**Files:**
- Modify: `app/templates/housekeeping.html`
- Modify: `app/static/style.css`
- Modify: `app/static/bundle.css` (regenerated)

- [ ] **Step 1: Add Schedule section to housekeeping.html**

Insert the following block between the closing `</header>` tag and the opening `<section>` (Tasks section) tag. The full file currently has `</header>` on line 11 and `<section>` on line 13. Insert between them:

```html
  <section class="hk-schedule-section">
    <div class="ike-eyebrow">Schedule</div>
    <div class="hk-schedule-card">
      <div class="hk-schedule-row">
        <label class="hk-schedule-toggle-label">
          <input type="checkbox" id="sched-enabled"
                 {% if schedule.enabled %}checked{% endif %}>
          Enable weekly run
        </label>
      </div>
      <div class="hk-schedule-row hk-schedule-time-row" id="sched-time-row">
        <label for="sched-day">Day</label>
        <select id="sched-day">
          {% for d, label in [('mon','Monday'),('tue','Tuesday'),('wed','Wednesday'),
                               ('thu','Thursday'),('fri','Friday'),('sat','Saturday'),
                               ('sun','Sunday')] %}
          <option value="{{ d }}" {% if schedule.day_of_week == d %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>
        <label for="sched-hour">Time</label>
        <input type="number" id="sched-hour" min="0" max="23"
               value="{{ schedule.hour }}" class="hk-time-input">
        <span class="hk-time-sep">:</span>
        <input type="number" id="sched-minute" min="0" max="59"
               value="{{ schedule.minute }}" class="hk-time-input">
      </div>
      <div class="hk-schedule-meta">
        <span class="hk-schedule-label">Next run:</span>
        <span id="sched-next">
          {%- if schedule.next_run -%}
            {{ schedule.next_run }}
          {%- elif schedule.enabled -%}
            Calculating…
          {%- else -%}
            Disabled
          {%- endif -%}
        </span>
      </div>
      <div class="hk-schedule-meta">
        <span class="hk-schedule-label">Last triggered:</span>
        <span id="sched-last">{{ schedule.last_triggered or 'Never' }}</span>
      </div>
      <div class="hk-schedule-footer">
        <button class="pill pill-primary" id="sched-save"
                onclick="saveSchedule()" style="display:none">Save</button>
        <span class="hk-form-msg" id="sched-msg"></span>
      </div>
    </div>
  </section>
```

- [ ] **Step 2: Add schedule JS to the script block**

In `housekeeping.html`, insert the following JS block before the closing `</script>` tag (after the `addTaskForm` submit listener):

```javascript
// ── Schedule control ──
const _schedState = {
  enabled: {{ schedule.enabled | tojson }},
  day_of_week: {{ schedule.day_of_week | tojson }},
  hour: {{ schedule.hour | int }},
  minute: {{ schedule.minute | int }},
};

function _schedChanged() {
  return document.getElementById('sched-enabled').checked !== _schedState.enabled ||
         document.getElementById('sched-day').value !== _schedState.day_of_week ||
         parseInt(document.getElementById('sched-hour').value) !== _schedState.hour ||
         parseInt(document.getElementById('sched-minute').value) !== _schedState.minute;
}

function _updateSaveBtn() {
  document.getElementById('sched-save').style.display = _schedChanged() ? '' : 'none';
}

['sched-enabled', 'sched-day', 'sched-hour', 'sched-minute'].forEach(function(id) {
  const el = document.getElementById(id);
  el.addEventListener('change', _updateSaveBtn);
  el.addEventListener('input', _updateSaveBtn);
});

async function saveSchedule() {
  const btn = document.getElementById('sched-save');
  const msg = document.getElementById('sched-msg');
  btn.disabled = true;
  msg.textContent = '';
  const payload = {
    enabled: document.getElementById('sched-enabled').checked,
    day_of_week: document.getElementById('sched-day').value,
    hour: parseInt(document.getElementById('sched-hour').value),
    minute: parseInt(document.getElementById('sched-minute').value),
  };
  try {
    const resp = await fetch('/housekeeping/schedule', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (resp.ok) {
      const data = await resp.json();
      _schedState.enabled = data.enabled;
      _schedState.day_of_week = data.day_of_week;
      _schedState.hour = data.hour;
      _schedState.minute = data.minute;
      document.getElementById('sched-next').textContent =
        data.next_run || (data.enabled ? 'Calculating…' : 'Disabled');
      document.getElementById('sched-last').textContent = data.last_triggered || 'Never';
      btn.style.display = 'none';
      msg.textContent = 'Saved.';
      setTimeout(function() { msg.textContent = ''; }, 2000);
    } else {
      const err = await resp.json().catch(function() { return {}; });
      msg.textContent = err.error || 'Failed to save.';
    }
  } catch (e) {
    msg.textContent = 'Network error — could not save schedule.';
  }
  btn.disabled = false;
}
```

- [ ] **Step 3: Add CSS to style.css**

Append the following to the end of `app/static/style.css`:

```css
/* ── Housekeeping schedule section ── */
.hk-schedule-section { margin-bottom: 2rem; }

.hk-schedule-card {
  background: var(--surface-card);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 560px;
}

.hk-schedule-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.hk-schedule-toggle-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-primary);
  cursor: pointer;
}

.hk-schedule-time-row label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.hk-schedule-time-row select {
  font-size: 0.8125rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--surface-input, var(--surface-card));
  color: var(--text-primary);
}

.hk-time-input {
  width: 3.25rem;
  font-size: 0.8125rem;
  padding: 0.25rem 0.4rem;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--surface-input, var(--surface-card));
  color: var(--text-primary);
  text-align: center;
  -moz-appearance: textfield;
}
.hk-time-input::-webkit-inner-spin-button,
.hk-time-input::-webkit-outer-spin-button { -webkit-appearance: none; }

.hk-time-sep {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.hk-schedule-meta {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  font-size: 0.8125rem;
}

.hk-schedule-label {
  color: var(--text-tertiary);
  white-space: nowrap;
}

.hk-schedule-footer {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.25rem;
}
```

- [ ] **Step 4: Rebuild the CSS bundle**

```bash
python3 scripts/bundle_css.py
```

Expected output: `bundle.css written (NNN bytes, 10 files inlined)` — byte count will be larger than before.

- [ ] **Step 5: Commit**

```bash
git add app/templates/housekeeping.html app/static/style.css app/static/bundle.css
git commit -m "feat: housekeeping schedule section on management page"
```

---

### Task 7: Wire up scheduler in create_app()

**Files:**
- Modify: `app/__init__.py`
- Modify: `tests/conftest.py`

The `client` fixture in conftest.py calls `create_app()` and then sets `TESTING=True` — but by then `start()` has already been called with `TESTING=False`. Fix: update `create_app()` to accept an optional config dict so tests can pass `TESTING=True` before blueprints finish registering.

- [ ] **Step 1: Update create_app() in app/__init__.py**

Change the function signature and add scheduler wiring. The full updated `create_app()` function (replace the existing one):

```python
def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    if config:
        app.config.update(config)
    app.secret_key = os.environ["FLASK_SECRET_KEY"]
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

    from app.routes.capture import bp as capture_bp
    from app.routes.browse import bp as browse_bp
    from app.routes.agents import bp as agents_bp
    from app.routes.housekeeping import bp as housekeeping_bp

    app.register_blueprint(capture_bp)
    app.register_blueprint(browse_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(housekeeping_bp)

    @app.template_filter("docker_image")
    def docker_image_filter(image: str) -> str:
        """'lscr.io/linuxserver/radarr:6.2.1.10461-ls306' → 'radarr 6.2.1'"""
        name_tag = image.split("/")[-1]
        if ":" in name_tag:
            name, tag = name_tag.split(":", 1)
            tag = re.sub(r"^v", "", tag)
            m = re.match(r"^[\d.]+", tag)
            version = m.group().rstrip(".") if m else tag
            if version and version != "latest" and not re.fullmatch(r"[0-9a-f]{7,}", version):
                return f"{name} {version}"
            return name
        return name_tag

    @app.template_filter("docker_ports")
    def docker_ports_filter(ports: str) -> str:
        """'0.0.0.0:7878->7878/tcp, [::]:7878->7878/tcp' → '7878'"""
        if not ports:
            return "—"
        seen: set[str] = set()
        unique = []
        for p in re.findall(r"(?:0\.0\.0\.0|\[::\]):(\d+)->", ports):
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return ", ".join(unique) if unique else "—"

    @app.context_processor
    def inject_config_version():
        try:
            with open("/claude-config/VERSION") as f:
                version = f.read().strip()
        except OSError:
            version = None
        return {"config_version": version}

    @app.route("/health")
    def health():
        return "ok", 200

    threading.Thread(target=_warm_cache, daemon=True).start()

    from app.services import scheduler as scheduler_svc
    scheduler_svc.start(app)

    return app
```

- [ ] **Step 2: Update conftest.py client fixture**

In `tests/conftest.py`, change the `client` fixture to pass `TESTING=True`:

```python
@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as c:
        yield c
```

The full updated `tests/conftest.py`:

```python
import os
import pytest
from app import create_app
from app.services.vault import _invalidate_cache


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")


@pytest.fixture(autouse=True)
def reset_vault_cache():
    _invalidate_cache()
    yield
    _invalidate_cache()


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as c:
        yield c
```

- [ ] **Step 3: Run full test suite**

```bash
docker.exe compose exec ikeos pytest tests/ -v 2>&1 | tail -30
```

Expected: all previously-passing tests still pass; no new failures.

- [ ] **Step 4: Commit**

```bash
git add app/__init__.py tests/conftest.py
git commit -m "feat: wire up housekeeping scheduler in create_app()"
```

---

### Task 8: Rebuild container and smoke test

**Files:**
- Rebuild Docker image

- [ ] **Step 1: Rebuild and restart the container**

```bash
docker.exe compose up --build -d ikeos
```

Wait ~8 seconds for gunicorn to start.

- [ ] **Step 2: Health check**

```bash
curl -s http://localhost:5009/health
```

Expected: `ok`

- [ ] **Step 3: Check scheduler started in container logs**

```bash
docker.exe compose logs ikeos 2>&1 | grep -i "scheduler\|housekeeping"
```

Expected: a log line like `Housekeeping scheduler started (enabled=False, schedule=sun 3:7)`

- [ ] **Step 4: Verify GET /housekeeping/schedule**

```bash
curl -s http://localhost:5009/housekeeping/schedule | python3 -m json.tool
```

Expected: JSON with `enabled`, `day_of_week`, `hour`, `minute`, `last_triggered`, `next_run` keys.

- [ ] **Step 5: Verify PATCH /housekeeping/schedule**

```bash
curl -s -X PATCH http://localhost:5009/housekeeping/schedule \
  -H "Content-Type: application/json" \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d '{"enabled": true}' | python3 -m json.tool
```

Expected: `200` response with `enabled: true` and a non-null `next_run` (the next Sunday at 3:07 AM).

- [ ] **Step 6: Disable again (don't leave enabled in smoke test)**

```bash
curl -s -X PATCH http://localhost:5009/housekeeping/schedule \
  -H "Content-Type: application/json" \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d '{"enabled": false}' | python3 -m json.tool
```

Expected: `200` with `enabled: false`, `next_run: null`.

- [ ] **Step 7: Load management page and verify schedule section renders**

```bash
curl -s http://localhost:5009/housekeeping | grep -o "hk-schedule-card\|sched-enabled\|sched-save"
```

Expected: all three strings found.

- [ ] **Step 8: Commit**

```bash
git add app/static/bundle.css  # in case bundle differs after rebuild
git diff --exit-code app/static/bundle.css || git commit -m "chore: rebuild bundle.css after scheduler integration"
```

Only commit if there are changes; if the bundle is already up to date from Task 6, this is a no-op.
