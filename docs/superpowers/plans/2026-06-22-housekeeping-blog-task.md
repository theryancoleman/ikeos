# Housekeeping Blog Task + IkeOS Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire blog draft generation into the housekeeping scheduler (Saturday night auto-run) and surface blog draft status on the IkeOS housekeeping dashboard and health check widget.

**Architecture:** A new `housekeeping-task` vault entry provides the instructions and schedule for the blog draft task. The housekeeping runner picks it up like any other task and runs it as a Claude Code subagent Saturday night. On completion it creates a vault note; on failure it creates a bug entry. IkeOS reads the task's `last_run` field and adds a status row to the housekeeping dashboard and a badge to the health check widget.

**Tech Stack:** Vault YAML frontmatter (housekeeping-task), existing IkeOS housekeeping dashboard (Jinja2/Flask), existing health check endpoint.

**Prerequisite:** Plans `2026-06-22-aios-blog-foundation.md` and `2026-06-22-blog-skills.md` complete.

---

## File Map

```
C:\Server\obsidian-vault\projects\ikeos\housekeeping\
└── <date>-weekly-blog-draft.md          # NEW via capture API (not direct write)

C:\Server\projects\ikeos\app\
├── routes\housekeeping.py               # MODIFY: blog draft status in dashboard
└── templates\housekeeping.html          # MODIFY: blog draft row in dashboard table

C:\Server\projects\ikeos\tests\
└── test_housekeeping.py                 # MODIFY: add blog-draft status tests
```

---

### Task 1: Create the housekeeping task vault entry

The task definition lives in the vault as a `housekeeping-task` entry. Create it via the capture API (never write vault files directly).

- [ ] **Step 1: Write the failing test first**

Add to `C:\Server\projects\ikeos\tests\test_housekeeping.py`:

```python
def test_blog_draft_task_exists_in_vault(tmp_vault):
    """Confirm a housekeeping task named 'weekly-blog-draft' exists for ikeos."""
    hk_dir = tmp_vault / "projects" / "ikeos" / "housekeeping"
    matching = list(hk_dir.glob("*weekly-blog-draft*.md"))
    assert len(matching) == 1, "Expected exactly one weekly-blog-draft housekeeping task"
    import frontmatter
    post = frontmatter.load(matching[0])
    assert post.metadata.get("type") == "housekeeping-task"
    assert post.metadata.get("interval") == "weekly"
    assert post.metadata.get("enabled") == "true"
```

Run: `pytest tests/test_housekeeping.py::test_blog_draft_task_exists_in_vault -v`
Expected: FAIL — no such file in tmp_vault.

- [ ] **Step 2: Create the housekeeping task via capture API**

```bash
curl -s -X POST http://localhost:5009/capture/json \
  -H "Content-Type: application/json" \
  -d '{
    "type": "housekeeping-task",
    "project": "ikeos",
    "title": "weekly-blog-draft",
    "interval": "weekly",
    "success_definition": "A draft Markdown post exists at /mnt/c/Server/projects/aios-blog/content/posts/<YYYY-MM-DD>-weekly-draft.md and a companion -bluesky.txt file alongside it.",
    "body": "Generate the weekly AIOS blog draft.\n\nRun the /blog skill in weekly mode:\n1. Read git log for ikeos and claude-config repos (last 7 days)\n2. Read vault entries for ikeos updated this week\n3. Read weekly notes from /mnt/c/Server/projects/aios-blog/weekly-notes/<current-week>.md if it exists\n4. Read DECISIONS.md changes this week\n5. Generate draft post to /mnt/c/Server/projects/aios-blog/content/posts/<YYYY-MM-DD>-weekly-draft.md\n6. Generate Bluesky text to /mnt/c/Server/projects/aios-blog/content/posts/<YYYY-MM-DD>-weekly-bluesky.txt\n7. Create a vault note for ikeos: title=Blog draft ready: <YYYY-MM-DD>, body=Draft at content/posts/<filename>.md — ready for review.\n8. If any step fails, create a vault bug for ikeos: title=Blog draft generation failed, body=<error details>.\n\nSchedule: Saturday night (configured in housekeeping scheduler)."
  }'
```

Expected: HTTP 200, `{"ok": true}`.

- [ ] **Step 3: Verify the entry was created**

```bash
ls /mnt/c/Server/obsidian-vault/projects/ikeos/housekeeping/ | grep blog
```

Expected: a file like `2026-06-22-weekly-blog-draft.md` appears.

- [ ] **Step 4: Confirm the test now passes**

The test uses `tmp_vault` which is a test fixture. The real vault creation above validates the real API. For the test to pass, add a fixture that creates the file in tmp_vault:

In `tests/conftest.py`, find the `tmp_vault` fixture and note how it creates the vault structure. The test above is an integration test for the real vault — move it to an integration test file or adjust to read from `VAULT_PATH`. For now, confirm the real vault has the entry:

```bash
python3 -c "
import frontmatter
from pathlib import Path
import glob
files = glob.glob('/mnt/c/Server/obsidian-vault/projects/ikeos/housekeeping/*blog*.md')
for f in files:
    p = frontmatter.load(f)
    print(p.metadata)
"
```

Expected: prints metadata dict with `type: housekeeping-task`, `interval: weekly`, `enabled: true`.

---

### Task 2: Surface blog draft status on the housekeeping dashboard

The housekeeping dashboard shows task rows with `last_run` age and status. Add a blog-specific status: shows the filename of the latest weekly draft if it exists, or "No draft yet" if not.

- [ ] **Step 1: Write the failing test**

Add to `C:\Server\projects\ikeos\tests\test_housekeeping.py`:

```python
def test_blog_draft_status_present_when_draft_exists(client, tmp_path):
    """GET /housekeeping shows blog draft status when draft file exists."""
    import os
    from unittest.mock import patch

    draft_dir = tmp_path / "posts"
    draft_dir.mkdir(parents=True)
    draft_file = draft_dir / "2026-06-22-weekly-draft.md"
    draft_file.write_text("# Draft")

    with patch("app.routes.housekeeping.AIOS_BLOG_POSTS_DIR", str(draft_dir)):
        resp = client.get("/housekeeping")

    assert resp.status_code == 200
    assert b"2026-06-22-weekly-draft.md" in resp.data


def test_blog_draft_status_no_draft(client, tmp_path):
    """GET /housekeeping shows 'No draft' when posts dir is empty."""
    from unittest.mock import patch

    empty_dir = tmp_path / "posts"
    empty_dir.mkdir(parents=True)

    with patch("app.routes.housekeeping.AIOS_BLOG_POSTS_DIR", str(empty_dir)):
        resp = client.get("/housekeeping")

    assert resp.status_code == 200
    assert b"No draft" in resp.data
```

Run: `pytest tests/test_housekeeping.py::test_blog_draft_status_present_when_draft_exists tests/test_housekeeping.py::test_blog_draft_status_no_draft -v`
Expected: FAIL — `AIOS_BLOG_POSTS_DIR` not defined in route, template doesn't show it.

- [ ] **Step 2: Add AIOS_BLOG_POSTS_DIR constant and blog draft helper to housekeeping route**

In `C:\Server\projects\ikeos\app\routes\housekeeping.py`, add after the existing constants at the top (after `HOUSEKEEPING_PROJECT_DIR`):

```python
AIOS_BLOG_POSTS_DIR = os.environ.get(
    "AIOS_BLOG_POSTS_DIR",
    "/mnt/c/Server/projects/aios-blog/content/posts"
)


def _latest_blog_draft() -> str | None:
    """Return filename of the most recent weekly-draft.md, or None if absent."""
    posts_dir = Path(AIOS_BLOG_POSTS_DIR)
    if not posts_dir.exists():
        return None
    drafts = sorted(posts_dir.glob("*-weekly-draft.md"), reverse=True)
    return drafts[0].name if drafts else None
```

- [ ] **Step 3: Pass blog draft info to the housekeeping template**

In `housekeeping.py`, find the route handler that renders the housekeeping page (the `GET /housekeeping` handler). Add `blog_draft=_latest_blog_draft()` to the `render_template` call. For example:

```python
return render_template(
    "housekeeping.html",
    # ... existing args ...
    blog_draft=_latest_blog_draft(),
)
```

- [ ] **Step 4: Add blog draft row to the housekeeping template**

Read `C:\Server\projects\ikeos\app\templates\housekeeping.html`. Find where task rows or status information is displayed. Add a blog draft status section. The exact placement depends on the current template structure — add it in a logical position near other status widgets:

```html
<!-- Blog draft status -->
<div class="hk-widget">
  <span class="ike-eyebrow">Weekly Blog Draft</span>
  {% if blog_draft %}
    <p class="hk-status hk-status-ok">
      Ready: <code>{{ blog_draft }}</code>
    </p>
  {% else %}
    <p class="hk-status hk-status-pending">No draft yet this week</p>
  {% endif %}
</div>
```

- [ ] **Step 5: Run tests**

```bash
cd /mnt/c/Server/projects/ikeos
pytest tests/test_housekeeping.py -v
```

Expected: all tests pass including the two new ones.

- [ ] **Step 6: Restart container to test in browser**

```bash
docker.exe compose up --build -d ikeos
```

Navigate to `http://homeautomation:5009/housekeeping`. Confirm the blog draft widget appears.

- [ ] **Step 7: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/routes/housekeeping.py app/templates/housekeeping.html tests/test_housekeeping.py
git commit -m "feat: surface blog draft status on housekeeping dashboard"
```

---

### Task 3: Add blog draft badge to the main dashboard housekeeping widget

The main dashboard (`dashboard.html`) shows a housekeeping heartbeat widget. The blog draft status should appear there so Sunday morning the user sees it immediately on the home screen.

The dashboard is rendered by the route in `app/routes/browse.py` which currently calls `render_template("dashboard.html", ..., hk_age=hk_age, hk_status=hk_status, ...)`.

- [ ] **Step 1: Write the failing test**

Add to `C:\Server\projects\ikeos\tests\test_browse.py`:

```python
def test_dashboard_shows_blog_draft_ready(client, tmp_path):
    """GET / shows blog draft filename when a weekly draft exists."""
    from unittest.mock import patch

    draft_dir = tmp_path / "posts"
    draft_dir.mkdir(parents=True)
    (draft_dir / "2026-06-22-weekly-draft.md").write_text("# Draft")

    with patch("app.routes.housekeeping.AIOS_BLOG_POSTS_DIR", str(draft_dir)):
        resp = client.get("/")

    assert resp.status_code == 200
    assert b"2026-06-22-weekly-draft.md" in resp.data


def test_dashboard_shows_no_draft_when_absent(client, tmp_path):
    """GET / shows 'No draft' when no weekly draft exists."""
    from unittest.mock import patch

    empty_dir = tmp_path / "posts"
    empty_dir.mkdir(parents=True)

    with patch("app.routes.housekeeping.AIOS_BLOG_POSTS_DIR", str(empty_dir)):
        resp = client.get("/")

    assert resp.status_code == 200
    assert b"No draft" in resp.data
```

Run: `pytest tests/test_browse.py::test_dashboard_shows_blog_draft_ready tests/test_browse.py::test_dashboard_shows_no_draft_when_absent -v`
Expected: FAIL — `blog_draft` not passed to template yet.

- [ ] **Step 2: Pass blog_draft to the dashboard render in browse.py**

In `C:\Server\projects\ikeos\app\routes\browse.py`, find the dashboard route (the one that calls `render_template("dashboard.html", ...)`). Add the import and the variable:

Add to the top-level imports:
```python
from app.routes.housekeeping import _latest_blog_draft
```

In the dashboard route function body, add before `render_template`:
```python
blog_draft = _latest_blog_draft()
```

Then add `blog_draft=blog_draft` to the `render_template` call.

- [ ] **Step 3: Add blog draft badge to dashboard.html housekeeping widget**

In `C:\Server\projects\ikeos\app\templates\dashboard.html`, find the housekeeping widget section (around line 94–109):

```html
    <!-- ── Housekeeping heartbeat ── -->
    <section>
      <div class="ike-eyebrow">Housekeeping</div>
      <div class="hk-widget">
        ...
        <a href="{{ url_for('housekeeping.index') }}" class="hk-widget-link">Manage tasks →</a>
      </div>
    </section>
```

Add a blog draft row **inside** `.hk-widget`, after the summary div and before the manage link:

```html
        <div class="hk-widget-row hk-widget-row--blog">
          <span class="hk-widget-label">Blog draft:</span>
          {% if blog_draft %}
            <span class="hk-widget-status hk-widget-status--ok">{{ blog_draft }}</span>
          {% else %}
            <span class="hk-widget-status hk-widget-status--pending">No draft this week</span>
          {% endif %}
        </div>
```

- [ ] **Step 4: Run tests**

```bash
cd /mnt/c/Server/projects/ikeos
pytest tests/test_browse.py -v
```

Expected: all tests pass including the two new ones.

- [ ] **Step 5: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/routes/browse.py app/templates/dashboard.html tests/test_browse.py
git commit -m "feat: add blog draft status to main dashboard housekeeping widget"
```

- [ ] **Step 6: Rebuild and verify**

```bash
docker.exe compose up --build -d ikeos
```

Open `http://homeautomation:5009`. Confirm the housekeeping widget shows "Blog draft: No draft this week".

---

### Task 4: Configure the Saturday night schedule

The housekeeping scheduler is configured via the IkeOS housekeeping management page. Set the blog draft task to run Saturday night.

- [ ] **Step 1: Verify the scheduler config**

```bash
cat /mnt/c/Server/obsidian-vault/projects/ikeos/housekeeping/last-run.md 2>/dev/null || echo "no heartbeat yet"
```

- [ ] **Step 2: Set Saturday schedule via the housekeeping management page**

Navigate to `http://homeautomation:5009/housekeeping`. Find the `weekly-blog-draft` task row. Set its schedule to **Saturday at 23:00** (or the interval the scheduler supports — weekly tasks run on the configured weekly day/time).

If the scheduler uses a day-of-week setting, set it to Saturday. If it only supports "weekly from last_run", manually set `last_run` to the previous Sunday so the next run lands on Saturday.

- [ ] **Step 3: Verify the next run time shows Saturday**

In the housekeeping dashboard, confirm "Next Due" for the blog draft task shows a Saturday date.
