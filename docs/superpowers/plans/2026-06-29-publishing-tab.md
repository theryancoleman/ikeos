# Publishing Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Publishing" nav tab to IkeOS that shows the latest blog draft status, a reverse-chronological post list, and recent Bluesky posts with engagement stats.

**Architecture:** New `app/services/publishing.py` reads blog post markdown from the mounted aios-blog posts directory and fetches Bluesky posts from the public AT Protocol API (`public.api.bsky.app`) — no auth required for public actor feeds. New `app/routes/publishing.py` is a thin handler that calls the service and renders `app/templates/publishing.html`. The existing blog draft editor at `/housekeeping/blog-draft` handles editing; this tab just surfaces status and links. Voice prompt management is deferred.

**Tech Stack:** Python 3.11+, Flask, python-frontmatter, requests, Jinja2, vanilla HTML/CSS

**Assumptions:**
- `AIOS_BLOG_POSTS_DIR` is already configured (mounts the aios-blog posts directory)
- `BLUESKY_HANDLE` will be added as a new env var (e.g. `ikeos.bsky.social`); if absent, the Bluesky panel is hidden
- Bluesky public API returns posts without auth for public accounts
- Voice prompt editor and versioning are deferred to a follow-up task

---

### File Map

| File | Action | Responsibility |
|---|---|---|
| `app/services/publishing.py` | Create | Read blog posts, fetch Bluesky posts |
| `app/routes/publishing.py` | Create | Thin route handler for /publishing |
| `app/templates/publishing.html` | Create | Publishing page template |
| `app/templates/base.html` | Modify | Add Publishing nav tab |
| `app/__init__.py` | Modify | Register publishing blueprint |
| `tests/test_publishing.py` | Create | Service unit tests |
| `.env.example` | Modify | Document BLUESKY_HANDLE |

---

### Task 1: Create `app/services/publishing.py` with `read_blog_posts()`

**Files:**
- Create: `app/services/publishing.py`
- Create: `tests/test_publishing.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_publishing.py`:

```python
import pytest
from pathlib import Path
from app.services.publishing import read_blog_posts


@pytest.fixture
def posts_dir(tmp_path):
    """Create sample blog post files."""
    (tmp_path / "2026-06-08-week-june-2.md").write_text(
        "---\ntitle: Week June 2\ndate: 2026-06-08\ndraft: false\ndescription: A summary\n---\nBody text here."
    )
    (tmp_path / "2026-06-15-week-june-11.md").write_text(
        "---\ntitle: Week June 11\ndate: 2026-06-15\ndraft: true\n---\nDraft body."
    )
    # Bluesky companion file should be ignored
    (tmp_path / "2026-06-08-week-june-2-bluesky.txt").write_text("bluesky text")
    return tmp_path


def test_read_blog_posts_returns_posts_newest_first(posts_dir):
    posts = read_blog_posts(posts_dir)
    assert len(posts) == 2
    assert posts[0]["date"] == "2026-06-15"
    assert posts[1]["date"] == "2026-06-08"


def test_read_blog_posts_includes_title_and_draft_status(posts_dir):
    posts = read_blog_posts(posts_dir)
    newest = posts[0]
    assert newest["title"] == "Week June 11"
    assert newest["draft"] is True
    assert newest["slug"] == "2026-06-15-week-june-11"


def test_read_blog_posts_includes_description(posts_dir):
    posts = read_blog_posts(posts_dir)
    oldest = posts[1]
    assert oldest["description"] == "A summary"


def test_read_blog_posts_excludes_bluesky_companion_files(posts_dir):
    posts = read_blog_posts(posts_dir)
    slugs = [p["slug"] for p in posts]
    assert not any("bluesky" in s for s in slugs)


def test_read_blog_posts_returns_empty_for_missing_dir():
    posts = read_blog_posts(Path("/nonexistent/path"))
    assert posts == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
docker exec ikeos pytest tests/test_publishing.py -v
```
Expected: FAILED — `ModuleNotFoundError: No module named 'app.services.publishing'`

- [ ] **Step 3: Implement `read_blog_posts()` in `app/services/publishing.py`**

Create `app/services/publishing.py`:

```python
from pathlib import Path

import frontmatter


def read_blog_posts(posts_dir: str | Path) -> list[dict]:
    """Read blog post markdown files from posts_dir, sorted newest-first.

    Excludes companion bluesky .txt files. Returns empty list if directory is missing.
    """
    posts_dir = Path(posts_dir)
    if not posts_dir.exists():
        return []

    posts = []
    for path in posts_dir.glob("*.md"):
        try:
            post = frontmatter.load(str(path))
        except Exception:
            continue
        slug = path.stem
        date_val = post.metadata.get("date")
        posts.append({
            "slug": slug,
            "filename": path.name,
            "title": post.metadata.get("title", slug),
            "date": str(date_val) if date_val else "",
            "draft": bool(post.metadata.get("draft", False)),
            "description": post.metadata.get("description", ""),
        })

    return sorted(posts, key=lambda p: p["date"], reverse=True)
```

- [ ] **Step 4: Run tests**

```bash
docker exec ikeos pytest tests/test_publishing.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/services/publishing.py tests/test_publishing.py
git commit -m "feat(publishing): add read_blog_posts() service"
```

---

### Task 2: Add `read_bluesky_posts()` to `app/services/publishing.py`

**Files:**
- Modify: `app/services/publishing.py`
- Modify: `tests/test_publishing.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_publishing.py`:

```python
from unittest.mock import patch, MagicMock
from app.services.publishing import read_bluesky_posts


def test_read_bluesky_posts_returns_formatted_posts(mocker):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "feed": [
            {
                "post": {
                    "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
                    "record": {"text": "Hello from IkeOS!", "createdAt": "2026-06-28T12:00:00Z"},
                    "likeCount": 5,
                    "repostCount": 2,
                    "replyCount": 1,
                }
            }
        ]
    }
    mocker.patch("app.services.publishing.requests.get", return_value=mock_resp)

    posts = read_bluesky_posts("ikeos.bsky.social", limit=5)
    assert len(posts) == 1
    assert posts[0]["text"] == "Hello from IkeOS!"
    assert posts[0]["likes"] == 5
    assert posts[0]["reposts"] == 2
    assert posts[0]["replies"] == 1
    assert "ikeos.bsky.social" in posts[0]["url"]


def test_read_bluesky_posts_returns_empty_on_error(mocker):
    mocker.patch("app.services.publishing.requests.get", side_effect=Exception("network error"))
    posts = read_bluesky_posts("ikeos.bsky.social")
    assert posts == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
docker exec ikeos pytest tests/test_publishing.py -k "bluesky" -v
```
Expected: FAILED — `ImportError` or `AttributeError`

- [ ] **Step 3: Implement `read_bluesky_posts()` in `app/services/publishing.py`**

Add `import requests` at the top, then add this function:

```python
import requests


def read_bluesky_posts(handle: str, *, limit: int = 5) -> list[dict]:
    """Fetch recent posts for a Bluesky handle using the public API.

    Returns empty list on any error (network failure, API change, missing handle).
    """
    try:
        resp = requests.get(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
            params={"actor": handle, "limit": limit},
            timeout=5,
        )
        if not resp.ok:
            return []
        feed = resp.json().get("feed", [])
        posts = []
        for item in feed:
            p = item.get("post", {})
            record = p.get("record", {})
            uri = p.get("uri", "")
            # Convert AT URI (at://did:.../rkey) to bsky.app URL
            rkey = uri.split("/")[-1] if "/" in uri else ""
            url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else ""
            posts.append({
                "text": record.get("text", ""),
                "created_at": record.get("createdAt", ""),
                "likes": p.get("likeCount", 0),
                "reposts": p.get("repostCount", 0),
                "replies": p.get("replyCount", 0),
                "url": url,
            })
        return posts
    except Exception:
        return []
```

- [ ] **Step 4: Run tests**

```bash
docker exec ikeos pytest tests/test_publishing.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/services/publishing.py tests/test_publishing.py
git commit -m "feat(publishing): add read_bluesky_posts() using public AT Protocol API"
```

---

### Task 3: Create `app/routes/publishing.py` and register blueprint

**Files:**
- Create: `app/routes/publishing.py`
- Modify: `app/__init__.py`
- Modify: `.env.example`

- [ ] **Step 1: Create `app/routes/publishing.py`**

```python
import os
from pathlib import Path

from flask import Blueprint, render_template

from app.services.publishing import read_blog_posts, read_bluesky_posts

bp = Blueprint("publishing", __name__)

AIOS_BLOG_POSTS_DIR = os.environ.get("AIOS_BLOG_POSTS_DIR", "")
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLOG_DRAFT_PATTERN = "-weekly-draft.md"


def _latest_draft_slug(posts: list[dict]) -> str | None:
    """Return slug of the newest post if it is a draft, else None."""
    if posts and posts[0]["draft"]:
        return posts[0]["slug"]
    return None


@bp.route("/publishing")
def index():
    posts = read_blog_posts(AIOS_BLOG_POSTS_DIR) if AIOS_BLOG_POSTS_DIR else []
    bluesky_posts = read_bluesky_posts(BLUESKY_HANDLE) if BLUESKY_HANDLE else []
    latest_draft_slug = _latest_draft_slug(posts)
    return render_template(
        "publishing.html",
        posts=posts,
        bluesky_posts=bluesky_posts,
        latest_draft_slug=latest_draft_slug,
        bluesky_handle=BLUESKY_HANDLE,
    )
```

- [ ] **Step 2: Register the blueprint in `app/__init__.py`**

Add after the existing blueprint imports:

```python
from app.routes.publishing import bp as publishing_bp
```

Add after the existing `app.register_blueprint(housekeeping_bp)`:

```python
app.register_blueprint(publishing_bp)
```

- [ ] **Step 3: Add env var to `.env.example`**

Add after `AIOS_BLOG_PROJECT_DIR`:

```
# Bluesky handle for the Publishing tab social panel (e.g. ikeos.bsky.social)
BLUESKY_HANDLE=
```

- [ ] **Step 4: Smoke-test the route**

```bash
docker exec ikeos python3 -c "
from app import create_app
app = create_app({'TESTING': True, 'SECRET_KEY': 'test'})
with app.test_client() as c:
    r = c.get('/publishing')
    print(r.status_code)
"
```
Expected: `200` (template will be missing until Task 4 — if you get 500/TemplateNotFound that's expected, route itself is wired)

- [ ] **Step 5: Commit**

```bash
git add app/routes/publishing.py app/__init__.py .env.example
git commit -m "feat(publishing): register /publishing blueprint"
```

---

### Task 4: Create `app/templates/publishing.html` and add nav tab

**Files:**
- Create: `app/templates/publishing.html`
- Modify: `app/templates/base.html`
- Modify: `app/static/style.css` (minor additions if needed)

- [ ] **Step 1: Create `app/templates/publishing.html`**

```html
{% extends "base.html" %}

{% block title %}Publishing — ʻIkeOS{% endblock %}

{% block content %}
<div class="publishing-page workspace-content">

  {# ── Latest post ── #}
  <section class="publishing-section">
    <h2 class="section-title">Latest</h2>
    {% if posts %}
      {% set latest = posts[0] %}
      <div class="publishing-card {% if latest.draft %}is-draft{% endif %}">
        <div class="publishing-card-header">
          <span class="publishing-title">{{ latest.title }}</span>
          {% if latest.draft %}
            <span class="pill pill-warning">Draft</span>
          {% else %}
            <span class="pill pill-ok">Published</span>
          {% endif %}
          <span class="publishing-date">{{ latest.date }}</span>
        </div>
        {% if latest.description %}
          <p class="publishing-description">{{ latest.description }}</p>
        {% endif %}
        <div class="publishing-actions">
          {% if latest.draft %}
            <a href="{{ url_for('housekeeping.blog_draft_editor') }}" class="btn btn-primary">Edit / Re-prompt</a>
            <button class="btn btn-success" onclick="publishPost()">Publish</button>
          {% endif %}
        </div>
      </div>
    {% else %}
      <p class="publishing-empty">No blog posts found. Check that <code>AIOS_BLOG_POSTS_DIR</code> is configured.</p>
    {% endif %}
  </section>

  {# ── All posts ── #}
  <section class="publishing-section">
    <h2 class="section-title">Posts</h2>
    {% if posts %}
      <div class="publishing-posts-list">
        {% for post in posts %}
          <div class="publishing-post-row">
            <span class="publishing-post-date">{{ post.date }}</span>
            <span class="publishing-post-title">{{ post.title }}</span>
            {% if post.draft %}
              <span class="pill pill-warning">Draft</span>
            {% else %}
              <span class="pill pill-ok">Published</span>
            {% endif %}
          </div>
          {% if loop.index == 10 and not loop.last %}
            <details class="publishing-older">
              <summary>Show older posts ({{ posts | length - 10 }} more)</summary>
          {% endif %}
        {% endfor %}
        {% if posts | length > 10 %}</details>{% endif %}
      </div>
    {% else %}
      <p class="publishing-empty">No posts yet.</p>
    {% endif %}
  </section>

  {# ── Bluesky ── #}
  {% if bluesky_handle %}
  <section class="publishing-section">
    <h2 class="section-title">Bluesky <span class="publishing-handle">@{{ bluesky_handle }}</span></h2>
    {% if bluesky_posts %}
      <div class="publishing-social-list">
        {% for bpost in bluesky_posts %}
          <div class="publishing-social-row">
            <p class="publishing-social-text">{{ bpost.text }}</p>
            <div class="publishing-social-meta">
              <span title="Likes">♥ {{ bpost.likes }}</span>
              <span title="Reposts">↺ {{ bpost.reposts }}</span>
              <span title="Replies">💬 {{ bpost.replies }}</span>
              <span class="publishing-social-date">{{ bpost.created_at[:10] }}</span>
              {% if bpost.url %}<a href="{{ bpost.url }}" target="_blank" rel="noopener">View ↗</a>{% endif %}
            </div>
          </div>
        {% endfor %}
      </div>
    {% else %}
      <p class="publishing-empty">No recent Bluesky posts, or handle not configured.</p>
    {% endif %}
  </section>
  {% endif %}

  {# ── Voice prompt (placeholder) ── #}
  <section class="publishing-section publishing-section--muted">
    <h2 class="section-title">Voice Prompt <span class="pill">Coming soon</span></h2>
    <p class="publishing-empty">Voice prompt editor and version history — deferred to a follow-up session.</p>
  </section>

</div>

<script>
async function publishPost() {
  if (!confirm('Publish this draft?')) return;
  const r = await fetch('/housekeeping/blog-draft/publish', {method: 'POST'});
  const data = await r.json();
  if (r.ok) {
    alert(data.message || 'Publish triggered.');
    location.reload();
  } else {
    alert('Publish failed: ' + (data.error || r.status));
  }
}
</script>
{% endblock %}
```

- [ ] **Step 2: Add CSS to `app/static/style.css`**

Find the end of the existing CSS and add:

```css
/* ── Publishing tab ── */
.publishing-page { padding: var(--space-4); max-width: 900px; }
.publishing-section { margin-bottom: var(--space-8); }
.publishing-section--muted { opacity: 0.6; }
.publishing-card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px; padding: var(--space-4); }
.publishing-card.is-draft { border-left: 3px solid var(--color-warning, #f59e0b); }
.publishing-card-header { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-2); }
.publishing-title { font-weight: 600; font-size: 1.1em; }
.publishing-date { color: var(--text-muted); font-size: 0.875em; margin-left: auto; }
.publishing-description { color: var(--text-muted); font-size: 0.9em; margin: 0 0 var(--space-3) 0; }
.publishing-actions { display: flex; gap: var(--space-2); }
.publishing-posts-list { display: flex; flex-direction: column; gap: 2px; }
.publishing-post-row { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-2) 0; border-bottom: 1px solid var(--border); }
.publishing-post-date { color: var(--text-muted); font-size: 0.8em; min-width: 90px; }
.publishing-post-title { flex: 1; }
.publishing-older summary { cursor: pointer; color: var(--text-muted); font-size: 0.875em; padding: var(--space-2) 0; }
.publishing-social-list { display: flex; flex-direction: column; gap: var(--space-3); }
.publishing-social-row { background: var(--surface-1); border: 1px solid var(--border); border-radius: 6px; padding: var(--space-3); }
.publishing-social-text { margin: 0 0 var(--space-2) 0; white-space: pre-wrap; }
.publishing-social-meta { display: flex; gap: var(--space-3); font-size: 0.8em; color: var(--text-muted); align-items: center; }
.publishing-social-meta a { color: var(--color-accent); text-decoration: none; }
.publishing-social-date { margin-left: auto; }
.publishing-handle { font-size: 0.8em; color: var(--text-muted); font-weight: 400; }
.publishing-empty { color: var(--text-muted); font-style: italic; }
```

- [ ] **Step 3: Add the nav tab to `app/templates/base.html`**

Find this line in `base.html`:
```html
      <a href="{{ url_for('housekeeping.index') }}" class="nav-link {% if request.endpoint == 'housekeeping.index' %}is-active{% endif %}">Housekeeping</a>
```

Add after it:
```html
      <a href="{{ url_for('publishing.index') }}" class="nav-link {% if request.endpoint == 'publishing.index' %}is-active{% endif %}">Publishing</a>
```

- [ ] **Step 4: Rebuild and verify the page loads**

```bash
docker.exe compose up --build -d ikeos && docker.exe compose logs -f ikeos
```

Wait for "Running on http://..." then open `http://192.168.1.77:5009/publishing` in a browser. Verify:
- Page loads without 500 errors
- "Latest" section shows or displays the "no posts" message (depending on whether AIOS_BLOG_POSTS_DIR is mounted)
- Nav tab "Publishing" is highlighted
- Bluesky section hidden if `BLUESKY_HANDLE` not set

- [ ] **Step 5: Commit**

```bash
git add app/templates/publishing.html app/templates/base.html app/static/style.css
git commit -m "feat(publishing): add Publishing tab UI with blog post list and Bluesky panel"
```

---

### Task 5: Wire up Bluesky with real data; verify paginated post list

**Files:**
- Modify: `app/.env` (local only — not committed)
- Verify end-to-end behavior

- [ ] **Step 1: Set `BLUESKY_HANDLE` in `.env`**

Add to the ikeos `.env` file (not committed):
```
BLUESKY_HANDLE=ikeos.bsky.social
```

- [ ] **Step 2: Rebuild and verify Bluesky section appears**

```bash
docker.exe compose up --build -d ikeos
```

Open `http://192.168.1.77:5009/publishing`. Verify:
- Bluesky section shows with `@ikeos.bsky.social`
- Posts appear (or "No recent Bluesky posts" if API call fails — check logs)
- Like/repost/reply counts display
- "View ↗" links open correct Bluesky URLs

- [ ] **Step 3: Verify pagination works for >10 posts**

If fewer than 10 posts exist, this is a visual check only. If you have >10 posts, confirm the `<details>` element shows "Show older posts (N more)" and expands correctly.

- [ ] **Step 4: Verify latest-draft publish button**

If the latest post is a draft, click "Publish" and confirm:
- The confirmation dialog appears
- It POSTs to `/housekeeping/blog-draft/publish`
- Response is handled (success alert or error display)

- [ ] **Step 5: Final commit**

```bash
git add .env.example  # if BLUESKY_HANDLE example was added
git commit -m "feat(publishing): Publishing tab complete — posts list, Bluesky panel, draft actions"
```

---

## Self-Review Checklist

- **Spec coverage:**
  - ✅ Latest blog post status + edit/re-prompt link + publish button
  - ✅ Past posts in reverse-chronological order, paginate at 10 via `<details>`
  - ✅ Bluesky posts with stats (likes, reposts, replies) and links
  - ✅ Modular service layer: `publishing.py` is separate from routes
  - ⏸ Voice prompt editor — explicitly deferred with placeholder section
  - ⏸ Additional socials beyond Bluesky — section is labelled but not wired (structural placeholder via the Bluesky section pattern)

- **Placeholder scan:** Voice prompt section has a "coming soon" badge — intentionally deferred, not a plan failure

- **Type consistency:**
  - `read_blog_posts(posts_dir: str | Path) -> list[dict]` — dict keys: slug, filename, title, date, draft, description
  - `read_bluesky_posts(handle: str, *, limit: int) -> list[dict]` — dict keys: text, created_at, likes, reposts, replies, url
  - Template accesses: `post.draft`, `post.date`, `post.title`, `post.description` — matches service output
