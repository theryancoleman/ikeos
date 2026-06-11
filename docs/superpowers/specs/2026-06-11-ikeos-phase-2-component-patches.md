# ʻIkeOS Brand Alignment — Phase 2: Component Patches

**Date:** 2026-06-11
**Project:** obsidian-capture
**Status:** Approved
**Phase:** 2 of 3
**Depends on:** Phase 1 landed and merged
**Estimated effort:** ~1 day
**Companion doc:** `docs/design/ikeos-interface-review.html` § 04–05

---

## Goal

With ʻIkeOS tokens live everywhere (Phase 1), patch the seven components that need brand-aware structure beyond a token swap: session cards, activity pills, type badges, status badges, dashboard headings, eyebrow labels, and the capture form.

After this phase, the workspace and tasks pages look like the "RECOMMENDED" mockups in the review doc.

---

## 1. Session card — halo + semantic dot

**File:** `app/static/workspace.css` → `.session-card`

**Today:** A 1px `var(--border)` rectangle with a 3px coloured top-border for active state, and a `box-shadow: 0 0 0 2px var(--accent)` ring for selected.

**Change to:** Plum-tinted card with a celestial halo on selected. Activity gets a glowing dot instead of a left-border colour.

```css
.session-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-4) var(--space-5);
  cursor: pointer;
  transition: border-color var(--dur-quick) var(--ease-out),
              box-shadow var(--dur-base) var(--ease-out);
}
.session-card:hover {
  border-color: var(--border-strong);
}
.session-card.selected {
  border-color: var(--brand-primary);
  box-shadow: var(--glow-purple-md);
}

/* Activity dot — replaces the 3px top-border pattern */
.card-name {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--fs-body-sm);
  font-weight: var(--fw-medium);
  color: var(--text-primary);
}
.session-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.session-dot.is-active {
  background: var(--sem-discovery);
  box-shadow: 0 0 8px rgba(45, 212, 191, 0.70);
  animation: ike-pulse 2.2s ease-in-out infinite;
}
.session-dot.is-stopped {
  background: var(--text-muted);
}

@keyframes ike-pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.45; }
}

@media (prefers-reduced-motion: reduce) {
  .session-dot.is-active { animation: none; }
}
```

**Template change:** `app/static/agents.js` — wherever the card HTML is built, prepend a `<span class="session-dot is-active">` (or `is-stopped`) inside `.card-name`, and remove the `border-top` colour swap.

---

## 2. Activity pills — lock to semantic palette

**File:** `app/static/workspace.css` → `.activity-thinking` / `.activity-working`

**Today:** Already nearly correct (lavender + sky blue). Lock the colours to tokens and add the pulse dot pattern.

```css
.activity-pill {
  font-size: var(--fs-caption);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 2px var(--space-3);
  border-radius: var(--radius-pill);
  border: 1px solid currentColor;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  line-height: 1.4;
}
.activity-pill::before {
  content: "";
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  animation: ike-pulse 2.2s ease-in-out infinite;
}
.activity-thinking { color: var(--ike-soft-lavender); background: rgba(180, 151, 255, 0.08); }
.activity-working  { color: var(--sem-knowledge);    background: rgba(59, 130, 246, 0.08); }
```

---

## 3. Type & status badges — semantic colour, pill shape

**File:** `app/static/style.css` → existing `.badge` + `.type-*` / `.status-*` rules

Phase 1 already mapped the colours. Phase 2 normalizes the shape and adds the lead-dot pattern from the design system's `Badge` component:

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 2px var(--space-3);
  border-radius: var(--radius-pill);
  font-family: var(--font-sans);
  font-size: var(--fs-caption);
  font-weight: var(--fw-medium);
  letter-spacing: 0.04em;
  border: 1px solid currentColor;
  background: transparent;
  text-transform: none;  /* lowercase reads calmer on dark plum */
}
.badge::before {
  content: "";
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

/* Type — what kind of entry */
.type-note { color: var(--sem-knowledge); background: rgba(59, 130, 246, 0.08); }
.type-idea { color: var(--ike-soft-lavender); background: rgba(180, 151, 255, 0.08); }
.type-bug  { color: var(--sem-insight); background: rgba(255, 120, 73, 0.08); }

/* Status — where it is */
.status-new        { color: var(--sem-insight); background: rgba(255, 120, 73, 0.10); }
.status-open       { color: var(--sem-knowledge); }
.status-inprogress { color: var(--ike-soft-lavender); }
.status-done       { color: var(--sem-discovery); }
.status-deferred   { color: var(--text-muted); border-color: var(--border-default); }
```

Note: Phase 1 set lowercase via removing `text-transform: uppercase`. Confirm `{{ e.status }}` in templates renders without `.upper()`.

---

## 4. Dashboard H1 — earn the serif

**File:** `app/templates/dashboard.html` + `app/static/style.css`

**Change template:**

```html
<header class="page-header">
  <span class="ike-eyebrow">Tasks</span>
  <h1>What needs your attention.</h1>
  <p class="page-subtitle">
    {{ projects | length }} projects · {{ in_flight | length }} in flight · {{ needs_triage | length }} awaiting triage
  </p>
</header>
```

**Add CSS:**

```css
.page-header {
  margin-bottom: var(--space-9);
}
.page-header h1 {
  font-family: var(--font-display);
  font-size: 36px;
  line-height: 1.06;
  letter-spacing: -0.026em;
  font-weight: var(--fw-bold);
  color: var(--text-primary);
  margin: var(--space-2) 0 var(--space-3);
}
.page-subtitle {
  font-family: var(--font-mono);
  font-size: var(--fs-caption);
  color: var(--text-tertiary);
}
```

Apply the same pattern to `app/templates/capture.html` (`<h1>New entry</h1>` → eyebrow + display H1: "Capture something."), `app/templates/entry.html`, and `app/templates/project.html` (`<h1>{{ name }}</h1>` already exists, just inherits new style).

---

## 5. Eyebrow class — replace fake-eyebrow `h2`s

**File:** `app/static/style.css` — remove the existing `h2` override entirely (the rule that does `font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em`). It's an almost-eyebrow that the brand replaces with the real thing.

**Templates** — wherever an `<h2>` is used as a section label (not a heading), replace it with the canonical eyebrow markup that `base.css` already provides:

```html
<!-- before -->
<h2>Projects</h2>

<!-- after -->
<div class="ike-eyebrow">Projects <span class="eyebrow-count">/ {{ projects | length }}</span></div>
```

**Add to `style.css`:**

```css
.eyebrow-count {
  color: var(--ike-sunset-orange);
  font-family: var(--font-mono);
  letter-spacing: 0;
  margin-left: var(--space-2);
}
```

Real H2s (entry titles, etc.) keep the `<h2>` tag and inherit the brand's display sizing from `base.css`.

---

## 6. Capture form — semantic chips for type, eyebrow labels, focus halo

**File:** `app/templates/capture.html` + `app/static/style.css`

**Change the type select to a chip group** (still posts `name="type"` so the route is unchanged):

```html
<div class="field">
  <label class="ike-eyebrow" for="type">Type</label>
  <div class="type-chips" role="radiogroup">
    <input type="radio" name="type" id="type-note" value="note" checked>
    <label class="type-chip type-chip-note" for="type-note">Note</label>
    <input type="radio" name="type" id="type-idea" value="idea">
    <label class="type-chip type-chip-idea" for="type-idea">Idea</label>
    <input type="radio" name="type" id="type-bug" value="bug">
    <label class="type-chip type-chip-bug" for="type-bug">Bug</label>
  </div>
</div>
```

**JS:** `updateFields(type)` is currently called from `onchange` on the `<select>`. Re-bind to the radio inputs:

```js
document.querySelectorAll('input[name="type"]').forEach(el => {
  el.addEventListener('change', e => updateFields(e.target.value));
});
```

**Add CSS:**

```css
.type-chips { display: flex; gap: var(--space-3); }
.type-chips input[type="radio"] { position: absolute; opacity: 0; pointer-events: none; }
.type-chip {
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-pill);
  border: 1px solid currentColor;
  font-size: var(--fs-body-sm);
  cursor: pointer;
  background: transparent;
  user-select: none;
  transition: background var(--dur-quick) var(--ease-out);
}
.type-chip-note { color: var(--sem-knowledge); }
.type-chip-idea { color: var(--ike-soft-lavender); }
.type-chip-bug  { color: var(--sem-insight); }
.type-chips input:checked + .type-chip { background: color-mix(in oklch, currentColor 14%, transparent); }
.type-chips input:focus-visible + .type-chip { box-shadow: var(--ring-focus); }
```

**Replace every `<label>` above a form field** with the eyebrow class:

```html
<label class="ike-eyebrow" for="title">Title</label>
```

Apply to: `capture.html` (project, title, body, priority, effort, severity, steps), `workspace.html` (the column-3 capture form), `project.html` (status select).

**Input focus halo** — `app/static/style.css`:

```css
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--brand-primary);
  box-shadow: var(--glow-purple-sm);
}
```

(Phase 1 swapped `--accent` → `--brand-primary`. Phase 2 adds the halo.)

**Add the keyboard hint to the submit row:**

```html
<div class="capture-footer">
  <span class="capture-help"><kbd>⌘</kbd>+<kbd>↵</kbd> to save</span>
  <button type="submit" class="ike-btn-primary">Save to vault</button>
</div>
```

```css
.capture-help {
  font-family: var(--font-mono);
  font-size: var(--fs-caption);
  color: var(--text-tertiary);
}
.capture-help kbd {
  font-family: var(--font-mono);
  background: var(--bg-inset);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xs);
  padding: 1px 6px;
  font-size: 11px;
}
.ike-btn-primary {
  background: var(--brand-primary);
  color: #FFFFFF;
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-6);
  font-family: var(--font-sans);
  font-size: var(--fs-body-sm);
  font-weight: var(--fw-medium);
  box-shadow: var(--glow-purple-sm);
  cursor: pointer;
  transition: box-shadow var(--dur-quick) var(--ease-out);
}
.ike-btn-primary:hover { box-shadow: var(--glow-purple-md); opacity: 1; }
.ike-btn-primary:active { transform: scale(0.98); }
```

Add the keyboard shortcut listener:

```js
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    document.querySelector('form')?.requestSubmit();
  }
});
```

---

## 7. Workspace column heads — use eyebrows

**File:** `app/templates/workspace.html` — replace the three `<h2>` in `.col-header` with `<span class="ike-eyebrow">` and **add a live count** where it adds value:

```html
<div class="col-header">
  <span class="ike-eyebrow">Sessions <span class="eyebrow-count" id="session-count">/ —</span></span>
  <button class="ike-btn-primary" onclick="openModal()">＋ New Session</button>
</div>
```

`agents.js` updates `#session-count` whenever it re-renders cards: `el.textContent = '/ ' + String(sessions.length).padStart(2, '0');`

---

## Files Changed

| File | Change |
|---|---|
| `app/static/workspace.css` | `.session-card`, `.activity-*`, `.pane-output`, focus halos |
| `app/static/style.css` | `.badge` + `.type-*` + `.status-*` + `.page-header` + `.type-chips` + `.ike-btn-primary` |
| `app/templates/base.html` | (unchanged from Phase 1) |
| `app/templates/dashboard.html` | Eyebrow + display H1, eyebrow on section labels |
| `app/templates/workspace.html` | Eyebrows on column heads, session-count, `ike-btn-primary` |
| `app/templates/capture.html` | Type chip group, eyebrow labels, ⌘↵ hint, primary button |
| `app/templates/project.html` | Eyebrow labels, status badge structure |
| `app/templates/entry.html` | Eyebrow + display H1 |
| `app/static/agents.js` | Session-dot in card markup, session-count, ⌘↵ listener |

---

## Acceptance criteria

1. Selected session card emits a soft purple halo (not a hard border).
2. Active sessions show a green pulsing 6px dot before the name; stopped sessions show a static grey dot.
3. Activity pills ("thinking", "working") each carry a pulsing 4px dot in the matching colour.
4. Every form `<label>` and section heading uses `.ike-eyebrow` (11px, 0.22em tracking, lavender-tertiary).
5. Dashboard H1 reads in DM Serif Display at 36px with a mono subtitle line beneath it.
6. Capture form Type field is three pill chips, not a `<select>`.
7. Capture submit button is the brand purple with a purple halo; hover thickens the halo, no translation.
8. `⌘↵` (or `Ctrl+↵`) submits the capture form from any focused field.
9. All existing tests still pass; `POST /capture` and `POST /capture/json` still accept the same fields.
