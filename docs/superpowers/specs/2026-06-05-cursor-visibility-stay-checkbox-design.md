# Design: Cursor Visibility Fix + Stay Checkbox Persistence

**Date:** 2026-06-05
**Scope:** Two small independent changes to `capture.html` and `style.css`

---

## Change 1: Fix cursor visibility in EasyMDE

### Problem
CodeMirror (the editor underlying EasyMDE) renders its text cursor as a DOM element with
`border-left: 1px solid black`. On the app's dark surface colour (`#16213e`) this is invisible,
making the description field appear uneditable.

### Fix
Add one CSS rule to `app/static/style.css` inside the existing EasyMDE dark-theme block:

```css
.EasyMDEContainer .CodeMirror-cursor {
  border-left-color: var(--text);
}
```

`var(--text)` resolves to `#e0e0e0` — light enough to be clearly visible on the dark background.

### Files changed
- `app/static/style.css` — add one rule to the EasyMDE section

---

## Change 2: Persist "stay on this page" checkbox

### Requirement
The "Stay on this page after saving" checkbox should remember its state. Once checked, it
remains checked across form reloads, redirects, and future visits — until the user explicitly
unchecks it.

### Approach: localStorage
- On checkbox `change`, write `captureStay` (`"1"` or `"0"`) to `localStorage`.
- On page load, read `captureStay` and set the checkbox accordingly.
- No server changes required — this is a UI preference.

### Behaviour
| Scenario | Result |
|---|---|
| User checks the box and saves | Redirects back to `/capture`; box is pre-checked |
| User navigates directly to `/capture` | Box is pre-checked (localStorage remembers) |
| User unchecks the box | State saved; next load starts unchecked |
| Fresh browser / cleared storage | Box defaults to unchecked (current behaviour) |

### Files changed
- `app/templates/capture.html` — add ~6 lines of JS in the existing `<script>` block

---

## What is not changing
- Server-side route logic in `capture.py` — no changes needed
- The redirect-to-`/capture?project=...` behaviour on stay — unchanged
- Any other template or service file
