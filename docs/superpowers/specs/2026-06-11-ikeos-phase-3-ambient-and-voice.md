# ʻIkeOS Brand Alignment — Phase 3: Ambient + Voice

**Date:** 2026-06-11
**Project:** obsidian-capture
**Status:** Approved
**Phase:** 3 of 3
**Depends on:** Phase 1 + Phase 2 landed and merged
**Estimated effort:** ~½ day
**Companion doc:** `docs/design/ikeos-interface-review.html` § 07–09

---

## Goal

Add the brand's ambient layer (constellation field, celestial loader) and patch the eleven UI strings that read as "generic dark tool" rather than "navigator's instrument".

After this phase, the app passes the squint test — at a glance, with no text legible, it reads as ʻIkeOS.

---

## 1. Constellation field — ambient background

**Goal:** A faint dotted starfield behind the workspace and tasks pages. The brand's signature ambient texture (`opacity: 0.30` max, never on long-form prose).

**File:** `app/static/style.css` — add a reusable class:

```css
.ike-constellation-field {
  position: relative;
}
.ike-constellation-field::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(1px 1px at 8% 20%,  rgba(180,151,255,0.50), transparent 60%),
    radial-gradient(1.5px 1.5px at 18% 64%, rgba(255,184,128,0.45), transparent 60%),
    radial-gradient(1px 1px at 28% 8%,  rgba(180,151,255,0.35), transparent 60%),
    radial-gradient(1px 1px at 42% 88%, rgba(180,151,255,0.40), transparent 60%),
    radial-gradient(1px 1px at 56% 32%, rgba(59,130,246,0.45),  transparent 60%),
    radial-gradient(1.5px 1.5px at 68% 12%, rgba(180,151,255,0.40), transparent 60%),
    radial-gradient(1px 1px at 78% 58%, rgba(255,184,128,0.40), transparent 60%),
    radial-gradient(1px 1px at 88% 28%, rgba(180,151,255,0.35), transparent 60%),
    radial-gradient(1px 1px at 92% 78%, rgba(180,151,255,0.30), transparent 60%);
  background-size: 100% 100%;
  opacity: 0.30;
  pointer-events: none;
  z-index: 0;
}
.ike-constellation-field > * { position: relative; z-index: 1; }
```

**Apply** to:

- `app/templates/workspace.html` → root `.workspace-page` element (add the class)
- `app/templates/dashboard.html` → wrap `{% block content %}` body in `<div class="ike-constellation-field" style="padding: 2rem 1.5rem; min-height: calc(100vh - 60px);">`

**Note on long-form pages:** Per the brand's "no constellation behind body text" rule, **do not** add the class to `entry.html` (where Markdown body text lives) or `capture.html` (the form column is dense). Workspace + tasks only.

---

## 2. LoadingMark — replace "Loading…"

**Goal:** Replace the literal `"Loading…"` text in `workspace.html`'s initial card-grid render with a slowly orbiting constellation glyph.

**File:** `app/static/style.css`:

```css
.ike-loading-mark {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-5);
  padding: var(--space-11) var(--space-5);
  color: var(--text-tertiary);
  font-family: var(--font-sans);
  font-size: var(--fs-caption);
  letter-spacing: 0.22em;
  text-transform: uppercase;
}
.ike-loading-orbit {
  width: 48px;
  height: 48px;
  position: relative;
  animation: ike-orbit var(--dur-orbit) linear infinite;
}
.ike-loading-orbit::before,
.ike-loading-orbit::after {
  content: "";
  position: absolute;
  border-radius: 50%;
}
.ike-loading-orbit::before {
  inset: 0;
  border: 1px solid rgba(180, 151, 255, 0.30);
}
.ike-loading-orbit::after {
  top: -3px;
  left: 50%;
  width: 6px;
  height: 6px;
  margin-left: -3px;
  background: var(--ike-sunset-orange);
  box-shadow: 0 0 12px rgba(255, 120, 73, 0.70);
}

@keyframes ike-orbit {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .ike-loading-orbit { animation: none; }
}
```

**File:** `app/templates/workspace.html` — replace the placeholder:

```html
<!-- before -->
<div class="empty-state">Loading…</div>

<!-- after -->
<div class="ike-loading-mark">
  <div class="ike-loading-orbit" aria-hidden="true"></div>
  <span>Tracing connections</span>
</div>
```

`agents.js` already replaces this on first response; no JS change needed.

---

## 3. Voice patches — eleven string edits

| File | Selector / context | Today | Change to |
|---|---|---|---|
| `app/templates/base.html` | `.nav-brand` | "Obsidian Capture" | (already done in Phase 1: ʻIkeOS wordmark) |
| `app/templates/base.html` | `<title>` block default | "Capture" | "ʻIkeOS" |
| `app/templates/workspace.html` | `#panel-placeholder` text | "Select a session to view details" | "Choose a session, or chart a new one." |
| `app/templates/workspace.html` | `#panel-cmd` placeholder | "Type a /command…" | "Tell ʻIkeOS what to do next…" |
| `app/templates/workspace.html` | "Live output" label | "Live output" | "Listening · live output" |
| `app/templates/workspace.html` | Capture submit | "Capture" | "Save to vault" |
| `app/templates/workspace.html` | Title input placeholder (col 3) | "Entry title…" | "What did you notice?" |
| `app/templates/capture.html` | Submit button | "Save entry" | "Save to vault" |
| `app/templates/capture.html` | Stay-on-page label | "Stay on this page after saving" | "Stay here after saving — keep capturing." |
| `app/templates/dashboard.html` | H1 (post Phase 2) | "Dashboard" | "What needs your attention." (already in Phase 2) |
| `app/templates/dashboard.html` | All-clear empty state | "All clear. Capture something." | "All clear. The map is quiet — capture something when you're ready." |
| `app/routes/capture.py` | Flash on success | (current: generic) | `flash("Saved. The vault remembers.")` |
| `app/static/agents.js` | Capture success message | "Saved ✓" | "Saved. The vault remembers." |
| `app/static/agents.js` | Capture error message | "Error" | "Couldn't save — try again in a moment." |

**Voice rules to keep applying** when this spec misses something:

- Second person ("you"), never "I" or "we" in product copy
- No em-dash for em-dash's sake, but freely otherwise
- No exclamation points
- No emoji — celestial glyphs only (`✦`, `✧`, `◦`, `ʻ`)
- Lowercase for state words (`thinking`, `working`, `stopped`); Title Case for actions (`New Session`, `Save to Vault`)
- Avoid: *unlock, supercharge, magic, AI-powered, intelligent assistant*. Prefer: *connects, recalls, surfaces, navigates, remembers*

---

## 4. Favicon + app icon

Already vendored in Phase 1 — Phase 3 ensures they're wired up:

```html
<!-- in base.html <head>, already added in Phase 1 -->
<link rel="icon" type="image/png" href="{{ url_for('static', filename='img/logo-ikeos-mark.png') }}">
<link rel="apple-touch-icon" href="{{ url_for('static', filename='img/logo-ikeos-appicon-dark.png') }}">
```

Verify both render correctly on Chrome, Safari, and (if applicable) the iOS "Add to Home Screen" lockup.

---

## 5. Selection + scrollbar polish

`tokens/base.css` already defines on-brand `::selection` (vibrant-purple at 40% alpha) and a thin lavender scrollbar. Phase 1 imported it; this phase verifies it's actually winning.

If any per-page CSS overrides scrollbar styling, remove it. The base styles should be the only place that touches `::selection` / `scrollbar-*`.

---

## Files Changed

| File | Change |
|---|---|
| `app/static/style.css` | `.ike-constellation-field`, `.ike-loading-mark`, `.ike-loading-orbit`, `@keyframes ike-orbit` |
| `app/templates/workspace.html` | Add `.ike-constellation-field` to root; LoadingMark markup; voice patches |
| `app/templates/dashboard.html` | Wrap body in `.ike-constellation-field`; empty-state copy |
| `app/templates/capture.html` | Voice patches (button, stay copy) |
| `app/templates/base.html` | `<title>` default |
| `app/routes/capture.py` | Flash messages |
| `app/static/agents.js` | Capture success/error strings |

---

## Acceptance criteria

1. Workspace and tasks pages show a faint starfield behind cards; long-form entry pages do not.
2. With `prefers-reduced-motion: reduce`, the orbit animation freezes; ambient texture remains.
3. Initial load of `/` shows the orbital loading mark, not the word "Loading…".
4. Eleven copy strings match the table above, byte-for-byte where applicable.
5. Favicon shows the ʻIkeOS constellation mark in browser tabs.
6. `prefers-reduced-motion` test: the session-dot pulse, command-pulse, and orbit all freeze; static visuals remain legible.
7. Squint test: open `/` at half-resolution, defocus. The image reads as the ʻIkeOS brand card — deep plum, lavender stars, a purple-orange focal point — within two seconds.

---

## Post-phase: optional follow-ups

These were intentionally **not** scoped into the three phases. Open issues if any feels valuable:

- **Lucide icons @ 1.5px stroke** for the nav links and command-send button. The brand uses Lucide; the app currently uses none. Adding them is one CDN link + ~6 SVG instances.
- **Real `Card`, `Badge`, `Button` React components** from the DS bundle (`app/static/ikeos/_ds_bundle.js`). Today the app is Jinja + vanilla JS; pulling the React components would require a build step. Worth it if the app gains more interactive surfaces.
- **A `LoadingMark` (React) component** replacing the CSS-only orbit, if/when React lands.
- **Light theme**. `tokens/colors.css` has the `[data-theme="light"]` scope ready; the app could opt in by setting that attribute on `<html>` based on a user preference.
