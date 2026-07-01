# Phase 2 Session Client — Design Spec

**Date:** 2026-07-01
**Status:** Proposed
**Context:** Phase 1 (capability gate) is complete. Phase 2 addresses the vault note "Consistent Terminal Session Interaction Model" — IkeOS-side session invocation centralisation.

---

## Problem

Five places in IkeOS create Claude Code sessions by calling `POST /sessions` on the session-manager:

| File | Function | Notes |
|---|---|---|
| `app/services/scheduler.py` | `trigger_now()` | Scheduled housekeeping |
| `app/routes/housekeeping.py` | `run_task()` | Individual task run; handles 409 |
| `app/routes/housekeeping.py` | `blog_draft_publish()` | Blog publish |
| `app/routes/housekeeping.py` | `blog_draft_rewrite()` | Blog rewrite; handles 409 + sends command to existing session |

Each call site has slightly different error handling (some check 409, some don't), different timeout values, different error messages, and none emit metrics on session creation. Any future autonomous capability must duplicate this pattern again.

---

## Goal

One importable function — `session_client.create_session()` — that all current and future session-spawning code in IkeOS uses. Standard response type. Consistent error handling. Automatic metrics emission on success.

---

## Out of Scope

- Session-manager changes (delays, `tmux.py`, startup sequences — already centralised there)
- Agent context awareness (what project am I in, how do I route tasks) — Phase 3
- The `SESSION_MANAGER_URL` variable in `housekeeping.py` used by proxy/session-status routes (those are reads, not session creation)

---

## New Service: `app/services/session_client.py`

### `SessionResult` dataclass

```python
@dataclass
class SessionResult:
    session_id: str
    already_running: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
```

Fields:
- `session_id` — the session ID returned by session-manager (or the existing session ID on 409)
- `already_running` — True when session-manager returned 409 (a session with this name already exists)
- `error` — human-readable error string, or None on success
- `ok` — True when error is None

### `create_session()` function

```python
def create_session(
    *,
    name: str,
    project: str,
    project_dir: str,
    initial_command: str | None = None,
) -> SessionResult:
```

Behaviour:
1. Reads `SESSION_MANAGER_URL` from env at call time (not module-level, so tests can patch via `monkeypatch.setenv`)
2. POSTs to `{SESSION_MANAGER_URL}/sessions` with `{name, project, project_dir, initial_command}`, timeout=5s
3. **409:** Returns `SessionResult(session_id=existing_id, already_running=True)` — extracts `id` from `response["session"]["id"]`
4. **Non-ok (not 409):** Returns `SessionResult(session_id="", error="Session manager returned {status}")`
5. **Timeout / ConnectionError:** Returns `SessionResult(session_id="", error="Session manager unreachable")`
6. **Success:** Emits `session.created` metric with `{session_id, name, project}` (fire-and-forget, wrapped in try/except, never raises), then returns `SessionResult(session_id=id)`

All keyword-only arguments — prevents positional argument confusion at call sites.

---

## Call Site Migration

### `app/services/scheduler.py` — `trigger_now()`

Replace:
```python
create_resp = requests.post(f"{sm_url}/sessions", json={...}, timeout=5)
if not create_resp.ok: ...
session_id = create_resp.json().get("id")
```

With:
```python
from app.services.session_client import create_session
result = create_session(
    name=session_name,
    project="claude-config",
    project_dir=project_dir,
    initial_command="/housekeeping — run in scheduled mode",
)
if not result.ok:
    logger.error("Failed to create housekeeping session: %s", result.error)
    return None
session_id = result.session_id
```

The `sm_url` local variable and the `requests` import are removed from this function.

### `app/routes/housekeeping.py` — `run_task()`

Replace the `requests.post(...)` block with:
```python
from app.services.session_client import create_session
result = create_session(
    name=session_name,
    project="claude-config",
    project_dir=HOUSEKEEPING_PROJECT_DIR,
    initial_command=command,
)
if result.already_running:
    return jsonify({"ok": True, "session_id": result.session_id, "already_running": True}), 200
if not result.ok:
    return jsonify({"error": "Failed to create session"}), 502
```

### `app/routes/housekeeping.py` — `blog_draft_publish()`

Replace the `requests.post(...)` block with:
```python
result = create_session(
    name=f"blog-publish-{draft.stem[:30]}",
    project="aios-blog",
    project_dir=AIOS_BLOG_PROJECT_DIR,
    initial_command=command,
)
if not result.ok:
    return jsonify({"error": "Failed to create publish session"}), 502
return jsonify({"ok": True, "session_id": result.session_id}), 200
```

### `app/routes/housekeeping.py` — `blog_draft_rewrite()`

The 409 branch (send command to existing session) remains in the route — only the session creation call is centralised:
```python
result = create_session(
    name=f"blog-rewrite-{draft.stem[:30]}",
    project="aios-blog",
    project_dir=AIOS_BLOG_PROJECT_DIR,
    initial_command=command,
)
if result.already_running:
    # Send feedback to the running session directly
    cmd_resp = requests.post(
        f"{SESSION_MANAGER_URL}/sessions/{result.session_id}/command", ...
    )
    ...
if not result.ok:
    return jsonify({"error": "Failed to create rewrite session"}), 502
return jsonify({"ok": True, "session_id": result.session_id}), 200
```

---

## Metrics

New event type: `session.created`
- Fields: `session_id`, `name`, `project`
- Emitted by `create_session()` on success (not on 409 or error)
- Fire-and-forget: wrapped in try/except, never raises, never blocks

---

## Testing

New file: `tests/test_session_client.py`

Test cases:
- `test_create_session_success` — mocks `requests.post` returning 200 with `{"id": "abc"}`, asserts `result.ok`, `result.session_id == "abc"`, `result.already_running == False`
- `test_create_session_409_returns_already_running` — mocks 409 with `{"session": {"id": "existing"}}`, asserts `result.already_running == True`, `result.session_id == "existing"`, `result.ok == True`
- `test_create_session_non_ok_returns_error` — mocks 500, asserts `result.ok == False`, `result.error` contains "500"
- `test_create_session_timeout_returns_error` — mocks `requests.Timeout`, asserts `result.ok == False`, error mentions "unreachable"
- `test_create_session_emits_metric_on_success` — mocks `requests.post` returning 200, patches `append_event`, asserts called with `"session.created"`
- `test_create_session_no_metric_on_failure` — mocks 500, patches `append_event`, asserts NOT called

Migration regression coverage: existing `test_housekeeping.py` tests for `run_task`, `blog_draft_publish`, `blog_draft_rewrite` already mock `requests.post` — they will need their mock target updated to `app.services.session_client.requests.post` or to use `monkeypatch` on the session_client module.

---

## What Stays the Same

- Session-manager codebase: no changes
- `tmux.py` delay configuration: no changes
- `housekeeping.py` still reads `SESSION_MANAGER_URL` for proxy and session-status routes
- The `requests` import in `housekeeping.py` remains (used by capture proxy and session-status routes)
- Blog rewrite 409 handling logic: preserved in the route, only the HTTP call is centralised

---

## Future Use

Any new autonomous capability in IkeOS that needs to spawn a Claude Code session imports `session_client.create_session()`. No new HTTP boilerplate, consistent metrics, consistent error handling out of the box.
