# Housekeeping Reliability, Blog Draft Management & Research Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the housekeeping scheduler's timezone bug and silent-stall blind spot, give the housekeeping page an honest at-a-glance health status, let the user list/delete accumulated blog drafts, and surface the weekly research findings that currently have no UI at all.

**Architecture:** All changes are confined to the IkeOS Flask app (`/mnt/c/Server/projects/ikeos`) — routes stay thin, services stay framework-free, vault/file I/O stays in services. No changes to the `claude-config` repo or the `/blog` skill in this plan (those are tracked separately as vault ideas — see "Out of scope" below).

**Tech Stack:** Python 3.11, Flask, APScheduler, `zoneinfo`/`tzdata`, python-frontmatter, Jinja2, vanilla CSS/JS, pytest.

**Out of scope (filed as vault ideas for a `claude-config` session, not this plan):**
- The `/blog` skill's missing/failing capture-API call to create the "Blog draft ready" vault note (root cause of last week's stalled housekeeping session).
- A generation-time dedup guard in the `/blog` skill so it doesn't create a second draft for a week that already has one (this plan's Task 3 gives the user a manual list+delete escape hatch instead, which covers the immediate need).

---

## File Structure

| File | Responsibility |
|---|---|
| `app/services/scheduler.py` (modify) | Make the cron trigger timezone-aware (America/Toronto) instead of running against the container's UTC clock |
| `requirements.txt` (modify) | Add `tzdata` so `zoneinfo` resolves IANA zones regardless of OS tzdata availability |
| `app/services/session_client.py` (modify) | Add `list_active_session_names()` — lets the housekeeping page detect a stalled run without a specific session_id |
| `app/routes/housekeeping.py` (modify) | Add `_run_state()` health computation; wire in blog-drafts list/delete routes, research-findings route, optional-filename draft editor route |
| `app/services/blog_drafts.py` (modify) | Add `list_drafts()`, `delete_draft()`; extend `read_draft_bundle()` to accept an optional specific filename |
| `app/services/research_findings.py` (create) | Read `research-summaries-latest.json` from the mounted claude-config library, mirroring `reflection.py`'s existing pattern |
| `app/templates/blog_drafts.html` (create) | List all weekly drafts with delete buttons |
| `app/templates/research_findings.html` (create) | Preview raw weekly research findings |
| `app/templates/housekeeping.html` (modify) | Full redesign: run-status bar, outputs grid, two-column config, existing tasks/recent-runs sections restyled |
| `app/templates/base.html` (modify) | Expand the Housekeeping subnav with Blog Drafts / Research Findings links |
| `app/static/style.css` (modify) | New CSS for the status bar, outputs grid, config grid, generic panel class, findings cards |

---

## Task 1: Scheduler Timezone Fix

**Files:**
- Modify: `app/services/scheduler.py`
- Modify: `requirements.txt`
- Test: `tests/test_scheduler.py`

The scheduler's `CronTrigger` currently runs against the container's system clock, which is UTC with no `TZ` configured. A schedule of `hour=16` (meant to mean 4pm Eastern) actually fires at noon Eastern. Fix: make the trigger explicitly timezone-aware using `zoneinfo`, independent of the container's OS-level timezone setting (`python:3.11-slim` doesn't ship `tzdata`, so we add the `tzdata` PyPI package, which `zoneinfo` automatically falls back to).

- [ ] **Step 1: Add the `tzdata` dependency**

Edit `requirements.txt`:

```
flask>=3.0
python-dotenv>=1.0
python-frontmatter>=1.1
gunicorn>=21.2
pytest>=8.0
pytest-mock>=3.0
requests>=2.31
APScheduler>=3.10
tzdata>=2024.1
obsidiantools==0.11.0
rich>=13.0
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_scheduler.py` (append after the existing `next_run` tests, before the "trigger_now works regardless of leader election" section):

```python
def test_compute_next_run_uses_toronto_timezone_not_utc(sched_vault, monkeypatch):
    """hour=16 must mean 4pm Toronto time, not 4pm UTC — this was the original bug:
    a schedule meant to fire at 4pm Eastern was actually firing at noon Eastern
    because CronTrigger ran against the container's UTC clock."""
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    from app.services.scheduler import update_config, get_config_with_next_run
    from zoneinfo import ZoneInfo
    from datetime import datetime

    update_config({"enabled": True, "day_of_week": "fri", "hour": 16, "minute": 0})
    result = get_config_with_next_run()
    next_run_dt = datetime.fromisoformat(result["next_run"])
    assert next_run_dt.hour == 16
    assert next_run_dt.tzinfo is not None
    toronto_now = datetime.now(ZoneInfo("America/Toronto"))
    assert next_run_dt.utcoffset() == toronto_now.utcoffset()


def test_trigger_now_last_triggered_is_timezone_aware(sched_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(sched_vault))
    ok_result = SessionResult(session_id="sess-tz")
    with patch("app.services.scheduler.run_scheduled_housekeeping", return_value=ok_result):
        from app.services.scheduler import trigger_now, get_config
        trigger_now()
    config = get_config()
    from datetime import datetime
    dt = datetime.fromisoformat(config["last_triggered"])
    assert dt.tzinfo is not None
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_scheduler.py -k "timezone" -v`
Expected: FAIL — `next_run_dt.tzinfo` is `None` (the current implementation uses naive `datetime.now()`).

- [ ] **Step 4: Make the scheduler timezone-aware**

Edit `app/services/scheduler.py`. Add the import and constant near the top (after the existing imports, before `_VALID_DAYS`):

```python
from zoneinfo import ZoneInfo
```

```python
_TZ = ZoneInfo("America/Toronto")
```

Replace `_compute_next_run`:

```python
def _compute_next_run(config: dict, now: datetime | None = None) -> str | None:
    """Analytically compute the next fire time from cron fields alone.

    Deliberately independent of any live APScheduler instance so every
    worker process — leader or not — computes the identical value from the
    same on-disk config. This is what makes GET /housekeeping/schedule
    consistent regardless of which worker answers it.
    """
    if not config.get("enabled"):
        return None
    trigger = CronTrigger(
        day_of_week=config["day_of_week"],
        hour=config["hour"],
        minute=config["minute"],
        timezone=_TZ,
    )
    next_fire = trigger.get_next_fire_time(None, now or datetime.now(_TZ))
    return next_fire.isoformat(timespec="seconds") if next_fire else None
```

In `_apply_to_live_scheduler`, add `timezone=_TZ` to the `reschedule_job` call:

```python
    _scheduler.reschedule_job(
        "housekeeping",
        trigger="cron",
        day_of_week=config["day_of_week"],
        hour=config["hour"],
        minute=config["minute"],
        timezone=_TZ,
    )
```

In `trigger_now`, make `last_triggered` timezone-aware:

```python
    config["last_triggered"] = datetime.now(_TZ).isoformat(timespec="seconds")
```

In `start()`, add `timezone=_TZ` to the initial `add_job` call:

```python
    _scheduler.add_job(
        _job,
        "cron",
        id="housekeeping",
        day_of_week=config["day_of_week"],
        hour=config["hour"],
        minute=config["minute"],
        timezone=_TZ,
    )
```

- [ ] **Step 5: Rebuild and run the tests**

Run: `docker.exe compose up --build -d ikeos` then `docker exec ikeos pytest tests/test_scheduler.py -v`
Expected: All tests PASS, including the two new ones. The `tzdata` package must install cleanly during the build — if `pip install` fails on `tzdata`, check the version pin against what's on PyPI.

- [ ] **Step 6: Commit**

```bash
git add app/services/scheduler.py requirements.txt tests/test_scheduler.py
git commit -m "fix: make housekeeping scheduler timezone-aware (America/Toronto)

The cron trigger ran against the container's UTC clock with no TZ
configured, so hour=16 (meant as 4pm Eastern) fired at noon Eastern.
zoneinfo + the tzdata package make this explicit and independent of
the container's OS-level timezone setting."
```

---

## Task 2: Housekeeping Run-State Visibility (Stalled-Run Detection)

**Files:**
- Modify: `app/services/session_client.py`
- Modify: `app/routes/housekeeping.py`
- Test: `tests/test_session_client.py`
- Test: `tests/test_housekeeping.py`

Last week's housekeeping session was triggered (the scheduler wrote `last_triggered`) but never completed — no heartbeat update, no surviving session — and the housekeeping page gave zero indication anything was wrong. This task adds a `_run_state()` computation with five states (`running`, `ok`, `failed`, `stalled`, `overdue`, `never`) so that silent stalls are visible.

- [ ] **Step 1: Write the failing test for `list_active_session_names`**

Add to `tests/test_session_client.py` (after the `get_session_status` tests):

```python
from app.services.session_client import list_active_session_names


def test_list_active_session_names_filters_by_prefix_and_status(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = [
        {"name": "housekeeping-20260721", "status": "active"},
        {"name": "housekeeping-20260714", "status": "idle"},
        {"name": "blog-publish-abc", "status": "active"},
    ]
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        names = list_active_session_names("housekeeping-")
    assert names == ["housekeeping-20260721"]


def test_list_active_session_names_empty_when_none_match(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = [{"name": "blog-publish-abc", "status": "active"}]
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        assert list_active_session_names("housekeeping-") == []


def test_list_active_session_names_empty_when_unreachable(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.get",
               side_effect=req_lib.RequestException("down")):
        assert list_active_session_names("housekeeping-") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker exec ikeos pytest tests/test_session_client.py -k "list_active_session_names" -v`
Expected: FAIL with `ImportError: cannot import name 'list_active_session_names'`.

- [ ] **Step 3: Implement `list_active_session_names`**

Edit `app/services/session_client.py`. Add after `get_session_status`:

```python
def list_active_session_names(prefix: str) -> list[str]:
    """Names of currently-active sessions whose name starts with `prefix`."""
    try:
        resp = requests.get(f"{session_manager_url()}/sessions", timeout=3)
    except requests.RequestException:
        return []
    if not resp.ok:
        return []
    sessions = resp.json()
    return [
        s.get("name", "") for s in sessions
        if s.get("status") == "active" and s.get("name", "").startswith(prefix)
    ]
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker exec ikeos pytest tests/test_session_client.py -k "list_active_session_names" -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Write the failing tests for `_run_state`**

Add to `tests/test_housekeeping.py` (near the top-level imports, add `from datetime import datetime, timedelta, timezone` if not already present; add these tests in a new section near the other route-adjacent unit tests):

```python
from app.routes.housekeeping import _run_state


def test_run_state_never_when_nothing_recorded():
    with patch("app.routes.housekeeping.list_active_session_names", return_value=[]):
        state, label, headline = _run_state({"last_triggered": None}, {"last_run": None})
    assert state == "never"
    assert label == "Never run"


def test_run_state_running_when_active_session_exists():
    with patch("app.routes.housekeeping.list_active_session_names",
               return_value=["housekeeping-20260721"]):
        state, label, headline = _run_state(
            {"last_triggered": "2026-07-21T16:00:00-04:00"},
            {"last_run": None},
        )
    assert state == "running"
    assert label == "Running"


def test_run_state_stalled_when_triggered_but_never_completed():
    old_trigger = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with patch("app.routes.housekeeping.list_active_session_names", return_value=[]):
        state, label, headline = _run_state({"last_triggered": old_trigger}, {"last_run": None})
    assert state == "stalled"
    assert "never reported completion" in headline


def test_run_state_not_stalled_within_grace_window():
    recent_trigger = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with patch("app.routes.housekeeping.list_active_session_names", return_value=[]):
        state, label, headline = _run_state({"last_triggered": recent_trigger}, {"last_run": None})
    assert state != "stalled"


def test_run_state_failed_when_tasks_failed_nonzero():
    with patch("app.routes.housekeeping.list_active_session_names", return_value=[]):
        state, label, headline = _run_state(
            {"last_triggered": "2026-07-16T14:00:00Z"},
            {"last_run": "2026-07-16T14:17:16Z", "tasks_failed": "2"},
        )
    assert state == "failed"
    assert label == "Attention"


def test_run_state_overdue_when_last_run_old():
    old_run = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    with patch("app.routes.housekeeping.list_active_session_names", return_value=[]):
        state, label, headline = _run_state(
            {"last_triggered": old_run},
            {"last_run": old_run, "tasks_failed": "0"},
        )
    assert state == "overdue"


def test_run_state_ok_when_recent_and_no_failures():
    recent_run = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with patch("app.routes.housekeeping.list_active_session_names", return_value=[]):
        state, label, headline = _run_state(
            {"last_triggered": recent_run},
            {"last_run": recent_run, "tasks_failed": "0"},
        )
    assert state == "ok"
    assert label == "Healthy"
```

- [ ] **Step 6: Run to verify they fail**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -k "run_state" -v`
Expected: FAIL with `ImportError: cannot import name '_run_state'`.

- [ ] **Step 7: Implement `_run_state` and wire it into the context**

Edit `app/routes/housekeeping.py`. Change the datetime import at the top:

```python
from datetime import datetime, timedelta, timezone
```

Add the `session_client` import (extend the existing import line):

```python
from app.services.session_client import get_session_status, list_active_session_names
```

Add these constants and functions after `_widget_status` (keep `_widget_status` as-is — it's still used by `hk_status`):

```python
_STALL_THRESHOLD_MINUTES = 45
_OVERDUE_DAYS = 9


def _parse_dt(value: str | None) -> datetime | None:
    if not value or value == "null":
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _run_state(schedule: dict, heartbeat: dict) -> tuple[str, str, str]:
    """Returns (state, label, headline) describing overall housekeeping health."""
    if list_active_session_names("housekeeping-"):
        return "running", "Running", "Housekeeping is running now…"

    triggered_dt = _parse_dt(schedule.get("last_triggered"))
    last_run_dt = _parse_dt(heartbeat.get("last_run"))

    if triggered_dt is None and last_run_dt is None:
        return "never", "Never run", "Housekeeping has not run yet."

    if triggered_dt is not None and (last_run_dt is None or last_run_dt < triggered_dt):
        elapsed = datetime.now(timezone.utc) - triggered_dt
        if elapsed > timedelta(minutes=_STALL_THRESHOLD_MINUTES):
            return "stalled", "Stalled", (
                f"Triggered {_age_str(schedule.get('last_triggered'))} but never reported "
                f"completion — check session logs."
            )

    if heartbeat.get("tasks_failed", "0") not in ("0", 0):
        n = heartbeat.get("tasks_failed")
        return "failed", "Attention", f"{n} task(s) failed on the last run ({_age_str(heartbeat.get('last_run'))})."

    if last_run_dt is not None:
        if (datetime.now(timezone.utc) - last_run_dt).days > _OVERDUE_DAYS:
            return "overdue", "Overdue", f"No successful run since {_age_str(heartbeat.get('last_run'))}."

    return "ok", "Healthy", f"Last run completed successfully — {_age_str(heartbeat.get('last_run'))}."
```

Update `_housekeeping_context` to include the new fields:

```python
def _housekeeping_context() -> dict:
    tasks = read_housekeeping_tasks()
    heartbeat = read_housekeeping_heartbeat(project_slug())
    schedule = get_config_with_next_run()
    run_state, run_state_label, run_state_headline = _run_state(schedule, heartbeat)
    findings = get_research_findings()
    return dict(
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
        run_state=run_state,
        run_state_label=run_state_label,
        run_state_headline=run_state_headline,
        schedule=schedule,
        capture_token=CAPTURE_TOKEN,
        blog_draft=latest_draft_name(),
        weekly_review_file=latest_review_name(),
        capabilities=get_capabilities(),
        recent_runs=read_events_by_type("housekeeping.run", limit=10),
        research_generated_at=findings["generated_at"] if findings else None,
        research_age_str=_age_str(findings["generated_at"]) if findings else None,
        research_source_count=len(findings["summaries"]) if findings else 0,
    )
```

(`get_research_findings` is added in Task 4 — this task's tests only exercise `_run_state` directly, so the import doesn't need to exist yet for Steps 1–6 above to pass; add the import now so the file is self-consistent going into Task 4:)

```python
from app.services.research_findings import get_research_findings
```

If Task 4 hasn't been done yet in your working tree, this import will fail at collection time — do Task 4's Step 3 (create `app/services/research_findings.py`) before running the full test suite, or run `pytest tests/test_housekeeping.py -k run_state` in isolation for now.

- [ ] **Step 8: Run to verify they pass**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -k "run_state" -v`
Expected: PASS (7 passed)

- [ ] **Step 9: Commit**

```bash
git add app/services/session_client.py app/routes/housekeeping.py tests/test_session_client.py tests/test_housekeeping.py
git commit -m "feat: detect stalled housekeeping runs

Last week a scheduled session was triggered but never completed, and
the housekeeping page gave no indication anything was wrong. _run_state()
computes running/ok/failed/stalled/overdue/never from the schedule,
heartbeat, and live session list so a silent stall is visible instead
of looking identical to a healthy idle state."
```

---

## Task 3: Blog Drafts List + Delete

**Files:**
- Modify: `app/services/blog_drafts.py`
- Modify: `app/routes/housekeeping.py`
- Create: `app/templates/blog_drafts.html`
- Test: `tests/test_blog_drafts.py`
- Test: `tests/test_housekeeping.py`

Duplicate weekly drafts accumulate silently because the editor only ever shows the single newest draft — older ones are invisible and un-deletable. This adds a list page and a delete action.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_blog_drafts.py` (after `test_save_draft_works_without_bluesky_file`):

```python
def test_read_draft_bundle_with_specific_filename(posts_dir):
    (posts_dir / "2026-06-01-weekly-draft.md").write_text("old", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("new", encoding="utf-8")
    bundle = blog_drafts.read_draft_bundle("2026-06-01-weekly-draft.md")
    assert bundle["filename"] == "2026-06-01-weekly-draft.md"
    assert bundle["content"] == "old"


def test_read_draft_bundle_specific_filename_not_found(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("new", encoding="utf-8")
    assert blog_drafts.read_draft_bundle("nonexistent-weekly-draft.md") is None


def test_list_drafts_newest_first_with_latest_flag(posts_dir):
    (posts_dir / "2026-06-01-weekly-draft.md").write_text("old", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("new", encoding="utf-8")
    drafts = blog_drafts.list_drafts()
    assert len(drafts) == 2
    assert drafts[0]["filename"] == "2026-07-01-weekly-draft.md"
    assert drafts[0]["is_latest"] is True
    assert drafts[1]["is_latest"] is False


def test_list_drafts_empty_when_no_dir(monkeypatch):
    monkeypatch.delenv("AIOS_BLOG_POSTS_DIR", raising=False)
    assert blog_drafts.list_drafts() == []


def test_delete_draft_removes_file_and_companion(posts_dir):
    (posts_dir / "2026-06-01-weekly-draft.md").write_text("old", encoding="utf-8")
    (posts_dir / "2026-06-01-weekly-bluesky.txt").write_text("sky", encoding="utf-8")
    assert blog_drafts.delete_draft("2026-06-01-weekly-draft.md") is True
    assert not (posts_dir / "2026-06-01-weekly-draft.md").exists()
    assert not (posts_dir / "2026-06-01-weekly-bluesky.txt").exists()


def test_delete_draft_missing_file_returns_false(posts_dir):
    assert blog_drafts.delete_draft("nonexistent-weekly-draft.md") is False


def test_delete_draft_rejects_path_traversal(posts_dir):
    assert blog_drafts.delete_draft("../outside-weekly-draft.md") is False


def test_delete_draft_rejects_non_draft_filename(posts_dir):
    (posts_dir / "2026-06-01-weekly.md").write_text("published", encoding="utf-8")
    assert blog_drafts.delete_draft("2026-06-01-weekly.md") is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker exec ikeos pytest tests/test_blog_drafts.py -k "list_drafts or delete_draft or specific_filename" -v`
Expected: FAIL — `list_drafts`/`delete_draft` don't exist; `read_draft_bundle` doesn't accept an argument.

- [ ] **Step 3: Implement the service additions**

Edit `app/services/blog_drafts.py`. Add after `latest_draft_paths`:

```python
def draft_paths(filename: str) -> tuple[Path | None, Path | None]:
    """Return (draft_path, bluesky_path) for a specific draft filename."""
    posts = _posts_dir()
    if not posts or not posts.exists():
        return None, None
    if "/" in filename or "\\" in filename or ".." in filename:
        return None, None
    draft = posts / filename
    if not draft.exists() or not draft.name.endswith("-weekly-draft.md"):
        return None, None
    bluesky = draft.with_name(draft.stem.replace("-weekly-draft", "-weekly-bluesky") + ".txt")
    return draft, bluesky if bluesky.exists() else None
```

Replace `read_draft_bundle` to accept an optional filename:

```python
def read_draft_bundle(filename: str | None = None) -> dict | None:
    """Return dict with filename, content, bluesky_text, bluesky_filename for the given
    draft filename, or the latest draft if filename is omitted; None if not found."""
    draft, bluesky = draft_paths(filename) if filename else latest_draft_paths()
    if not draft:
        return None
    return {
        "filename": draft.name,
        "content": draft.read_text(encoding="utf-8"),
        "bluesky_text": bluesky.read_text(encoding="utf-8") if bluesky else "",
        "bluesky_filename": bluesky.name if bluesky else "",
    }
```

Add `list_drafts` and `delete_draft` at the end of the file:

```python
def list_drafts() -> list[dict]:
    """All weekly drafts, newest first, each flagged with whether it's the current latest."""
    posts = _posts_dir()
    if not posts or not posts.exists():
        return []
    drafts = sorted(posts.glob("*-weekly-draft.md"), reverse=True)
    return [
        {"filename": draft.name, "generated_at": draft.name[:10], "is_latest": i == 0}
        for i, draft in enumerate(drafts)
    ]


def delete_draft(filename: str) -> bool:
    """Delete a draft (and its companion bluesky file, if present). Returns True if deleted."""
    posts = _posts_dir()
    if not posts or not posts.exists():
        return False
    if "/" in filename or "\\" in filename or ".." in filename:
        return False
    if not filename.endswith("-weekly-draft.md"):
        return False
    draft = posts / filename
    if not draft.exists():
        return False
    draft.unlink()
    bluesky = draft.with_name(draft.stem.replace("-weekly-draft", "-weekly-bluesky") + ".txt")
    if bluesky.exists():
        bluesky.unlink()
    return True
```

- [ ] **Step 4: Run to verify they pass**

Run: `docker exec ikeos pytest tests/test_blog_drafts.py -v`
Expected: All PASS (previous tests plus 8 new ones).

- [ ] **Step 5: Write the failing route tests**

Add to `tests/test_housekeeping.py` (near the other blog-draft route tests):

```python
def test_blog_drafts_list_route_renders(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("body", encoding="utf-8")
    resp = client.get("/housekeeping/blog-drafts")
    assert resp.status_code == 200
    assert b"2026-07-01-weekly-draft.md" in resp.data


def test_blog_draft_delete_requires_token(client, monkeypatch, tmp_path):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("body", encoding="utf-8")
    resp = client.post("/housekeeping/blog-drafts/2026-07-01-weekly-draft.md/delete")
    assert resp.status_code == 401


def test_blog_draft_delete_success(client, monkeypatch, tmp_path):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("body", encoding="utf-8")
    resp = client.post("/housekeeping/blog-drafts/2026-07-01-weekly-draft.md/delete",
                        headers={"X-Capture-Token": "tok"})
    assert resp.status_code == 200
    assert not (tmp_path / "2026-07-01-weekly-draft.md").exists()


def test_blog_draft_delete_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    resp = client.post("/housekeeping/blog-drafts/nonexistent-weekly-draft.md/delete",
                        headers={"X-Capture-Token": "tok"})
    assert resp.status_code == 404


def test_blog_draft_editor_with_specific_filename(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-06-01-weekly-draft.md").write_text("old content", encoding="utf-8")
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("new content", encoding="utf-8")
    resp = client.get("/housekeeping/blog-draft/2026-06-01-weekly-draft.md")
    assert resp.status_code == 200
    assert b"old content" in resp.data
```

- [ ] **Step 6: Run to verify they fail**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -k "blog_drafts_list or blog_draft_delete or editor_with_specific" -v`
Expected: FAIL — 404s, routes don't exist yet.

- [ ] **Step 7: Add the routes**

Edit `app/routes/housekeeping.py`. Replace the blog_drafts import line:

```python
from app.services.blog_drafts import delete_draft, latest_draft_name, list_drafts, read_draft_bundle, save_draft
```

Replace the `blog_draft_editor` route to accept an optional filename:

```python
@bp.route("/housekeeping/blog-draft")
@bp.route("/housekeeping/blog-draft/<filename>")
def blog_draft_editor(filename: str | None = None):
    bundle = read_draft_bundle(filename)
    if not bundle:
        return render_template("housekeeping.html", **_housekeeping_context(), no_draft=True)
    return render_template(
        "blog_draft.html",
        filename=bundle["filename"],
        content=bundle["content"],
        bluesky_text=bundle["bluesky_text"],
        bluesky_filename=bundle["bluesky_filename"],
        capture_token=CAPTURE_TOKEN,
    )
```

Add these routes after `blog_draft_editor`:

```python
@bp.route("/housekeeping/blog-drafts")
def blog_drafts_list():
    return render_template("blog_drafts.html", drafts=list_drafts(), capture_token=CAPTURE_TOKEN)


@bp.route("/housekeeping/blog-drafts/<filename>/delete", methods=["POST"])
@require_capture_token
def blog_draft_delete(filename: str):
    if not delete_draft(filename):
        return jsonify({"error": "Draft not found"}), 404
    return jsonify({"ok": True}), 200
```

- [ ] **Step 8: Create the list template**

Create `app/templates/blog_drafts.html`:

```html
{% extends "base.html" %}
{% block title %}Blog Drafts{% endblock %}

{% block content %}
<div class="settings-page">

  <header class="page-header">
    <span class="ike-eyebrow"><a href="{{ url_for('housekeeping.index') }}">Housekeeping</a> / Blog Drafts</span>
    <h1>Blog Drafts</h1>
    <p class="page-subtitle">All weekly drafts generated by housekeeping — {{ drafts | length }} total.</p>
  </header>

  <div style="margin-bottom:20px;">
    <a href="{{ url_for('housekeeping.index') }}" class="pill">&larr; Housekeeping</a>
  </div>

  {% if drafts %}
  <div class="hk-table-wrap">
    <table class="hk-table">
      <thead>
        <tr>
          <th class="hk-col-name">Filename</th>
          <th class="hk-col-status">Status</th>
          <th class="hk-col-date">Generated</th>
          <th class="hk-col-actions">Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for d in drafts %}
        <tr>
          <td class="hk-name">{{ d.filename }}</td>
          <td><span class="hk-pill {{ 'hk-pill--ok' if d.is_latest else 'hk-pill--disabled' }}">
            {{ 'Latest' if d.is_latest else 'Archived' }}
          </span></td>
          <td class="hk-date">{{ d.generated_at }}</td>
          <td class="hk-actions">
            <a class="pill" href="{{ url_for('housekeeping.blog_draft_editor', filename=d.filename) }}">Open</a>
            <button class="pill pill-danger" onclick="deleteDraft({{ d.filename | tojson | forceescape }}, this)">Delete</button>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <p class="empty">No drafts yet.</p>
  {% endif %}

</div>

<script>
const _captureToken = {{ capture_token | tojson }};
async function deleteDraft(filename, btn) {
  if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;
  btn.disabled = true;
  try {
    const resp = await fetch(`/housekeeping/blog-drafts/${encodeURIComponent(filename)}/delete`,
                             {method: 'POST', headers: {'X-Capture-Token': _captureToken}});
    if (resp.ok) { location.reload(); }
    else { btn.disabled = false; alert('Failed to delete draft.'); }
  } catch (e) { btn.disabled = false; alert('Network error — could not delete draft.'); }
}
</script>
{% endblock %}
```

- [ ] **Step 9: Run to verify all pass**

Run: `docker.exe compose up --build -d ikeos` then `docker exec ikeos pytest tests/test_housekeeping.py tests/test_blog_drafts.py -v`
Expected: All PASS.

- [ ] **Step 10: Commit**

```bash
git add app/services/blog_drafts.py app/routes/housekeeping.py app/templates/blog_drafts.html tests/test_blog_drafts.py tests/test_housekeeping.py
git commit -m "feat: list and delete blog drafts

The editor only ever showed the single newest draft, so duplicates
from repeated /blog skill runs accumulated invisibly. Adds a list
page (/housekeeping/blog-drafts) and a delete action, and lets the
editor open any specific draft by filename, not just the latest."
```

---

## Task 4: Research Findings Preview Page

**Files:**
- Create: `app/services/research_findings.py`
- Modify: `app/routes/housekeeping.py`
- Create: `app/templates/research_findings.html`
- Test: `tests/test_research_findings.py`
- Test: `tests/test_housekeeping.py`

The weekly `deep-research-weekly` cycle produces `research-summaries-latest.json` (mounted read-only into the container at `${CLAUDE_CONFIG_DIR}/library/`), but nothing in IkeOS ever displays it — the only research-adjacent page (`/research-sources`) manages source URLs, not findings. This mirrors the existing `reflection.py` pattern for reading claude-config library files.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_research_findings.py`:

```python
import json
import pytest
from unittest.mock import patch
from app.services import research_findings as rf


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "library").mkdir()
    return tmp_path


def test_get_research_findings_none_when_env_not_set():
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", ""):
        assert rf.get_research_findings() is None


def test_get_research_findings_none_when_file_missing(config_dir):
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", str(config_dir)):
        assert rf.get_research_findings() is None


def test_get_research_findings_reads_file(config_dir):
    data = {
        "generated_at": "2026-07-16T14:00:00Z",
        "summaries": [
            {"url": "https://example.com", "label": "Example", "key_points": ["a"], "notable_updates": ["b"]}
        ],
    }
    (config_dir / "library" / "research-summaries-latest.json").write_text(json.dumps(data), encoding="utf-8")
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", str(config_dir)):
        result = rf.get_research_findings()
    assert result["generated_at"] == "2026-07-16T14:00:00Z"
    assert len(result["summaries"]) == 1
    assert result["summaries"][0]["label"] == "Example"


def test_get_research_findings_none_on_malformed_json(config_dir):
    (config_dir / "library" / "research-summaries-latest.json").write_text("{not valid json", encoding="utf-8")
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", str(config_dir)):
        assert rf.get_research_findings() is None


def test_get_research_findings_none_when_root_not_dict(config_dir):
    (config_dir / "library" / "research-summaries-latest.json").write_text("[1, 2, 3]", encoding="utf-8")
    with patch("app.services.research_findings.CLAUDE_CONFIG_DIR", str(config_dir)):
        assert rf.get_research_findings() is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `docker exec ikeos pytest tests/test_research_findings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.research_findings'`.

- [ ] **Step 3: Create the service**

Create `app/services/research_findings.py`:

```python
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CLAUDE_CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR", "")


def get_research_findings() -> dict | None:
    """Return the latest weekly research findings, or None if unavailable.

    Returns a dict with `generated_at` (str) and `summaries` (list of
    {url, label, key_points, notable_updates}) — a direct pass-through of
    research-summaries-latest.json's shape.
    """
    if not CLAUDE_CONFIG_DIR:
        return None
    path = Path(CLAUDE_CONFIG_DIR) / "library" / "research-summaries-latest.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("unexpected JSON root type")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to read research findings file: %s", exc)
        return None
    return {
        "generated_at": data.get("generated_at"),
        "summaries": data.get("summaries", []),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `docker exec ikeos pytest tests/test_research_findings.py -v`
Expected: All PASS (5 passed).

- [ ] **Step 5: Write the failing route test**

Add to `tests/test_housekeeping.py`:

```python
def test_research_findings_route_renders(client):
    fake_findings = {
        "generated_at": "2026-07-16T14:00:00Z",
        "summaries": [{"url": "https://example.com", "label": "Example", "key_points": [], "notable_updates": ["Something happened"]}],
    }
    with patch("app.routes.housekeeping.get_research_findings", return_value=fake_findings):
        resp = client.get("/housekeeping/research-findings")
    assert resp.status_code == 200
    assert b"Example" in resp.data
    assert b"Something happened" in resp.data


def test_research_findings_route_handles_none(client):
    with patch("app.routes.housekeeping.get_research_findings", return_value=None):
        resp = client.get("/housekeeping/research-findings")
    assert resp.status_code == 200
    assert b"No research findings yet" in resp.data
```

- [ ] **Step 6: Run to verify they fail**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -k "research_findings_route" -v`
Expected: FAIL — 404, route doesn't exist.

- [ ] **Step 7: Add the route** (also add the import needed by Task 2's `_housekeeping_context`)

Edit `app/routes/housekeeping.py`. Add the import near the other service imports:

```python
from app.services.research_findings import get_research_findings
```

Add the route after `blog_drafts_list`/`blog_draft_delete`:

```python
@bp.route("/housekeeping/research-findings")
def research_findings():
    findings = get_research_findings()
    if findings is None:
        return render_template("research_findings.html", generated_at=None, summaries=[])
    return render_template(
        "research_findings.html",
        generated_at=findings["generated_at"],
        summaries=findings["summaries"],
    )
```

- [ ] **Step 8: Create the template**

Create `app/templates/research_findings.html`:

```html
{% extends "base.html" %}
{% block title %}Research Findings{% endblock %}

{% block content %}
<div class="settings-page">

  <header class="page-header">
    <span class="ike-eyebrow"><a href="{{ url_for('housekeeping.index') }}">Housekeeping</a> / Research Findings</span>
    <h1>Research Findings</h1>
    <p class="page-subtitle">
      {% if generated_at %}Generated {{ generated_at }} · {{ summaries | length }} sources
      {% else %}No research run yet{% endif %}
    </p>
  </header>

  <div style="display:flex; gap:10px; align-items:center; margin-bottom:20px;">
    <a href="{{ url_for('housekeeping.index') }}" class="pill">&larr; Housekeeping</a>
    <a href="{{ url_for('research_sources.index') }}" class="pill">Manage Sources</a>
  </div>

  {% if summaries %}
  <div class="hk-findings-list">
    {% for s in summaries %}
    <article class="hk-panel hk-finding-card">
      <div class="hk-finding-card__head">
        <a href="{{ s.url }}" target="_blank" rel="noopener" class="hk-finding-card__label">{{ s.label }}</a>
        {% if s.notable_updates %}
        <span class="hk-pill hk-pill--due">{{ s.notable_updates | length }} notable</span>
        {% endif %}
      </div>
      {% if s.notable_updates %}
      <ul class="hk-finding-card__notable">
        {% for n in s.notable_updates %}<li>{{ n }}</li>{% endfor %}
      </ul>
      {% endif %}
      {% if s.key_points %}
      <details class="hk-finding-card__details">
        <summary>All key points ({{ s.key_points | length }})</summary>
        <ul>{% for k in s.key_points %}<li>{{ k }}</li>{% endfor %}</ul>
      </details>
      {% endif %}
    </article>
    {% endfor %}
  </div>
  {% else %}
  <div class="hk-widget">
    <p class="empty">No research findings yet.</p>
  </div>
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 9: Run the full test suite to verify everything passes together**

Run: `docker.exe compose up --build -d ikeos` then `docker exec ikeos pytest -v`
Expected: All PASS — this is also where Task 2's `_housekeeping_context` (which imports `get_research_findings`) becomes fully exercisable.

- [ ] **Step 10: Commit**

```bash
git add app/services/research_findings.py app/routes/housekeeping.py app/templates/research_findings.html tests/test_research_findings.py tests/test_housekeeping.py
git commit -m "feat: add research findings preview page

The weekly deep-research-weekly cycle produces research-summaries-latest.json
with zero UI surface — the only path to seeing it was manually running
/platform-review first. Adds /housekeeping/research-findings, mirroring
reflection.py's existing pattern for reading claude-config library files."
```

---

## Task 5: Housekeeping Page Redesign

**Files:**
- Modify: `app/templates/housekeeping.html`
- Modify: `app/templates/base.html`
- Modify: `app/static/style.css`
- Test: `tests/test_housekeeping.py`

Ties together Tasks 2–4: a run-status bar (the one thing the page must answer at a glance — "did it run, is anything broken"), an outputs grid linking to blog drafts / platform review / research findings, and a two-column configuration section. Also fixes three broken CSS references discovered during design review: `pill--housekeeping`/`pill--muted` and `.hk-status`/`.hk-status-ok`/`.hk-status-pending` were used in templates but never defined in CSS (badges rendered unstyled), and `.card` (Recent Runs section) was also undefined. Everything consolidates onto the one complete pill system already in CSS: `.hk-pill--*`.

- [ ] **Step 1: Write the failing context test**

Add to `tests/test_housekeeping.py`:

```python
def test_housekeeping_index_includes_run_state_and_outputs_context(client):
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    # run-state badge and outputs grid must render regardless of data availability
    assert b"hk-status-bar" in resp.data
    assert b"This Week" in resp.data
    assert b"Research Findings" in resp.data
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker exec ikeos pytest tests/test_housekeeping.py -k "run_state_and_outputs" -v`
Expected: FAIL — current template has no `hk-status-bar`/outputs grid.

- [ ] **Step 3: Replace `app/templates/housekeeping.html`**

Replace the entire file content with:

```html
{% extends "base.html" %}
{% block title %}Housekeeping{% endblock %}

{% block content %}
<div class="settings-page">

  <header class="page-header">
    <span class="ike-eyebrow">System</span>
    <h1>Housekeeping</h1>
    <p class="page-subtitle">Automated maintenance — reads task definitions from the claude-config vault.</p>
  </header>

  <!-- ── Run status bar — the one thing this page must answer at a glance ── -->
  <section class="hk-status-bar" id="hk-status-bar" data-state="{{ run_state }}">
    <span class="hk-status-bar__badge hk-status-bar__badge--{{ run_state }}" id="hk-status-badge">
      {{ run_state_label }}
    </span>
    <div class="hk-status-bar__detail">
      <div class="hk-status-bar__headline" id="hk-status-headline">{{ run_state_headline }}</div>
      <div class="hk-status-bar__meta">
        Next run: <span id="sched-next">
          {%- if schedule.next_run -%}{{ schedule.next_run }}
          {%- elif schedule.enabled -%}Calculating…
          {%- else -%}Disabled{%- endif -%}
        </span>
        &nbsp;·&nbsp;
        Last triggered: <span id="sched-last">{{ schedule.last_triggered or 'Never' }}</span>
      </div>
    </div>
    <div class="hk-status-bar__actions">
      <button class="pill pill-primary" id="hk-run-now-btn" onclick="runHousekeeping(this)">Run Now</button>
      <span class="hk-form-msg" id="hk-run-now-msg"></span>
    </div>
  </section>

  <!-- ── This week's outputs ── -->
  <section class="hk-outputs-section">
    <div class="ike-eyebrow">This Week's Outputs</div>
    <div class="hk-outputs-grid">

      <div class="hk-output-card">
        <div class="hk-output-card__title">
          <span class="hk-output-card__name">Blog Draft</span>
          <span class="hk-pill {{ 'hk-pill--ok' if blog_draft else 'hk-pill--uninitialized' }}">
            {{ 'Ready' if blog_draft else 'None yet' }}
          </span>
        </div>
        <p class="hk-output-card__body">
          {% if blog_draft %}{{ blog_draft }}{% else %}Generated weekly by the housekeeping run.{% endif %}
        </p>
        <div class="hk-output-card__footer">
          <a class="hk-output-card__link" href="{{ url_for('housekeeping.blog_draft_editor') }}">
            {{ 'Review draft →' if blog_draft else 'View editor →' }}
          </a>
          <a class="hk-output-card__link" href="{{ url_for('housekeeping.blog_drafts_list') }}">All drafts</a>
        </div>
      </div>

      <div class="hk-output-card">
        <div class="hk-output-card__title">
          <span class="hk-output-card__name">Platform Review</span>
          <span class="hk-pill {{ 'hk-pill--ok' if weekly_review_file else 'hk-pill--uninitialized' }}">
            {{ 'Ready' if weekly_review_file else 'None yet' }}
          </span>
        </div>
        <p class="hk-output-card__body">
          {% if weekly_review_file %}{{ weekly_review_file }}
          {% else %}Strategic ecosystem review — enable the capability below to run.{% endif %}
        </p>
        <div class="hk-output-card__footer">
          <a class="hk-output-card__link" href="{{ url_for('housekeeping.weekly_review') }}">
            {{ 'Read review →' if weekly_review_file else 'View page →' }}
          </a>
        </div>
      </div>

      <div class="hk-output-card">
        <div class="hk-output-card__title">
          <span class="hk-output-card__name">Research Findings</span>
          <span class="hk-pill {{ 'hk-pill--ok' if research_generated_at else 'hk-pill--uninitialized' }}">
            {{ research_age_str if research_generated_at else 'None yet' }}
          </span>
        </div>
        <p class="hk-output-card__body">
          {% if research_generated_at %}{{ research_source_count }} sources scanned
          {% else %}Weekly external research digest.{% endif %}
        </p>
        <div class="hk-output-card__footer">
          <a class="hk-output-card__link" href="{{ url_for('housekeeping.research_findings') }}">
            {{ 'View findings →' if research_generated_at else 'View page →' }}
          </a>
          <a class="hk-output-card__link" href="{{ url_for('research_sources.index') }}">Sources</a>
        </div>
      </div>

    </div>
  </section>

  <!-- ── Configuration: schedule + capabilities, side by side on wide screens ── -->
  <section class="hk-config-section">
    <div class="ike-eyebrow">Configuration</div>
    <div class="hk-config-grid">

      <div class="hk-schedule-card">
        <div class="hk-schedule-row">
          <label class="hk-schedule-toggle-label">
            <input type="checkbox" id="sched-enabled" {% if schedule.enabled %}checked{% endif %}>
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
          <input type="number" id="sched-hour" min="0" max="23" value="{{ schedule.hour }}" class="hk-time-input">
          <span class="hk-time-sep">:</span>
          <input type="number" id="sched-minute" min="0" max="59" value="{{ schedule.minute }}" class="hk-time-input">
        </div>
        <div class="hk-schedule-footer">
          <button class="pill pill-primary" id="sched-save" onclick="saveSchedule()" style="display:none">Save</button>
          <span class="hk-form-msg" id="sched-msg"></span>
        </div>
      </div>

      <div class="hk-schedule-card hk-capabilities-card">
        {% for name, cap in capabilities.items() %}
        <div class="hk-schedule-row" style="justify-content: space-between; align-items: center;" id="cap-card-{{ name }}">
          <div>
            <strong>{{ name | replace('_', ' ') | title }}</strong>
            <p class="hk-schedule-meta" style="margin: 2px 0 0;">{{ cap.description }}</p>
          </div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <span class="hk-pill {% if cap.enabled %}hk-pill--ok{% else %}hk-pill--disabled{% endif %}"
                  id="cap-status-{{ name }}">
              {{ 'ENABLED' if cap.enabled else 'DISABLED' }}
            </span>
            <button class="pill"
                    onclick="toggleCapability({{ name | tojson | forceescape }}, {{ (not cap.enabled) | tojson | forceescape }})"
                    id="cap-btn-{{ name }}">
              {{ 'Disable' if cap.enabled else 'Enable' }}
            </button>
          </div>
        </div>
        <div class="hk-form-msg" id="cap-msg-{{ name }}"></div>
        {% endfor %}
      </div>

    </div>
  </section>

  <!-- ── Tasks ── -->
  <section>
    <div class="ike-eyebrow">Tasks <span class="eyebrow-count">/ {{ tasks | length }}</span></div>
    {% if tasks %}
    <div class="hk-table-wrap">
      <table class="hk-table">
        <thead>
          <tr>
            <th class="hk-col-name">Name</th>
            <th class="hk-col-interval">Interval</th>
            <th class="hk-col-status">Status</th>
            <th class="hk-col-date">Last Run</th>
            <th class="hk-col-date">Next Due</th>
            <th class="hk-col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for task in tasks %}
          <tr>
            <td class="hk-name">{{ task.title }}</td>
            <td class="hk-interval">{{ task.interval }}</td>
            <td><span class="hk-pill hk-pill--{{ task.status }}">{{ task.status }}</span></td>
            <td class="hk-date">{{ task.last_run if task.last_run and task.last_run != 'null' else '—' }}</td>
            <td class="hk-date">{{ task.next_run or '—' }}</td>
            <td class="hk-actions">
              <button class="pill" onclick="toggleTask({{ task.filename | tojson | forceescape }}, this)"
                      data-enabled="{{ task.enabled | string | lower }}">
                {{ 'Disable' if (task.enabled | string | lower) == 'true' else 'Enable' }}
              </button>
              <button class="pill" onclick="resetTask({{ task.filename | tojson | forceescape }}, this)">Reset</button>
              <button class="pill pill-primary-filled" onclick="runTask({{ task.filename | tojson | forceescape }}, this)">Run</button>
              <button class="pill pill-danger" onclick="deleteTask({{ task.filename | tojson | forceescape }}, this)">Delete</button>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <p class="empty">No tasks defined yet. Add one below.</p>
    {% endif %}

    <details class="hk-add-details">
      <summary class="hk-add-summary">+ Add task</summary>
      <form class="hk-add-form" id="addTaskForm">
        <div class="hk-form-row">
          <label for="hk-title">Title</label>
          <input type="text" id="hk-title" name="title" required placeholder="e.g. Prune stale vault entries">
        </div>
        <div class="hk-form-row">
          <label for="hk-interval">Interval</label>
          <select id="hk-interval" name="interval">
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
            <option value="annually">Annually</option>
          </select>
        </div>
        <div class="hk-form-row">
          <label for="hk-success">Success Definition</label>
          <textarea id="hk-success" name="success_definition" required rows="3"
                    placeholder="Describe what success looks like — passed to the judge subagent."></textarea>
        </div>
        <div class="hk-form-footer">
          <button type="submit" class="pill pill-primary-filled">Add Task</button>
          <span class="hk-form-msg" id="addTaskMsg"></span>
        </div>
      </form>
    </details>
  </section>

  <!-- ── Recent runs ── -->
  {% if recent_runs %}
  <section class="hk-panel hk-recent-runs">
    <div class="ike-eyebrow">Recent Runs</div>
    <table class="hk-table" style="margin-top: var(--space-4);">
      <thead>
        <tr><th>Time</th><th>Trigger</th><th>Run</th><th>Failed</th><th>Skipped</th></tr>
      </thead>
      <tbody>
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
          <td colspan="5" style="padding:0 0.5rem 0.5rem 1.5rem; border-top:0">
            <details{% if (run.tasks_failed | default(0) | int) > 0 %} open{% endif %}>
              <summary style="cursor:pointer; color:var(--text-tertiary); font-size:0.85rem">
                task detail ({{ results | length }})
              </summary>
              <ul style="margin:0.4rem 0 0 1rem; padding:0; list-style:none; font-size:0.85rem; font-family:var(--font-mono)">
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
      </tbody>
    </table>
  </section>
  {% endif %}

</div>

<script>
const _captureToken = {{ capture_token | tojson }};

// ── Task actions ──
async function toggleTask(filename, btn) {
  btn.disabled = true;
  try {
    const resp = await fetch(`/housekeeping/tasks/${encodeURIComponent(filename)}/toggle`, {method: 'POST'});
    if (resp.ok) { location.reload(); } else { btn.disabled = false; alert('Failed to toggle task.'); }
  } catch (e) { btn.disabled = false; alert('Network error — could not toggle task.'); }
}
async function resetTask(filename, btn) {
  btn.disabled = true;
  try {
    const resp = await fetch(`/housekeeping/tasks/${encodeURIComponent(filename)}/reset`, {method: 'POST'});
    if (resp.ok) { location.reload(); } else { btn.disabled = false; alert('Failed to reset timer.'); }
  } catch (e) { btn.disabled = false; alert('Network error — could not reset task.'); }
}
async function runTask(filename, btn) {
  btn.disabled = true; btn.textContent = '…';
  try {
    const resp = await fetch(`/housekeeping/tasks/${encodeURIComponent(filename)}/run`, {method: 'POST'});
    if (resp.ok) {
      btn.textContent = 'Launched ↗';
      btn.onclick = () => window.location.href = '/agents';
      btn.disabled = false;
    } else { btn.textContent = 'Run'; btn.disabled = false; alert('Failed to launch session.'); }
  } catch (e) { btn.textContent = 'Run'; btn.disabled = false; alert('Network error — could not launch session.'); }
}
async function deleteTask(filename, btn) {
  if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;
  btn.disabled = true;
  try {
    const resp = await fetch(`/housekeeping/tasks/${encodeURIComponent(filename)}/delete`,
                             {method: 'POST', headers: {'X-Capture-Token': _captureToken}});
    if (resp.ok) { location.reload(); } else { btn.disabled = false; alert('Failed to delete task.'); }
  } catch (e) { btn.disabled = false; alert('Network error — could not delete task.'); }
}
document.getElementById('addTaskForm').addEventListener('submit', async function(e) {
  e.preventDefault();
  const msg = document.getElementById('addTaskMsg');
  msg.textContent = '';
  const resp = await fetch('/housekeeping/tasks', {method: 'POST', body: new FormData(e.target)});
  if (resp.ok) {
    msg.textContent = 'Task added.';
    e.target.reset();
    setTimeout(() => location.reload(), 800);
  } else {
    const err = await resp.json().catch(() => ({}));
    msg.textContent = err.error || 'Failed to add task.';
  }
});

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
  btn.disabled = true; msg.textContent = '';
  const payload = {
    enabled: document.getElementById('sched-enabled').checked,
    day_of_week: document.getElementById('sched-day').value,
    hour: parseInt(document.getElementById('sched-hour').value),
    minute: parseInt(document.getElementById('sched-minute').value),
  };
  try {
    const resp = await fetch('/housekeeping/schedule', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json', 'X-Capture-Token': _captureToken},
      body: JSON.stringify(payload),
    });
    if (resp.ok) {
      const data = await resp.json();
      _schedState.enabled = data.enabled; _schedState.day_of_week = data.day_of_week;
      _schedState.hour = data.hour; _schedState.minute = data.minute;
      document.getElementById('sched-next').textContent = data.next_run || (data.enabled ? 'Calculating…' : 'Disabled');
      document.getElementById('sched-last').textContent = data.last_triggered || 'Never';
      btn.style.display = 'none';
      msg.textContent = 'Saved.';
      setTimeout(function() { msg.textContent = ''; }, 2000);
    } else {
      const err = await resp.json().catch(function() { return {}; });
      msg.textContent = err.error || 'Failed to save.';
    }
  } catch (e) { msg.textContent = 'Network error — could not save schedule.'; }
  btn.disabled = false;
}

async function toggleCapability(name, enable) {
  const btn = document.getElementById('cap-btn-' + name);
  const statusEl = document.getElementById('cap-status-' + name);
  const msgEl = document.getElementById('cap-msg-' + name);
  btn.disabled = true; msgEl.textContent = '';
  try {
    const resp = await fetch('/housekeeping/capabilities/' + name, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json', 'X-Capture-Token': _captureToken},
      body: JSON.stringify({ enabled: enable }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      msgEl.textContent = err.error || 'Failed'; btn.disabled = false; return;
    }
    const data = await resp.json();
    const enabled = data.capability.enabled;
    statusEl.textContent = enabled ? 'ENABLED' : 'DISABLED';
    statusEl.className = 'hk-pill ' + (enabled ? 'hk-pill--ok' : 'hk-pill--disabled');
    btn.textContent = enabled ? 'Disable' : 'Enable';
    btn.onclick = () => toggleCapability(name, !enabled);
    btn.disabled = false;
  } catch (e) { msgEl.textContent = 'Request failed'; btn.disabled = false; }
}

// ── Run status bar ──
const _STATE_TEXT = {
  running: 'Running', ok: 'Healthy', failed: 'Attention',
  stalled: 'Stalled', overdue: 'Overdue', never: 'Never run',
};
function _setStatusBadge(state, headline) {
  const badge = document.getElementById('hk-status-badge');
  const bar = document.getElementById('hk-status-bar');
  bar.dataset.state = state;
  badge.className = 'hk-status-bar__badge hk-status-bar__badge--' + state;
  badge.textContent = _STATE_TEXT[state] || state;
  if (headline) document.getElementById('hk-status-headline').textContent = headline;
}

let _hkPollTimer = null;
async function runHousekeeping(btn) {
  const msg = document.getElementById('hk-run-now-msg');
  if (_hkPollTimer) { clearTimeout(_hkPollTimer); _hkPollTimer = null; }
  btn.disabled = true; btn.textContent = 'Starting…';
  if (msg) msg.textContent = '';
  try {
    const resp = await fetch('/housekeeping/run', {method: 'POST', headers: {'X-Capture-Token': _captureToken}});
    const data = await resp.json();
    if (!resp.ok) {
      btn.textContent = 'Run Now'; btn.disabled = false;
      if (msg) msg.textContent = data.error || 'Error starting housekeeping.';
    } else {
      btn.textContent = 'Running…';
      _setStatusBadge('running', 'Housekeeping is running now…');
      _pollHousekeepingStatus(data.session_id, btn, msg);
    }
  } catch (e) {
    btn.textContent = 'Run Now'; btn.disabled = false;
    if (msg) msg.textContent = 'Network error.';
  }
}
function _pollHousekeepingStatus(sessionId, btn, msg) {
  _hkPollTimer = setTimeout(async () => {
    try {
      const resp = await fetch(`/housekeeping/run-status?session_id=${sessionId}`);
      const data = await resp.json();
      if (data.active) {
        const act = data.activity || 'working';
        _setStatusBadge('running', `Housekeeping is running now (${act})…`);
        if (msg) msg.textContent = `Running (${act})`;
        _pollHousekeepingStatus(sessionId, btn, msg);
      } else {
        btn.textContent = 'Run Now'; btn.disabled = false;
        if (data.last_run) {
          const failed = parseInt(data.tasks_failed) || 0;
          const run = parseInt(data.tasks_run) || 0;
          const state = failed > 0 ? 'failed' : 'ok';
          const outcome = failed > 0 ? `${failed} task(s) failed` : `${run} tasks, all passed`;
          _setStatusBadge(state, `Last run completed — ${outcome}.`);
          if (msg) msg.textContent = `Done — ${outcome} · last run ${data.last_run.replace('T', ' ').replace('Z', '')} UTC`;
        } else {
          _setStatusBadge('stalled', 'Session ended — no heartbeat written. Check session logs.');
          if (msg) msg.textContent = 'Session ended — no heartbeat written (check logs)';
        }
      }
    } catch (e) {
      btn.textContent = 'Run Now'; btn.disabled = false;
      if (msg) msg.textContent = 'Could not poll status.';
    }
  }, 15000);
}
</script>
{% endblock %}
```

- [ ] **Step 4: Update the nav in `app/templates/base.html`**

Replace the existing Housekeeping nav-item block (the one spanning `request.endpoint in ('housekeeping.index', 'research_sources.index')`):

```html
<div class="nav-item{% if request.endpoint in ('housekeeping.index', 'housekeeping.weekly_review', 'housekeeping.blog_draft_editor', 'housekeeping.blog_drafts_list', 'housekeeping.research_findings', 'research_sources.index') %} is-active{% endif %}">
  <a href="{{ url_for('housekeeping.index') }}" class="nav-link {% if request.endpoint == 'housekeeping.index' %}is-active{% endif %}">Housekeeping</a>
  <div class="nav-subnav">
    <a href="{{ url_for('housekeeping.weekly_review') }}" class="nav-sub-link {% if request.endpoint == 'housekeeping.weekly_review' %}is-active{% endif %}">Weekly Review</a>
    <a href="{{ url_for('housekeeping.blog_drafts_list') }}" class="nav-sub-link {% if request.endpoint in ('housekeeping.blog_draft_editor','housekeeping.blog_drafts_list') %}is-active{% endif %}">Blog Drafts</a>
    <a href="{{ url_for('housekeeping.research_findings') }}" class="nav-sub-link {% if request.endpoint == 'housekeeping.research_findings' %}is-active{% endif %}">Research Findings</a>
    <a href="{{ url_for('research_sources.index') }}" class="nav-sub-link {% if request.endpoint == 'research_sources.index' %}is-active{% endif %}">Research Sources</a>
  </div>
</div>
```

- [ ] **Step 5: Append new CSS to `app/static/style.css`**

Insert the following block immediately after the existing `.hk-widget-status--failed { ... }` rule (the last line of the current "Housekeeping page" CSS section, right before the `/* ── Blog Draft Editor ── */` comment):

```css

/* ── Housekeeping: run status bar ── */
.hk-status-bar {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  padding: var(--space-5) var(--space-6);
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--rim-card);
  margin-bottom: var(--space-8);
  flex-wrap: wrap;
}
.hk-status-bar__badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px var(--space-4);
  border-radius: var(--radius-pill);
  font-size: var(--fs-body-sm);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.hk-status-bar__badge::before {
  content: "";
  width: 8px; height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.hk-status-bar__badge--ok      { background: rgba(45,212,191,0.10);  color: var(--status-success); }
.hk-status-bar__badge--running { background: rgba(59,130,246,0.10);  color: var(--status-info); }
.hk-status-bar__badge--running::before { animation: ike-pulse 2.2s ease-in-out infinite; box-shadow: 0 0 8px currentColor; }
.hk-status-bar__badge--overdue { background: rgba(250,204,21,0.10);  color: var(--status-warn); }
.hk-status-bar__badge--failed  { background: rgba(248,113,113,0.12); color: var(--status-error); }
.hk-status-bar__badge--stalled {
  background: rgba(248,113,113,0.08);
  color: var(--status-error);
  border: 1px dashed rgba(248,113,113,0.45);
  padding: 3px calc(var(--space-4) - 1px);
}
.hk-status-bar__badge--never   { background: rgba(139,130,164,0.10); color: var(--text-muted); }

.hk-status-bar__detail   { flex: 1; min-width: 220px; }
.hk-status-bar__headline { font-size: var(--fs-body-sm); font-weight: var(--fw-medium); color: var(--text-primary); margin-bottom: 2px; }
.hk-status-bar__meta     { font-size: var(--fs-caption); color: var(--text-tertiary); font-family: var(--font-mono); }
.hk-status-bar__actions  { display: flex; align-items: center; gap: var(--space-3); flex-shrink: 0; }

@media (max-width: 768px) {
  .hk-status-bar { flex-direction: column; align-items: flex-start; }
  .hk-status-bar__actions { width: 100%; }
  .hk-status-bar__actions .pill { flex: 1; }
}

/* ── Housekeeping: outputs card row ── */
.hk-outputs-section { margin-bottom: var(--space-8); }
.hk-outputs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--space-5);
  margin-top: var(--space-4);
}
.hk-output-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--rim-card);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.hk-output-card__title  { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
.hk-output-card__name   { font-size: var(--fs-body-sm); font-weight: var(--fw-semibold); color: var(--text-primary); }
.hk-output-card__body   { font-size: var(--fs-caption); color: var(--text-tertiary); flex: 1; margin: 0; }
.hk-output-card__footer { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
.hk-output-card__link   { font-size: var(--fs-body-sm); }

/* ── Housekeeping: configuration two-column layout ── */
.hk-config-section { margin-bottom: var(--space-8); }
.hk-config-grid {
  display: grid;
  grid-template-columns: minmax(320px, 480px) 1fr;
  gap: var(--space-6);
  align-items: start;
  margin-top: var(--space-4);
}
.hk-capabilities-card { display: flex; flex-direction: column; gap: var(--space-4); }
@media (max-width: 900px) {
  .hk-config-grid { grid-template-columns: 1fr; }
}

/* ── Generic elevated panel — replaces the undefined `.card` class ── */
.hk-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-5) var(--space-6);
  box-shadow: var(--rim-card);
  margin-top: var(--space-8);
}

/* ── Add-task collapsible ── */
.hk-add-details { margin-top: var(--space-6); }
.hk-add-summary {
  cursor: pointer;
  font-size: var(--fs-body-sm);
  font-weight: var(--fw-medium);
  color: var(--ike-soft-lavender);
  list-style: none;
  padding: var(--space-2) 0;
}
.hk-add-summary::-webkit-details-marker { display: none; }
.hk-add-details[open] .hk-add-summary { color: var(--text-primary); }

/* ── Research findings ── */
.hk-findings-list { display: flex; flex-direction: column; gap: var(--space-5); }
.hk-finding-card { display: flex; flex-direction: column; gap: var(--space-3); }
.hk-finding-card__head  { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.hk-finding-card__label { font-size: var(--fs-body-sm); font-weight: var(--fw-semibold); color: var(--text-primary); }
.hk-finding-card__label:hover { color: var(--ike-soft-lavender); text-decoration: underline; }
.hk-finding-card__notable { margin: 0; padding-left: var(--space-6); font-size: var(--fs-body-sm); color: var(--text-secondary); }
.hk-finding-card__notable li { margin: 2px 0; }
.hk-finding-card__details summary { cursor: pointer; font-size: var(--fs-caption); color: var(--text-tertiary); }
.hk-finding-card__details ul { margin: var(--space-2) 0 0; padding-left: var(--space-6); font-size: var(--fs-caption); color: var(--text-tertiary); }
```

If `@keyframes ike-pulse` doesn't already exist elsewhere in the CSS (check with `grep -n "ike-pulse" app/static/style.css app/static/ikeos/styles.css app/static/workspace.css`), add it right above the `.hk-status-bar__badge--running::before` rule:

```css
@keyframes ike-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
```

- [ ] **Step 6: Rebuild (CSS bundling and template changes both require it) and run the full suite**

Run: `docker.exe compose up --build -d ikeos` then `docker exec ikeos pytest -v`
Expected: All PASS, including the new `test_housekeeping_index_includes_run_state_and_outputs_context`.

- [ ] **Step 7: Manual visual check**

Run: open `http://localhost:5009/housekeeping` in a browser (or `curl -s http://localhost:5009/housekeeping | grep -c "hk-status-bar"` for a headless sanity check — expect `1`).
Confirm: status bar shows a colored badge (not plain unstyled text), outputs grid shows three cards, capability ENABLED/DISABLED pills are colored, Recent Runs section no longer looks visually broken.

- [ ] **Step 8: Commit**

```bash
git add app/templates/housekeeping.html app/templates/base.html app/static/style.css tests/test_housekeeping.py
git commit -m "redesign: housekeeping page — status-first layout

Consolidates three separate status-pill systems (two of them entirely
undefined in CSS — pill--housekeeping/pill--muted and hk-status-*, plus
an undefined .card class) onto the one complete system, .hk-pill--*.
Adds a run-status bar answering 'did it run, is anything broken' at a
glance, an outputs grid linking to blog drafts / platform review /
research findings, and a two-column configuration layout. Task list
and recent-runs content unchanged, only restyled."
```

---

## Self-Review Notes

- **Spec coverage:** Verify housekeeping ran (Task 2 gives ongoing visibility, plus the original investigation already answered "did it run last week"); clean up housekeeping page (Task 5); surface research report (Task 4); delete blog drafts (Task 3); why last week's post didn't deploy (root cause already identified as a claude-config-side `/blog` skill issue — filed as a vault idea, not a code task, since it's prose/skill work outside this repo).
- **Timezone dependency:** `tzdata` pip package is required because `python:3.11-slim` has no OS-level tzdata; confirmed via Dockerfile read.
- **Backward compatibility:** `read_draft_bundle()` keeps its no-arg call signature working identically for all four existing callers (`save`, `publish`, `rewrite`, `content` routes) — only `blog_draft_editor` gains the optional filename.
- **Ordering:** Tasks 1–4 are independent of each other except Task 2 imports `get_research_findings` (from Task 4) into `_housekeeping_context` — noted explicitly in Task 2 Step 7 so a subagent doesn't get stuck on a transient import error when running Task 2's tests in isolation. Task 5 depends on 2, 3, and 4 all being complete (it wires their context fields and routes into the template).
