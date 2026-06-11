# ʻIkeOS Brand Alignment — Phase 1: Tokens + Identity

**Date:** 2026-06-11
**Project:** obsidian-capture
**Status:** Approved
**Phase:** 1 of 3
**Estimated effort:** ~1 day
**Companion doc:** `docs/design/ikeos-interface-review.html` (open in browser for visual reference)

---

## Goal

Replace the two ad-hoc dark-mode token sets in `app/static/style.css` and `app/static/workspace.css` with a single import of the **ʻIkeOS Design System** tokens (already vendored at `app/static/ikeos/`), and rebrand the navigation from "Obsidian Capture" to **ʻIkeOS**.

After this phase, every surface, text colour, border, and font in the app inherits from the ʻIkeOS system. No raw hex codes remain in app CSS.

---

## Why this first

The two existing stylesheets each define their own `:root` block and have **already drifted**:

| Variable | `style.css` | `workspace.css` |
|---|---|---|
| Canvas | `#1A1A2E` (blue-black) | `#1A1A1A` (true black) |
| Accent | `#7C5CBF` (dusty violet) | `#7C6AF7` (cold violet) |
| Surface | `#16213E` (navy) | `#1A1A1A` (true black) |

Neither matches the brand (`#120A1F` plum, `#7C3AED` vibrant purple). Phase 1 is a token swap — it touches every screen at once and gets the app ~80% to on-brand visually with minimal logic change.

---

## Vendored assets (already in repo)

These were delivered alongside the spec:

```
app/static/ikeos/
├── styles.css              ← single import entry
└── tokens/
    ├── base.css            ← reset + font-family on body + .ike-eyebrow
    ├── colors.css          ← deep plum, vibrant purple, sunset orange, semantic aliases
    ├── elevation.css       ← --glow-purple-md, --ring-focus, etc.
    ├── motion.css          ← --dur-quick, --ease-out, prefers-reduced-motion
    ├── spacing.css         ← --space-1..14, --radius-*, --container-*
    └── typography.css      ← Geist + DM Serif Display + Geist Mono via Google Fonts @import

app/static/img/
├── logo-ikeos-mark.png             ← constellation mark only (favicon, nav)
├── logo-ikeos-mark-color-dark.png  ← coloured mark on dark
├── logo-ikeos-color-dark.png       ← full wordmark lockup
└── logo-ikeos-appicon-dark.png     ← rounded-square app icon
```

`styles.css` is the single entry point — it `@import`s all six token files. Consumers only ever reference `styles.css`.

---

## Changes

### 1. `app/static/style.css` — replace `:root` block

**Delete** the entire `:root { … }` block at the top of the file (lines 1–18 currently).

**Add** at the very top:

```css
/* Inherit every token from the ʻIkeOS Design System. */
@import url("ikeos/styles.css");
```

Then walk the rest of the file and swap variables per the table below. Replacements are mechanical — no other logic changes.

| Find | Replace with | Notes |
|---|---|---|
| `var(--bg)` | `var(--bg-canvas)` | page background |
| `var(--surface)` | `var(--bg-surface)` | nav, cards, inputs |
| `var(--border)` | `var(--border-default)` | every border |
| `var(--text)` | `var(--text-primary)` | body text |
| `var(--text-muted)` | `var(--text-tertiary)` | helper / dates / "v2026.06.11" |
| `var(--accent)` | `var(--brand-primary)` | links, focus, brand wordmark |
| `font-family: system-ui, sans-serif;` | *(delete — inherits from base.css)* | body sets `var(--font-sans)` |
| `font-family: monospace;` | `font-family: var(--font-mono);` | `.nav-version`, `.entry-date`, `.status-select` |
| `border-radius: 4px;` (inputs/buttons) | `border-radius: var(--radius-md);` | 10px on inputs/buttons |
| `border-radius: 6px;` (cards) | `border-radius: var(--radius-lg);` | 14px on cards |
| `border-radius: 3px;` (badges) | `border-radius: var(--radius-pill);` | pill on every chip/badge |

**Type/status/severity/priority badges** — replace the eight hand-mixed `--badge-*` hexes:

| Class | Old hex | New value |
|---|---|---|
| `.type-note` | `#2D6A4F` | `background: rgba(59,130,246,0.12); color: var(--sem-knowledge); border: 1px solid rgba(59,130,246,0.30);` |
| `.type-idea` | `#1E4D8C` | `background: rgba(180,151,255,0.10); color: var(--ike-soft-lavender); border: 1px solid rgba(180,151,255,0.25);` |
| `.type-bug` | `#7B2D2D` | `background: rgba(255,120,73,0.10); color: var(--sem-insight); border: 1px solid rgba(255,120,73,0.30);` |
| `.status-new` | `#5A3E8C` | `color: var(--ike-sunset-orange);` (triage-indicator pill) |
| `.status-open` | `#2D5A8C` | `color: var(--sem-knowledge);` |
| `.status-inprogress` | `#8C6A2D` | `color: var(--sem-understanding);` |
| `.status-done` | `#2D7A4F` | `color: var(--sem-discovery);` |
| `.status-deferred` | `#4A4A4A` | `color: var(--text-muted);` |
| `.severity-*` / `.priority-*` | mixed | move to alpha-over-semantic pattern (low → discovery, medium → understanding, high → insight, critical → status-error) |

### 2. `app/static/workspace.css` — replace `.workspace-page` token block

**Delete** the entire `.workspace-page { --bg-card: …; --accent: …; … }` block (currently lines 2–14).

`.workspace-page` keeps only its layout rules. Throughout the file:

| Find | Replace |
|---|---|
| `var(--bg-card)` | `var(--bg-surface)` |
| `var(--bg-panel)` | `var(--bg-raised)` |
| `var(--bg-pane)` | `var(--bg-inset)` |
| `var(--accent)` (≈9 occurrences) | `var(--brand-primary)` |
| `var(--success)` | `var(--sem-discovery)` |
| `var(--warn)` | `var(--sem-understanding)` |
| `var(--danger)` | `var(--status-error)` |
| `var(--thinking)` | `var(--ike-soft-lavender)` |
| `var(--working)` | `var(--sem-knowledge)` |
| Raw `#111` (input backgrounds) | `var(--bg-inset)` |
| Raw `#141414`, `#1a1a1a`, `#0f3460` | `var(--bg-raised)` / `var(--bg-surface)` |
| Font stack `'Consolas', 'Monaco', monospace` on `.pane-output` | `var(--font-mono)` |

### 3. `app/templates/base.html` — rebrand the nav

**Replace** the existing `<nav>` block with:

```html
<nav class="ike-nav">
  <a href="{{ url_for('agents.home') }}" class="nav-brand" aria-label="ʻIkeOS home">
    <img src="{{ url_for('static', filename='img/logo-ikeos-mark.png') }}"
         alt="" class="nav-mark" width="22" height="22">
    <span class="nav-wordmark"><span class="okina">ʻ</span>IkeOS</span>
  </a>
  <a href="{{ url_for('agents.home') }}"   class="nav-link {% if request.endpoint == 'agents.home' %}is-active{% endif %}">Home</a>
  <a href="{{ url_for('browse.tasks') }}"  class="nav-link {% if request.endpoint == 'browse.tasks' %}is-active{% endif %}">Tasks</a>
  <a href="{{ url_for('agents.agents') }}" class="nav-link {% if request.endpoint == 'agents.agents' %}is-active{% endif %}">Sessions</a>
  <a href="{{ url_for('capture.capture_form') }}" class="nav-link {% if request.endpoint == 'capture.capture_form' %}is-active{% endif %}">Capture</a>
  {% if config_version %}<span class="nav-version">{{ config_version }}</span>{% endif %}
</nav>
```

And in `app/static/style.css`, replace the existing `nav` / `.nav-brand` / `.nav-link` rules with:

```css
.ike-nav {
  background: rgba(11, 6, 26, 0.65);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--border-subtle);
  padding: 12px 20px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 18px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  text-decoration: none;
}
.nav-brand:hover { color: var(--text-primary); text-decoration: none; }
.nav-mark { display: block; }
.nav-wordmark .okina {
  color: var(--ike-sunset-orange);
  text-shadow: 0 0 12px rgba(255, 120, 73, 0.45);
}
.nav-link {
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-secondary);
  text-decoration: none;
  padding: 2px 0;
  position: relative;
}
.nav-link:hover { color: var(--text-primary); text-decoration: none; }
.nav-link.is-active { color: var(--text-primary); }
.nav-link.is-active::after {
  content: "";
  position: absolute;
  left: 0; right: 0; bottom: -6px;
  height: 1px;
  background: var(--ike-sunset-orange);
  box-shadow: 0 0 6px rgba(255, 120, 73, 0.7);
}
.nav-version {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}
```

### 4. `app/templates/base.html` — title + favicon

Update `<head>`:

```html
<title>{% block title %}ʻIkeOS{% endblock %} — ʻIkeOS</title>
<link rel="icon" type="image/png" href="{{ url_for('static', filename='img/logo-ikeos-mark.png') }}">
<link rel="apple-touch-icon" href="{{ url_for('static', filename='img/logo-ikeos-appicon-dark.png') }}">
```

---

## Files Changed

| File | Change |
|---|---|
| `app/static/ikeos/**` | **Vendored** — do not edit |
| `app/static/img/logo-ikeos-*.png` | **Vendored** — do not edit |
| `app/static/style.css` | Delete `:root`, add `@import`, swap vars per table, rebrand nav rules |
| `app/static/workspace.css` | Delete `.workspace-page` token block, swap vars per table |
| `app/templates/base.html` | Replace nav, update `<title>`, add favicon links |

---

## Acceptance criteria

1. `grep -E "#[0-9A-Fa-f]{3,6}" app/static/style.css app/static/workspace.css` returns **zero hex codes** (every colour goes through `var(--…)`).
2. `grep "system-ui" app/static/` returns nothing.
3. The browser tab shows "ʻIkeOS" as the title and the constellation mark as the favicon.
4. The nav reads **ʻ**IkeOS in DM Serif Display, with an orange okina, on a blurred plum bar.
5. The active nav link shows a glowing sunset-orange whisker under it (not just colour shift).
6. Visiting `/`, `/tasks`, `/agents`, and `/capture` — every surface is on the plum canvas; no navy, no blue-black, no #1A1A1A.
7. The five tests in `tests/test_capture.py` still pass.

---

## Out of scope (Phase 2 + 3 will cover)

- Session card halo + activity pulse — Phase 2
- Dashboard H1 typography (DM Serif Display) — Phase 2
- Eyebrow class on `h2` section labels — Phase 2
- Constellation field background — Phase 3
- Voice/copy edits — Phase 3
