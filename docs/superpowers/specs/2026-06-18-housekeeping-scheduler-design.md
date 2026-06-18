# Housekeeping Scheduler Design

## Goal

IkeOS owns the weekly housekeeping schedule. At the configured time it spawns a Claude Code session via the session manager, sends `/housekeeping — run in scheduled mode`, and the skill runs autonomously. The schedule is configurable from the housekeeping management page without a container restart.

## Architecture

Four units are affected:

| Unit | Role |
|---|---|
| `app/services/scheduler.py` (new) | APScheduler instance, config read/write, job logic |
| `app/routes/housekeeping.py` (extended) | Two new endpoints + shared session-spawn helper |
| `app/templates/housekeeping.html` (extended) | Schedule control section |
| `app/__init__.py` (extended) | Start scheduler after blueprints register |

## Tech Stack

- **APScheduler>=3.10** — `BackgroundScheduler` with cron trigger
- Config persisted in vault JSON file (no new volume mount)
- All existing housekeeping infrastructure unchanged

---

## Schedule Config

**File:** `/vault/projects/claude-config/housekeeping/schedule.json`

```json
{
  "enabled": false,
  "day_of_week": "sun",
  "hour": 3,
  "minute": 7,
  "last_triggered": null
}
```

- `enabled` defaults to `false` — must be explicitly turned on from the UI.
- `day_of_week` accepts APScheduler cron values: `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`.
- `last_triggered` is an ISO datetime string written by the scheduler on each successful session spawn (not on skill completion — completion is observable via `last-run.md`).
- If the file is absent on startup, defaults above are used and the scheduler stays inactive.

---

## `app/services/scheduler.py`

```python
# Public surface
def start(app: Flask) -> None: ...       # called once from create_app()
def get_config() -> dict: ...            # reads schedule.json, returns defaults if missing
def update_config(fields: dict) -> dict: # validates, writes, reschedules; returns updated config
def trigger_now() -> str: ...            # fires job immediately, returns session_id
```

### Job logic

On each scheduled fire (and when `trigger_now()` is called):

1. `POST /sessions` → `{ "name": "housekeeping-<YYYYMMDD>" }`
2. `POST /sessions/<id>/command` → `{ "command": "/housekeeping — run in scheduled mode" }`
3. On success: write `last_triggered` to `schedule.json`.
4. On failure (session manager unreachable, non-2xx): log error, skip. No retry. Completion is tracked via the heartbeat (`last-run.md`), not via the session.

### Rescheduling

`update_config()` calls `scheduler.reschedule_job("housekeeping", trigger="cron", ...)` when `enabled` is true, or `scheduler.pause_job("housekeeping")` when false. Changes take effect immediately — no restart needed.

### No-op in test mode

`start()` checks `app.testing` and returns early. Existing tests are unaffected.

---

## New API Endpoints

### `GET /housekeeping/schedule`

Returns schedule config with a computed field:

```json
{
  "enabled": true,
  "day_of_week": "sun",
  "hour": 3,
  "minute": 7,
  "last_triggered": "2026-06-15T03:07:42",
  "next_run": "2026-06-22T03:07:00"
}
```

`next_run` is null when `enabled` is false.

No auth required (read-only).

### `PATCH /housekeeping/schedule`

Requires `X-Capture-Token` header.

Accepts any subset of `{ "enabled": bool, "day_of_week": str, "hour": int, "minute": int }`.

Validation:
- `day_of_week`: one of `mon tue wed thu fri sat sun`
- `hour`: 0–23
- `minute`: 0–59

Returns updated config (same shape as GET) on success, or `{ "error": "..." }` with 400/401.

---

## UI Changes (`housekeeping.html`)

New "Schedule" section, above the task table:

```
┌─ Schedule ──────────────────────────────────────┐
│  [✓] Enable weekly run                          │
│  Day   [Sunday ▼]   Time  [03] : [07]           │
│  Next run: Sunday 22 Jun · 3:07 AM              │
│  Last triggered: 3 days ago                     │
│                                   [ Save ]      │
└─────────────────────────────────────────────────┘
```

- "Save" button only appears when any field has changed from the current saved values.
- After a successful PATCH, "Next run" and "Last triggered" update in place without a page reload.
- When disabled, day/time inputs are greyed out and "Next run" shows "Disabled".
- The `GET /housekeeping/schedule` call is made when the page loads (already in the route handler, passed to template as `schedule`).

---

## Testing

`tests/test_scheduler.py` — no Flask or APScheduler needed for most cases:

- `get_config()` returns defaults when file missing
- `get_config()` reads file correctly when present
- `update_config()` rejects invalid `day_of_week` / out-of-range `hour` / `minute`
- `update_config()` writes merged config to file
- `trigger_now()` with mocked `requests` — verifies session name format and command string
- `trigger_now()` with mocked requests raising `RequestException` — logs and returns None

`tests/test_housekeeping.py` (extended):

- `GET /housekeeping/schedule` returns config with `next_run`
- `PATCH /housekeeping/schedule` with valid fields → 200
- `PATCH /housekeeping/schedule` with invalid `hour` → 400
- `PATCH /housekeeping/schedule` without token → 401

---

## File Summary

| File | Change |
|---|---|
| `requirements.txt` | Add `APScheduler>=3.10` |
| `app/services/scheduler.py` | New — scheduler service |
| `app/routes/housekeeping.py` | Add GET/PATCH schedule endpoints, extract shared spawn helper |
| `app/templates/housekeeping.html` | Add Schedule section |
| `app/__init__.py` | Call `scheduler.start(app)` |
| `tests/test_scheduler.py` | New — unit tests for scheduler service |
| `tests/test_housekeeping.py` | Extend with schedule endpoint tests |
