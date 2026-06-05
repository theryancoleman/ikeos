# Cursor Visibility Fix + Stay Checkbox Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the invisible cursor in the EasyMDE description field and make the "Stay on this page" checkbox remember its state until explicitly unchecked.

**Architecture:** Two independent, self-contained changes — one CSS rule in `style.css`, one JS block in `capture.html`. No server-side changes. Both are guarded with lightweight regression tests that verify content appears in rendered responses or static files.

**Tech Stack:** Flask, Jinja2, EasyMDE/CodeMirror, localStorage (browser), pytest

---

## Files

| Action | File | Change |
|---|---|---|
| Modify | `app/static/style.css` | Add one CSS rule for `.CodeMirror-cursor` |
| Modify | `app/templates/capture.html` | Add ~6 lines of localStorage JS |
| Modify | `tests/test_capture.py` | Add two regression tests |

---

## Task 1: Fix invisible cursor in EasyMDE

CodeMirror renders its cursor as a DOM element with `border-left: 1px solid black`. On the dark
surface (`#16213e`) this is invisible. Fix: override the border colour with `var(--text)`.

**Files:**
- Modify: `tests/test_capture.py`
- Modify: `app/static/style.css`

- [ ] **Step 1: Write the failing test**

Add to the bottom of `tests/test_capture.py`:

```python
def test_style_css_contains_codemirror_cursor_rule():
    with open("app/static/style.css") as f:
        css = f.read()
    assert "CodeMirror-cursor" in css
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
cd /mnt/c/Server/projects/obsidian-capture
pytest tests/test_capture.py::test_style_css_contains_codemirror_cursor_rule -v
```

Expected: `FAILED — AssertionError` (rule not yet present)

- [ ] **Step 3: Add the CSS rule**

In `app/static/style.css`, locate the comment `/* EasyMDE dark theme overrides */` block
(around line 253). Add the new rule after the existing `.CodeMirror-scroll` block:

```css
.EasyMDEContainer .CodeMirror-cursor {
  border-left-color: var(--text);
}
```

The full EasyMDE block after the change should end:

```css
.EasyMDEContainer .CodeMirror-scroll {
  min-height: 120px;
}

.EasyMDEContainer .CodeMirror-cursor {
  border-left-color: var(--text);
}
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
pytest tests/test_capture.py::test_style_css_contains_codemirror_cursor_rule -v
```

Expected: `PASSED`

- [ ] **Step 5: Run the full test suite — expect all green**

```bash
pytest -v
```

Expected: all tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add app/static/style.css tests/test_capture.py
git commit -m "fix: make CodeMirror cursor visible on dark background"
```

---

## Task 2: Persist "Stay on this page" checkbox via localStorage

When the user checks "Stay on this page", that preference should be remembered across page loads
and direct navigation until they explicitly uncheck it.

**Files:**
- Modify: `tests/test_capture.py`
- Modify: `app/templates/capture.html`

- [ ] **Step 1: Write the failing test**

Add to the bottom of `tests/test_capture.py`:

```python
def test_capture_form_contains_stay_persistence_js(client):
    response = client.get("/capture")
    assert b"captureStay" in response.data
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
pytest tests/test_capture.py::test_capture_form_contains_stay_persistence_js -v
```

Expected: `FAILED — AssertionError` (`captureStay` not yet present in rendered HTML)

- [ ] **Step 3: Add the localStorage JS to `capture.html`**

In `app/templates/capture.html`, locate the first `<script>` block (the one with `updateFields`
and `updateProject`, ending around line 121). Add the persistence logic **inside that block**,
after the existing functions:

```html
<script>
function updateFields(type) {
  document.getElementById('idea-fields').classList.add('hidden');
  document.getElementById('bug-fields').classList.add('hidden');
  if (type === 'idea') document.getElementById('idea-fields').classList.remove('hidden');
  if (type === 'bug') document.getElementById('bug-fields').classList.remove('hidden');
}
function updateProject(value) {
  const field = document.getElementById('future-project-field');
  const input = document.getElementById('future_project_name');
  if (value === '__future__') {
    field.classList.remove('hidden');
    input.required = true;
  } else {
    field.classList.add('hidden');
    input.required = false;
  }
}

(function () {
  const stayBox = document.querySelector('input[name="stay"]');
  if (localStorage.getItem('captureStay') === '1') stayBox.checked = true;
  stayBox.addEventListener('change', function () {
    localStorage.setItem('captureStay', this.checked ? '1' : '0');
  });
})();
</script>
```

The IIFE runs on load — restores state from localStorage, then wires up the change listener.

- [ ] **Step 4: Run the test — expect PASS**

```bash
pytest tests/test_capture.py::test_capture_form_contains_stay_persistence_js -v
```

Expected: `PASSED`

- [ ] **Step 5: Run the full test suite — expect all green**

```bash
pytest -v
```

Expected: all tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add app/templates/capture.html tests/test_capture.py
git commit -m "feat: persist stay-on-page checkbox state via localStorage"
```

---

## Done

Both changes are independent — Task 2 can be done before Task 1 with no conflict. After both
commits, visually verify in the running app:

1. Load `/capture` — click in the Description field — cursor should be visible.
2. Check "Stay on this page" — save an entry — checkbox should still be checked on reload.
3. Uncheck the box — reload the page — box should be unchecked.
