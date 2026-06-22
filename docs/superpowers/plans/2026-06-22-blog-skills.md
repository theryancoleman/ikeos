# Blog Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two Claude skills in `claude-config`: a new `/blog` skill for generating blog post drafts on demand, and a modification to `/close-session` that captures a three-prompt blog notes block appended to the current week's notes file.

**Architecture:** Both live in `C:\Server\claude-config\global\commands\`. The `/blog` skill reads git log (ikeos + claude-config repos), vault entries, DECISIONS.md, and the weekly notes file, then writes a Markdown draft + Bluesky text to `aios-blog/content/posts/`. The `/close-session` modification adds a Phase 5a step that appends highlight/why/challenge to `aios-blog/weekly-notes/YYYY-Wxx.md`.

**Tech Stack:** Markdown skill files, bash commands for git/file reads, Python3 inline for date calculations.

**Prerequisite:** Plan `2026-06-22-aios-blog-foundation.md` complete — `C:\Server\projects\aios-blog\` exists with `weekly-notes/` and `content/posts/` directories.

---

## File Map

```
C:\Server\claude-config\global\commands\
├── blog.md            # NEW: /blog skill
└── close-session.md   # MODIFY: add Phase 5a blog notes block
```

---

### Task 1: Create the /blog skill

**Files:**
- Create: `C:\Server\claude-config\global\commands\blog.md`

The `/blog` skill has two modes:
1. **Weekly digest** (no args or `weekly`): reads last 7 days of git history + vault + weekly notes → generates structured post
2. **Topic post** (any other args): generates a focused post on the given topic, reading relevant vault entries and skills

- [ ] **Step 1: Create blog.md**

Create `C:\Server\claude-config\global\commands\blog.md`:

````markdown
---
name: blog
description: Generate a blog post draft for lab.ryancoleman.ca — weekly digest or topic-driven. Writes to aios-blog/content/posts/ with a companion Bluesky text block.
---

Generate a blog post draft for lab.ryancoleman.ca.

**Two modes:**
- No args or `weekly`: generate the weekly AIOS digest from the last 7 days of activity
- Any other text: generate a focused post on that topic (e.g., `/blog explain the housekeeping skill system`)

## Step 0: Determine mode

If args are empty or equal "weekly": **WEEKLY mode**.
Otherwise: **TOPIC mode** with the args as the topic prompt.

---

## WEEKLY MODE

### Step 1: Collect data

Run each of these in sequence and capture the output:

**Git log — ikeos repo:**
```bash
git -C /mnt/c/Server/projects/ikeos log --since="7 days ago" --oneline --no-merges
```

**Git log — claude-config repo:**
```bash
git -C /mnt/c/Server/claude-config log --since="7 days ago" --oneline --no-merges
```

**Vault entries updated this week — ikeos project:**

Read all files matching `/mnt/c/Server/obsidian-vault/projects/ikeos/{bugs,ideas,notes,grill-me}/*.md`. Collect entries where the `updated` or `created` field is within the last 7 days. Note title, type, status, and any `why` field.

**DECISIONS.md changes:**
```bash
git -C /mnt/c/Server/projects/ikeos log --since="7 days ago" --oneline -- .claude/DECISIONS.md
```
If commits exist, read the file:
```bash
cat /mnt/c/Server/projects/ikeos/.claude/DECISIONS.md
```

**Weekly notes (from close-session):**

Calculate the ISO week number for today:
```python3
import datetime
today = datetime.date.today()
year, week, _ = today.isocalendar()
print(f"{year}-W{week:02d}")
```

Read `/mnt/c/Server/projects/aios-blog/weekly-notes/<YYYY-Wxx>.md` if it exists. This file contains session highlights, whys, and challenges captured during `/close-session`.

**Skills changes:**
```bash
git -C /mnt/c/Server/claude-config log --since="7 days ago" --oneline -- global/commands/ global/skills/ plugins/
```

### Step 2: Assess activity level

Count meaningful commits (excluding `chore:` and `docs:`). If fewer than 3 AND no new/updated skills AND no weekly notes file: flag the post as `low-activity` and note it in the draft frontmatter. The draft is still generated — the user decides whether to publish or pull from the backlog instead.

### Step 3: Generate the weekly post draft

Write a blog post to `/mnt/c/Server/projects/aios-blog/content/posts/<YYYY-MM-DD>-weekly-draft.md` with this exact structure:

```markdown
---
title: "Week of <Month DD> — <brief 4-6 word summary of the week>"
date: <YYYY-MM-DD>
description: "<One sentence summary for the post card>"
draft: true
low_activity: <true|false>
---

## What We Built

<For each significant commit or completed idea, 1-3 sentences. Focus on the user-visible change and why it matters. Group related commits. Skip pure chores and minor typo fixes.>

## What We Considered (and Said No)

<Vault ideas that were deferred, rejected, or are still open. Explain the reasoning — what trade-off or dependency made us hold off. If nothing was deferred this week, omit this section.>

## Challenges & How We Solved Them

<From weekly notes and bug fixes. If a session note mentioned a challenge, expand it with the actual solution. This is where the interesting engineering stories live.>

## The Skill Stack

<New or updated skills in claude-config. For each: name, what it does, and why it was added/changed. Omit if no skills changed this week.>

## What's Next

<Top 2-3 open high-priority vault items for ikeos. One sentence each.>
```

Write authoritatively. Use your reasoning about the commits and vault entries to explain decisions — you were there for these sessions. The post should read like a thoughtful practitioner writing for peers, not a commit log summary.

### Step 4: Generate the Bluesky announcement

Immediately after the Markdown post, write a `BLUESKY.txt` file at `/mnt/c/Server/projects/aios-blog/content/posts/<YYYY-MM-DD>-weekly-bluesky.txt`:

```
<Post title or week summary — max 80 chars>

<2-3 sentences hitting the highlight + one interesting decision from the week>

lab.ryancoleman.ca/posts/<slug>/

#AIOS #ClaudeCode #homelab
```

Total length must be ≤ 300 characters. Count and confirm before writing.

### Step 5: Report

Tell the user:
- Draft saved to: `content/posts/<filename>.md`
- Bluesky text saved to: `content/posts/<filename>-bluesky.txt`
- Activity level: normal / low-activity
- If low-activity: suggest pulling a backlog draft instead (list any `draft: true` posts in `content/posts/`)
- Next step: review the draft, then run `bash deploy.sh content/posts/<filename>.md "$(cat content/posts/<filename>-bluesky.txt)"`

---

## TOPIC MODE

### Step 1: Read relevant sources

Read the following based on the topic:
- `/mnt/c/Server/claude-config/global/commands/` — skill files relevant to the topic
- `/mnt/c/Server/obsidian-vault/projects/ikeos/ideas/` and `notes/` — entries related to the topic
- Recent git commits related to the topic: `git -C /mnt/c/Server/projects/ikeos log --oneline --grep="<keywords from topic>" | head -20`

### Step 2: Generate the topic post

Write the post to `/mnt/c/Server/projects/aios-blog/content/posts/<YYYY-MM-DD>-<slug>.md`:

```markdown
---
title: "<Descriptive title>"
date: <YYYY-MM-DD>
description: "<One sentence for the post card>"
draft: true
---

<Write a focused, practitioner-level post on the topic. Use concrete examples from the actual codebase and skills. Show real commands, real skill file excerpts, real decision reasoning. Aim for 400-800 words.>
```

### Step 3: Generate Bluesky text

Write `/mnt/c/Server/projects/aios-blog/content/posts/<YYYY-MM-DD>-<slug>-bluesky.txt`:

```
<Hook sentence — what this post is about>

<Key insight in 1-2 sentences>

lab.ryancoleman.ca/posts/<slug>/

#AIOS #ClaudeCode #homelab
```

≤ 300 characters total. Count before writing.

### Step 4: Report

Tell the user:
- Draft saved to: `content/posts/<filename>.md`
- Bluesky text: `content/posts/<filename>-bluesky.txt`
- Next step: review, then `bash deploy.sh content/posts/<filename>.md "$(cat content/posts/<filename>-bluesky.txt)"`
````

- [ ] **Step 2: Commit to claude-config**

```bash
cd /mnt/c/Server/claude-config
git add global/commands/blog.md
git commit -m "feat: add /blog skill — weekly digest and topic-driven post generation"
```

- [ ] **Step 3: Sync to ~/.claude**

```bash
bash /mnt/c/Server/claude-config/scripts/sync.sh apply
```

Expected: sync completes without error. Verify: `ls ~/.claude/commands/blog.md` exists.

---

### Task 2: Modify /close-session — add Phase 5a blog notes

**Files:**
- Modify: `C:\Server\claude-config\global\commands\close-session.md`

The current close-session has phases 0–5. This task inserts a **Phase 5a** between Phase 4 (vault entry updates) and Phase 5 (report). Phase 5a captures three prompts from the user and appends them to the weekly notes file.

- [ ] **Step 1: Read the current close-session file to locate the insertion point**

Read `C:\Server\claude-config\global\commands\close-session.md`.

Find the line `## 5. Report back and wait` — Phase 5a inserts immediately before it.

- [ ] **Step 2: Insert Phase 5a**

In `C:\Server\claude-config\global\commands\close-session.md`, insert the following block immediately before `## 5. Report back and wait`:

```markdown
## 5a. Capture blog notes for the weekly digest

Ask the user **three questions, one at a time**. Wait for each answer before asking the next.

1. **"Highlight: What was the most interesting or impactful thing we built or decided this session?"**
2. **"Why: Why did that matter — what problem did it solve or what goal does it advance?"**
3. **"Challenge: What was the hardest problem you faced this session, and how did it get resolved? (Skip if none.)"**

If the user says "skip", "none", or similar for any prompt, record it as blank.

After collecting all three answers, calculate the current ISO week:
```python3
import datetime
today = datetime.date.today()
year, week, _ = today.isocalendar()
ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
print(f"week={year}-W{week:02d} ts={ts}")
```

Append to `/mnt/c/Server/projects/aios-blog/weekly-notes/<YYYY-Wxx>.md` (create the file if it doesn't exist):

```markdown
## Session <YYYY-MM-DDTHH:MM> — <project from working directory>
**Highlight:** <user's answer>
**Why:** <user's answer>
**Challenge:** <user's answer or "(none)">

```

Do NOT create the weekly-notes file if all three answers were skipped/empty — there's nothing worth recording.

```

- [ ] **Step 3: Commit to claude-config**

```bash
cd /mnt/c/Server/claude-config
git add global/commands/close-session.md
git commit -m "feat: add Phase 5a blog notes capture to close-session"
```

- [ ] **Step 4: Sync to ~/.claude**

```bash
bash /mnt/c/Server/claude-config/scripts/sync.sh apply
```

Expected: sync completes. Verify: `grep "5a" ~/.claude/commands/close-session.md` — shows the new phase.

- [ ] **Step 5: Dry-run verification**

In a test session, run `/close-session` and confirm Phase 5a appears after Phase 4 and before Phase 5. Answer the three prompts. Verify that `C:\Server\projects\aios-blog\weekly-notes\<current-week>.md` was created with the correct format.
