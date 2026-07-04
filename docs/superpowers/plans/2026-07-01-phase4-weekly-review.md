# Phase 4 — Weekly Platform Review Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the IkeOS-side infrastructure for the Weekly AI Engineering Platform Review: a gated trigger route, a Markdown viewer, a status widget on the housekeeping page, and the Docker/env plumbing to connect them to the review output directory.

**Architecture:** The review skill (to be built in claude-config separately) writes `YYYY-MM-DD-weekly-review.md` files to a host directory. IkeOS mounts that directory read-only at `/weekly-reviews`. `GET /housekeeping/weekly-review` reads the latest file and renders it. `POST /housekeeping/weekly-review/run` checks `is_enabled("weekly_platform_review")` and creates a session running `/platform-review` in the claude-config project dir. The housekeeping page gains a status widget showing the last review date and a conditional run button.

**Tech Stack:** Python 3.11, Flask, Jinja2, vanilla JS, Docker Compose, pytest

---

## File Map

| File | Change |
|---|---|
| `docker-compose.yml` | Add `WEEKLY_REVIEW_OUTPUT_DIR` env var + `/weekly-reviews` volume mount |
| `.env.example` | Document `WEEKLY_REVIEW_OUTPUT_PATH` |
| `app/routes/housekeeping.py` | Add `WEEKLY_REVIEW_OUTPUT_DIR` module var, `_latest_weekly_review()` helper, `_housekeeping_context()` update, `GET /weekly-review`, `POST /weekly-review/run` |
| `app/templates/weekly_review.html` | New template: renders review Markdown in a styled pre block |
| `app/templates/housekeeping.html` | Add weekly review status widget + `runWeeklyReview()` JS function |
| `tests/test_housekeeping.py` | 5 new tests for the two new routes |

---

### Task 1: Docker mount and env vars

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

No tests for Docker config — verify by checking the container starts clean.

- [x] **Step 1.1: Add env var to docker-compose.yml**

In `docker-compose.yml`, in the `environment:` block (alongside `AIOS_BLOG_POSTS_DIR`), add:

```yaml
      - WEEKLY_REVIEW_OUTPUT_DIR=/weekly-reviews
```

- [x] **Step 1.2: Add volume mount to docker-compose.yml**

In `docker-compose.yml`, in the `volumes:` block (alongside the blog-posts mount), add:

```yaml
      - ${WEEKLY_REVIEW_OUTPUT_PATH:-/tmp/ikeos-no-weekly-reviews}:/weekly-reviews:ro
```

The fallback `/tmp/ikeos-no-weekly-reviews` means Docker starts cleanly even when `WEEKLY_REVIEW_OUTPUT_PATH` is not set in `.env`. The app code checks if `/weekly-reviews` has any `*.md` files before reading — an empty or missing directory is a valid "no review yet" state.

- [x] **Step 1.3: Document in .env.example**

In `.env.example`, after the `AIOS_BLOG_PROJECT_DIR` line, add:

```
# Host path to the directory where weekly platform review Markdown files are written
# The review skill writes YYYY-MM-DD-weekly-review.md files here
WEEKLY_REVIEW_OUTPUT_PATH=/path/to/claude-config/library/weekly-reviews
```

- [x] **Step 1.4: Rebuild and confirm clean start**

```bash
docker.exe compose up --build -d ikeos
docker.exe compose logs --tail=20 ikeos
```

Expected: no errors about missing volumes or env vars.

- [x] **Step 1.5: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add docker-compose.yml .env.example
git -C /mnt/c/Server/projects/ikeos commit -m "chore: add weekly-reviews volume mount and env var for platform review output"
```

---

### Task 2: New routes in housekeeping.py

**Files:**
- Modify: `app/routes/housekeeping.py`
- Test: `tests/test_housekeeping.py`

Read `app/routes/housekeeping.py` before editing — understand the existing module-level vars (`AIOS_BLOG_POSTS_DIR`, `HOUSEKEEPING_PROJECT_DIR`) and helper patterns (`_blog_draft_paths`, `_latest_blog_draft`). The new code follows the same patterns.

- [x] **Step 2.1: Write the failing tests**

Read `tests/test_housekeeping.py` to find the import block at the top. The file uses `from unittest.mock import patch, MagicMock` and `import app.routes.housekeeping as hk_mod`. Add these 5 tests at the bottom of the file (after the last existing test):

```python
# ── GET /housekeeping/weekly-review ──

def test_weekly_review_returns_200_with_no_review_dir(client, monkeypatch):
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "WEEKLY_REVIEW_OUTPUT_DIR", "")
    resp = client.get("/housekeeping/weekly-review")
    assert resp.status_code == 200
    assert b"No review" in resp.data or b"weekly" in resp.data.lower()


def test_weekly_review_returns_200_with_no_files(client, monkeypatch, tmp_path):
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "WEEKLY_REVIEW_OUTPUT_DIR", str(tmp_path))
    resp = client.get("/housekeeping/weekly-review")
    assert resp.status_code == 200


def test_weekly_review_returns_latest_file_content(client, monkeypatch, tmp_path):
    import app.routes.housekeeping as hk_mod
    monkeypatch.setattr(hk_mod, "WEEKLY_REVIEW_OUTPUT_DIR", str(tmp_path))
    (tmp_path / "2026-06-30-weekly-review.md").write_text("# Review June 30")
    (tmp_path / "2026-07-01-weekly-review.md").write_text("# Review July 1")
    resp = client.get("/housekeeping/weekly-review")
    assert resp.status_code == 200
    assert b"Review July 1" in resp.data


# ── POST /housekeeping/weekly-review/run ──

def test_weekly_review_run_returns_403_when_capability_disabled(client, monkeypatch):
    import app.routes.housekeeping as hk_mod
    import app.services.capabilities as caps_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    monkeypatch.setattr(caps_mod, "is_enabled", lambda name: False)
    resp = client.post(
        "/housekeeping/weekly-review/run",
        headers={"X-Capture-Token": "tok"},
    )
    assert resp.status_code == 403
    assert "disabled" in resp.get_json().get("error", "").lower()


def test_weekly_review_run_creates_session_when_enabled(client, monkeypatch):
    import app.routes.housekeeping as hk_mod
    import app.services.capabilities as caps_mod
    monkeypatch.setattr(hk_mod, "CAPTURE_TOKEN", "tok")
    monkeypatch.setattr(hk_mod, "HOUSEKEEPING_PROJECT_DIR", "/srv/claude-config")
    monkeypatch.setattr(caps_mod, "is_enabled", lambda name: True)

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "review-sess-1"}

    with patch("app.services.session_client.requests.post", return_value=mock_resp):
        with patch("app.services.session_client.append_event"):
            resp = client.post(
                "/housekeeping/weekly-review/run",
                headers={"X-Capture-Token": "tok"},
            )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["session_id"] == "review-sess-1"
```

- [x] **Step 2.2: Run tests to confirm they fail**

```bash
docker exec ikeos pytest tests/test_housekeeping.py::test_weekly_review_returns_200_with_no_review_dir tests/test_housekeeping.py::test_weekly_review_run_returns_403_when_capability_disabled -v
```

Expected: FAIL with `404` (route does not exist yet).

- [x] **Step 2.3: Add module-level var and helper to housekeeping.py**

At the top of `app/routes/housekeeping.py`, after `AIOS_BLOG_PROJECT_DIR = os.environ.get(...)`, add:

```python
WEEKLY_REVIEW_OUTPUT_DIR = os.environ.get("WEEKLY_REVIEW_OUTPUT_DIR", "")
```

Then add this helper function after `_latest_blog_draft()`:

```python
def _latest_weekly_review() -> str | None:
    """Return the filename of the most recent weekly review Markdown file, or None."""
    if not WEEKLY_REVIEW_OUTPUT_DIR:
        return None
    review_dir = Path(WEEKLY_REVIEW_OUTPUT_DIR)
    if not review_dir.exists():
        return None
    reviews = sorted(review_dir.glob("*-weekly-review.md"), reverse=True)
    return reviews[0].name if reviews else None
```

- [x] **Step 2.4: Update _housekeeping_context() to include weekly review**

In `_housekeeping_context()`, add `weekly_review_file=_latest_weekly_review()` to the returned dict:

```python
def _housekeeping_context() -> dict:
    from app.services.vault import read_housekeeping_tasks, read_housekeeping_heartbeat
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
        weekly_review_file=_latest_weekly_review(),
        capabilities=get_capabilities(),
    )
```

- [x] **Step 2.5: Add the two new routes**

Add these two routes after `blog_draft_session_status()` and before `get_schedule()`:

```python
@bp.route("/housekeeping/weekly-review")
def weekly_review():
    """Display the most recent weekly platform review report."""
    if not WEEKLY_REVIEW_OUTPUT_DIR:
        return render_template("weekly_review.html", content=None, filename=None,
                               capture_token=CAPTURE_TOKEN, capabilities=get_capabilities())
    review_dir = Path(WEEKLY_REVIEW_OUTPUT_DIR)
    reviews = sorted(review_dir.glob("*-weekly-review.md"), reverse=True) if review_dir.exists() else []
    if not reviews:
        return render_template("weekly_review.html", content=None, filename=None,
                               capture_token=CAPTURE_TOKEN, capabilities=get_capabilities())
    latest = reviews[0]
    content = latest.read_text(encoding="utf-8")
    return render_template("weekly_review.html", content=content, filename=latest.name,
                           capture_token=CAPTURE_TOKEN, capabilities=get_capabilities())


@bp.route("/housekeeping/weekly-review/run", methods=["POST"])
def weekly_review_run():
    """Create a session to run the weekly platform review. Requires capability gate."""
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    from app.services.capabilities import is_enabled
    if not is_enabled("weekly_platform_review"):
        return jsonify({"error": "weekly_platform_review capability is disabled"}), 403
    result = create_session(
        name="weekly-platform-review",
        project="claude-config",
        project_dir=HOUSEKEEPING_PROJECT_DIR,
        initial_command="/platform-review",
    )
    if result.already_running:
        return jsonify({"ok": True, "session_id": result.session_id, "already_running": True}), 200
    if not result.ok:
        return jsonify({"error": "Failed to create review session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200
```

- [x] **Step 2.6: Run all 5 new tests — should pass**

```bash
docker exec ikeos pytest tests/test_housekeeping.py::test_weekly_review_returns_200_with_no_review_dir tests/test_housekeeping.py::test_weekly_review_returns_200_with_no_files tests/test_housekeeping.py::test_weekly_review_returns_latest_file_content tests/test_housekeeping.py::test_weekly_review_run_returns_403_when_capability_disabled tests/test_housekeeping.py::test_weekly_review_run_creates_session_when_enabled -v
```

Expected: all 5 PASS.

- [x] **Step 2.7: Run full test suite**

```bash
docker exec ikeos pytest tests/ -q
```

Expected: 333+ passed, 0 failed.

- [x] **Step 2.8: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/routes/housekeeping.py tests/test_housekeeping.py
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add weekly review routes and capability gate"
```

---

### Task 3: weekly_review.html template

**Files:**
- Create: `app/templates/weekly_review.html`

No unit tests for templates — verified visually after rebuild.

- [x] **Step 3.1: Create the template**

Create `app/templates/weekly_review.html` with this content:

```html
{% extends "base.html" %}
{% block title %}Weekly Platform Review{% endblock %}

{% block content %}
<div class="settings-page">

  <header class="page-header">
    <span class="ike-eyebrow">Housekeeping</span>
    <h1>Weekly Platform Review</h1>
    <p class="page-subtitle">
      Strategic review of the AI engineering ecosystem — what should change in IkeOS?
    </p>
  </header>

  <div style="display:flex; gap:10px; align-items:center; margin-bottom:20px;">
    <a href="{{ url_for('housekeeping.index') }}" class="pill">← Housekeeping</a>
    {% if capabilities.weekly_platform_review.enabled %}
    <button class="pill pill-primary" id="run-review-btn" onclick="runWeeklyReview(this)">
      Run Review
    </button>
    <span id="run-review-msg" style="font-size:0.85rem; color:var(--color-muted);"></span>
    {% else %}
    <span class="pill pill--muted">Enable capability to run</span>
    {% endif %}
  </div>

  {% if content %}
  <section>
    <div class="ike-eyebrow">{{ filename }}</div>
    <div class="hk-schedule-card" style="overflow-x:auto;">
      <pre style="white-space:pre-wrap; word-break:break-word; font-family:var(--font-mono, monospace);
                  font-size:0.85rem; line-height:1.6; margin:0;">{{ content | e }}</pre>
    </div>
  </section>
  {% else %}
  <div class="hk-widget">
    <p class="hk-status hk-status-pending">No review report found yet.</p>
    {% if not capabilities.weekly_platform_review.enabled %}
    <p style="font-size:0.9rem; color:var(--color-muted);">
      Enable the <strong>Weekly Platform Review</strong> capability on the
      <a href="{{ url_for('housekeeping.index') }}">Housekeeping page</a> to run the first review.
    </p>
    {% endif %}
  </div>
  {% endif %}

</div>

<script>
const _captureToken = {{ capture_token | tojson }};

async function runWeeklyReview(btn) {
  const msg = document.getElementById('run-review-msg');
  btn.disabled = true;
  btn.textContent = 'Starting…';
  msg.textContent = '';
  try {
    const resp = await fetch('/housekeeping/weekly-review/run', {
      method: 'POST',
      headers: {'X-Capture-Token': _captureToken},
    });
    const data = await resp.json();
    if (!resp.ok) {
      btn.textContent = 'Run Review';
      btn.disabled = false;
      msg.textContent = data.error || 'Error starting review.';
    } else if (data.already_running) {
      btn.textContent = 'Already running';
      msg.textContent = `Session: ${data.session_id}`;
    } else {
      btn.textContent = 'Running…';
      msg.textContent = `Session started: ${data.session_id}`;
    }
  } catch (e) {
    btn.textContent = 'Run Review';
    btn.disabled = false;
    msg.textContent = 'Network error.';
  }
}
</script>
{% endblock %}
```

- [x] **Step 3.2: Rebuild and verify the route renders**

```bash
docker.exe compose up --build -d ikeos
curl -s http://localhost:5009/housekeeping/weekly-review | grep -i "Weekly Platform Review"
```

Expected: the page title appears in the HTML.

- [x] **Step 3.3: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/templates/weekly_review.html
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add weekly platform review viewer template"
```

---

### Task 4: Housekeeping page status widget

**Files:**
- Modify: `app/templates/housekeeping.html`

This adds a "Weekly Platform Review" status widget to the housekeeping page, mirroring the existing "Weekly Blog Draft" widget pattern. It shows the latest review filename (linked to the viewer) and a "Run Review" button (only when capability is enabled).

- [x] **Step 4.1: Add the status widget to housekeeping.html**

In `app/templates/housekeeping.html`, after the closing `</div>` of the "Weekly Blog Draft" `hk-widget` block (around line 109), add:

```html
  <!-- Weekly Platform Review status -->
  <div class="hk-widget">
    <span class="ike-eyebrow">Weekly Platform Review</span>
    {% if weekly_review_file %}
      <p class="hk-status hk-status-ok">
        <a href="{{ url_for('housekeeping.weekly_review') }}" class="hk-draft-link">
          {{ weekly_review_file }}
        </a>
        — ready for review
      </p>
    {% else %}
      <p class="hk-status hk-status-pending">No review yet this week</p>
    {% endif %}
    {% if capabilities.weekly_platform_review.enabled %}
    <button class="pill pill-primary" style="margin-top:6px;"
            id="hk-run-review-btn" onclick="runWeeklyReview(this)">
      Run Review
    </button>
    <span id="hk-run-review-msg" style="font-size:0.85rem; color:var(--color-muted); margin-left:8px;"></span>
    {% else %}
    <p style="font-size:0.85rem; color:var(--color-muted); margin-top:4px;">
      Enable the <strong>Weekly Platform Review</strong> capability above to run.
    </p>
    {% endif %}
  </div>
```

- [x] **Step 4.2: Add the runWeeklyReview() JS function**

In `app/templates/housekeeping.html`, in the `<script>` block (after the existing `runTask()` function and before `deleteTask()`), add:

```javascript
async function runWeeklyReview(btn) {
  const msgId = btn.id === 'hk-run-review-btn' ? 'hk-run-review-msg' : 'run-review-msg';
  const msg = document.getElementById(msgId);
  btn.disabled = true;
  btn.textContent = 'Starting…';
  if (msg) msg.textContent = '';
  try {
    const resp = await fetch('/housekeeping/weekly-review/run', {
      method: 'POST',
      headers: {'X-Capture-Token': _captureToken},
    });
    const data = await resp.json();
    if (!resp.ok) {
      btn.textContent = 'Run Review';
      btn.disabled = false;
      if (msg) msg.textContent = data.error || 'Error starting review.';
    } else if (data.already_running) {
      btn.textContent = 'Already running';
      if (msg) msg.textContent = `Session: ${data.session_id}`;
    } else {
      btn.textContent = 'Running…';
      if (msg) msg.textContent = `Session started: ${data.session_id}`;
    }
  } catch (e) {
    btn.textContent = 'Run Review';
    btn.disabled = false;
    if (msg) msg.textContent = 'Network error.';
  }
}
```

- [x] **Step 4.3: Rebuild and verify the widget appears**

```bash
docker.exe compose up --build -d ikeos
curl -s http://localhost:5009/housekeeping | grep -i "Weekly Platform Review"
```

Expected: the widget text appears in the page HTML.

- [x] **Step 4.4: Run full test suite to confirm no regressions**

```bash
docker exec ikeos pytest tests/ -q
```

Expected: 333+ passed, 0 failed.

- [x] **Step 4.5: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add app/templates/housekeeping.html
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add weekly platform review status widget to housekeeping page"
```

---

## Self-Review

**Spec coverage:**
- Docker mount + env: Task 1 ✓
- `GET /housekeeping/weekly-review`: Task 2 routes + Task 3 template ✓
- `POST /housekeeping/weekly-review/run` with capability gate: Task 2 ✓
- Housekeeping page widget: Task 4 ✓
- Tests for new routes (3 GET + 2 POST): Task 2 ✓

**Placeholder scan:** No TBDs. All steps include actual code. Template has actual HTML. JavaScript is complete.

**Type consistency:**
- `WEEKLY_REVIEW_OUTPUT_DIR` is a `str` module var used consistently in `_latest_weekly_review()` and both routes.
- `_latest_weekly_review()` returns `str | None` and is called in both `_housekeeping_context()` and the `weekly_review` route.
- `create_session()` returns `SessionResult` — `.ok`, `.already_running`, `.session_id` properties used consistently with existing patterns in the file.
- `get_capabilities()` return value passed to template as `capabilities` — accessed in template as `capabilities.weekly_platform_review.enabled`, matching the structure returned by `capabilities.py`.
