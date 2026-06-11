# Three-Column Home Dashboard — Design Spec

**Date:** 2026-06-11
**Project:** obsidian-capture
**Status:** Approved

---

## Goal

Replace the current bare dashboard at `/` with a unified three-column workspace that combines session management, session detail, and quick capture into a single view. The existing `/agents` (two-column), `/capture`, and `/tasks` (current dashboard) pages remain intact.

---

## Route Changes

| Route | Before | After |
|---|---|---|
| `/` | `browse.dashboard` → `dashboard.html` | `agents.home` → `workspace.html` (three_col=True) |
| `/tasks` | *(new)* | `browse.tasks` → `dashboard.html` (same template, new route) |
| `/agents` | `agents.agents` → `agents.html` | `agents.agents` → `workspace.html` (three_col=False) |
| `/capture` | unchanged | unchanged |

The old `browse.dashboard` route at `/` moves to `/tasks`. A new `agents.home` route at `/` renders `workspace.html` with `three_col=True`.

---

## Navigation (`base.html`)

```
[Obsidian Capture]  Home   Tasks   Sessions   Capture
```

- Brand link ("Obsidian Capture") points to `/`
- "Home" → `/` (active on home page)
- "Tasks" → `/tasks`  (was the brand link destination)
- "Sessions" → `/agents` (renamed from "Agents")
- "Capture" → `/capture` (renamed from "+ New entry")

---

## Template: `workspace.html`

Replaces `agents.html` (which is deleted). Rendered by both `/` and `/agents`.

### Layout

```
three_col=True  (home page):
┌─────────────────┬──────────────────────┬───────────────────┐
│ Sessions  [New+]│ Session Detail    [×] │ Capture           │
│─────────────────│──────────────────────│───────────────────│
│ [session card]  │ [command input]  Send│ Project ▾         │
│ [session card]  │ ──────────────────── │ Type    ▾         │
│                 │ live output          │ Title             │
│                 │                      │ Body              │
│                 │ ──────────────────── │                   │
│                 │ Actions              │        [Capture]  │
└─────────────────┴──────────────────────┴───────────────────┘

three_col=False (/agents page):
┌─────────────────┬──────────────────────┐
│ Sessions  [New+]│ Session Detail    [×] │
│─────────────────│──────────────────────│
│ [session card]  │ [command input]  Send│
│ ...             │ live output          │
│                 │ Actions              │
└─────────────────┴──────────────────────┘
```

CSS grid: `three_col=True` → `grid-template-columns: 250px 1fr 280px`, `three_col=False` → `grid-template-columns: 250px 1fr`.

### Col 1 — Sessions
- Heading "Sessions" + [New+] button (same as current)
- Session card grid with polling (same logic as current)

### Col 2 — Session Detail
- Heading "Session Detail" + [×] close button
- **Command input row is the first element** inside the panel body (moved from current bottom position)
- Live output below the command input
- Actions section below live output
- Placeholder shown when no session selected; command row hidden until a session is open

### Col 3 — Capture (three_col only)
- Heading "Capture"
- Compact form: Project `<select>`, Type `<select>`, Title `<input>`, Body `<textarea rows="4">`
- Submit button: AJAX POST to `/capture/json`; on success show inline "Saved ✓" and reset form (keep project + type values); on error show inline error message
- **Project auto-select:** when a session is opened, the Project dropdown sets its value to `session.project` (if that slug exists in the options); when the panel is closed, reverts to first option

---

## URL State

Selected session persisted in the URL query string: `?session=<session-id>`.

- On session open: `history.replaceState(null, '', '?session=' + id)`
- On panel close: `history.replaceState(null, '', location.pathname)`
- On page load: read `new URLSearchParams(location.search).get('session')`; after initial session list loads, auto-open the matching session if found

This ensures a page refresh returns to the same selected session.

---

## New Endpoint: `POST /capture/json`

Added to `capture.py`. Accepts JSON, returns JSON. No auth required (same as the existing form POST).

**Request:**
```json
{
  "type": "note|idea|bug",
  "project": "project-slug",
  "title": "Entry title",
  "body": "Optional description",
  "priority": "low|medium|high",   // ideas only
  "effort": "low|medium|large"     // ideas only
}
```

**Response:**
- `200 {"ok": true}`
- `400 {"error": "message"}` for missing required fields

Internally calls the same `write_entry()` service used by the form POST.

---

## JS Architecture

`agents.html` currently embeds ~300 lines of JS inline. This spec extracts it.

- **`static/agents.js`** — all session management logic: polling, card rendering, panel open/close, actions, modal, URL state. Loaded by `workspace.html` via `<script src>`.
- **Inline in `workspace.html`** — ~30 lines for capture column: form submit, project sync, success/error display.
- `agents.css` renamed to `workspace.css` and updated for 3-col layout.

---

## Files Changed

| File | Change |
|---|---|
| `app/routes/browse.py` | Add `/tasks` route; remove or rename old `/` route |
| `app/routes/agents.py` | Add `/` route (home, three_col=True); update `/agents` to render `workspace.html` with `three_col=False` |
| `app/routes/capture.py` | Add `POST /capture/json` endpoint |
| `app/templates/base.html` | Update nav links and labels |
| `app/templates/agents.html` | **Delete** — replaced by `workspace.html` |
| `app/templates/workspace.html` | **New** — three-column template |
| `app/static/agents.js` | **New** — extracted session JS |
| `app/static/agents.css` | Renamed to `workspace.css`, updated for 3-col layout |

---

## Assumptions

- `session.project` in the session list API response matches the project slug in the vault (confirmed: session creation sets `project` to the selected slug)
- The `/tasks` route name does not conflict with any existing Flask route or template
- The existing `dashboard.html` template needs no changes — it's reused at `/tasks` unchanged
- No mobile/responsive breakpoints required (internal homelab tool)
