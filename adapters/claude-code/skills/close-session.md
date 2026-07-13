---
name: close-session
description: Wrap up the current session — document loose ends, update and close vault entries, then report ready to close. Requires IKEOS_URL and CAPTURE_TOKEN. Optionally CLAUDE_CONFIG_DIR for reflection signals and BLOG_NOTES_DIR for blog capture.
---

Session close-out requested. Work through all phases in order (0 through 5), then report. Do not ask questions between phases — only the final report needs the user.

## 0. Reflect on this session

Do a brief introspective scan **before** inventorying artifacts. The goal is to surface only *non-obvious* learnings — corrections you received, workarounds you invented, rule gaps you noticed. Most sessions produce zero entries here. Prefer silence to noise.

**Scan for:**
- **Corrections received:** user said "no, not that", "stop doing X", redirected you mid-task
- **Workarounds invented:** you discovered a constraint that no skill or CLAUDE.md rule currently documents
- **Rule gaps:** a situation arose where you reasoned from first principles because no skill covered it

**Quality gate — skip if either condition fails:**
1. **Signal threshold:** the pattern is notable enough that a future agent would benefit knowing it
2. **Dedup:** it is NOT already captured in an open vault entry OR in the current text of a relevant skill file (spot-check by reading the skill file)

**If a signal passes the quality gate:**

Option A — Significant finding (would change agent behavior in a future session):
```
IKEOS_URL="${IKEOS_URL:-http://localhost:5009}"
curl -s -o /dev/null -X POST "${IKEOS_URL}/capture" \
  -d "type=idea" -d "project=claude-config" \
  -d "title=<title>" \
  -d "body=<pattern description and context from this session>"
```

Option B — Minor repeated pattern (same issue arose but not yet urgent — build up recurrence count):
Read `library/weak-signals.json`, then update it using Python3:

```python
import json, datetime, os, sys

import os
_config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "")
SIGNALS = os.path.join(_config_dir, "library", "weak-signals.json") if _config_dir else ""
if not SIGNALS or not os.path.exists(SIGNALS):
    print("CLAUDE_CONFIG_DIR not set or weak-signals.json not found — skipping signal update")
    import sys; sys.exit(0)

today = datetime.date.today().isoformat()

with open(SIGNALS) as f:
    data = json.load(f)

# --- Fill in these values for the signal ---
new_pattern = "YOUR-1-SENTENCE-PATTERN"
new_category = "skill-gap"  # skill-gap | rule-violation | friction-point | external-opportunity
new_skill = "close-session.md"  # or None

# Dedup on skill_referenced + pattern
found = False
for s in data['signals']:
    if s.get('skill_referenced') == new_skill and s['pattern'] == new_pattern:
        s['occurrences'] = int(s.get('occurrences', 0)) + 1
        s['last_seen'] = today
        found = True
        break

if not found:
    data['signals'].append({
        'category': new_category,
        'skill_referenced': new_skill,
        'pattern': new_pattern,
        'occurrences': 1,
        'first_seen': today,
        'last_seen': today
    })

# Prune signals older than 45 days
cutoff = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
data['signals'] = [s for s in data['signals'] if s['last_seen'] >= cutoff]

with open(SIGNALS, 'w') as f:
    json.dump(data, f, indent=2)
print('Updated weak-signals.json')
```

Then check for promotable signals (occurrences >= 3):
```python
import json, os

_config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "")
_signals_path = os.path.join(_config_dir, "library", "weak-signals.json") if _config_dir else ""
if not _signals_path or not os.path.exists(_signals_path):
    print("CLAUDE_CONFIG_DIR not set — skipping promotable signals check")
else:
    data = json.load(open(_signals_path))
    for s in data['signals']:
        if s['occurrences'] >= 3:
            print(f"PROMOTE: [{s['category']}] {s['pattern']} (x{s['occurrences']})")
```
For each promoted signal, capture it to vault (Option A above), then remove it from weak-signals.json.

**After reflection (even if zero signals written), mark that close-session ran:**
```bash
touch ~/.claude/session-closed-flag
date -u +"%Y-%m-%dT%H:%M:%SZ" > ~/.claude/last-closed
```
This lets the StopHook know it was a clean close.

## 1. Inventory what happened this session

- Derive the current project from the working directory. List every repo you touched this session.
- For each: `git status --short` and `git log --oneline` for commits made this session. Note anything uncommitted, unpushed, or half-finished.
- Recall any tests/verifications run and their outcomes, and any decisions made that aren't yet written down.

## 2. Document loose ends

- **Uncommitted work:** commit it if it's complete and verified; otherwise leave it and record it as a loose end.
- **Follow-ups, deferred items, bugs noticed but not fixed:** create a vault entry for each via the obsidian-capture API (do NOT write files into bugs/ideas/notes directly):

  ```
  IKEOS_URL="${IKEOS_URL:-http://localhost:5009}"
  curl -s -o /dev/null -X POST "${IKEOS_URL}/capture" \
    -d "type=<note|idea|bug>" -d "project=<project-slug>" \
    -d "title=<title>" -d "body=<what's left and why it was deferred>"
  ```

- **Cross-project dependencies created this session:** if your changes require work in another project (e.g., IkeOS needs a new UI to surface data you added, another service needs to call a new endpoint), create an idea entry in that project's vault with detailed requirements:

  ```
  IKEOS_URL="${IKEOS_URL:-http://localhost:5009}"
  curl -s -o /dev/null -X POST "${IKEOS_URL}/capture" \
    -d "type=idea" -d "project=<affected-project-slug>" \
    -d "title=<what the other project needs to implement>" \
    -d "body=<requirements: what changed here, what they need to build, any contracts/shapes to match>"
  ```

- **Architecture decisions made this session:** append them to the project's `.claude/DECISIONS.md` if it exists.

## 3. Promote approved permissions to global baseline

Check whether the current project accumulated any session-specific permissions that should live in the global baseline.

- Find the project's `.claude/settings.local.json` (relative to the project working directory). If it doesn't exist, skip this phase.
- Read its `permissions.allow` array.
- Read the global `settings.json` from `$CLAUDE_CONFIG_DIR/global/settings.json` (if `CLAUDE_CONFIG_DIR` is set) and extract its `permissions.allow` array.
- Compute the diff: rules in local that are **not** in global.
- If there are new rules, add them to the global `settings.json` allow list, commit the change, and run `sync.sh apply`:

  ```bash
  # Example — actual rules will vary
  # 1. Edit $CLAUDE_CONFIG_DIR/global/settings.json to append new rules to permissions.allow
  # 2. Commit:
  cd "$CLAUDE_CONFIG_DIR"
  git add global/settings.json
  git commit -m "chore: promote session-approved permissions to global baseline"
  # 3. Sync to ~/.claude:
  bash "$CLAUDE_CONFIG_DIR/scripts/sync.sh" apply
  ```

- If there are no new rules, note "No new permissions to promote." and continue.
- Do not remove or modify any existing global rules — append only.

## 4. Update and close vault entries worked on

- Scan `$VAULT_PATH/projects/<project>/{bugs,ideas,notes}/` for entries with status `open` or `in-progress` that this session's work addressed (reading vault files directly is fine — writing is not).
- For each entry actually completed and verified, update it via the capture API (file writes to the vault are permission-denied):

  ```
  IKEOS_URL="${IKEOS_URL:-http://localhost:5009}"
  curl -s -o /dev/null -X PATCH "${IKEOS_URL}/entries" \
    -H "X-Capture-Token: $CAPTURE_TOKEN" \
    -d "project=<project>" -d "type=<bug|idea|note>" \
    -d "filename=<filename-without-.md>" -d "status=done"
  ```

- Entries partially addressed: PATCH to `status=in-progress`. Progress context goes in a new capture *note* referencing the entry — never into the entry's body.
- Never mark an entry `done` on intention alone — only if the work was verified this session.

## 5a. Capture blog notes for the weekly digest

**Draft all three answers from session context first**, then present them as a block for the user to approve, edit, or skip — one prompt, not three sequential questions.

Format:
> **Highlight:** [your draft]
> **Why:** [your draft]
> **Challenge:** [your draft — or "(none)" if nothing notable]
>
> _Approve, edit any, or say "skip" to skip all blog notes._

If the user approves or edits, use their final text. If the user says "skip" for any item, record it as blank. Do not write the file if all three are blank/skipped.

After collecting all three answers, calculate the current ISO week:
```python3
import datetime
today = datetime.date.today()
year, week, _ = today.isocalendar()
ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
print(f"week={year}-W{week:02d} ts={ts}")
```

Append to `$BLOG_NOTES_DIR/<YYYY-Wxx>.md` (skip if BLOG_NOTES_DIR is not set):

```python
import os, datetime

_blog_dir = os.environ.get("BLOG_NOTES_DIR", "")
if not _blog_dir:
    print("BLOG_NOTES_DIR not set — skipping blog notes capture")
else:
    today = datetime.date.today()
    year, week, _ = today.isocalendar()
    target = os.path.join(_blog_dir, f"{year}-W{week:02d}.md")
    # create the file if it doesn't exist, then append the session block
```

Do NOT create the weekly-notes file if all three answers were skipped/empty — there's nothing worth recording.

## 5. Report back and wait

Present a close-out summary:

- **Changes:** repos touched, commits made (hashes), anything unpushed or uncommitted
- **Vault:** entries closed (done), entries updated (in-progress), new entries captured
- **Loose ends:** anything the user should know before the session ends, including pending confirmations (e.g., unpushed commits awaiting approval)

End with: **"Ready to close session."** — then stop and wait. Do not push to any remote as part of close-out unless the user has already confirmed it.
