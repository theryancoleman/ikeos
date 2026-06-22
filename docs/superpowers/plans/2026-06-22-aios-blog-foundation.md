# aios-blog Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `aios-blog` Hugo static site project — scaffold, custom theme, deploy-via-rsync script, and Bluesky post script — that will host the AIOS weekly blog at `lab.ryancoleman.ca`.

**Architecture:** Plain git repo at `C:\Server\projects\aios-blog\` with no Docker component. Hugo builds static HTML from Markdown posts. A `deploy.sh` script runs `gitleaks` → `hugo build` → `rsync` to the cPanel server over SSH. A Python Bluesky script (adapted from worldwardle) posts the announcement.

**Tech Stack:** Hugo (static site generator), custom HTML/CSS theme, `atproto` Python library, `rsync` over SSH, `gitleaks` for secret scanning.

---

## File Map

```
C:\Server\projects\aios-blog\
├── hugo.toml                        # Hugo configuration
├── .env                             # Secrets — gitignored
├── .env.example                     # Placeholder template
├── .gitignore
├── deploy.sh                        # gitleaks → hugo build → rsync → bluesky
├── requirements.txt                 # atproto, python-dotenv
├── scripts/
│   └── post_bluesky.py              # Bluesky post script
├── content/
│   └── posts/
│       └── .gitkeep
├── weekly-notes/                    # Gitignored — session close-out notes
│   └── .gitkeep
└── themes/
    └── lab/
        ├── theme.toml
        └── layouts/
            ├── _default/
            │   ├── baseof.html
            │   ├── list.html
            │   └── single.html
            └── index.html
        └── static/
            └── css/
                └── style.css
```

---

### Task 1: Scaffold the Hugo site and config

**Files:**
- Create: `C:\Server\projects\aios-blog\hugo.toml`
- Create: `C:\Server\projects\aios-blog\.gitignore`
- Create: `C:\Server\projects\aios-blog\.env.example`
- Create: `C:\Server\projects\aios-blog\content\posts\.gitkeep`
- Create: `C:\Server\projects\aios-blog\weekly-notes\.gitkeep`

- [ ] **Step 1: Create project directory and Hugo config**

Create `C:\Server\projects\aios-blog\hugo.toml`:
```toml
baseURL = "https://lab.ryancoleman.ca/"
languageCode = "en-us"
title = "lab"
theme = "lab"
paginate = 10

[params]
  description = "Building a personal AI operating system with Claude"
  author = "Ryan Coleman"
  tagline = "An ongoing experiment in AI-assisted homelab development"
  bluesky = "ryan.ryancoleman.ca"

[markup]
  [markup.highlight]
    style = "monokai"
    lineNos = false
    noClasses = true

[build]
  writeStats = false
```

- [ ] **Step 2: Create .gitignore**

Create `C:\Server\projects\aios-blog\.gitignore`:
```
public/
.hugo_build.lock
.env
weekly-notes/
resources/
```

- [ ] **Step 3: Create .env.example**

Create `C:\Server\projects\aios-blog\.env.example`:
```
# SSH deploy target
BLOG_SSH_USER=your_cpanel_username
BLOG_SSH_HOST=ryancoleman.ca
BLOG_SSH_PORT=22
BLOG_SSH_PATH=/home/your_cpanel_username/public_html/lab
BLOG_HOST=lab.ryancoleman.ca

# Bluesky credentials
BLUESKY_HANDLE=yourhandle.bsky.social
BLUESKY_APP_PASSWORD=your-app-password-here
```

- [ ] **Step 4: Create content directory structure**

```bash
mkdir -p /mnt/c/Server/projects/aios-blog/content/posts
touch /mnt/c/Server/projects/aios-blog/content/posts/.gitkeep
mkdir -p /mnt/c/Server/projects/aios-blog/weekly-notes
touch /mnt/c/Server/projects/aios-blog/weekly-notes/.gitkeep
```

- [ ] **Step 5: Init git repo**

```bash
cd /mnt/c/Server/projects/aios-blog
git init
git add hugo.toml .gitignore .env.example content/ weekly-notes/
git commit -m "chore: init aios-blog Hugo site"
```

---

### Task 2: Create the lab Hugo theme

**Files:**
- Create: `themes/lab/theme.toml`
- Create: `themes/lab/layouts/_default/baseof.html`
- Create: `themes/lab/layouts/index.html`
- Create: `themes/lab/layouts/_default/list.html`
- Create: `themes/lab/layouts/_default/single.html`
- Create: `themes/lab/static/css/style.css`

- [ ] **Step 1: Create theme.toml**

Create `C:\Server\projects\aios-blog\themes\lab\theme.toml`:
```toml
name = "lab"
description = "Minimal dark theme for lab.ryancoleman.ca"
```

- [ ] **Step 2: Create baseof.html**

Create `C:\Server\projects\aios-blog\themes\lab\layouts\_default\baseof.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ if .IsHome }}{{ .Site.Title }}{{ else }}{{ .Title }} — {{ .Site.Title }}{{ end }}</title>
  <meta name="description" content="{{ with .Description }}{{ . }}{{ else }}{{ .Site.Params.description }}{{ end }}">
  <link rel="stylesheet" href="{{ "css/style.css" | absURL }}">
</head>
<body>
  <header class="site-header">
    <nav class="nav">
      <a href="{{ .Site.BaseURL }}" class="nav-brand">{{ .Site.Title }}</a>
      <div class="nav-links">
        <a href="{{ .Site.BaseURL }}">posts</a>
        <a href="https://bsky.app/profile/{{ .Site.Params.bluesky }}" target="_blank" rel="noopener">bluesky</a>
      </div>
    </nav>
  </header>
  <main class="main">
    {{ block "main" . }}{{ end }}
  </main>
  <footer class="site-footer">
    <p>{{ .Site.Params.author }} · <a href="https://bsky.app/profile/{{ .Site.Params.bluesky }}" target="_blank" rel="noopener">@{{ .Site.Params.bluesky }}</a></p>
  </footer>
</body>
</html>
```

- [ ] **Step 3: Create index.html (homepage)**

Create `C:\Server\projects\aios-blog\themes\lab\layouts\index.html`:
```html
{{ define "main" }}
<div class="hero">
  <h1>{{ .Site.Title }}</h1>
  <p class="hero-tagline">{{ .Site.Params.tagline }}</p>
</div>
<div class="posts">
  {{ range where .Site.RegularPages "Section" "posts" }}
  {{ if not .Params.draft }}
  <article class="post-card">
    <time class="post-date" datetime="{{ .Date.Format "2006-01-02" }}">{{ .Date.Format "January 2, 2006" }}</time>
    <h2><a href="{{ .RelPermalink }}">{{ .Title }}</a></h2>
    {{ with .Description }}<p class="post-excerpt">{{ . }}</p>{{ end }}
  </article>
  {{ end }}
  {{ end }}
</div>
{{ end }}
```

- [ ] **Step 4: Create list.html (section pages)**

Create `C:\Server\projects\aios-blog\themes\lab\layouts\_default\list.html`:
```html
{{ define "main" }}
<div class="section-header">
  <h1>{{ .Title }}</h1>
</div>
<div class="posts">
  {{ range .Pages }}
  {{ if not .Params.draft }}
  <article class="post-card">
    <time class="post-date" datetime="{{ .Date.Format "2006-01-02" }}">{{ .Date.Format "January 2, 2006" }}</time>
    <h2><a href="{{ .RelPermalink }}">{{ .Title }}</a></h2>
    {{ with .Description }}<p class="post-excerpt">{{ . }}</p>{{ end }}
  </article>
  {{ end }}
  {{ end }}
</div>
{{ end }}
```

- [ ] **Step 5: Create single.html (post pages)**

Create `C:\Server\projects\aios-blog\themes\lab\layouts\_default\single.html`:
```html
{{ define "main" }}
<article class="post">
  <header class="post-header">
    <time class="post-date" datetime="{{ .Date.Format "2006-01-02" }}">{{ .Date.Format "January 2, 2006" }}</time>
    <h1>{{ .Title }}</h1>
    {{ with .Description }}<p class="post-summary">{{ . }}</p>{{ end }}
  </header>
  <div class="post-content">
    {{ .Content }}
  </div>
  <footer class="post-footer">
    <a href="{{ .Site.BaseURL }}" class="back-link">← all posts</a>
  </footer>
</article>
{{ end }}
```

- [ ] **Step 6: Create style.css**

Create `C:\Server\projects\aios-blog\themes\lab\static\css\style.css`:
```css
:root {
  --bg: #0f172a;
  --surface: #1e293b;
  --border: #334155;
  --text: #e2e8f0;
  --text-muted: #94a3b8;
  --accent: #0ea5e9;
  --accent-hover: #38bdf8;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
}

*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 17px;
  line-height: 1.7;
}

a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-hover); }

/* ── Navigation ── */
.site-header { border-bottom: 1px solid var(--border); padding: 0 1.5rem; }
.nav {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
}
.nav-brand { font-size: 1.1rem; font-weight: 700; color: var(--text); letter-spacing: -0.02em; }
.nav-brand:hover { color: var(--accent); }
.nav-links { display: flex; gap: 1.5rem; }
.nav-links a { color: var(--text-muted); font-size: 0.9rem; }
.nav-links a:hover { color: var(--text); }

/* ── Main container ── */
.main { max-width: 720px; margin: 0 auto; padding: 2rem 1.5rem 5rem; }

/* ── Hero ── */
.hero {
  padding: 3rem 0 2.5rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2.5rem;
}
.hero h1 {
  font-size: 2.6rem;
  font-weight: 800;
  margin: 0 0 0.5rem;
  letter-spacing: -0.04em;
}
.hero-tagline { color: var(--text-muted); font-size: 1.05rem; margin: 0; }

/* ── Section header ── */
.section-header { padding: 2rem 0 1.5rem; border-bottom: 1px solid var(--border); margin-bottom: 2rem; }
.section-header h1 { font-size: 1.6rem; font-weight: 700; margin: 0; letter-spacing: -0.03em; }

/* ── Post cards ── */
.posts { display: flex; flex-direction: column; gap: 1.25rem; }

.post-card {
  padding: 1.25rem 1.5rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: border-color 0.15s ease;
}
.post-card:hover { border-color: var(--accent); }

.post-date {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 0.35rem;
}

.post-card h2 { margin: 0 0 0.4rem; font-size: 1.15rem; font-weight: 600; letter-spacing: -0.02em; }
.post-card h2 a { color: var(--text); }
.post-card h2 a:hover { color: var(--accent); }
.post-excerpt { margin: 0; color: var(--text-muted); font-size: 0.9rem; line-height: 1.55; }

/* ── Single post ── */
.post-header { padding-bottom: 2rem; border-bottom: 1px solid var(--border); margin-bottom: 2.5rem; }
.post-header h1 { font-size: 2rem; font-weight: 700; margin: 0.5rem 0 0; letter-spacing: -0.03em; line-height: 1.25; }
.post-summary { color: var(--text-muted); font-size: 1.05rem; margin: 1rem 0 0; line-height: 1.6; }

/* ── Post content typography ── */
.post-content h2 { font-size: 1.35rem; font-weight: 700; margin: 2.5rem 0 0.75rem; letter-spacing: -0.02em; }
.post-content h3 { font-size: 1.1rem; font-weight: 600; margin: 2rem 0 0.5rem; color: var(--text-muted); }
.post-content p { margin: 1rem 0; }
.post-content ul, .post-content ol { padding-left: 1.5rem; margin: 1rem 0; }
.post-content li { margin: 0.35rem 0; }
.post-content blockquote {
  margin: 1.5rem 0;
  padding: 1rem 1.25rem;
  border-left: 3px solid var(--accent);
  background: var(--surface);
  border-radius: 0 6px 6px 0;
  color: var(--text-muted);
  font-style: italic;
}
.post-content code {
  font-family: var(--font-mono);
  font-size: 0.87em;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 0.15em 0.4em;
  border-radius: 3px;
  color: var(--accent-hover);
}
.post-content pre {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.25rem;
  overflow-x: auto;
  margin: 1.5rem 0;
}
.post-content pre code {
  background: none;
  border: none;
  padding: 0;
  color: var(--text);
  font-size: 0.875rem;
}
.post-content img { max-width: 100%; border-radius: 6px; display: block; margin: 1.5rem 0; }
.post-content a { text-decoration: underline; text-decoration-color: var(--border); }
.post-content a:hover { text-decoration-color: var(--accent); }
.post-content hr { border: none; border-top: 1px solid var(--border); margin: 2.5rem 0; }
.post-content table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; font-size: 0.9rem; }
.post-content th { text-align: left; padding: 0.6rem 1rem; border-bottom: 2px solid var(--border); color: var(--text-muted); font-weight: 600; }
.post-content td { padding: 0.6rem 1rem; border-bottom: 1px solid var(--border); }
.post-content tr:last-child td { border-bottom: none; }

/* ── Post footer ── */
.post-footer { margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border); }
.back-link { color: var(--text-muted); font-size: 0.9rem; }
.back-link:hover { color: var(--accent); }

/* ── Site footer ── */
.site-footer { text-align: center; padding: 2rem 1.5rem; border-top: 1px solid var(--border); color: var(--text-muted); font-size: 0.85rem; }
.site-footer a { color: var(--text-muted); }
.site-footer a:hover { color: var(--accent); }

/* ── Responsive ── */
@media (max-width: 640px) {
  .hero h1 { font-size: 1.9rem; }
  .post-header h1 { font-size: 1.5rem; }
  .nav { height: 52px; }
  .main { padding: 1.5rem 1rem 4rem; }
}
```

- [ ] **Step 7: Verify Hugo builds without errors**

```bash
cd /mnt/c/Server/projects/aios-blog
hugo build
```

Expected output: `Start building sites…` then `Total in Xms`. No errors. `public/` directory created.

- [ ] **Step 8: Commit the theme**

```bash
cd /mnt/c/Server/projects/aios-blog
git add themes/
git commit -m "feat: add lab Hugo theme — dark minimal design"
```

---

### Task 3: Bluesky post script

**Files:**
- Create: `scripts/post_bluesky.py`
- Create: `requirements.txt`

- [ ] **Step 1: Create requirements.txt**

Create `C:\Server\projects\aios-blog\requirements.txt`:
```
atproto>=0.0.50
python-dotenv>=1.0
```

- [ ] **Step 2: Create scripts/post_bluesky.py**

Create `C:\Server\projects\aios-blog\scripts\post_bluesky.py`:
```python
#!/usr/bin/env python3
"""Post a blog announcement to Bluesky. Credentials read from .env."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CHAR_LIMIT = 300


def post(text: str) -> None:
    if len(text) > CHAR_LIMIT:
        raise ValueError(f"Post text is {len(text)} chars — exceeds {CHAR_LIMIT}-char Bluesky limit")

    handle = os.environ.get("BLUESKY_HANDLE")
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_password:
        raise EnvironmentError("BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set in .env")

    from atproto import Client

    client = Client()
    client.login(handle, app_password)
    client.send_post(text=text)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: post_bluesky.py <text>", file=sys.stderr)
        sys.exit(1)
    try:
        post(sys.argv[1])
        print("Posted to Bluesky.")
    except (ValueError, EnvironmentError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 3: Write unit tests**

Create `C:\Server\projects\aios-blog\tests\test_post_bluesky.py`:
```python
import sys
import types
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from scripts.post_bluesky import post, CHAR_LIMIT


def test_raises_on_text_over_limit():
    long_text = "x" * (CHAR_LIMIT + 1)
    with pytest.raises(ValueError, match="exceeds"):
        post(long_text)


def test_raises_when_env_missing(monkeypatch):
    monkeypatch.delenv("BLUESKY_HANDLE", raising=False)
    monkeypatch.delenv("BLUESKY_APP_PASSWORD", raising=False)
    with pytest.raises(EnvironmentError, match="must be set"):
        post("hello")


def test_posts_successfully(monkeypatch):
    monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
    monkeypatch.setenv("BLUESKY_APP_PASSWORD", "secret")

    mock_client = MagicMock()
    mock_atproto = types.ModuleType("atproto")
    mock_atproto.Client = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"atproto": mock_atproto}):
        post("Hello, lab!")

    mock_client.login.assert_called_once_with("test.bsky.social", "secret")
    mock_client.send_post.assert_called_once_with(text="Hello, lab!")


def test_exact_limit_is_allowed(monkeypatch):
    monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
    monkeypatch.setenv("BLUESKY_APP_PASSWORD", "secret")

    mock_client = MagicMock()
    mock_atproto = types.ModuleType("atproto")
    mock_atproto.Client = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"atproto": mock_atproto}):
        post("x" * CHAR_LIMIT)  # should not raise
```

- [ ] **Step 4: Run tests — expect FAIL (module not importable yet before install)**

```bash
cd /mnt/c/Server/projects/aios-blog
python3 -m pytest tests/test_post_bluesky.py -v
```

Expected: 4 tests pass (unittest.mock patches atproto so no install needed).

- [ ] **Step 5: Commit**

```bash
cd /mnt/c/Server/projects/aios-blog
git add scripts/ requirements.txt tests/
git commit -m "feat: add Bluesky post script with unit tests"
```

---

### Task 4: Deploy script

**Files:**
- Create: `deploy.sh`

- [ ] **Step 1: Create deploy.sh**

Create `C:\Server\projects\aios-blog\deploy.sh`:
```bash
#!/usr/bin/env bash
# Usage: ./deploy.sh [post-file] [bluesky-text]
# post-file: path to the Markdown post being published (for gitleaks scan)
# bluesky-text: if provided, posts to Bluesky after successful deploy
set -euo pipefail

# Load .env if present
if [ -f "$(dirname "$0")/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$(dirname "$0")/.env"
  set +a
fi

POST_FILE="${1:-}"
BLUESKY_TEXT="${2:-}"

# ── 1. Secret scan ──────────────────────────────────────────────────────────
if [ -n "$POST_FILE" ] && [ -f "$POST_FILE" ]; then
  if command -v gitleaks &>/dev/null; then
    echo "==> Scanning ${POST_FILE} for secrets..."
    tmpdir=$(mktemp -d)
    cp "$POST_FILE" "$tmpdir/"
    if ! gitleaks detect --source "$tmpdir" --no-banner 2>&1; then
      echo "ERROR: gitleaks flagged secrets in the post. Aborting."
      rm -rf "$tmpdir"
      exit 1
    fi
    rm -rf "$tmpdir"
    echo "    Clean."
  else
    echo "WARNING: gitleaks not found — skipping secret scan. Install from https://github.com/gitleaks/gitleaks"
  fi
fi

# ── 2. Build ─────────────────────────────────────────────────────────────────
echo "==> Building Hugo site..."
hugo --minify
echo "    Build complete."

# ── 3. Deploy ────────────────────────────────────────────────────────────────
: "${BLOG_SSH_USER:?BLOG_SSH_USER not set in .env}"
: "${BLOG_SSH_HOST:?BLOG_SSH_HOST not set in .env}"
: "${BLOG_SSH_PATH:?BLOG_SSH_PATH not set in .env}"

echo "==> Deploying to ${BLOG_SSH_USER}@${BLOG_SSH_HOST}:${BLOG_SSH_PATH}..."
rsync -avz --delete \
  -e "ssh -p ${BLOG_SSH_PORT:-22}" \
  public/ \
  "${BLOG_SSH_USER}@${BLOG_SSH_HOST}:${BLOG_SSH_PATH}/"

echo "==> Site live at https://${BLOG_HOST:-$BLOG_SSH_HOST}/"

# ── 4. Bluesky ───────────────────────────────────────────────────────────────
if [ -n "$BLUESKY_TEXT" ]; then
  echo "==> Posting to Bluesky..."
  python3 "$(dirname "$0")/scripts/post_bluesky.py" "$BLUESKY_TEXT"
  echo "==> Done."
fi
```

- [ ] **Step 2: Make executable**

```bash
chmod +x /mnt/c/Server/projects/aios-blog/deploy.sh
```

- [ ] **Step 3: Commit**

```bash
cd /mnt/c/Server/projects/aios-blog
git add deploy.sh
git commit -m "feat: add rsync deploy script with gitleaks scan and Bluesky post"
```

---

### Task 5: First test post — end-to-end verification

**Files:**
- Create: `content/posts/2026-06-22-hello-lab.md`

- [ ] **Step 1: Create a sample post**

Create `C:\Server\projects\aios-blog\content\posts\2026-06-22-hello-lab.md`:
```markdown
---
title: "Hello, Lab"
date: 2026-06-22
description: "Launching lab.ryancoleman.ca — a weekly blog about building a homelab AI operating system with Claude."
draft: true
---

Welcome to **lab** — a weekly blog about building and operating a personal AI operating system (AIOS) with Claude as a collaborative partner.

## What this is

Each week I ship changes to IkeOS, a homelab management platform that treats Claude Code as a first-class operator. This blog documents what we built, what we considered (and rejected), and the reasoning behind it.

## What's coming

- Weekly digests generated by Claude from vault entries, git history, and session notes
- Deep dives on specific skills and infrastructure decisions
- The occasional project feature post

Stay tuned — or follow on [Bluesky](https://bsky.app).
```

- [ ] **Step 2: Build with draft excluded (production build)**

```bash
cd /mnt/c/Server/projects/aios-blog
hugo --minify
```

Expected: `public/` is generated. The hello-lab post does NOT appear (it's `draft: true`).

Verify: `ls public/posts/` — should be empty or show only non-draft posts.

- [ ] **Step 3: Build with drafts included (local preview)**

```bash
hugo server -D --port 1313
```

Expected: Hugo dev server starts. Open `http://localhost:1313` in a browser to verify the design renders correctly. The hello-lab post should appear. Ctrl+C to stop.

- [ ] **Step 4: Commit the sample post**

```bash
cd /mnt/c/Server/projects/aios-blog
git add content/posts/2026-06-22-hello-lab.md
git commit -m "docs: add hello-lab sample post (draft: true)"
```

---

### Task 6: GitHub public repo setup

> **Note:** This task requires interactive steps the user performs. The subagent documents the steps; the user executes them.

- [ ] **Step 1: Create public GitHub repo**

On GitHub: create a new **public** repository named `aios-blog` under your account. Do NOT initialize with a README.

- [ ] **Step 2: Push local repo**

```bash
cd /mnt/c/Server/projects/aios-blog
git remote add origin https://github.com/<your-username>/aios-blog.git
git push -u origin main
```

- [ ] **Step 3: Verify .env is not tracked**

```bash
cd /mnt/c/Server/projects/aios-blog
git ls-files | grep -E "\.env$" && echo "ERROR: .env is tracked" || echo "OK: .env not tracked"
```

Expected: `OK: .env not tracked`

- [ ] **Step 4: Verify weekly-notes/ is not tracked**

```bash
cd /mnt/c/Server/projects/aios-blog
git ls-files | grep "weekly-notes/" | grep -v ".gitkeep" && echo "WARNING: notes tracked" || echo "OK: weekly-notes gitignored"
```

Expected: `OK: weekly-notes gitignored`
