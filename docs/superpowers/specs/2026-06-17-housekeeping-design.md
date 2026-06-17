# Housekeeping System Design

**Date:** 2026-06-17
**Projects:** obsidian-capture (Phase 1), IkeOS (Phase 2)
**Status:** Approved

---

## Overview

The housekeeping system consists of a scheduled Claude Code skill that runs maintenance tasks against the Obsidian vault, writes runtime state back via the obsidian-capture API, and surfaces status in IkeOS. This spec covers the full stack: obsidian-capture API extensions, IkeOS vault service functions, the task management page, and the dashboard heartbeat widget.

---

## Execution Model

**Scheduled runs:** The `/housekeeping` skill self-schedules via `CronCreate`. The prompt field must include the phrase `run in scheduled mode` for the skill to enter automated mode (no user prompts). Runs as a standard Claude Code CLI session — no programmatic Anthropic API usage. After each run the skill writes a heartbeat entry to the vault and exits.

**On-demand (Force Run):** IkeOS calls `POST /agents/sessions` on the session manager (port 5010) to create a new named tmux session (`housekeeping-<task-slug>`), then `POST /agents/sessions/<id>/command` to send `/housekeeping run in scheduled mode <task-slug>`. The session is visible in the Sessions manager. Force Run advances `last_run` on pass, does not advance it on fail — identical to a scheduled run.

**IkeOS role:** Read-only against the vault (no live session dependency). Proxies write actions to obsidian-capture API. Proxies Force Run to the session manager.

---

## Phase 1: obsidian-capture Extensions

### 1.1 New entry types — `POST /capture`

Add support for `type=housekeeping-task` and `type=housekeeping-heartbeat`. Both write to `projects/<project>/housekeeping/` subfolder (create if absent).

**`housekeeping-task` frontmatter on creation:**
```yaml
title: <string>
type: housekeeping-task
project: <string>
interval: weekly|monthly|quarterly|annually
enabled: 'true'
success_definition: <string>
last_run: 'null'
last_error: 'null'
consecutive_failures: '0'
created: <ISO datetime>
tags: [housekeeping-task, <project>, status/enabled]
```

**`housekeeping-heartbeat` frontmatter on creation:**
```yaml
title: Housekeeping Last Run
type: housekeeping-heartbeat
project: <string>
last_run: 'null'
tasks_run: '0'
tasks_failed: '0'
tasks_skipped: '0'
created: <ISO datetime>
tags: [housekeeping-heartbeat, <project>]
```

**Singleton behavior:** When `type=housekeeping-heartbeat`, write to `last-run.md` (no date prefix). This entry is updated in-place on every run, not appended. If the file already exists, overwrite it.

### 1.2 Extended PATCH endpoint — `PATCH /entries/housekeeping`

New route, same `X-Capture-Token` authentication as `PATCH /entries`. Accepts **JSON body only** (not form data) — `fields` is a nested object that doesn't serialize cleanly in form encoding.

**Request body (JSON):**

| Field | Required | Description |
|-------|----------|-------------|
| `project` | yes | Project slug |
| `type` | yes | `housekeeping-task` or `housekeeping-heartbeat` |
| `filename` | yes | Filename without `.md` (path traversal rejected) |
| `fields` | yes | JSON object of fields to write (see below) |

**Allowed fields by type:**

`housekeeping-task`: `enabled`, `last_run`, `last_error`, `consecutive_failures`

`housekeeping-heartbeat`: `last_run`, `tasks_run`, `tasks_failed`, `tasks_skipped`

This endpoint updates only the named fields. It does not touch `status`, `tags`, or any other frontmatter. Returns `{"message": "Updated"}` on success, 404 if file not found, 400 for invalid input, 401/503 for auth failures.

---

## Phase 2: IkeOS

### 2.1 Vault service additions (`app/services/vault.py`)

Two new uncached read functions (housekeeping state changes frequently — do not use the 10-minute TTL cache):

**`read_housekeeping_tasks(project: str) -> list[dict]`**

Globs `VAULT_PATH/projects/<project>/housekeeping/*.md`, filters to `type=housekeeping-task`. For each task, appends two computed fields:

- `status`: `"disabled"` if `enabled != 'true'`; `"error"` if `consecutive_failures != '0'`; `"uninitialized"` if `last_run == 'null'` and interval is not `weekly`; `"overdue"` if days since `last_run` exceeds threshold + 3 grace days; `"due"` if at or past threshold; `"ok"` otherwise.
- `next_run`: `None` if `last_run == 'null'`; else `last_run_date + threshold_days` as an ISO date string.

Thresholds: `weekly=6`, `monthly=27`, `quarterly=83`, `annually=364`.

Returns empty list if the `housekeeping/` folder does not exist.

**`read_housekeeping_heartbeat(project: str) -> dict`**

Reads `VAULT_PATH/projects/<project>/housekeeping/last-run.md`. Returns parsed frontmatter dict. If the file does not exist or fails to parse, returns:

```python
{"last_run": None, "tasks_run": "0", "tasks_failed": "0", "tasks_skipped": "0"}
```

### 2.2 Housekeeping blueprint (`app/routes/housekeeping.py`)

New Flask blueprint registered at `/housekeeping`.

| Route | Method | Description |
|-------|--------|-------------|
| `/housekeeping` | GET | Render task management page |
| `/housekeeping/tasks` | POST | Create new task via obsidian-capture POST /capture |
| `/housekeeping/tasks/<filename>/toggle` | POST | Flip `enabled` via obsidian-capture PATCH /entries/housekeeping |
| `/housekeeping/tasks/<filename>/reset` | POST | Set `last_run='null'` via obsidian-capture PATCH /entries/housekeeping |
| `/housekeeping/tasks/<filename>/run` | POST | Create session + send command via session manager |

All write routes return JSON (`{"ok": true}` or `{"error": "..."}`) for fetch()-based UI updates. The GET route reads tasks and the heartbeat, passes both to the template.

**Force Run session creation:**

```
POST /sessions  →  {"name": "housekeeping-<slug>"}
POST /sessions/<id>/command  →  {"command": "/housekeeping run in scheduled mode <slug>"}
```

Returns `{"ok": true, "session_id": "<id>"}` to the UI, which links to `/agents`.

**Obsidian-capture base URL:** read from env var `CAPTURE_URL` (default `http://host.docker.internal:5009`). Token from `CAPTURE_TOKEN` env var.

### 2.3 Task management template (`app/templates/housekeeping.html`)

Extends `base.html`. Uses `settings-page` layout class for consistency.

**Table columns:** Name | Interval | Status | Last Run | Next Due | Actions

**Status pill colors:**
- `ok` → green
- `due` → amber
- `overdue` → red
- `error` → red
- `disabled` → gray
- `uninitialized` → gray/muted

**Actions per row (pill buttons, fetch()-based):**
- Enable / Disable (toggles label based on current `enabled` value)
- Reset Timer
- Run (creates session, shows link to Sessions manager on success)

**Add Task form** — inline at bottom of page:
- Title (text input, required)
- Interval (select: weekly / monthly / quarterly / annually)
- Success Definition (textarea, required)

On submit, `POST /housekeeping/tasks`, page reloads on success.

### 2.4 Dashboard heartbeat widget

Location: dashboard sidebar (`dashboard-sidebar`), below the project cards section.

**Widget content:**
- Eyebrow label: `Housekeeping`
- Last run: relative time string (e.g. "3 days ago") or "Never"
- Status pill: `OK` / `OVERDUE` (last_run null or >9 days ago) / `FAILED` (tasks_failed > 0)
- Run summary line: `X run · Y failed · Z skipped`
- Link: "Manage tasks →" → `/housekeeping`

The dashboard route (`browse.py` or `agents.py`, whichever serves `dashboard`) calls `read_housekeeping_heartbeat("claude-config")` and passes the result as `housekeeping_heartbeat` to the template.

### 2.5 Navigation

Add `Housekeeping` as a top-level nav link in `base.html`, between Skills and Settings:

```html
<a href="{{ url_for('housekeeping.index') }}" class="nav-link ...">Housekeeping</a>
```

### 2.6 App factory

Register the new blueprint in `app/__init__.py`:

```python
from app.routes.housekeeping import bp as housekeeping_bp
app.register_blueprint(housekeeping_bp)
```

---

## Dependency Order

1. obsidian-capture session implements Phase 1 (new types + extended PATCH + last-run.md singleton)
2. IkeOS implements Phase 2 — vault service functions and all routes work against real vault data
3. Vault seed: housekeeping task entries and heartbeat created via obsidian-capture API once Phase 1 ships
4. `/schedule` run to register the weekly CronCreate job

---

## Out of Scope

- Remove Task action (deferred — can be added as a disable + status=deferred flow later)
- `--dry-run` flag for Force Run (noted in alignment; implement in the housekeeping skill, not IkeOS)
- Token count / session health on task rows
