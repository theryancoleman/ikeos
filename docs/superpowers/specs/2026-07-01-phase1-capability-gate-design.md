# Phase 1 Capability Gate — Design Spec

**Date:** 2026-07-01  
**Status:** Proposed  
**Context:** Phase 0 (metrics observability) and Phase 0.5 (session-manager event wiring) are complete.

---

## Goal

Every autonomous capability in IkeOS — actions that fire without a human clicking a button — must ship locked (disabled by default) and require an explicit architect action to enable. Phase 1 implements this gate for the one capability that is currently fully autonomous: the housekeeping scheduler.

---

## Scope

### In scope
- `capabilities.json` vault-stored registry (new file, new service)
- Housekeeping scheduler gated by the registry (scheduler checks capability before firing)
- UI panel on `/housekeeping` to view and toggle capability state (CAPTURE_TOKEN protected)
- Metrics events: `capability.enabled` / `capability.disabled` with actor and timestamp
- `/metrics` page shows current capability states alongside the event timeline

### Out of scope
- Blog draft publish/rewrite — human-triggered (UI click required); no additional gate needed
- Individual housekeeping task run — human-triggered; no additional gate needed
- `/auto` mode — sessions are human-initiated; no additional gate needed
- Session invocation centralisation (vault note "Consistent Terminal Session Interaction Model") — Phase 2 workstream

---

## Assumptions

- The existing `enabled` field in `schedule.json` is **not removed** — it still controls whether APScheduler pauses/resumes the job. The capability gate is a **pre-condition layer** on top: both must be true for the scheduler to fire. This avoids a migration risk.
- "Actor" for enablement is always `"architect"` in v1 — there's only one user and no auth identity system. The field is recorded for future use.
- The capability registry lives at `{VAULT_PATH}/projects/claude-config/housekeeping/capabilities.json`, co-located with `schedule.json`. Both are in the same vault project, same housekeeping subdirectory.

---

## Data Model

### `capabilities.json`

```json
{
  "housekeeping_scheduler": {
    "enabled": false,
    "enabled_by": null,
    "enabled_at": null,
    "description": "Scheduled weekly housekeeping runs via session manager"
  }
}
```

**Fields:**
- `enabled` — bool, defaults `false` for every capability
- `enabled_by` — string or null; set to `"architect"` on enable, `null` on disable
- `enabled_at` — ISO timestamp or null; set on enable, `null` on disable
- `description` — human-readable label for the UI

**Default (file absent):** all capabilities disabled. The app never errors on a missing file — it reads the default.

---

## Component Design

### New: `app/services/capabilities.py`

Single-responsibility: read and write `capabilities.json`. No Flask imports.

```python
CAPABILITY_NAMES = ["housekeeping_scheduler"]

DEFAULT_CAPABILITIES = {
    "housekeeping_scheduler": {
        "enabled": False,
        "enabled_by": None,
        "enabled_at": None,
        "description": "Scheduled weekly housekeeping runs via session manager",
    }
}

def get_capabilities() -> dict           # reads file, merges with defaults
def is_enabled(name: str) -> bool        # convenience: get_capabilities()[name]["enabled"]
def update_capability(name: str, enabled: bool, actor: str = "architect") -> dict
                                         # writes file, emits metrics event, returns updated record
```

`update_capability` emits `capability.enabled` or `capability.disabled` to metrics with fields `{capability: name, actor: actor}`. This is fire-and-forget (matches `_post_metric()` pattern in session manager).

### Modify: `app/services/scheduler.py`

In `_job()`, add a capability check before calling `trigger_now()`:

```python
def _job() -> None:
    from app.services.capabilities import is_enabled
    if not is_enabled("housekeeping_scheduler"):
        logger.info("Housekeeping job skipped: capability gate disabled")
        return
    logger.info("Housekeeping scheduled trigger firing")
    trigger_now()
```

The APScheduler job still runs on its cron schedule — it just exits early if the gate is off. This is intentional: the schedule config (day/hour/minute) stays independent of the authorization gate.

### New routes: `app/routes/housekeeping.py`

```
GET  /housekeeping/capabilities         → JSON {capabilities: {...}}
PATCH /housekeeping/capabilities/<name> → JSON {capability: {...}}  (CAPTURE_TOKEN required)
```

PATCH body: `{"enabled": true}`. Response: updated capability record + emits metrics event.

### Modify: `app/templates/housekeeping.html`

Add a **Capabilities** section above the schedule section. For each capability:
- Name + description
- Status badge: `ENABLED` (green) / `DISABLED` (grey)
- Toggle button: "Enable" / "Disable" — calls PATCH with X-Capture-Token header
- If enabled: show `enabled_at` timestamp

### Modify: `app/templates/metrics.html`

Add a **Capability Status** panel above the event timeline. Shows current state of all capabilities (read from `GET /housekeeping/capabilities`). Static snapshot — no polling. Refreshes on page load.

---

## Metrics Events

Two new event types emitted by `update_capability()`:

| Event | When | Fields |
|---|---|---|
| `capability.enabled` | Capability toggled on | `capability`, `actor` |
| `capability.disabled` | Capability toggled off | `capability`, `actor` |

These appear in the `/metrics` timeline alongside `housekeeping.trigger` events, giving a clear picture of when the gate was opened and what ran afterward.

---

## Testing

- `test_capabilities.py` — unit tests for `get_capabilities()`, `is_enabled()`, `update_capability()` using `tmp_path`; mock `append_event` to verify metrics emission
- `test_housekeeping.py` — add test that `_job()` does NOT call `trigger_now()` when capability is disabled; add test that PATCH `/housekeeping/capabilities/housekeeping_scheduler` requires CAPTURE_TOKEN
- `test_metrics.py` — add test that `/metrics` page renders capability status panel

---

## Adding Future Capabilities (Phase 2+)

To gate a new autonomous capability:
1. Add an entry to `DEFAULT_CAPABILITIES` in `capabilities.py`
2. In the capability's trigger function, call `is_enabled("new_capability_name")` before firing
3. The UI panel picks it up automatically (iterates `get_capabilities()`)
4. No schema migration — file is merged with defaults on read

---

## What This Is Not

This is not a full RBAC or permissions system. It's a single-user, single-actor gate: the architect enables or disables autonomous capabilities through the IkeOS UI. The CAPTURE_TOKEN is the authorization mechanism — same as every other mutation in IkeOS v1.
