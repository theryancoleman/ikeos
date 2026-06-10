# Agents UI Redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current clunky table-based session manager UI with a card grid + slide-in detail panel that is visually polished, reactive, and higher-contrast.

**Architecture:** Pure frontend overhaul (HTML/CSS/JS) plus one new backend endpoint. No framework dependencies — vanilla JS with `fetch`. Auto-refresh via polling replaces all `window.location.reload()` calls.

**Tech Stack:** Jinja2 templates, vanilla CSS (dark theme, CSS custom properties), vanilla JS (fetch, setInterval), Flask (one new route), Fable model for frontend design agent.

---

## Visual Design

### Colour system (high-contrast dark theme)

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#0f0f0f` | Page background |
| `--bg-card` | `#1a1a1a` | Card / panel background |
| `--bg-panel` | `#141414` | Side panel background |
| `--bg-pane` | `#000` | Terminal pane output |
| `--text` | `#f0f0f0` | Primary text |
| `--text-muted` | `#aaaaaa` | Secondary / label text (was `#666`, now lighter) |
| `--border` | `#2e2e2e` | Card / table borders |
| `--accent` | `#7c6af7` | Primary accent (purple) |
| `--success` | `#4ade80` | Active / RC on / health-fresh |
| `--warn` | `#fb923c` | Health-aging |
| `--danger` | `#f87171` | Stopped / health-heavy / danger actions |
| `--thinking` | `#a78bfa` | Activity: thinking |
| `--working` | `#38bdf8` | Activity: working |

All existing CSS custom property names (`--color-accent`, etc.) are replaced with this tighter set. Both `agents.css` and `agents.html` are full rewrites.

---

## Layout

```
┌─ Page header ──────────────────────────────────┐
│  Agents                          [+ New Session]│
└─────────────────────────────────────────────────┘
┌─ Card grid ────────────────┐ ┌─ Detail panel ──┐
│  [Card]  [Card]  [Card]    │ │  Session name   │
│  [Card]  [Card]  [Card]    │ │  ─────────────  │
│                            │ │  Pane output    │
│                            │ │  (live, scroll) │
│                            │ │  ─────────────  │
│                            │ │  All actions    │
│                            │ │  Command input  │
└────────────────────────────┘ └─────────────────┘
```

- Grid is `repeat(auto-fill, minmax(260px, 1fr))`, responsive.
- Panel is fixed-width `380px`, hidden on page load. It slides in from the right when a card is selected; the page layout switches to a flex row so the grid area narrows (cards don't reflow to fewer columns — the grid container just gets narrower).
- Panel is dismissed by clicking `×` or clicking another card (replaces content with the new session).
- On narrow viewports (< 800px), panel overlays the grid instead of pushing it.

---

## Card Design

Each card contains:

**Top accent bar** — 3px top border in health colour (fresh=green, aging=amber, heavy=red).

**Body:**
- Session name — `1rem`, `--text`, bold
- Project slug — `0.75rem`, `--text-muted`, below name
- Status badge — inline pill: `● active` (green) or `○ stopped` (muted). If active, activity appended: `● active · thinking` (purple) / `● active · working` (sky) / `● active · idle` (muted)
- Age — `0.75rem`, `--text-muted`, right-aligned

**Footer (key actions):**
- Active session: **[Stop]** (danger outline), **[RC: on/off]** (toggle chip), **[Auto: on/off]** (toggle chip)
- Stopped session: **[Start]** (accent filled), **[Remove]** (danger text, no border)

Clicking anywhere on the card body (not the footer buttons) opens the detail panel for that session.

Selected card gets a subtle `--accent` ring (`box-shadow: 0 0 0 2px var(--accent)`).

---

## Detail Panel

**Header:** Session name + project, close `×` button.

**Pane output section:**
- Label: `Live output` with a small pulsing dot when active
- Monospace black box (`--bg-pane`), `0.75rem`, `--success` text (terminal green), `min-height: 200px`, `max-height: 40vh`, overflow-y scroll, anchored to bottom (auto-scroll unless user has scrolled up)
- Polls `GET /agents/sessions/{id}/pane` every 2 seconds while panel is open
- Shows last 40 lines
- If session is stopped: shows `— session stopped —` in muted text

**Actions section:**
- RC and Auto toggles are also available on the card footer for quick access — their presence in the panel is intentional, giving labeled context alongside the other controls.
- All controls for the selected session in a clean vertical stack:
  - Toggle RC (button)
  - Toggle Auto (button)
  - Clear context (button)
  - Compact (button)
  - Reset session (button)
  - Stop / Start (prominent, at bottom)
  - Remove (danger, text link style, below stop)
- Buttons are full-width, consistent height, with clear labels

**Command input:**
- Text input + **Send** button side by side
- Placeholder: `Type a /command…`
- Enter key submits
- Input clears after send

---

## Polling / Reactivity

| What | How | Interval |
|---|---|---|
| Card grid (status, activity, age) | `setInterval` → `GET /agents/sessions` → diff and patch DOM | 4 seconds |
| Pane output | `setInterval` → `GET /agents/sessions/{id}/pane` → replace pre content | 2 seconds (only while panel open) |

All action buttons (`fetch` + await) update the relevant session card immediately from the response — no `reload()` anywhere.

The pane poll is started when the panel opens and cleared when it closes.

---

## New Session Modal

Triggered by **[+ New Session]** in the header. A centred modal overlay:
- Name input
- Project dropdown (same data as before)
- Project dir (auto-fills from project selection)
- **[Start Session]** button / **[Cancel]**

Replaces the always-visible form section in the current layout.

---

## Backend Changes

### New endpoint — `GET /agents/sessions/{id}/pane`

**`agents.py`** — new route:
```python
@bp.route("/agents/sessions/<session_id>/pane")
def session_pane(session_id):
    data, status = _proxy("GET", f"/sessions/{session_id}/pane")
    return jsonify(data), status
```

**`session-manager/app.py`** — new route on the session manager:
```python
@app.route("/sessions/<session_id>/pane")
def get_pane(session_id):
    session = next((s for s in _sessions if s["id"] == session_id), None)
    if not session:
        return jsonify({"error": "not found"}), 404
    if session.get("status") != "active":
        return jsonify({"lines": [], "active": False}), 200
    try:
        output = capture_pane(session["tmux_session"])
        lines = output.splitlines()[-40:]
        return jsonify({"lines": lines, "active": True}), 200
    except Exception as e:
        return jsonify({"lines": [], "active": False, "error": str(e)}), 200
```

No other backend changes. All other API routes stay as-is.

---

## Files Changed

| File | Change |
|---|---|
| `app/templates/agents.html` | Full rewrite — card grid, modal, panel, polling JS |
| `app/static/agents.css` | Full rewrite — new colour system, card, panel, terminal styles |
| `app/routes/agents.py` | Add `session_pane` route |
| `services/session-manager/app.py` | Add `get_pane` endpoint |

---

## Out of Scope

- Persistent session history / logs
- Multi-select actions
- Drag-to-reorder cards
- Dark/light theme toggle
- Mobile-optimised layout (panel overlays on narrow viewports is sufficient)
