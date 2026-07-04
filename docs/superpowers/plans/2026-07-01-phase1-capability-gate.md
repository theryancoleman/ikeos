# Phase 1 Capability Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a capability registry that gates the housekeeping scheduler (the only fully-autonomous IkeOS capability), with UI toggle on `/housekeeping`, metrics events on enable/disable, and capability status on `/metrics`.

**Architecture:** New `app/services/capabilities.py` reads/writes `capabilities.json` in the vault (same location as `schedule.json`). `scheduler._job()` calls `is_enabled("housekeeping_scheduler")` as a pre-condition. Two new routes on the housekeeping blueprint expose read/write. The housekeeping and metrics templates each get a capabilities panel. All work is in `/mnt/c/Server/projects/ikeos`.

**Tech Stack:** Python 3.11, Flask, pytest, Jinja2. Tests run via `docker exec ikeos pytest`. All module-level env vars are patched with `monkeypatch.setenv`; module-level objects patched with `monkeypatch.setattr`.

---

## File Map

| Task | Action | File |
|---|---|---|
| 1 | Create | `app/services/capabilities.py` |
| 1 | Create | `tests/test_capabilities.py` |
| 2 | Modify | `app/services/scheduler.py` |
| 2 | Modify | `tests/test_scheduler.py` |
| 3 | Modify | `app/routes/housekeeping.py` |
| 3 | Modify | `tests/test_housekeeping.py` |
| 4 | Modify | `app/routes/housekeeping.py` (`_housekeeping_context`) |
| 4 | Modify | `app/templates/housekeeping.html` |
| 5 | Modify | `app/routes/agents.py` (`metrics_view`) |
| 5 | Modify | `app/templates/metrics.html` |

---

## Task 1: `app/services/capabilities.py`

New service. No Flask imports. Reads/writes `capabilities.json` in the vault at
`{VAULT_PATH}/projects/claude-config/housekeeping/capabilities.json`. Returns defaults
(all disabled) when the file is absent. Emits metrics events on capability changes.

**Files:**
- Create: `app/services/capabilities.py`
- Create: `tests/test_capabilities.py`

- [x] **Step 1: Write failing tests**

Create `tests/test_capabilities.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def cap_vault(tmp_path):
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    return tmp_path


def _hk_dir(vault) -> Path:
    return vault / "projects" / "claude-config" / "housekeeping"


# ── get_capabilities ──

def test_get_capabilities_returns_defaults_when_no_file(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    caps = caps_mod.get_capabilities()
    assert "housekeeping_scheduler" in caps
    assert caps["housekeeping_scheduler"]["enabled"] is False
    assert caps["housekeeping_scheduler"]["enabled_by"] is None
    assert caps["housekeeping_scheduler"]["enabled_at"] is None


def test_get_capabilities_reads_existing_file(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    cap_file.write_text(json.dumps({
        "housekeeping_scheduler": {
            "enabled": True,
            "enabled_by": "architect",
            "enabled_at": "2026-07-01T10:00:00+00:00",
            "description": "Scheduled weekly housekeeping runs via session manager",
        }
    }))
    import app.services.capabilities as caps_mod
    caps = caps_mod.get_capabilities()
    assert caps["housekeeping_scheduler"]["enabled"] is True
    assert caps["housekeeping_scheduler"]["enabled_by"] == "architect"


def test_get_capabilities_merges_with_defaults_for_missing_keys(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    # File only has enabled, missing other fields
    cap_file.write_text(json.dumps({"housekeeping_scheduler": {"enabled": True}}))
    import app.services.capabilities as caps_mod
    caps = caps_mod.get_capabilities()
    assert caps["housekeeping_scheduler"]["enabled"] is True
    assert "description" in caps["housekeeping_scheduler"]


def test_get_capabilities_returns_defaults_on_corrupt_file(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    cap_file.write_text("not json {{{")
    import app.services.capabilities as caps_mod
    caps = caps_mod.get_capabilities()
    assert caps["housekeeping_scheduler"]["enabled"] is False


# ── is_enabled ──

def test_is_enabled_false_by_default(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    assert caps_mod.is_enabled("housekeeping_scheduler") is False


def test_is_enabled_true_when_file_says_enabled(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    cap_file.write_text(json.dumps({"housekeeping_scheduler": {"enabled": True}}))
    import app.services.capabilities as caps_mod
    assert caps_mod.is_enabled("housekeeping_scheduler") is True


def test_is_enabled_false_for_unknown_capability(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    assert caps_mod.is_enabled("nonexistent_capability") is False


# ── update_capability ──

def test_update_capability_enables_and_writes_file(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with patch("app.services.capabilities.append_event"):
        record = caps_mod.update_capability("housekeeping_scheduler", True)
    assert record["enabled"] is True
    assert record["enabled_by"] == "architect"
    assert record["enabled_at"] is not None
    cap_file = _hk_dir(cap_vault) / "capabilities.json"
    assert cap_file.exists()
    saved = json.loads(cap_file.read_text())
    assert saved["housekeeping_scheduler"]["enabled"] is True


def test_update_capability_disable_clears_actor_and_timestamp(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with patch("app.services.capabilities.append_event"):
        caps_mod.update_capability("housekeeping_scheduler", True)
        record = caps_mod.update_capability("housekeeping_scheduler", False)
    assert record["enabled"] is False
    assert record["enabled_by"] is None
    assert record["enabled_at"] is None


def test_update_capability_emits_enabled_event(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with patch("app.services.capabilities.append_event") as mock_emit:
        caps_mod.update_capability("housekeeping_scheduler", True)
    mock_emit.assert_called_once_with(
        "capability.enabled",
        {"capability": "housekeeping_scheduler", "actor": "architect"},
    )


def test_update_capability_emits_disabled_event(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with patch("app.services.capabilities.append_event") as mock_emit:
        caps_mod.update_capability("housekeeping_scheduler", False)
    mock_emit.assert_called_once_with(
        "capability.disabled",
        {"capability": "housekeeping_scheduler", "actor": "architect"},
    )


def test_update_capability_raises_for_unknown_name(cap_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(cap_vault))
    import app.services.capabilities as caps_mod
    with pytest.raises(ValueError, match="Unknown capability"):
        caps_mod.update_capability("nonexistent", True)
```

- [x] **Step 2: Run tests to confirm they fail**

```bash
docker exec ikeos pytest tests/test_capabilities.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError` or `ImportError` — `app.services.capabilities` does not exist yet.

- [x] **Step 3: Create `app/services/capabilities.py`**

```python
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CAPABILITIES: dict = {
    "housekeeping_scheduler": {
        "enabled": False,
        "enabled_by": None,
        "enabled_at": None,
        "description": "Scheduled weekly housekeeping runs via session manager",
    }
}


def _capabilities_path() -> Path:
    vault = Path(os.environ.get("VAULT_PATH", "/vault"))
    return vault / "projects" / "claude-config" / "housekeeping" / "capabilities.json"


def get_capabilities() -> dict:
    path = _capabilities_path()
    result = {k: dict(v) for k, v in DEFAULT_CAPABILITIES.items()}
    if not path.exists():
        return result
    try:
        with open(path) as f:
            data = json.load(f)
        for name, record in data.items():
            if name in result:
                result[name].update(record)
        return result
    except Exception:
        logger.exception("Failed to read capabilities from %s", path)
        return result


def is_enabled(name: str) -> bool:
    return bool(get_capabilities().get(name, {}).get("enabled", False))


def update_capability(name: str, enabled: bool, actor: str = "architect") -> dict:
    if name not in DEFAULT_CAPABILITIES:
        raise ValueError(f"Unknown capability: {name}")
    caps = get_capabilities()
    caps[name]["enabled"] = enabled
    caps[name]["enabled_by"] = actor if enabled else None
    caps[name]["enabled_at"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds") if enabled else None
    )
    path = _capabilities_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(caps, f, indent=2)
    tmp.replace(path)
    from app.services.metrics import append_event
    event_type = "capability.enabled" if enabled else "capability.disabled"
    append_event(event_type, {"capability": name, "actor": actor})
    return caps[name]
```

- [x] **Step 4: Run tests to confirm they pass**

```bash
docker exec ikeos pytest tests/test_capabilities.py -v
```

Expected: all PASSED.

- [x] **Step 5: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/services/capabilities.py tests/test_capabilities.py
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add capabilities service with vault-backed registry

get_capabilities/is_enabled/update_capability. Defaults all
capabilities to disabled. update_capability emits capability.enabled
or capability.disabled to metrics. housekeeping_scheduler is the
first registered capability."
```

---

## Task 2: Gate `scheduler._job()` behind capability check

`_job()` is the APScheduler callback. It currently always calls `trigger_now()`. Add
`is_enabled("housekeeping_scheduler")` as a pre-condition. The cron job still fires on
schedule — it just exits early when the gate is off. Tests import `_job` directly.

**Files:**
- Modify: `app/services/scheduler.py` (lines around `_job`)
- Modify: `tests/test_scheduler.py`

- [x] **Step 1: Write failing tests**

Add to the bottom of `tests/test_scheduler.py`:

```python
# ── _job capability gate ──

def test_job_skips_trigger_when_capability_disabled(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    # capability file absent → disabled by default
    with patch("app.services.scheduler.trigger_now") as mock_trigger, \
         patch("app.services.capabilities.append_event"):
        from app.services.scheduler import _job
        _job()
    mock_trigger.assert_not_called()


def test_job_calls_trigger_when_capability_enabled(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    # write capabilities.json with enabled=True
    cap_file = _hk_dir(sched_vault) / "capabilities.json"
    cap_file.write_text(json.dumps({"housekeeping_scheduler": {"enabled": True}}))
    with patch("app.services.scheduler.trigger_now") as mock_trigger, \
         patch("app.services.capabilities.append_event"):
        from app.services.scheduler import _job
        _job()
    mock_trigger.assert_called_once()
```

Note: `_hk_dir` and `sched_vault` are already defined at the top of `test_scheduler.py`. These new tests reuse them — no new fixtures needed.

- [x] **Step 2: Run to confirm they fail**

```bash
docker exec ikeos pytest tests/test_scheduler.py -k "test_job_skips or test_job_calls" -v
```

Expected: `test_job_skips` FAILS (trigger IS called even when disabled). `test_job_calls` may pass or fail depending on import caching.

- [x] **Step 3: Modify `_job()` in `app/services/scheduler.py`**

Find the existing `_job` function (currently 3 lines) and replace it:

```python
def _job() -> None:
    from app.services.capabilities import is_enabled
    if not is_enabled("housekeeping_scheduler"):
        logger.info("Housekeeping job skipped: capability gate disabled")
        return
    logger.info("Housekeeping scheduled trigger firing")
    trigger_now()
```

- [x] **Step 4: Run to confirm they pass**

```bash
docker exec ikeos pytest tests/test_scheduler.py -v
```

Expected: all PASSED, including the two new tests.

- [x] **Step 5: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/services/scheduler.py tests/test_scheduler.py
git -C /mnt/c/Server/projects/ikeos commit -m "feat: gate housekeeping scheduler behind capability registry

_job() now calls is_enabled('housekeeping_scheduler') before
trigger_now(). Scheduler still runs on its cron schedule — the
job exits early when the capability gate is off. New tests verify
both the skip and the trigger paths."
```

---

## Task 3: Capability routes on the housekeeping blueprint

Two new routes:
- `GET /housekeeping/capabilities` — returns `{capabilities: {...}}`, no auth required (read-only)
- `PATCH /housekeeping/capabilities/<name>` — updates one capability, requires CAPTURE_TOKEN

**Files:**
- Modify: `app/routes/housekeeping.py`
- Modify: `tests/test_housekeeping.py`

- [x] **Step 1: Write failing tests**

Add to the bottom of `tests/test_housekeeping.py`:

```python
# ── capability routes ──

def test_get_capabilities_returns_200(client):
    resp = client.get("/housekeeping/capabilities")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "capabilities" in data
    assert "housekeeping_scheduler" in data["capabilities"]


def test_get_capabilities_scheduler_disabled_by_default(client):
    resp = client.get("/housekeeping/capabilities")
    assert resp.status_code == 200
    cap = resp.get_json()["capabilities"]["housekeeping_scheduler"]
    assert cap["enabled"] is False


def test_patch_capability_requires_auth(client):
    resp = client.patch(
        "/housekeeping/capabilities/housekeeping_scheduler",
        json={"enabled": True},
        content_type="application/json",
    )
    assert resp.status_code in (401, 503)


def test_patch_capability_enables(client, tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    import app.routes.housekeeping as hk_mod
    import app.services.capabilities as caps_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    with patch("app.services.capabilities.append_event"):
        resp = client.patch(
            "/housekeeping/capabilities/housekeeping_scheduler",
            json={"enabled": True},
            content_type="application/json",
            headers={"X-Capture-Token": "tok"},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["capability"]["enabled"] is True
    assert data["capability"]["enabled_by"] == "architect"


def test_patch_capability_rejects_unknown_name(client, monkeypatch):
    monkeypatch.setattr("app.routes.housekeeping.CAPTURE_TOKEN", "tok")
    resp = client.patch(
        "/housekeeping/capabilities/nonexistent_cap",
        json={"enabled": True},
        content_type="application/json",
        headers={"X-Capture-Token": "tok"},
    )
    assert resp.status_code == 404


def test_patch_capability_rejects_missing_enabled_field(client, monkeypatch):
    monkeypatch.setattr("app.routes.housekeeping.CAPTURE_TOKEN", "tok")
    resp = client.patch(
        "/housekeeping/capabilities/housekeeping_scheduler",
        json={"something": "else"},
        content_type="application/json",
        headers={"X-Capture-Token": "tok"},
    )
    assert resp.status_code == 400
```

- [x] **Step 2: Run to confirm they fail**

```bash
docker exec ikeos pytest tests/test_housekeeping.py -k "capability" -v
```

Expected: 404 NOT FOUND errors — routes don't exist yet.

- [x] **Step 3: Add routes to `app/routes/housekeeping.py`**

At the top of the file, add to the existing imports line:

```python
from app.services.capabilities import get_capabilities, update_capability
```

Then add these two routes after the `patch_schedule` route (around line 415):

```python
@bp.route("/housekeeping/capabilities")
def get_capabilities_route():
    return jsonify({"capabilities": get_capabilities()}), 200


@bp.route("/housekeeping/capabilities/<name>", methods=["PATCH"])
def patch_capability(name: str):
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = request.get_json(silent=True) or {}
    if "enabled" not in data:
        return jsonify({"error": "enabled field required"}), 400
    try:
        record = update_capability(name, bool(data["enabled"]))
        return jsonify({"capability": record}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
```

- [x] **Step 4: Run to confirm they pass**

```bash
docker exec ikeos pytest tests/test_housekeeping.py -k "capability" -v
```

Expected: all PASSED.

- [x] **Step 5: Run the full housekeeping suite to check regressions**

```bash
docker exec ikeos pytest tests/test_housekeeping.py -v
```

Expected: 0 FAILED.

- [x] **Step 6: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/routes/housekeeping.py tests/test_housekeeping.py
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add GET/PATCH capability routes to housekeeping blueprint

GET /housekeeping/capabilities returns all capability states.
PATCH /housekeeping/capabilities/<name> updates one capability
(CAPTURE_TOKEN required). Returns 404 for unknown capability names."
```

---

## Task 4: Capabilities panel in `housekeeping.html`

Wire capabilities into `_housekeeping_context()` and render a panel above the schedule
section in `housekeeping.html`. Each capability shows its status and a toggle button.

**Files:**
- Modify: `app/routes/housekeeping.py` (`_housekeeping_context` function)
- Modify: `app/templates/housekeeping.html`

- [x] **Step 1: Add `capabilities` to `_housekeeping_context()`**

Find `_housekeeping_context()` in `app/routes/housekeeping.py` (around line 344). Add
the import and the capabilities key to the returned dict:

```python
def _housekeeping_context() -> dict:
    from app.services.vault import read_housekeeping_tasks, read_housekeeping_heartbeat
    from app.services.capabilities import get_capabilities
    tasks = read_housekeeping_tasks()
    heartbeat = read_housekeeping_heartbeat("claude-config")
    schedule = get_config_with_next_run()
    return dict(
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
        schedule=schedule,
        capture_token=CAPTURE_TOKEN,
        blog_draft=_latest_blog_draft(),
        capabilities=get_capabilities(),
    )
```

- [x] **Step 2: Add capabilities panel to `housekeeping.html`**

Open `app/templates/housekeeping.html`. Find the `<section class="hk-schedule-section">` block. Insert the following **before** it (i.e., between `</header>` and `<section class="hk-schedule-section">`):

```html
  <!-- Capabilities gate -->
  <section class="hk-schedule-section">
    <div class="ike-eyebrow">Capabilities</div>
    {% for name, cap in capabilities.items() %}
    <div class="hk-schedule-card" id="cap-card-{{ name }}">
      <div class="hk-schedule-row" style="justify-content: space-between; align-items: center;">
        <div>
          <strong>{{ name | replace('_', ' ') | title }}</strong>
          <p class="hk-schedule-meta" style="margin: 2px 0 0;">{{ cap.description }}</p>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="pill {% if cap.enabled %}pill--housekeeping{% else %}pill--muted{% endif %}"
                id="cap-status-{{ name }}">
            {{ 'ENABLED' if cap.enabled else 'DISABLED' }}
          </span>
          <button class="pill pill-primary"
                  onclick="toggleCapability('{{ name }}', {{ 'false' if cap.enabled else 'true' }})"
                  id="cap-btn-{{ name }}">
            {{ 'Disable' if cap.enabled else 'Enable' }}
          </button>
        </div>
      </div>
      {% if cap.enabled and cap.enabled_at %}
      <div class="hk-schedule-meta">
        <span class="hk-schedule-label">Enabled:</span>
        {{ cap.enabled_at | replace('T', ' ') | replace('+00:00', '') }} by {{ cap.enabled_by }}
      </div>
      {% endif %}
      <div class="hk-form-msg" id="cap-msg-{{ name }}"></div>
    </div>
    {% endfor %}
  </section>
```

- [x] **Step 3: Add `toggleCapability` JS to `housekeeping.html`**

Find the `<script>` block in `housekeeping.html`. Add the following function inside it (before the closing `</script>` tag):

```javascript
async function toggleCapability(name, enable) {
  const btn = document.getElementById('cap-btn-' + name);
  const statusEl = document.getElementById('cap-status-' + name);
  const msgEl = document.getElementById('cap-msg-' + name);
  btn.disabled = true;
  msgEl.textContent = '';
  try {
    const resp = await fetch('/housekeeping/capabilities/' + name, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Capture-Token': captureToken,
      },
      body: JSON.stringify({ enabled: enable }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      msgEl.textContent = data.error || 'Failed';
      btn.disabled = false;
      return;
    }
    const enabled = data.capability.enabled;
    statusEl.textContent = enabled ? 'ENABLED' : 'DISABLED';
    statusEl.className = 'pill ' + (enabled ? 'pill--housekeeping' : 'pill--muted');
    btn.textContent = enabled ? 'Disable' : 'Enable';
    btn.onclick = () => toggleCapability(name, !enabled);
    btn.disabled = false;
  } catch (e) {
    msgEl.textContent = 'Request failed';
    btn.disabled = false;
  }
}
```

Note: `captureToken` is already defined in the existing `<script>` block as
`const captureToken = {{ capture_token | tojson }};` — do not redefine it.

- [x] **Step 4: Rebuild and smoke test**

```bash
docker.exe compose up --build -d ikeos
curl -s http://localhost:5009/housekeeping | grep -i "capabilities\|ENABLED\|DISABLED"
```

Expected: output contains "Capabilities" section text.

- [x] **Step 5: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/routes/housekeeping.py app/templates/housekeeping.html
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add capabilities panel to housekeeping page

Shows each capability's enabled/disabled state with a toggle button.
_housekeeping_context() now passes capabilities dict to the template.
toggleCapability() JS calls PATCH /housekeeping/capabilities/<name>
and updates the UI inline without a page reload."
```

---

## Task 5: Capability status panel on `/metrics`

Pass capability state to `metrics.html` and render a status panel above the event table.

**Files:**
- Modify: `app/routes/agents.py` (`metrics_view`)
- Modify: `app/templates/metrics.html`
- Modify: `tests/test_metrics.py`

- [x] **Step 1: Write a failing test**

Add to `tests/test_metrics.py`:

```python
def test_metrics_view_shows_capability_status(client, tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    (tmp_path / "projects" / "claude-config" / "housekeeping").mkdir(parents=True)
    import app.services.metrics as metrics_mod
    with patch("app.services.metrics.METRICS_PATH", tmp_path / "events.jsonl"):
        resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "housekeeping_scheduler" in body.lower() or "housekeeping scheduler" in body.lower()
```

- [x] **Step 2: Run to confirm it fails**

```bash
docker exec ikeos pytest tests/test_metrics.py::test_metrics_view_shows_capability_status -v
```

Expected: FAILED — "housekeeping" not yet in the metrics template.

- [x] **Step 3: Update `metrics_view()` in `app/routes/agents.py`**

Find `metrics_view()` (around line 184) and add the capabilities import and argument:

```python
@bp.route("/metrics")
def metrics_view() -> str:
    from app.services.capabilities import get_capabilities
    events = read_events(limit=50)
    capabilities = get_capabilities()
    return render_template("metrics.html", events=events, capabilities=capabilities)
```

- [x] **Step 4: Add capability status panel to `metrics.html`**

Open `app/templates/metrics.html`. After `</header>` and before the `{% if not events %}` block, insert:

```html
  <section style="margin-bottom: 24px;">
    <div class="ike-eyebrow">Capability Status</div>
    <table class="settings-list metrics-table">
      <thead>
        <tr>
          <th>Capability</th>
          <th>Status</th>
          <th>Since</th>
        </tr>
      </thead>
      <tbody>
      {% for name, cap in capabilities.items() %}
        <tr class="settings-row metrics-row">
          <td>{{ name | replace('_', ' ') | title }}</td>
          <td>
            <span class="pill {% if cap.enabled %}pill--housekeeping{% else %}pill--muted{% endif %}">
              {{ 'ENABLED' if cap.enabled else 'DISABLED' }}
            </span>
          </td>
          <td class="metrics-ts">
            {% if cap.enabled and cap.enabled_at %}
              {{ cap.enabled_at | replace('T', ' ') | replace('+00:00', '') }}
            {% else %}
              —
            {% endif %}
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </section>
```

- [x] **Step 5: Run the metrics test suite**

```bash
docker exec ikeos pytest tests/test_metrics.py -v
```

Expected: all PASSED.

- [x] **Step 6: Rebuild and smoke test**

```bash
docker.exe compose up --build -d ikeos
curl -s http://localhost:5009/metrics | grep -i "capability\|scheduler"
```

Expected: output contains capability status table text.

- [x] **Step 7: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/routes/agents.py app/templates/metrics.html tests/test_metrics.py
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add capability status panel to /metrics view

metrics_view() now passes capabilities dict to the template.
A read-only status table above the event timeline shows each
capability's enabled state and when it was last enabled."
```

---

## Verification Contract

This plan is done when:

- [x] `docker exec ikeos pytest tests/test_capabilities.py -v` — 0 FAILED
- [x] `docker exec ikeos pytest tests/test_scheduler.py -v` — 0 FAILED, gate tests passing
- [x] `docker exec ikeos pytest tests/test_housekeeping.py -v` — 0 FAILED, capability route tests passing
- [x] `docker exec ikeos pytest tests/test_metrics.py -v` — 0 FAILED
- [x] `docker exec ikeos pytest` — full suite 0 FAILED
- [x] `curl -s http://localhost:5009/housekeeping/capabilities` — returns `{"capabilities": {"housekeeping_scheduler": {"enabled": false, ...}}}`
- [x] `curl -s http://localhost:5009/metrics` — renders capability status panel
- [x] `curl -s http://localhost:5009/housekeeping` — renders Capabilities section above Schedule section
- [x] Toggling housekeeping_scheduler via UI PATCH changes state and emits a metrics event
