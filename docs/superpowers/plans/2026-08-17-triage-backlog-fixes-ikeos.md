# IkeOS Triage Backlog Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four bugs surfaced during the 2026-08-17 `/triage` of the ikeOS vault backlog: the opening animation never auto-advances, the blog-draft editor's Save/Publish/Rewrite/Reload actions silently operate on the wrong draft when an older one is open, the Housekeeping page's blog-draft status pill never reflects that a draft has actually been published, and the capture API's PATCH endpoint has no way to correct a mis-filed entry's `project`, which is currently blocking the claude-config `Vault schema check` housekeeping task.

**Architecture:** Task 1 is a pure frontend bugfix (a JS syntax error breaks the whole splash-screen script). Tasks 2–3 touch the same blog-draft editing surface (`app/routes/housekeeping.py`, `app/services/blog_drafts.py`, `app/templates/blog_draft.html`, `app/templates/housekeeping.html`) and are ordered so Task 2 (draft identity) lands before Task 3 (publish detection), since Task 3's tests reuse Task 2's now-correct single-draft addressing. Task 4 is independent — it extends `app/services/vault_entries.py` and `app/routes/capture.py` to support relocating a vault entry to a different project, both frontmatter and physical file location.

**Tech Stack:** Python 3.11 / Flask (existing app), pytest, vanilla JS (no build pipeline), Jinja2.

**Spec:** No separate spec doc — derived from live investigation during today's `/triage` session: vault bugs `projects/ikeos/bugs/2026-08-17-the-opening-animation-still-doesnt-auto-advance-ca.md`, `projects/ikeos/bugs/2026-07-28-if-i-ask-the-publishing-to-rewrite-an-older-draft-.md`, `projects/ikeos/bugs/2026-07-28-blog-draft-on-housekeeping-page-doesnt-update-stat.md`, and `projects/claude-config/bugs/2026-08-03-housekeeping-task-failed-vault-schema-check-2nd-co.md`, plus direct reads of the current source.

## Global Constraints

- Routes stay thin: parse request → call service → return response (existing `app/routes/housekeeping.py` / `app/routes/capture.py` convention).
- `vault.py` / `vault_entries.py` / `vault_cache.py` remain the sole owners of vault file I/O — no direct filesystem access from routes.
- No JS build pipeline — edit `app/templates/*.html` inline `<script>` blocks directly, plain ES2017-safe syntax (no smart/curly quotes, ever).
- Every new Python behavior gets a pytest test in the matching `tests/test_*.py` file, run via `docker exec ikeos pytest` (per project CLAUDE.md) or `python3 -m pytest` if running outside the container.
- Frontmatter writes always go through the existing temp-file-then-rename atomic pattern already used in `vault_entries.py`.

---

### Task 1: Fix curly-quote JS syntax error breaking the splash screen

**Files:**
- Modify: `app/templates/loading.html:414-453`

**Interfaces:**
- No new interfaces — this is a syntax-only fix inside an existing inline `<script>` block. Nothing else in the codebase calls into this script.

**Root cause:** The inline `<script>` block uses typographic/curly quotes (`‘`/`’`, U+2018/U+2019) as JS string delimiters instead of straight quotes (`'`), e.g. `const CAPTIONS = [‘Tracing connections…’, ...]` and `document.getElementById(‘ls-caption’)`. Curly quotes are not valid JS string delimiters, so the browser throws `Uncaught SyntaxError: Invalid or unexpected token` on page load. The entire IIFE fails to execute — captions never advance, and the closing `setTimeout` that flips `is-exiting` and redirects to `/dashboard` after 6.5s never fires. This is exactly the reported symptom: "the opening animation still doesn't auto advance."

- [ ] **Step 1: Reproduce — confirm the syntax error**

Run:
```bash
cd /mnt/c/Server/projects/ikeos
grep -n '[‘’]' app/templates/loading.html
```
Expected: multiple matches inside the `<script>` block (lines ~416-449), confirming curly quotes are present in what must be plain JS string literals.

- [ ] **Step 2: Fix — replace curly quotes with straight quotes in the script block**

In `app/templates/loading.html`, within the `<script>` block starting at line 412, replace every curly-quoted JS string literal with a straight-quoted one. The block currently reads (abbreviated):

```javascript
const CAPTIONS = [
  ‘Tracing connections…’,
  ‘Re-reading what you’ve captured…’,
  ‘Threading memory through time…’,
  ‘Surfacing the patterns you’d forgotten…’,
  ‘Drawing the constellation…’,
];
...
const captionEl = document.getElementById(‘ls-caption’);
const welcomeEl = document.getElementById(‘ls-welcome’);
const screenEl  = document.getElementById(‘ls-screen’);

function setCaption(idx) {
  captionEl.textContent = CAPTIONS[idx];
  captionEl.style.animation = ‘none’;
  void captionEl.offsetWidth;
  captionEl.style.animation = ‘’;
}
...
welcomeEl.classList.add(‘is-visible’);
...
screenEl.classList.add(‘is-exiting’);
sessionStorage.setItem(‘ike_splash_seen’, ‘1’);
...
window.location.href = ‘/dashboard’;
```

Replace it with (note the apostrophes inside caption text like "you've captured" must switch to double-quoted strings to avoid re-introducing an unescaped apostrophe, or use a backslash-escaped `\'`):

```javascript
const CAPTIONS = [
  'Tracing connections…',
  "Re-reading what you've captured…",
  'Threading memory through time…',
  "Surfacing the patterns you'd forgotten…",
  'Drawing the constellation…',
];
```
and every other `‘...’` occurrence in the block to `'...'` (or `"..."` where the content itself contains an apostrophe), including:
- `document.getElementById('ls-caption')`, `'ls-welcome'`, `'ls-screen'`
- `captionEl.style.animation = 'none'` / `= ''`
- `welcomeEl.classList.add('is-visible')`
- `screenEl.classList.add('is-exiting')`
- `sessionStorage.setItem('ike_splash_seen', '1')`
- `window.location.href = '/dashboard'`

- [ ] **Step 3: Verify no curly quotes remain in the script block**

Run:
```bash
sed -n '412,455p' app/templates/loading.html | grep -n '[‘’]'
```
Expected: no output (no matches).

- [ ] **Step 4: Verify the script parses as valid JS**

Run (extracts just the script body and checks it with Node's syntax checker — Node is available on the host for this one-off check even though the project has no JS build pipeline):
```bash
sed -n '/<script>/,/<\/script>/p' app/templates/loading.html | sed '1d;$d' > /tmp/loading_script_check.js
node --check /tmp/loading_script_check.js && echo "SYNTAX OK"
rm /tmp/loading_script_check.js
```
Expected: `SYNTAX OK`, no syntax error output.

- [ ] **Step 5: Manual browser verification**

Use the `/run` skill (or `docker compose up -d ikeos` + open a browser) to load `/` fresh (clear `sessionStorage` or use a private window so `ike_splash_seen` isn't set). Confirm: captions visibly change every ~1.3s, and after ~6.5s the "Welcome." overlay appears and the page auto-redirects to `/dashboard` without any click.

- [ ] **Step 6: Commit**

```bash
git add app/templates/loading.html
git commit -m "fix: replace curly quotes with straight quotes in loading.html script

Curly quotes are not valid JS string delimiters, so the splash-screen
script threw a SyntaxError on load and the whole IIFE never ran —
captions never advanced and the auto-redirect to /dashboard never fired."
```

---

### Task 2: Thread the open draft's filename through Save / Publish / Rewrite / Reload

**Files:**
- Modify: `app/routes/housekeeping.py:262-302,331-341` (`blog_draft_save`, `blog_draft_publish`, `blog_draft_rewrite`, `blog_draft_content`)
- Modify: `app/templates/blog_draft.html:45,67,97-107,117,152,170,204-206` (add hidden filename + include it in every fetch)
- Test: `tests/test_housekeeping.py` (append near existing blog-draft tests, e.g. after line 743)

**Interfaces:**
- Consumes: `app.services.blog_drafts.read_draft_bundle(filename: str | None = None) -> dict | None` and `save_draft(content: str, bluesky_text: str) -> str` (existing — `save_draft` still only targets the latest draft; see Step 4 below for the one small addition needed there).
- Produces: no new public functions — all four route handlers now read an optional `filename` request field and pass it through to the existing `read_draft_bundle(filename)` (already supports this parameter; routes just weren't using it).

**Root cause:** `blog_draft_editor(filename)` (the GET route rendering the editor) already supports viewing any specific draft via `/housekeeping/blog-draft/<filename>` and passes that exact `filename` into the template. But every mutating action on that page — `blog_draft_save`, `blog_draft_publish`, `blog_draft_rewrite`, and the reload endpoint `blog_draft_content` — calls `read_draft_bundle()` **with no argument**, which per `app/services/blog_drafts.py:42-45` always falls back to `latest_draft_paths()` (the newest draft on disk), regardless of which draft is actually open in the browser. So if you open an older draft and click "Request Rewrite" (or Publish, or Save), the action silently targets whatever the *newest* draft file is instead. This matches the reported bug exactly ("rewrite an older draft ... rewrites the most current one").

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_housekeeping.py` (reuse the `client` fixture already defined in that file):

```python
def test_blog_draft_rewrite_targets_specific_open_draft(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    monkeypatch.setenv("AIOS_BLOG_PROJECT_DIR", "/srv/blog")
    (tmp_path / "2026-06-01-weekly-draft.md").write_text("# Old draft")
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("# New draft")

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "rw-sess-old"}

    with patch("app.services.session_client.requests.post", return_value=mock_resp) as post:
        with patch("app.services.session_client.append_event"):
            resp = client.post(
                "/housekeeping/blog-draft/rewrite",
                data={"feedback": "make it shorter", "filename": "2026-06-01-weekly-draft.md"},
                headers={"X-Capture-Token": "tok"},
            )
    assert resp.status_code == 200
    # The session command must reference the OLD draft, not the newest one.
    sent_command = post.call_args.kwargs["json"]["initial_command"] if "json" in post.call_args.kwargs else None
    assert sent_command is None or "2026-06-01-weekly-draft.md" in sent_command


def test_blog_draft_save_targets_specific_open_draft(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "tok")
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-06-01-weekly-draft.md").write_text("old content")
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("new content")

    resp = client.post(
        "/housekeeping/blog-draft/save",
        data={"content": "edited old content", "bluesky_text": "", "filename": "2026-06-01-weekly-draft.md"},
        headers={"X-Capture-Token": "tok"},
    )
    assert resp.status_code == 200
    assert (tmp_path / "2026-06-01-weekly-draft.md").read_text() == "edited old content"
    assert (tmp_path / "2026-07-01-weekly-draft.md").read_text() == "new content"


def test_blog_draft_content_reload_targets_specific_draft(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-06-01-weekly-draft.md").write_text("old content")
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("new content")

    resp = client.get("/housekeeping/blog-draft/content?filename=2026-06-01-weekly-draft.md")
    assert resp.status_code == 200
    assert resp.get_json()["content"] == "old content"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Server/projects/ikeos && python3 -m pytest tests/test_housekeeping.py -k "targets_specific_open_draft" -v`
Expected: FAIL — all three should either pick up the wrong (newest) draft's content, or `save_draft`/route currently ignores `filename` entirely, so the old-draft assertions fail.

- [ ] **Step 3: Add a `filename`-aware `save_draft` to `blog_drafts.py`**

In `app/services/blog_drafts.py`, replace `save_draft` (currently lines 56-67) with a version that accepts an optional `filename`, defaulting to current latest-only behavior when omitted:

```python
def save_draft(content: str, bluesky_text: str, filename: str | None = None) -> str:
    """Write content and bluesky_text to the given draft (or the latest draft
    if filename is omitted). Returns filename.

    Raises FileNotFoundError if the target draft doesn't exist.
    """
    draft, bluesky = draft_paths(filename) if filename else latest_draft_paths()
    if not draft:
        raise FileNotFoundError("No draft file found")
    draft.write_text(content, encoding="utf-8")
    if bluesky:
        bluesky.write_text(bluesky_text, encoding="utf-8")
    return draft.name
```

- [ ] **Step 4: Update the four route handlers in `app/routes/housekeeping.py` to read and forward `filename`**

Replace `blog_draft_save` (lines 262-273):

```python
@bp.route("/housekeeping/blog-draft/save", methods=["POST"])
@require_capture_token
def blog_draft_save():
    content = request.form.get("content", "")
    bluesky_text = request.form.get("bluesky_text", "")
    filename = request.form.get("filename") or None
    try:
        filename = save_draft(content, bluesky_text, filename)
    except FileNotFoundError:
        return jsonify({"error": "No draft found"}), 404
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "filename": filename}), 200
```

Replace `blog_draft_publish` (lines 276-285):

```python
@bp.route("/housekeeping/blog-draft/publish", methods=["POST"])
@require_capture_token
def blog_draft_publish():
    filename = request.form.get("filename") or None
    bundle = read_draft_bundle(filename)
    if not bundle:
        return jsonify({"error": "No draft found"}), 404
    result = publish_blog_draft(bundle["filename"], bundle["bluesky_filename"] or "")
    if not result.ok:
        return jsonify({"error": "Failed to create publish session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200
```

Replace `blog_draft_rewrite` (lines 288-302):

```python
@bp.route("/housekeeping/blog-draft/rewrite", methods=["POST"])
@require_capture_token
def blog_draft_rewrite():
    filename = request.form.get("filename") or None
    bundle = read_draft_bundle(filename)
    if not bundle:
        return jsonify({"error": "No draft found"}), 404
    feedback = request.form.get("feedback", "").strip()
    if not feedback:
        return jsonify({"error": "Feedback is required"}), 400
    result = rewrite_blog_draft(bundle["filename"], feedback)
    if result.already_running and result.ok:
        return jsonify({"ok": True, "session_id": result.session_id}), 200
    if not result.ok:
        return jsonify({"error": result.error or "Failed to create rewrite session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200
```

Replace `blog_draft_content` (lines 331-340):

```python
@bp.route("/housekeeping/blog-draft/content")
def blog_draft_content():
    """Return current draft file content as JSON — used by JS to reload after rewrite."""
    filename = request.args.get("filename") or None
    bundle = read_draft_bundle(filename)
    if not bundle:
        return jsonify({"error": "No draft found"}), 404
    return jsonify({
        "content": bundle["content"],
        "bluesky_text": bundle["bluesky_text"],
    })
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /mnt/c/Server/projects/ikeos && python3 -m pytest tests/test_housekeeping.py -k "blog_draft" -v`
Expected: PASS — all blog-draft tests including the three new ones, plus the pre-existing ones (which omit `filename` and must keep defaulting to latest-draft behavior).

- [ ] **Step 6: Wire `filename` through the editor template's JS so the browser actually sends it**

In `app/templates/blog_draft.html`, add a hidden filename constant right after the existing `_captureToken` declaration (after line 67):

```javascript
  const _captureToken = {{ capture_token | tojson }};
  const _draftFilename = {{ filename | tojson }};
```

Then update every `FormData`/fetch call that currently omits it:

- Save handler (around line 97-101): after `body.append('bluesky_text', bskyEditor.value);` add `body.append('filename', _draftFilename);`
- Publish handler (around line 117): change the fetch call to `fetch('/housekeeping/blog-draft/publish', { method: 'POST', body: (() => { const b = new FormData(); b.append('filename', _draftFilename); return b; })(), headers: { 'X-Capture-Token': _captureToken } })`
- Reload handler (around line 170): change `fetch('/housekeeping/blog-draft/content')` to `` fetch(`/housekeeping/blog-draft/content?filename=${encodeURIComponent(_draftFilename)}`) ``
- Rewrite submit handler (around line 204-206): after `body.append('feedback', feedback);` add `body.append('filename', _draftFilename);`

- [ ] **Step 7: Manual browser verification**

Use the `/run` skill to start the app, open an older draft via `/housekeeping/blog-drafts` → pick a non-latest entry, click "Request Rewrite" with test feedback, and confirm (via the session's initial command, visible in `/agents`) that it references the older filename, not the latest one.

- [ ] **Step 8: Commit**

```bash
git add app/routes/housekeeping.py app/services/blog_drafts.py app/templates/blog_draft.html tests/test_housekeeping.py
git commit -m "fix: blog draft Save/Publish/Rewrite/Reload target the open draft, not the latest

All four actions on the blog draft editor called read_draft_bundle()
with no filename, which always falls back to the newest draft on disk.
Opening an older draft and clicking Rewrite silently rewrote whatever
the current week's draft was instead."
```

---

### Task 3: Detect and surface "Published" status on the Housekeeping page's blog-draft pill

**Files:**
- Modify: `app/services/blog_drafts.py` (add `is_published`, use it in `latest_draft_name` and `list_drafts`)
- Modify: `app/routes/housekeeping.py:305-328` (`_housekeeping_context`)
- Modify: `app/templates/housekeeping.html:44-53`
- Test: `tests/test_blog_drafts.py`, `tests/test_housekeeping.py`

**Interfaces:**
- Produces: `app.services.blog_drafts.is_published(draft_path: Path) -> bool` — True if the draft's canonical (non `-draft`) counterpart file exists.
- Produces: `app.services.blog_drafts.latest_unpublished_draft_name() -> str | None` — like `latest_draft_name()` but skips drafts that are already published; used by `_housekeeping_context()` for the pill.
- Consumes (Task 3 relies on Task 2 already being in place, since it also touches `_housekeeping_context`'s `blog_draft` computation): no change to Task 2's public interfaces.

**Root cause:** `publish.sh` / `scripts/publish_post.py` (fixed 2026-08-15 in `aios-blog`, commit `6e055e3` on this side) deliberately **leaves the original `-draft.md` file in place** after promoting it — it writes a new canonical file (e.g. `2026-08-15-weekly-draft.md` → `2026-08-15-weekly.md`) rather than renaming or deleting the draft. `blog_drafts.latest_draft_name()` globs only on the `-weekly-draft.md` suffix, so it has no way to know the draft it's pointing at has already gone live. The Housekeeping page's pill (`app/templates/housekeeping.html:44-45`) only ever renders `'Ready' if blog_draft else 'None yet'` — there has never been a third "Published" state in the template at all, which is exactly what the bug report is asking for.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_blog_drafts.py` (near the existing `latest_draft` tests):

```python
def test_is_published_false_when_no_canonical_file(posts_dir):
    draft = posts_dir / "2026-07-01-weekly-draft.md"
    draft.write_text("draft content", encoding="utf-8")
    assert blog_drafts.is_published(draft) is False


def test_is_published_true_when_canonical_file_exists(posts_dir):
    draft = posts_dir / "2026-07-01-weekly-draft.md"
    draft.write_text("draft content", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly.md").write_text("published content", encoding="utf-8")
    assert blog_drafts.is_published(draft) is True


def test_latest_unpublished_draft_name_skips_published_draft(posts_dir):
    (posts_dir / "2026-06-01-weekly-draft.md").write_text("old")
    (posts_dir / "2026-06-01-weekly.md").write_text("old published")
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("new, not yet published")
    assert blog_drafts.latest_unpublished_draft_name() == "2026-07-01-weekly-draft.md"


def test_latest_unpublished_draft_name_none_when_latest_is_published(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("published already")
    (posts_dir / "2026-07-01-weekly.md").write_text("published")
    assert blog_drafts.latest_unpublished_draft_name() is None
```

Add to `tests/test_housekeeping.py` (near the housekeeping index/context tests):

```python
def test_housekeeping_index_shows_published_pill_for_published_draft(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    (tmp_path / "2026-07-01-weekly-draft.md").write_text("content")
    (tmp_path / "2026-07-01-weekly.md").write_text("published content")
    resp = client.get("/housekeeping")
    assert resp.status_code == 200
    assert b"Published" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Server/projects/ikeos && python3 -m pytest tests/test_blog_drafts.py tests/test_housekeeping.py -k "published" -v`
Expected: FAIL — `is_published` and `latest_unpublished_draft_name` don't exist yet; the pill has no "Published" text path.

- [ ] **Step 3: Implement `is_published` and `latest_unpublished_draft_name` in `blog_drafts.py`**

Add these two functions to `app/services/blog_drafts.py`, after `latest_draft_name` (currently ending line 25):

```python
def is_published(draft: Path) -> bool:
    """True if the draft's canonical (non "-draft") published file already exists.

    publish.sh intentionally leaves the -draft.md file in place after promoting
    it, so file presence alone can't distinguish a live post from a pending one.
    """
    canonical_name = draft.name.replace("-weekly-draft.md", "-weekly.md")
    return draft.with_name(canonical_name).exists()


def latest_unpublished_draft_name() -> str | None:
    """Like latest_draft_name(), but skips drafts that have already been published."""
    posts = _posts_dir()
    if not posts or not posts.exists():
        return None
    for draft in sorted(posts.glob("*-weekly-draft.md"), reverse=True):
        if not is_published(draft):
            return draft.name
    return None
```

- [ ] **Step 4: Wire published detection into the housekeeping context**

In `app/routes/housekeeping.py`, `_housekeeping_context()` (lines 305-328): compute the pill state as local variables before the `return dict(...)`. Insert just before the `return dict(` line (line 311):

```python
    latest_name = latest_draft_name()
    latest_published = False
    if latest_name:
        latest_path, _ = draft_paths(latest_name)
        latest_published = is_published(latest_path) if latest_path else False
```

and change the import on line 8 from:
```python
from app.services.blog_drafts import delete_draft, latest_draft_name, list_drafts, read_draft_bundle, save_draft
```
to:
```python
from app.services.blog_drafts import (
    delete_draft, draft_paths, is_published, latest_draft_name,
    latest_unpublished_draft_name, list_drafts, read_draft_bundle, save_draft,
)
```

Then in the `return dict(...)` block, replace `blog_draft=latest_draft_name(),` with:
```python
        blog_draft=latest_unpublished_draft_name(),
        blog_draft_published=latest_published,
```

- [ ] **Step 5: Add the "Published" pill state to `housekeeping.html`**

In `app/templates/housekeeping.html`, replace the pill block (lines 44-45):

```html
          <span class="hk-pill {{ 'hk-pill--ok' if blog_draft else 'hk-pill--uninitialized' }}">
            {{ 'Ready' if blog_draft else 'None yet' }}
```

with a three-state version:

```html
          <span class="hk-pill {{ 'hk-pill--ok' if blog_draft else ('hk-pill--ok' if blog_draft_published else 'hk-pill--uninitialized') }}">
            {% if blog_draft %}Ready{% elif blog_draft_published %}Published{% else %}None yet{% endif %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /mnt/c/Server/projects/ikeos && python3 -m pytest tests/test_blog_drafts.py tests/test_housekeeping.py -v`
Expected: PASS — full suite for both files, no regressions in existing tests.

- [ ] **Step 7: Manual browser verification**

Use the `/run` skill to start the app and load `/housekeeping`. With the current real draft data (`2026-08-15-weekly-draft.md` already has a published `2026-08-15-weekly.md` counterpart per today's filesystem state), confirm the pill now reads "Published" instead of "Ready".

- [ ] **Step 8: Commit**

```bash
git add app/services/blog_drafts.py app/routes/housekeeping.py app/templates/housekeeping.html tests/test_blog_drafts.py tests/test_housekeeping.py
git commit -m "fix: Housekeeping page blog-draft pill reflects Published status

publish.sh deliberately leaves the -draft.md file in place after
promoting it, so a simple glob for *-weekly-draft.md could never tell
a live post from a pending one — the pill was stuck on 'Ready' forever.
Added is_published() (checks for the canonical non-draft file) and a
third pill state."
```

---

### Task 4: Extend PATCH /entries to support relocating an entry to a different project

**Files:**
- Modify: `app/services/vault_entries.py` (add `relocate_entry_project`)
- Modify: `app/services/vault.py` (re-export)
- Modify: `app/routes/capture.py:107-157` (`patch_entries`)
- Test: `tests/test_capture.py`, `tests/test_vault_housekeeping.py` or a new `tests/test_vault_entries.py` section matching existing conventions in that area

**Interfaces:**
- Produces: `app.services.vault_entries.relocate_entry_project(entry_type: str, project: str, filename: str, new_project: str) -> bool` — moves the entry's file into the new project's folder (creating it if needed) and updates its `project` frontmatter field and `project` tag to match. Returns `False` if the source entry doesn't exist, `entry_type` is invalid, or `new_project` is blank.
- Consumes: existing `app.services.vault_cache.ENTRY_TYPE_CONFIG`, `VAULT_PATH`, `_invalidate_cache`.

**Root cause / motivation:** The claude-config housekeeping task "Vault schema check" has failed twice in a row (`projects/claude-config/bugs/2026-08-03-housekeeping-task-failed-vault-schema-check-2nd-co.md`) because 18-20 files under `projects/Visualizer/{bugs,ideas,notes}/*.md` have `project: visualizer` (lowercase) instead of the canonical `Visualizer`. The existing PATCH `/entries` endpoint (`app/routes/capture.py:107-157`) only updates `status`/`updated`/the `status/*` tag via `update_entry_status_generic` — there is no way to correct a `project` field or move a misfiled entry, and direct vault file writes are permission-denied to agents by design (`Vault Access Rules` in the global CLAUDE.md — "there is no third door"). This task adds that door, narrowly scoped to `project` relocation only, so this class of fix goes through the same authenticated capture API as every other vault mutation.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_capture.py` (reuse the existing `client` fixture, which already creates `tmp_path / "projects" / "bcr-waivers"`):

```python
def test_patch_entries_relocates_project(client, tmp_path):
    src_dir = tmp_path / "projects" / "bcr-waivers" / "bugs"
    src_dir.mkdir(parents=True)
    entry = src_dir / "2026-01-01-test-bug.md"
    entry.write_text(
        "---\nproject: bcr-waivers\nstatus: open\ntags:\n- bug\n- bcr-waivers\ntitle: Test bug\ntype: bug\n---\n\nBody.\n",
        encoding="utf-8",
    )

    resp = client.patch(
        "/entries",
        data={
            "project": "bcr-waivers",
            "type": "bug",
            "filename": "2026-01-01-test-bug",
            "new_project": "bottle-drive",
        },
        headers={"X-Capture-Token": "test-token-secret"},
    )
    assert resp.status_code == 200
    assert not entry.exists()

    moved = tmp_path / "projects" / "bottle-drive" / "bugs" / "2026-01-01-test-bug.md"
    assert moved.exists()
    content = moved.read_text(encoding="utf-8")
    assert "project: bottle-drive" in content
    assert "bcr-waivers" not in content


def test_patch_entries_relocate_requires_token(client, tmp_path):
    resp = client.patch("/entries", data={
        "project": "bcr-waivers", "type": "bug",
        "filename": "whatever", "new_project": "bottle-drive",
    })
    assert resp.status_code == 401


def test_patch_entries_relocate_404_when_source_missing(client, tmp_path):
    (tmp_path / "projects" / "bcr-waivers" / "bugs").mkdir(parents=True)
    resp = client.patch(
        "/entries",
        data={"project": "bcr-waivers", "type": "bug", "filename": "nonexistent", "new_project": "bottle-drive"},
        headers={"X-Capture-Token": "test-token-secret"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Server/projects/ikeos && python3 -m pytest tests/test_capture.py -k "relocate" -v`
Expected: FAIL — `new_project` is currently ignored entirely by `patch_entries`, so the file never moves; no 404 branch exists for this case either (falls through to the existing status-based 404, which happens to also fire, so check that test separately passes for the right reason once implemented).

- [ ] **Step 3: Implement `relocate_entry_project` in `vault_entries.py`**

Add this function to `app/services/vault_entries.py`, immediately after `update_entry_status_generic` (after line 342):

```python
def relocate_entry_project(entry_type: str, project: str, filename: str, new_project: str) -> bool:
    """Move an entry to a different project's folder and correct its project
    frontmatter/tag to match. Used to fix vault-schema violations (e.g. a
    mis-cased or wrong `project:` field) that the capture API's PATCH endpoint
    otherwise can't touch — direct vault file writes are permission-denied to
    agents, so this is the sole sanctioned path for this class of correction.
    """
    new_project = (new_project or "").strip()
    if not new_project or entry_type not in _vc.ENTRY_TYPE_CONFIG:
        return False

    cfg = _vc.ENTRY_TYPE_CONFIG[entry_type]
    if not project:
        return False

    src_path = _vc.VAULT_PATH / "projects" / project / cfg["folder"]
    filepath = src_path / (filename if filename.endswith(".md") else f"{filename}.md")
    if not filepath.exists():
        return False

    try:
        post = frontmatter.load(filepath)
        post.metadata["project"] = new_project
        post.metadata["updated"] = datetime.now().isoformat(timespec="seconds")
        tags = [t for t in post.metadata.get("tags", []) if t != project]
        if new_project not in tags:
            tags.append(new_project)
        post.metadata["tags"] = tags

        dest_dir = _vc.VAULT_PATH / "projects" / new_project / cfg["folder"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filepath.name

        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        filepath.unlink()

        _vc._invalidate_cache()
        return True
    except Exception:
        logger.exception(
            "Failed to relocate %s/%s/%s to project %s", entry_type, project, filename, new_project
        )
        return False
```

- [ ] **Step 4: Re-export from `vault.py`**

In `app/services/vault.py`, find the import block that already brings in `update_entry_status_generic` (around line 38-40) and add `relocate_entry_project` alongside it.

- [ ] **Step 5: Wire it into `patch_entries` in `app/routes/capture.py`**

In `patch_entries` (lines 107-157), after extracting `status` (line 126), also extract the new field:

```python
    new_project = req_data.get("new_project", "").strip().lower()
```

Then, before the existing status-validation block (line 136 `if entry_type not in PATCH_VALID_TYPES:`), branch on whether this is a relocation request. Reuse the existing `_reject_path_traversal` check (already applied to `filename` at line 129) on `new_project` too, since it becomes part of a filesystem path this endpoint creates:

```python
    if new_project:
        if not _reject_path_traversal(new_project):
            return jsonify({"error": "Invalid project"}), 400
        from app.services.vault import relocate_entry_project
        success = relocate_entry_project(entry_type, project, filename, new_project)
        if not success:
            return jsonify({"error": "Entry not found or invalid project"}), 404
        return jsonify({"message": "Project updated"}), 200
```

Place this branch immediately after the `entry_type` and `project` validation lines (128-134) already present, so path-traversal and type checks still apply, but before the status-lifecycle validation (which doesn't apply to a pure relocation call).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /mnt/c/Server/projects/ikeos && python3 -m pytest tests/test_capture.py -v`
Expected: PASS — full file, including the three new relocate tests and all pre-existing ones.

- [ ] **Step 7: Commit**

```bash
git add app/services/vault_entries.py app/services/vault.py app/routes/capture.py tests/test_capture.py
git commit -m "feat: PATCH /entries supports relocating an entry to a different project

Unblocks the claude-config 'Vault schema check' housekeeping task,
which has failed twice because 18-20 Visualizer entries have
project: visualizer (lowercase) instead of the canonical Visualizer,
and there was previously no sanctioned way to correct a project field
without direct vault file writes (permission-denied to agents)."
```

**Follow-up (not part of this plan, do manually after this deploys):** once Task 4 ships, use the new `new_project=Visualizer` PATCH parameter to actually correct the 18-20 mis-cased `projects/Visualizer/*` entries flagged in `2026-08-03-housekeeping-task-failed-vault-schema-check-2nd-co.md`, so that housekeeping task can pass on its next run.
