# Blog Publish Pipeline Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the blog publish pipeline so clicking "Publish" reliably takes a draft live — build, deploy, git commit/push, and Bluesky post — instead of silently doing nothing or partially completing.

**Architecture:** The publish session's `initial_command` (built in `app/services/driver.py`) currently tells the Claude Code session to run `deploy.sh` directly against the `-draft.md` file. `deploy.sh` runs `hugo --minify`, which silently excludes any post with `draft: true` from the build — so the site never gets the new post even when the session "succeeds." The command also never asks for a git commit/push, so even when a post makes it live (confirmed for the 2026-07-24 post), it's never captured in git. Fix: move the mechanical, must-be-exact steps (flip `draft: false`, rename to the canonical filename, build, deploy, commit, push) into a deterministic script (`publish.sh`) in the aios-blog repo, and reduce the Claude Code session's job to invoking that one script. This removes the LLM's room to interpret "publish" inconsistently.

**Tech Stack:** Python 3.10 (aios-blog scripts, matches the interpreter already used by `scripts/post_bluesky.py`), Bash (deploy/publish scripts), `python-frontmatter` (already installed on this host; not yet declared in aios-blog's `requirements.txt`), pytest (both repos already use it).

**Spec:** No separate spec doc — derived from live investigation (vault entry `ideas/2026-08-15-blog-posts-not-publishing.md`, git history in `/mnt/c/Server/projects/aios-blog`, and the current site at https://lab.ryancoleman.ca/posts/).

## Global Constraints

- `aios-blog` scripts run under the system `python3` (3.10) already used by `deploy.sh` / `post_bluesky.py` — do not require a newer interpreter.
- `driver.py` is the single place IkeOS constructs `initial_command` strings (per its own module docstring) — no other file may build a publish command.
- Never commit `.env` or secrets; `publish.sh` must not print or log credentials.
- Keep `deploy.sh` unchanged and general-purpose (it's also used for non-post site deploys) — new post-specific logic goes in a new `publish.sh`, not inside `deploy.sh`.
- The original `-draft.md` file must be left in place after publish (matches existing repo convention — draft files are left as local working history, e.g. `2026-07-05-weekly-draft.md` still exists after that post published).

---

### Task 1: `publish_post.py` — flip draft flag and compute canonical filename

**Files:**
- Create: `/mnt/c/Server/projects/aios-blog/scripts/publish_post.py`
- Create: `/mnt/c/Server/projects/aios-blog/tests/test_publish_post.py`
- Modify: `/mnt/c/Server/projects/aios-blog/requirements.txt`

**Interfaces:**
- Produces: `canonical_path(draft_path: Path) -> Path` — strips the `-draft.md` suffix, raises `ValueError` if the filename doesn't end with it.
- Produces: `publish(draft_path: Path) -> Path` — loads the draft's frontmatter, sets `draft: False`, writes it to `canonical_path(draft_path)`, returns that path. Leaves the original draft file untouched.
- Produces: CLI entrypoint — `python3 scripts/publish_post.py <draft-file>` prints the canonical path to stdout (used by `publish.sh` in Task 2).

- [ ] **Step 1: Add `python-frontmatter` to requirements.txt**

Add this line to `/mnt/c/Server/projects/aios-blog/requirements.txt`:

```
python-frontmatter>=1.0
```

- [ ] **Step 2: Write the failing tests**

Create `/mnt/c/Server/projects/aios-blog/tests/test_publish_post.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.publish_post import canonical_path, publish


def test_canonical_path_strips_draft_suffix():
    assert canonical_path(Path("content/posts/2026-07-12-weekly-draft.md")) == Path(
        "content/posts/2026-07-12-weekly.md"
    )


def test_canonical_path_rejects_non_draft_filename():
    with pytest.raises(ValueError, match="does not end with"):
        canonical_path(Path("content/posts/2026-07-12-weekly.md"))


def test_publish_flips_draft_flag_and_writes_canonical_file(tmp_path):
    draft = tmp_path / "2026-07-12-weekly-draft.md"
    draft.write_text(
        "---\n"
        'title: "Week of July 12"\n'
        "date: 2026-07-12\n"
        "draft: true\n"
        "low_activity: false\n"
        "---\n\n"
        "## What We Built\n\nSome content.\n"
    )

    result = publish(draft)

    assert result == tmp_path / "2026-07-12-weekly.md"
    assert result.exists()

    import frontmatter

    published = frontmatter.load(result)
    assert published["draft"] is False
    assert published["title"] == "Week of July 12"
    assert draft.exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /mnt/c/Server/projects/aios-blog && python3 -m pytest tests/test_publish_post.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'scripts.publish_post'`

- [ ] **Step 4: Write the implementation**

Create `/mnt/c/Server/projects/aios-blog/scripts/publish_post.py`:

```python
#!/usr/bin/env python3
"""Promote a blog draft to a published post.

Flips `draft: true` to `draft: false` in the frontmatter and writes the
result to the canonical (non "-draft") filename. The original draft file
is left in place. Prints the canonical file's path to stdout so callers
(publish.sh) can pick it up.
"""
import sys
from pathlib import Path

import frontmatter

_DRAFT_SUFFIX = "-draft.md"


def canonical_path(draft_path: Path) -> Path:
    if not draft_path.name.endswith(_DRAFT_SUFFIX):
        raise ValueError(f"{draft_path} does not end with '{_DRAFT_SUFFIX}'")
    canonical_name = draft_path.name[: -len(_DRAFT_SUFFIX)] + ".md"
    return draft_path.with_name(canonical_name)


def publish(draft_path: Path) -> Path:
    post = frontmatter.load(draft_path)
    post["draft"] = False
    out_path = canonical_path(draft_path)
    with open(out_path, "w") as f:
        frontmatter.dump(post, f)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: publish_post.py <draft-file>", file=sys.stderr)
        sys.exit(1)
    print(publish(Path(sys.argv[1])))
```

- [ ] **Step 5: Install the new dependency and run tests to verify they pass**

Run: `cd /mnt/c/Server/projects/aios-blog && pip install -r requirements.txt && python3 -m pytest tests/test_publish_post.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Server/projects/aios-blog
git add scripts/publish_post.py tests/test_publish_post.py requirements.txt
git commit -m "feat: add publish_post.py to flip draft flag and compute canonical post filename"
```

---

### Task 2: `publish.sh` — orchestrate promote, deploy, and git commit/push

**Files:**
- Create: `/mnt/c/Server/projects/aios-blog/publish.sh`

**Interfaces:**
- Consumes: `scripts/publish_post.py <draft-file>` (Task 1) — stdout is the canonical file path.
- Consumes: existing `/mnt/c/Server/projects/aios-blog/deploy.sh <post-file> [bluesky-file]` — unchanged, builds + rsyncs + posts to Bluesky.
- Produces: `bash publish.sh <draft-file> [bluesky-file]`, invoked from the aios-blog repo root. Used by `driver.py` in Task 3.

- [ ] **Step 1: Write the script**

Create `/mnt/c/Server/projects/aios-blog/publish.sh`:

```bash
#!/usr/bin/env bash
# Usage: ./publish.sh <draft-file> [bluesky-file]
# Promotes a draft to a published post (flips draft:false, renames to the
# canonical filename), builds and deploys the site via deploy.sh, then
# commits and pushes the published post.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DRAFT_FILE="${1:?Usage: publish.sh <draft-file> [bluesky-file]}"
BLUESKY_FILE="${2:-}"

echo "==> Promoting draft to published post..."
PUBLISHED_FILE="$(python3 "${SCRIPT_DIR}/scripts/publish_post.py" "$DRAFT_FILE")"
echo "    Published file: ${PUBLISHED_FILE}"

BLUESKY_TEXT=""
if [ -n "$BLUESKY_FILE" ] && [ -f "$BLUESKY_FILE" ]; then
  BLUESKY_TEXT="$(cat "$BLUESKY_FILE")"
fi

"${SCRIPT_DIR}/deploy.sh" "$PUBLISHED_FILE" "$BLUESKY_TEXT"

echo "==> Committing published post to git..."
cd "$SCRIPT_DIR"
git add "$PUBLISHED_FILE"
if [ -n "$BLUESKY_FILE" ] && [ -f "$BLUESKY_FILE" ]; then
  git add "$BLUESKY_FILE"
fi

if git diff --cached --quiet; then
  echo "    Nothing to commit."
else
  git commit -m "feat: publish $(basename "$PUBLISHED_FILE" .md)"
  git push
  echo "    Pushed."
fi
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x /mnt/c/Server/projects/aios-blog/publish.sh`

- [ ] **Step 3: Syntax-check the script**

Run: `bash -n /mnt/c/Server/projects/aios-blog/publish.sh`
Expected: no output (exit code 0)

- [ ] **Step 4: Dry-run the promote step against a throwaway fixture**

This verifies `publish_post.py` wiring inside the script without touching real content, deploying, or pushing:

```bash
cd /mnt/c/Server/projects/aios-blog
mkdir -p /tmp/publish-sh-smoketest/content/posts
cat > /tmp/publish-sh-smoketest/content/posts/2099-01-01-smoketest-draft.md <<'EOF'
---
title: "Smoketest"
date: 2099-01-01
draft: true
low_activity: false
---

Smoketest content.
EOF
python3 scripts/publish_post.py /tmp/publish-sh-smoketest/content/posts/2099-01-01-smoketest-draft.md
rm -rf /tmp/publish-sh-smoketest
```

Expected: prints `/tmp/publish-sh-smoketest/content/posts/2099-01-01-smoketest.md` and that file exists with `draft: false` before cleanup (inspect with `cat` before the `rm -rf` if you want to confirm visually).

- [ ] **Step 5: Commit**

```bash
cd /mnt/c/Server/projects/aios-blog
git add publish.sh
git commit -m "feat: add publish.sh to orchestrate draft promotion, deploy, and git publish"
```

---

### Task 3: Point `driver.py` at `publish.sh` instead of `deploy.sh`

**Files:**
- Modify: `/mnt/c/Server/projects/ikeos/app/services/driver.py:57-71`
- Modify: `/mnt/c/Server/projects/ikeos/tests/test_driver.py:42-49`

**Interfaces:**
- Consumes: `publish.sh <draft-file> [bluesky-file]` (Task 2).
- Produces: `publish_blog_draft(draft_name: str, bluesky_name: str, model: str | None = None) -> SessionResult` — signature unchanged, only the `initial_command` content changes.

- [ ] **Step 1: Update the failing/changed test first**

Replace the existing test in `/mnt/c/Server/projects/ikeos/tests/test_driver.py` (lines 42-49):

```python
def test_publish_blog_draft_builds_publish_prompt(monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_PROJECT_DIR", "/mnt/c/Server/projects/aios-blog")
    with patch("app.services.driver.create_session", return_value=OK) as cs:
        publish_blog_draft("2026-07-01-weekly-draft.md", "2026-07-01-weekly-bluesky.txt")
    kw = cs.call_args.kwargs
    assert (
        "bash publish.sh content/posts/2026-07-01-weekly-draft.md "
        "content/posts/2026-07-01-weekly-bluesky.txt" in kw["initial_command"]
    )
    assert kw["project"] == "aios-blog"
    assert kw["name"] == "blog-publish-2026-07-01-weekly-draft"


def test_publish_blog_draft_omits_bluesky_arg_when_absent(monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_PROJECT_DIR", "/mnt/c/Server/projects/aios-blog")
    with patch("app.services.driver.create_session", return_value=OK) as cs:
        publish_blog_draft("2026-07-01-weekly-draft.md", "")
    kw = cs.call_args.kwargs
    assert kw["initial_command"].startswith(
        "Run `bash publish.sh content/posts/2026-07-01-weekly-draft.md`"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Server/projects/ikeos && docker exec ikeos pytest tests/test_driver.py -v`
Expected: FAIL — `test_publish_blog_draft_builds_publish_prompt` fails because `initial_command` still contains `deploy.sh`; `test_publish_blog_draft_omits_bluesky_arg_when_absent` fails/errors since the function doesn't exist under that name yet (it does — same function, just check the assertion fails).

- [ ] **Step 3: Update the implementation**

In `/mnt/c/Server/projects/ikeos/app/services/driver.py`, replace `publish_blog_draft` (lines 57-71):

```python
def publish_blog_draft(draft_name: str, bluesky_name: str, model: str | None = None) -> SessionResult:
    project_dir = _blog_project_dir()
    bluesky_arg = f" content/posts/{bluesky_name}" if bluesky_name else ""
    command = (
        f"Run `bash publish.sh content/posts/{draft_name}{bluesky_arg}` in {project_dir}. "
        "This promotes the draft to a published post, builds and deploys the site, "
        "commits and pushes the change, and posts to Bluesky if a companion text file "
        "was given."
    )
    stem = draft_name.rsplit(".", 1)[0]
    return create_session(
        name=f"blog-publish-{stem[:30]}",
        project="aios-blog",
        project_dir=project_dir,
        initial_command=command,
        model=model,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Server/projects/ikeos && docker exec ikeos pytest tests/test_driver.py -v`
Expected: all tests in the file PASS

- [ ] **Step 5: Run the full ikeos test suite to check for regressions**

Run: `cd /mnt/c/Server/projects/ikeos && docker exec ikeos pytest -v`
Expected: all tests PASS (no regressions elsewhere)

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/services/driver.py tests/test_driver.py
git commit -m "fix: publish_blog_draft invokes publish.sh so drafts actually go live and get committed"
```

---

## Out of scope (handled after this plan, with explicit confirmation)

Recovering the backlog of already-stuck drafts (2026-07-12, 2026-07-13, 2026-07-31, 2026-08-07, and committing the already-live-but-uncommitted 2026-07-24 post) requires pushing to the `ikeos-blog` GitHub remote and posting to the live Bluesky account for older content. Per the "actions visible to others / hard to reverse" rule, that runs as a separate, explicitly confirmed step using the now-fixed `publish.sh` — not automatically as part of this plan.
