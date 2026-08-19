# Adapter/Harness Consolidation — Pass 1 (Skills) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the 4 tractable duplicated skills (`triage`, `promote`, `schema-check`, `close-session`) into `ikeos/adapters/claude-code/skills/` as the single source of truth, fix the root cause of part of the drift (missing `env` values on the deployed Claude Code runtime), and build the `sync.sh generate`/`check-drift.sh` mechanism that keeps `claude-config`'s deployed copies generated from that source going forward.

**Architecture:** Four tasks across two repos. Task 1 fixes the live `~/.claude/settings.json` env gap (not the git-tracked repo file — see the task for why) and makes the fix durable via `bootstrap-wsl2.sh`. Task 2 is the one skill needing real content reconciliation (`close-session.md`) — the other three are already fully dominated by the adapter copy and need no edits. Task 3 builds the `generate` mechanism in `sync.sh` and runs it for the first time. Task 4 extends `check-drift.sh` to watch and auto-heal the new boundary, mirroring its existing pattern one hop earlier in the chain.

**Tech Stack:** Bash (`sync.sh`, `check-drift.sh`, `bootstrap-wsl2.sh`), Python 3 (JSON manipulation, matching this codebase's existing inline-heredoc style), Markdown (the skill files themselves).

**Spec:** `docs/superpowers/specs/2026-08-19-adapter-harness-consolidation-design.md`

## Global Constraints

- `CAPTURE_TOKEN` must never be written to any git-tracked file, in either repo. It stays exclusively in `.env`-file reads with `tr -d '\r\n'` CRLF stripping.
- `claude-config/global/settings.json` (the git-tracked repo file) must NOT gain an `env` key — `sync.sh`'s `merge_settings()` already discards it on every apply; any fix there is a no-op.
- `housekeeping.md` and `code-review.md` are out of scope for this plan — do not touch them.
- Every generated file (`claude-config/global/commands/{triage,promote,schema-check,close-session}.md`) must carry a "do not edit, generated from ikeos" header comment.
- `sync.sh generate` must be idempotent — running it twice in a row produces byte-identical output the second time.
- Do not remove or weaken the `.env`-file-read fallback pattern anywhere it currently exists in the deployed skills — only add to it, never replace it.

---

## File Structure

- Modify: `/mnt/c/Users/ServerAdmin/.claude/settings.json` (live, not git-tracked) — add `env` block.
- Modify: `claude-config/scripts/bootstrap-wsl2.sh` — add idempotent env-setup step.
- Modify: `ikeos/adapters/claude-code/skills/close-session.md` — reconcile with deployed content.
- Modify: `claude-config/scripts/sync.sh` — add `generate` subcommand and `IKEOS_REPO_PATH` config.
- Modify: `claude-config/scripts/check-drift.sh` — extend to watch the new `ikeos/adapters/` → `claude-config/global/commands/` boundary.

---

## Task 1: Root-cause env fix — live `~/.claude/settings.json` + `bootstrap-wsl2.sh`

**Files:**
- Modify: `/mnt/c/Users/ServerAdmin/.claude/settings.json` (the live deployed file — NOT `claude-config/global/settings.json`)
- Modify: `claude-config/scripts/bootstrap-wsl2.sh`

**Interfaces:**
- Produces: `VAULT_PATH=/mnt/c/Server/obsidian-vault`, `IKEOS_URL=http://localhost:5009`, `CLAUDE_CONFIG_DIR=/mnt/c/Server/claude-config` reliably present in every subsequent Claude Code session's shell environment on this host. Task 2 relies on `CLAUDE_CONFIG_DIR` being set to verify `close-session.md`'s weak-signals digest works end-to-end.

- [ ] **Step 1: Apply the env block to the live settings.json now**

Run this Python3 script directly (it's a one-off operational fix, not committed code — do not write it to either repo):

```python
import json

path = "/mnt/c/Users/ServerAdmin/.claude/settings.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

data.setdefault("env", {})
data["env"].setdefault("VAULT_PATH", "/mnt/c/Server/obsidian-vault")
data["env"].setdefault("IKEOS_URL", "http://localhost:5009")
data["env"].setdefault("CLAUDE_CONFIG_DIR", "/mnt/c/Server/claude-config")

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("env block:", json.dumps(data["env"], indent=2))
```

`setdefault` is deliberate — if any of these three keys already exist with a different value (someone customized it), this must not clobber it.

- [ ] **Step 2: Verify the live file**

```bash
python3 -c "import json; print(json.load(open('/mnt/c/Users/ServerAdmin/.claude/settings.json'))['env'])"
```

Expected: `{'VAULT_PATH': '/mnt/c/Server/obsidian-vault', 'IKEOS_URL': 'http://localhost:5009', 'CLAUDE_CONFIG_DIR': '/mnt/c/Server/claude-config'}` (order may vary; a pre-existing `CAPTURE_TOKEN` key must NOT be present — if the file already had one from prior manual edits, stop and flag it, do not proceed).

- [ ] **Step 3: Verify `sync.sh apply` preserves this (it must, per `merge_settings()`'s existing design)**

```bash
cd /mnt/c/Server/claude-config
SKIP_EVALS=1 bash scripts/sync.sh apply
python3 -c "import json; print(json.load(open('/mnt/c/Users/ServerAdmin/.claude/settings.json'))['env'])"
```

Expected: the same three keys are still present after `apply` runs (confirms the existing `merged['env'] = target.get('env', {})` preservation logic works as designed — this is a regression check, not new behavior).

- [ ] **Step 4: Add the idempotent bootstrap step**

Edit `claude-config/scripts/bootstrap-wsl2.sh`. Insert this as a new step 4, after the existing step 3 (PATH setup) and before the closing "Done." echo block:

```bash
# 4. Ensure required env vars are present on ~/.claude/settings.json
SETTINGS="$HOME/.claude/settings.json"
if [ -f "$SETTINGS" ]; then
    python3 - "$SETTINGS" << 'PYEOF'
import json, sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

changed = False
env = data.setdefault("env", {})
for key, value in {
    "VAULT_PATH": "/mnt/c/Server/obsidian-vault",
    "IKEOS_URL": "http://localhost:5009",
    "CLAUDE_CONFIG_DIR": "/mnt/c/Server/claude-config",
}.items():
    if key not in env:
        env[key] = value
        changed = True

if changed:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("    [ok] env block updated in ~/.claude/settings.json")
else:
    print("    [skip] env block already complete")
PYEOF
else
    echo "    [skip] ~/.claude/settings.json not found yet — run 'claude' once to create it, then re-run this script"
fi
```

Update the script's header comment (currently "Bootstrap the WSL2 host environment for claude-config. Run this after a fresh WSL2 install or rebuild.") — no change needed there, it already covers this.

- [ ] **Step 5: Verify the bootstrap script runs cleanly on the current (already-bootstrapped) system**

```bash
bash /mnt/c/Server/claude-config/scripts/bootstrap-wsl2.sh
```

Expected: exits 0, step 4 prints `[skip] env block already complete` (since Step 1 already set it), no errors.

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Server/claude-config
git add scripts/bootstrap-wsl2.sh
git commit -m "feat: bootstrap sets VAULT_PATH/IKEOS_URL/CLAUDE_CONFIG_DIR env

Root-cause fix for part of the ikeos-adapter/deployed-skill drift --
these were never reliably available in non-interactive agent shells.
Targets the live ~/.claude/settings.json only (not this repo's
global/settings.json, which sync.sh's merge_settings() already
excludes from the env key on every apply). CAPTURE_TOKEN stays on
the existing .env-file-read pattern, not added here."
```

---

## Task 2: Reconcile `close-session.md`

**Files:**
- Modify: `ikeos/adapters/claude-code/skills/close-session.md`

**Interfaces:**
- Consumes: `CLAUDE_CONFIG_DIR` env var set by Task 1 (used by this file's weak-signals digest logic, already present in the adapter version — no change needed to that logic itself).
- Produces: `ikeos/adapters/claude-code/skills/close-session.md`, the reconciled canonical version. Task 3 copies this file verbatim (plus a header stamp) into `claude-config/global/commands/close-session.md`.

`triage.md`, `promote.md`, and `schema-check.md` need **no changes** in this task — full-file comparison during plan-writing confirmed the adapter versions already contain 100% of the deployed versions' real content (the deployed copies have zero unique content beyond hardcoded paths, which the adapter already handles more robustly via env vars). Task 3 generates `claude-config`'s copies of these three directly from the current adapter content, unmodified.

- [ ] **Step 1: Add the `POST /capture` 302 note**

In `ikeos/adapters/claude-code/skills/close-session.md`, the file currently opens:

```markdown
---
name: close-session
description: Wrap up the current session — document loose ends, update and close vault entries, then report ready to close. Requires IKEOS_URL and CAPTURE_TOKEN. Optionally CLAUDE_CONFIG_DIR for reflection signals and BLOG_NOTES_DIR for blog capture.
---

Session close-out requested. Work through all phases in order (0 through 5), then report. Do not ask questions between phases — only the final report needs the user.

## 0. Reflect on this session
```

Using the Edit tool, insert this new line between the "Session close-out requested..." paragraph and the "## 0. Reflect on this session" heading:

```markdown

> **Note on `POST /capture` responses:** `POST /capture` returns HTTP 302 (redirect to `/tasks`) on success, not 200 — this is normal, not an error. Check with `curl -s -o /dev/null -w '%{http_code}'` and treat 302 as success, or use `-L` to follow the redirect. `POST /capture/json` returns 200 JSON directly and doesn't have this quirk. This applies to every `POST /capture` call in this file.
```

- [ ] **Step 2: Add the memory-retention-study footnote**

The file's "## 0. Reflect on this session" section currently reads:

```markdown
## 0. Reflect on this session

Do a brief introspective scan **before** inventorying artifacts. The goal is to surface only *non-obvious* learnings — corrections you received, workarounds you invented, rule gaps you noticed. Most sessions produce zero entries here. Prefer silence to noise.

**Scan for:**
```

Using the Edit tool, insert this new paragraph between the "Do a brief introspective scan..." paragraph and "**Scan for:**":

```markdown

**Why selective, not exhaustive:** a 2026 study on persistent agent memory (arXiv:2607.09493) found that retaining full session history *degrades* task completion below having no memory at all (71% vs. 79%), while retaining a small set of durable, reusable categories reached 96%. Never write a narrative recap of the session to memory or vault — capture only the specific, reusable fact (a correction, a workaround, a stable project/reference detail), in the same spirit as this project's existing memory types (`user`, `feedback`, `project`, `reference`).
```

- [ ] **Step 3: Investigate the blog-notes divergence (Section 5a) before deciding**

The adapter's current Section 5a has real, executable Python that reads `BLOG_NOTES_DIR` and appends to a weekly file (this is the version to default to keeping — a portable reference implementation should be self-contained and runnable, not a template the agent has to improvise from). The deployed version replaced this with a hardcoded path (`/mnt/c/Server/projects/aios-blog/weekly-notes/<YYYY-Wxx>.md`) and a markdown-template placeholder instead of executable code.

Read `git -C /mnt/c/Server/claude-config log --follow -p -- global/commands/close-session.md 2>/dev/null | head -300` (from outside any worktree isolation — run this in the `claude-config` repo directly) to check whether the commit history shows *why* this changed — e.g. a commit message mentioning a bug in the Python append logic, or the file simply being trimmed for brevity. Also check `ikeos/.claude/DECISIONS.md` and `claude-config`'s own decision/history docs for any mention of blog-notes capture.

- **If you find evidence of a real problem with the adapter's executable script** (a bug, a specific failure mode): fix that specific problem in the adapter's Python instead of reverting to the template-only approach, and note what you found and fixed in your report.
- **If you find no evidence of a specific problem** (the change looks like an unexplained simplification): keep the adapter's existing executable Python as the reconciled version, unmodified. Note in your report that no reason for the deployed simplification was found.

Either way, do not silently adopt the deployed version's non-executable template — the reconciled adapter version must remain something an agent can actually run, not something it has to freelance from a markdown example.

- [ ] **Step 4: Verify the file is well-formed**

```bash
grep -c "^## " ikeos/adapters/claude-code/skills/close-session.md
```

Expected: `7` (the seven numbered/lettered section headings: 0, 1, 2, 3, 4, 5a, 5 — count these yourself against the file to confirm the number before treating a mismatch as an error, since 5a uses `##` too).

```bash
grep -n "arXiv:2607.09493\|POST /capture. returns HTTP 302" ikeos/adapters/claude-code/skills/close-session.md
```

Expected: both strings found, confirming Steps 1 and 2 landed.

- [ ] **Step 5: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/skills/close-session.md
git commit -m "docs: reconcile close-session.md with deployed improvements

Ports the POST /capture 302-response note and the memory-retention-
study rationale from the deployed claude-config copy, which had
diverged with real content the adapter lacked. Blog-notes logic
investigated per docs/superpowers/plans/2026-08-19-adapter-harness-consolidation-pass1-skills.md Task 2 Step 3 (see commit body / report for outcome)."
```

Before running this commit, replace the placeholder clause at the end of the message ("(see commit body / report for outcome)") with one concrete sentence stating what Step 3 actually found and did — do not commit with the placeholder text still present.

---

## Task 3: `sync.sh generate` — deploy from `ikeos/adapters/` instead of hand-editing

**Files:**
- Modify: `claude-config/scripts/sync.sh`

**Interfaces:**
- Consumes: `ikeos/adapters/claude-code/skills/{triage,promote,schema-check,close-session}.md` (Task 2's output for `close-session.md`; `triage`/`promote`/`schema-check` unchanged from their current adapter content).
- Produces: `claude-config/global/commands/{triage,promote,schema-check,close-session}.md`, each prefixed with a generated-file header comment. Task 4 relies on this `do_generate` function existing and being callable as `bash scripts/sync.sh generate`.

`sync.sh`'s current structure (read the whole file first — it's ~305 lines) defines `SYNC_ITEMS`, `show_diff`, `do_backup`, `do_apply`, `merge_settings`, `do_backfill`, `do_watch`, and a `case` statement dispatching on `$1`. This task adds a parallel `GENERATE_ITEMS` mapping and a `do_generate` function following the same style (the `log_info`/`log_warn`/`log_error` helpers, already defined near the top, are used throughout).

- [ ] **Step 1: Add `IKEOS_REPO_PATH` near the other path constants**

Near the top of `claude-config/scripts/sync.sh`, the existing constants block reads:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE="$REPO_ROOT/global"
TARGET="$HOME/.claude"
BACKUP_DIR="$TARGET/backups/config-sync"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
```

Using the Edit tool, add one line after `TIMESTAMP=$(date +%Y%m%d-%H%M%S)`:

```bash
IKEOS_REPO_PATH="${IKEOS_REPO_PATH:-/mnt/c/Server/projects/ikeos}"
```

This is overridable via an actual `IKEOS_REPO_PATH` environment variable (bash `${VAR:-default}` syntax), defaulting to this homelab's standard colocated-projects path.

- [ ] **Step 2: Add the `GENERATE_ITEMS` mapping**

After the existing `SYNC_ITEMS` array declaration:

```bash
# Files/dirs to sync from global/ to ~/.claude/
SYNC_ITEMS=(
    "CLAUDE.md"
    "commands"
    "rules"
)
```

Using the Edit tool, add this new array immediately after it:

```bash

# Skills reconciled into ikeos/adapters/claude-code/skills/ and generated
# here from that source. Do NOT hand-edit the files this produces --
# edit the ikeos source and re-run 'sync.sh generate'.
# Format: "source-relative-path:target-relative-path"
GENERATE_ITEMS=(
    "skills/triage.md:commands/triage.md"
    "skills/promote.md:commands/promote.md"
    "skills/schema-check.md:commands/schema-check.md"
    "skills/close-session.md:commands/close-session.md"
)
```

- [ ] **Step 3: Add the `do_generate` function**

Insert this new function after `do_backfill` and before `do_watch`:

```bash
do_generate() {
    local ikeos_skills="$IKEOS_REPO_PATH/adapters/claude-code/skills"

    if [ ! -d "$ikeos_skills" ]; then
        log_error "ikeos adapter skills not found at: $ikeos_skills"
        log_error "Set IKEOS_REPO_PATH if ikeos is checked out somewhere else."
        exit 1
    fi

    local changed=0
    local unchanged=0

    for mapping in "${GENERATE_ITEMS[@]}"; do
        local src_rel="${mapping%%:*}"
        local dst_rel="${mapping##*:}"
        local src="$IKEOS_REPO_PATH/adapters/claude-code/$src_rel"
        local dst="$SOURCE/$dst_rel"

        if [ ! -f "$src" ]; then
            log_error "Generate source not found: $src"
            exit 1
        fi

        local header="<!-- GENERATED from ikeos/adapters/claude-code/$src_rel -- do not edit here. Edit the source and run: bash scripts/sync.sh generate -->"
        local tmp
        tmp=$(mktemp)
        printf '%s\n' "$header" > "$tmp"
        cat "$src" >> "$tmp"

        if [ -f "$dst" ] && cmp -s "$tmp" "$dst"; then
            unchanged=$((unchanged + 1))
            rm "$tmp"
        else
            mv "$tmp" "$dst"
            log_info "Generated: global/$dst_rel (from ikeos/adapters/claude-code/$src_rel)"
            changed=$((changed + 1))
        fi
    done

    log_info "Generate complete — $changed file(s) updated, $unchanged already current."
}
```

- [ ] **Step 4: Wire the `generate` command into the dispatcher and usage text**

The file's `case` statement currently ends:

```bash
    backfill)
        do_backfill
        ;;
    *)
        echo "Usage: $0 [diff|apply|watch|backfill]"
        echo ""
        echo "  diff      — Preview changes (default)"
        echo "  apply     — Deploy global/ to ~/.claude/ (backs up first)"
        echo "  watch     — Auto-deploy on file changes (requires inotify-tools)"
        echo "  backfill  — Copy updated library/agents/ into all existing projects"
        exit 1
        ;;
esac
```

Using the Edit tool, replace it with:

```bash
    backfill)
        do_backfill
        ;;
    generate)
        do_generate
        ;;
    *)
        echo "Usage: $0 [diff|apply|watch|backfill|generate]"
        echo ""
        echo "  diff      — Preview changes (default)"
        echo "  apply     — Deploy global/ to ~/.claude/ (backs up first)"
        echo "  watch     — Auto-deploy on file changes (requires inotify-tools)"
        echo "  backfill  — Copy updated library/agents/ into all existing projects"
        echo "  generate  — Regenerate global/commands/{triage,promote,schema-check,close-session}.md from ikeos/adapters/claude-code/skills/"
        exit 1
        ;;
esac
```

- [ ] **Step 5: Run it for the first time and verify**

```bash
cd /mnt/c/Server/claude-config
bash scripts/sync.sh generate
```

Expected: 4 files reported as "Generated" (all four will change the first time, since none currently carry the header comment).

```bash
head -1 global/commands/triage.md global/commands/promote.md global/commands/schema-check.md global/commands/close-session.md
```

Expected: each file's first line is its `<!-- GENERATED from ... -->` header comment.

```bash
diff <(tail -n +2 global/commands/close-session.md) /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/close-session.md
```

Expected: no output (the generated file, minus its header line, is byte-identical to the source).

- [ ] **Step 6: Verify idempotency**

```bash
bash scripts/sync.sh generate
```

Expected: all 4 files reported as already current (`0 file(s) updated, 4 already current`) — running `generate` twice in a row with no source changes must not rewrite the files.

- [ ] **Step 7: Verify `sync.sh apply` still deploys the generated content correctly**

```bash
SKIP_EVALS=1 bash scripts/sync.sh apply
diff ~/.claude/commands/triage.md global/commands/triage.md
```

Expected: no diff output — the existing `apply` mechanism (unmodified by this task) correctly deploys the now-generated `global/commands/` files to `~/.claude/commands/`, exactly as it already does for every other command.

- [ ] **Step 8: Commit**

```bash
cd /mnt/c/Server/claude-config
git add scripts/sync.sh global/commands/triage.md global/commands/promote.md global/commands/schema-check.md global/commands/close-session.md
git commit -m "feat: sync.sh generate -- deploy skills from ikeos/adapters/ source

triage.md, promote.md, schema-check.md, and close-session.md are no
longer hand-maintained duplicates -- they're generated from
ikeos/adapters/claude-code/skills/, which is now the single source
of truth. Idempotent; existing 'apply' step is unchanged and deploys
the generated content the same way it deploys everything else."
```

---

## Task 4: Extend `check-drift.sh` to watch the new boundary

**Files:**
- Modify: `claude-config/scripts/check-drift.sh`

**Interfaces:**
- Consumes: `sync.sh generate` (Task 3) — this task calls it, does not reimplement its logic.
- Produces: a `check-drift.sh` that, on every `SessionStart` hook firing (it's already wired into `settings.json`'s `hooks.SessionStart`, no change needed there), also detects and auto-heals drift between `ikeos/adapters/claude-code/skills/` and the generated `claude-config/global/commands/` files — mirroring its existing `global/` → `~/.claude` check one hop earlier in the chain.

The current file (12 lines) reads:

```bash
#!/bin/bash
# SessionStart hook: catch any residual drift (e.g. launched without the ~/bin
# wrapper) and auto-apply sync. Silent when already in sync.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$SCRIPT_DIR/../global"
TARGET="$HOME/.claude"

drift=""
diff -q "$REPO/CLAUDE.md" "$TARGET/CLAUDE.md" >/dev/null 2>&1 || drift="CLAUDE.md"
diff -rq "$REPO/commands" "$TARGET/commands" >/dev/null 2>&1 || drift="$drift commands/"
diff -rq "$REPO/rules" "$TARGET/rules" >/dev/null 2>&1 || drift="$drift rules/"

if [ -n "$drift" ]; then
  SKIP_EVALS=1 bash "$SCRIPT_DIR/sync.sh" apply >/dev/null 2>&1
  msg="Config auto-synced at session start (drift in:$drift was not caught by the launch wrapper — check that ~/bin is first in PATH)."
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$msg"
fi
```

- [ ] **Step 1: Rewrite the file**

Using the Write tool, replace `claude-config/scripts/check-drift.sh` with:

```bash
#!/bin/bash
# SessionStart hook: catch any residual drift (e.g. launched without the ~/bin
# wrapper) and auto-apply sync. Silent when already in sync.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$SCRIPT_DIR/../global"
TARGET="$HOME/.claude"
IKEOS_REPO_PATH="${IKEOS_REPO_PATH:-/mnt/c/Server/projects/ikeos}"

drift=""

# Adapter-source -> generated-copy boundary (ikeos/adapters/claude-code/skills/
# -> global/commands/). Regenerate here, before the commands/ check below, so
# a source-only change is caught and deployed within this same hook run.
GENERATE_ITEMS=(
  "skills/triage.md:commands/triage.md"
  "skills/promote.md:commands/promote.md"
  "skills/schema-check.md:commands/schema-check.md"
  "skills/close-session.md:commands/close-session.md"
)
if [ -d "$IKEOS_REPO_PATH/adapters/claude-code/skills" ]; then
  for mapping in "${GENERATE_ITEMS[@]}"; do
    src_rel="${mapping%%:*}"
    dst_rel="${mapping##*:}"
    src="$IKEOS_REPO_PATH/adapters/claude-code/$src_rel"
    dst="$REPO/$dst_rel"
    if [ -f "$src" ] && { [ ! -f "$dst" ] || ! diff -q <(tail -n +2 "$dst") "$src" >/dev/null 2>&1; }; then
      drift="$drift adapters/$src_rel"
    fi
  done
  if [ -n "$drift" ]; then
    SKIP_EVALS=1 bash "$SCRIPT_DIR/sync.sh" generate >/dev/null 2>&1
  fi
fi

diff -q "$REPO/CLAUDE.md" "$TARGET/CLAUDE.md" >/dev/null 2>&1 || drift="$drift CLAUDE.md"
diff -rq "$REPO/commands" "$TARGET/commands" >/dev/null 2>&1 || drift="$drift commands/"
diff -rq "$REPO/rules" "$TARGET/rules" >/dev/null 2>&1 || drift="$drift rules/"

if [ -n "$drift" ]; then
  SKIP_EVALS=1 bash "$SCRIPT_DIR/sync.sh" apply >/dev/null 2>&1
  msg="Config auto-synced at session start (drift in:$drift was not caught by the launch wrapper — check that ~/bin is first in PATH)."
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$msg"
fi
```

Note the one change to pre-existing behavior: the original first check was `drift="CLAUDE.md"` (a plain overwrite, safe only because it was always the first write to `drift`). It's now `drift="$drift CLAUDE.md"` (append, matching the style already used by the `commands/` and `rules/` checks below it) — required because the new adapter-boundary check may have already written to `drift` earlier in the script. This is a behaviorally identical change when `drift` is still empty at that point, and correctly additive when it isn't.

- [ ] **Step 2: Verify normal (no-drift) behavior is unchanged**

```bash
bash /mnt/c/Server/claude-config/scripts/check-drift.sh
echo "exit: $?"
```

Expected: no output (everything should already be in sync after Tasks 1–3), exit 0.

- [ ] **Step 3: Verify the new boundary actually detects and heals drift**

Manually introduce drift, then confirm the hook catches and fixes it:

```bash
echo "<!-- test drift -->" >> /mnt/c/Server/claude-config/global/commands/triage.md
bash /mnt/c/Server/claude-config/scripts/check-drift.sh
```

Expected: output is a single JSON line (`{"hookSpecificOutput":...}`) whose `additionalContext` mentions `adapters/skills/triage.md`.

```bash
diff <(tail -n +2 /mnt/c/Server/claude-config/global/commands/triage.md) /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/triage.md
```

Expected: no output — the manually-introduced drift was regenerated away and re-deployed.

- [ ] **Step 4: Verify the pre-existing `global/` → `~/.claude` boundary still works (regression check)**

```bash
echo "<!-- test drift -->" >> ~/.claude/rules/debugging.md
bash /mnt/c/Server/claude-config/scripts/check-drift.sh
```

Expected: JSON output mentioning `rules/`. Then:

```bash
diff /mnt/c/Server/claude-config/global/rules/debugging.md ~/.claude/rules/debugging.md
```

Expected: no output — the pre-existing mechanism, unmodified by this task, still heals correctly.

- [ ] **Step 5: Commit**

```bash
cd /mnt/c/Server/claude-config
git add scripts/check-drift.sh
git commit -m "feat: check-drift.sh watches ikeos/adapters -> global/commands too

Extends the existing SessionStart drift-check one hop earlier in the
chain -- previously only global/ -> ~/.claude was watched, leaving
zero tooling on the ikeos-adapter boundary that caused the original
triage.md divergence this consolidation is fixing."
```
