# Adapter/Harness Consolidation — Pass 2 (Session-Manager) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ikeos/adapters/claude-code/session-manager/` the single source of truth for the session-manager service, with `claude-config/services/session-manager/` generated from it (extending the same `sync.sh generate`/`check-drift.sh` mechanism Pass 1 built for the 4 skills), then restart the live service from the generated copy and verify it actually works — not just that its tests pass.

**Governing spec:** `docs/superpowers/specs/2026-08-19-adapter-harness-consolidation-design.md` §6 (Pass 2) and Success Criteria.

---

## Critical grounding: a prior, unmerged branch already did most of this

Before writing this plan, `git log --all` turned up `feat/session-manager-adapter-sync` (6 commits, 2026-07-21/22, still present locally and on `origin`, never merged) implementing exactly this reconciliation, from its own plan at `docs/superpowers/plans/2026-07-21-session-manager-adapter-sync.md`. It ports `list_session_names()`, `model` parameter threading, `research_sources.py` + its three routes, and `_reconcile_sessions()` into the adapter — deliberately keeping the adapter's env-var-based `CLAUDE_BIN`/`CLAUDE_PLUGIN_BASE` config and a `Path.home()`-relative storage convention for `research_sources.py`, rather than copying the deployed service's hardcoded absolute host paths. `main` has **zero** commits touching `adapters/claude-code/session-manager/` since the branch's base (`9725e38`), so it merges as a clean fast-forward. Its own "Explicitly Out of Scope" section declined to build automated drift-detection, reasoning "if drift recurs after this sync, that's the signal to build automation" — which is exactly what this pass's `generate`/`check-drift.sh` extension now provides.

**Task 1 recovers this work first.** Everything after that reconciles only the *further* drift the deployed service accumulated after 2026-07-22 (a 2026-08-17 incident fix, a raw-keys endpoint, and a few smaller items) — a much smaller diff than a from-scratch reconciliation would suggest.

**One regression to not carry forward:** deployed's `research_sources.py`/`app.py` currently has a TOCTOU race on duplicate source URLs (`app.py` checks `any(s["url"]==url for s in list_sources())` *before* calling `add_source()`, non-atomically) that the branch's `3c4f28d fix: close TOCTOU race...` commit already fixed (atomic check inside `add_source()`'s lock, returning `None` on conflict). Task 4 keeps the branch's fixed version — this is a case where "port the deployed improvement" is backwards; the deployed copy is the one with the bug.

---

## Global Constraints

- Do not copy deployed's hardcoded `CLAUDE_BIN`/`PLUGIN_BASE` absolute paths into the adapter — preserve the env-var-based config (matches `ikeos/.claude/DECISIONS.md` 2026-07-22 entry and the branch's own stated rationale).
- Do not copy deployed's non-atomic duplicate-URL check in `create_research_source` — the branch's atomic version is correct and deployed's is a regression.
- `research_sources.py`'s storage path is a genuine, intentional deployment difference (deployed's copy is read by other `claude-config` tooling at `library/research-sources.json` — see `COMPONENT_MODEL.md` §3), not incidental drift like `CLAUDE_BIN`. Make it env-var overridable rather than picking one hardcoded path for both sides (see Task 3).
- Every generated file under `claude-config/services/session-manager/` must carry the same "do not edit, generated from ikeos" header Pass 1 established, adapted for Python (`# GENERATED from ...` comment, not HTML).
- `sync.sh generate` must remain idempotent for the existing 4 skill mappings and idempotent for the new session-manager mappings.
- Do not touch `restart.sh` or `setup-startup.ps1` — deployed-only ops tooling, not part of the portable reference (matches the design spec's Success Criteria, which names only `research_sources.py` + its test as adapter additions).
- The live service must be restarted and verified working (a real session create/status/remove cycle against the running port), not just `pytest`-verified, before this pass is considered done — per the design spec.

---

## File Structure

- Merge: branch `feat/session-manager-adapter-sync` into `main` (fast-forward).
- Modify: `adapters/claude-code/session-manager/pane_parser.py` — port `parse_stuck_on_menu()`.
- Modify: `adapters/claude-code/session-manager/tmux.py` — resolve the `DEFAULT_MODEL` question (Task 2).
- Modify: `adapters/claude-code/session-manager/research_sources.py` — env-var-overridable storage path.
- Modify: `adapters/claude-code/session-manager/app.py` — `blocked_on_menu` wiring, `/sessions/<id>/keys` endpoint, defensive `remote_control` read, investigate `_reconcile_sessions()`'s metric-emission difference.
- Modify: `adapters/claude-code/session-manager/start.sh` — port the `unset TMUX` isolation fix and `exec python3 app.py`.
- Modify: `adapters/claude-code/session-manager/tests/{test_pane_parser,test_tmux,test_app}.py` — tests for all of the above.
- Modify: `claude-config/scripts/sync.sh` — extend `GENERATE_ITEMS`/`do_generate` to cover the session-manager files.
- Modify: `claude-config/scripts/check-drift.sh` — extend to watch the session-manager boundary too.
- Modify (after both passes verified): `docs/COMPONENT_MODEL.md` §7, `ikeos/.claude/DECISIONS.md`, `claude-config`'s decisions record.

---

## Task 1: Recover the orphaned branch

**Files:** none (git operation only)

- [ ] **Step 1: Confirm the branch is still a clean fast-forward**

```bash
cd /mnt/c/Server/projects/ikeos
git fetch origin
git merge-base --is-ancestor $(git merge-base main feat/session-manager-adapter-sync) main && echo "base unchanged"
git log --oneline feat/session-manager-adapter-sync..main -- adapters/claude-code/session-manager/
```

Expected: "base unchanged", and the second command prints nothing (no commits on `main` touch that path since the branch diverged). If either check fails, stop — `main` has moved since this plan was written and the merge needs manual conflict resolution instead of a fast-forward.

- [ ] **Step 2: Run the branch's own test suite before merging**

```bash
cd /mnt/c/Server/projects/ikeos
git worktree add /tmp/sm-sync-verify feat/session-manager-adapter-sync
cd /tmp/sm-sync-verify/adapters/claude-code/session-manager
pip install -q -r requirements.txt pytest pytest-mock
python3 -m pytest tests/ -v
```

Expected: 9 pre-existing failures in `test_pane_parser.py`/`test_app.py` around `parse_activity` returning `not_started` (stale tests, unrelated to this branch — the same 9 fail identically on current `main`'s adapter copy; confirmed during this plan's investigation). No *other* failures. If you see failures beyond those exact 9, stop and investigate before merging.

```bash
cd /mnt/c/Server/projects/ikeos
git worktree remove /tmp/sm-sync-verify
```

- [ ] **Step 3: Merge**

```bash
cd /mnt/c/Server/projects/ikeos
git merge --ff-only feat/session-manager-adapter-sync
git branch -d feat/session-manager-adapter-sync
git push origin --delete feat/session-manager-adapter-sync
```

- [ ] **Step 4: Re-diff against deployed to confirm the recovered scope**

```bash
for f in app.py tmux.py pane_parser.py sessions.py start.sh; do
  echo "=== $f ==="
  diff -u adapters/claude-code/session-manager/$f /mnt/c/Server/claude-config/services/session-manager/$f | grep -c '^[+-]'
done
```

Expected: `sessions.py` shows `0` (fully reconciled by the merge). The others show a smaller diff than before the merge — this is the real remaining scope for Tasks 2–6.

---

## Task 2: `pane_parser.py` — port `parse_stuck_on_menu()`

**Files:**
- Modify: `adapters/claude-code/session-manager/pane_parser.py`
- Modify: `adapters/claude-code/session-manager/tests/test_pane_parser.py`

No conflict — this function and its docstring (citing incident 2026-08-17) exist only on the deployed side and are purely additive.

- [ ] **Step 1: Port the function verbatim**

Copy `parse_stuck_on_menu()` (including its full docstring — it documents a deliberate false-positive tradeoff, don't trim it) from `/mnt/c/Server/claude-config/services/session-manager/pane_parser.py` into the adapter's `pane_parser.py`, in the same position (just before the `_IDLE_STATUS` constants block).

- [ ] **Step 2: Port its tests**

Copy these six test functions from deployed's `tests/test_pane_parser.py` into the adapter's copy: `test_parse_stuck_on_menu_detects_enter_to_confirm`, `test_parse_stuck_on_menu_detects_esc_to_cancel`, `test_parse_stuck_on_menu_detects_leading_question_glyph`, `test_parse_stuck_on_menu_false_for_normal_idle_prompt`, `test_parse_stuck_on_menu_false_for_normal_working_output`, `test_parse_stuck_on_menu_true_when_shortcuts_footer_lingers_elsewhere`.

(Leave the three `test_parse_activity_not_started_*`/`test_parse_activity_generating_plain_text` deployed-only tests alone — they exercise the same pre-existing `not_started`-state discrepancy flagged in Task 1 Step 2, not `parse_stuck_on_menu`. Out of scope for this pass.)

- [ ] **Step 3: Verify**

```bash
cd /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager
python3 -m pytest tests/test_pane_parser.py -k stuck_on_menu -v
```

Expected: all 6 new tests pass.

- [ ] **Step 4: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/session-manager/pane_parser.py adapters/claude-code/session-manager/tests/test_pane_parser.py
git commit -m "feat: port parse_stuck_on_menu() into session-manager adapter

Ports the incident-2026-08-17-driven stuck-on-menu detector from the
deployed session-manager -- purely additive, no adapter-side conflict."
```

---

## Task 3: `research_sources.py` — env-var-overridable storage path, keep the TOCTOU fix

**Files:**
- Modify: `adapters/claude-code/session-manager/research_sources.py`
- Modify: `adapters/claude-code/session-manager/app.py` (route stays on the branch's atomic-check version — verify only, no change expected if Task 1 merged cleanly)

- [ ] **Step 1: Make the storage path env-var overridable**

In `adapters/claude-code/session-manager/research_sources.py`, change:

```python
# Standalone reference-implementation storage: a home-directory dotfile,
# matching sessions.py's SESSIONS_FILE convention — no dependency on any
# specific host's private repo layout.
RESEARCH_SOURCES_FILE = Path.home() / ".claude-research-sources.json"
```

to:

```python
import os

# Standalone reference-implementation storage: a home-directory dotfile by
# default, matching sessions.py's SESSIONS_FILE convention. Deployments that
# want this visible to other tooling (e.g. claude-config's housekeeping
# dashboard, which reads it directly — see docs/COMPONENT_MODEL.md §3) can
# override via RESEARCH_SOURCES_PATH.
RESEARCH_SOURCES_FILE = Path(os.environ["RESEARCH_SOURCES_PATH"]) if os.environ.get("RESEARCH_SOURCES_PATH") else Path.home() / ".claude-research-sources.json"
```

(Add the `import os` near the top with the other stdlib imports, not inline, if not already present.)

- [ ] **Step 2: Confirm `add_source()` still has the atomic duplicate check**

```bash
grep -n "def add_source" -A 15 /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/research_sources.py
```

Expected: the duplicate check (`if any(s["url"] == url for s in data.get("sources", [])): return None`) is present *inside* the `with _lock:` block, and the function returns `dict | None`. This should already be true post-merge (Task 1) — this step is a verification checkpoint, not new work. If it's missing, something went wrong in the merge; stop and investigate rather than re-adding it by hand.

- [ ] **Step 3: Confirm `app.py`'s route matches**

```bash
grep -n "def create_research_source" -A 10 /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/app.py
```

Expected: `source = add_source(url, label)` followed by `if source is None: return jsonify({"error": "source already exists"}), 409` — **not** a pre-check via `any(...)` before calling `add_source`. Same verification-only note as Step 2.

- [ ] **Step 4: Document the env var**

Add `RESEARCH_SOURCES_PATH` to `adapters/claude-code/session-manager/.env.example` with a comment: `# Optional: override where research-sources.json lives (default: ~/.claude-research-sources.json)`.

- [ ] **Step 5: Verify**

```bash
cd /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager
python3 -m pytest tests/test_research_sources.py tests/test_app.py -k research -v
RESEARCH_SOURCES_PATH=/tmp/rs-test.json python3 -c "
import os
os.environ['RESEARCH_SOURCES_PATH'] = '/tmp/rs-test.json'
import research_sources
print(research_sources.RESEARCH_SOURCES_FILE)
"
```

Expected: existing research-sources tests still pass; the env-var probe prints `/tmp/rs-test.json`.

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/session-manager/research_sources.py adapters/claude-code/session-manager/.env.example
git commit -m "feat: make research_sources.py storage path env-var overridable

Defaults to ~/.claude-research-sources.json (portable reference
behavior, unchanged). RESEARCH_SOURCES_PATH lets a deployment point
it at claude-config's library/research-sources.json instead, which
other claude-config tooling reads directly (COMPONENT_MODEL.md §3) --
this is a real deployment-specific need, not incidental drift."
```

---

## Task 4: `app.py` — `blocked_on_menu`, `/keys` endpoint, defensive `remote_control` read, reconcile-metric investigation

**Files:**
- Modify: `adapters/claude-code/session-manager/app.py`
- Modify: `adapters/claude-code/session-manager/tests/test_app.py`

- [ ] **Step 1: Wire `blocked_on_menu` into the refresh loop**

Add the `parse_stuck_on_menu` import (from Task 2) to `app.py`'s `pane_parser` import block, and in the session-refresh loop, add:

```python
session["blocked_on_menu"] = parse_stuck_on_menu(pane)
```

immediately after the existing `session["activity"] = parse_activity(pane)` line.

- [ ] **Step 2: Add the raw-key endpoint**

Port verbatim from deployed's `app.py`:

```python
_ALLOWED_KEYS = {
    "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right",
    "Enter": "Enter", "Esc": "Escape", "Space": "Space", "Tab": "Tab",
}


@app.route("/sessions/<session_id>/keys", methods=["POST"])
def send_raw_key(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    data = request.get_json(silent=True) or {}
    key = data.get("key", "")
    tmux_key = _ALLOWED_KEYS.get(key)
    if not tmux_key:
        return jsonify({"error": f"Unsupported key: {key!r}"}), 400
    if not has_session(session["tmux_session"]):
        return jsonify({"error": "Session not running"}), 404
    send_key(session["tmux_session"], tmux_key)
    return jsonify({"ok": True})
```

Place it near `toggle_remote_control` (same area as deployed).

- [ ] **Step 3: Defensive `remote_control` read**

In `toggle_remote_control`, change:

```python
new_state = not session["remote_control"]
```

to:

```python
new_state = not session.get("remote_control", False)
```

- [ ] **Step 4: Investigate the `_reconcile_sessions()` metric difference**

The adapter's (post-Task-1-merge) `_reconcile_sessions()` calls `_post_metric("agent.session_end", ...)` when dropping a stale session record; deployed's does not — deployed's docstring only explains the WSL2-restart scenario, with no mention of metrics being deliberately dropped.

```bash
cd /mnt/c/Server/claude-config
git log --follow -p --since=2026-07-22 -- services/session-manager/app.py | grep -B5 -A20 "_reconcile_sessions" | head -100
```

- **If you find a specific reason the metric emission was removed** (a bug report, a decision that reconcile-drops shouldn't count as real session-ends for metrics purposes): keep deployed's metric-free version, and note the reason in your report.
- **If you find no such reason** (looks like an incidental drop during a later edit): keep the adapter's existing metric emission — it's more complete, and a metric that undercounts `session_end` events silently is worse than one that's occasionally attributed to "reconcile" rather than an explicit removal.

Either way, don't silently pick one side — record which you found and why in the commit message.

- [ ] **Step 5: Add tests**

Port these test functions from deployed's `tests/test_app.py`: `test_toggle_remote_control_missing_key_falls_back_to_false`, `test_refresh_marks_session_blocked_on_menu`, `test_refresh_not_blocked_on_menu_for_normal_idle`, `test_send_raw_key_calls_tmux_send_key`, `test_send_raw_key_maps_esc_to_tmux_escape_name`, `test_send_raw_key_rejects_unknown_key`, `test_send_raw_key_404_when_session_not_running`, `test_send_raw_key_404_when_session_id_unknown`.

(Skip `test_create_session_with_model_passes_through`/`test_create_session_without_model_uses_default` and the `reconcile_sessions` test variants here — those depend on Task 2's `DEFAULT_MODEL` decision and are already covered by the branch's own reconcile tests respectively; re-check after Task 2 lands whether any are still missing.)

- [ ] **Step 6: Verify**

```bash
cd /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager
python3 -m pytest tests/test_app.py -k "blocked_on_menu or send_raw_key or remote_control" -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/session-manager/app.py adapters/claude-code/session-manager/tests/test_app.py
git commit -m "feat: port blocked_on_menu, raw-key endpoint, defensive remote_control read

Ports the 2026-08-17-incident blocked_on_menu wiring and the
/sessions/<id>/keys endpoint from the deployed session-manager.
_reconcile_sessions() metric-emission difference investigated: <fill
in what Step 4 found>."
```

Before committing, replace `<fill in what Step 4 found>` with the actual finding.

---

## Task 5: `tmux.py` / `sessions.py` / `app.py` — resolve the `DEFAULT_MODEL` question

**Files:**
- Modify: `adapters/claude-code/session-manager/tmux.py`
- Modify: `adapters/claude-code/session-manager/app.py`
- Modify: `adapters/claude-code/session-manager/tests/test_tmux.py`

The branch's own plan (`docs/superpowers/plans/2026-07-21-session-manager-adapter-sync.md`, Task 3 Step 6 note) deliberately did **not** add a `DEFAULT_MODEL` constant or default deployed's `model or DEFAULT_MODEL` fallback into the adapter, reasoning: *"the deployed service defaults to `model or DEFAULT_MODEL` here because it hardcodes a specific default model constant; the adapter has no such constant today and shouldn't invent a homelab-specific default — `model=model` with `None` falling through to `launch_session`'s own no-op default is the correct adapter-scoped behavior."*

- [ ] **Step 1: Keep that decision — do not add `DEFAULT_MODEL` to the adapter**

No code change needed here; this step is a documentation checkpoint. Confirm current state:

```bash
grep -n "DEFAULT_MODEL\|model=model" /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tmux.py /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/app.py
```

Expected: no `DEFAULT_MODEL` in either file; `app.py`'s `create_session()` call still passes `model=model` (not `model=model or DEFAULT_MODEL`).

- [ ] **Step 2: Record the decision explicitly in this pass's commit trail**

```bash
cd /mnt/c/Server/projects/ikeos
git commit --allow-empty -m "docs: reaffirm no-hardcoded-default-model decision for session-manager adapter

Re-confirmed during Pass 2 of the adapter/harness consolidation
(docs/superpowers/plans/2026-08-20-adapter-harness-consolidation-pass2-session-manager.md).
Deployed's tmux.py defines DEFAULT_MODEL = \"claude-sonnet-5\" and
defaults model=model or DEFAULT_MODEL in POST /sessions; the adapter
deliberately does not carry this forward, per the original sync
plan's Task 3 Step 6 rationale: a specific default model is a
this-host preference, not reference-implementation material. The
generate mechanism (Task 7) must therefore NOT try to make these
files byte-identical for this one line -- see Task 7's handling."
```

This is an empty commit by design — it exists so `git log` on this file shows the decision was revisited and reaffirmed, not missed. Task 7 needs to know about this because it means `app.py`/`tmux.py` can **not** be verbatim-generated the way Pass 1's skill files were — see Task 7 Step 1.

---

## Task 6: `start.sh` — port the tmux-isolation fix

**Files:**
- Modify: `adapters/claude-code/session-manager/start.sh`

- [ ] **Step 1: Port the fix**

Replace the adapter's `start.sh` content with deployed's version (the `unset TMUX` block with its explanatory comment, and `exec python3 app.py` instead of `python3 app.py`), keeping the adapter's simpler header comment style (deployed's references `restart.sh`, which doesn't exist in the adapter — use a generic "Run from WSL2: bash start.sh" header instead, matching the adapter's existing convention, not deployed's `restart.sh`-specific phrasing).

- [ ] **Step 2: Verify it's still valid bash**

```bash
bash -n /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/start.sh
```

Expected: no output (syntax OK).

- [ ] **Step 3: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/session-manager/start.sh
git commit -m "fix: port tmux-server isolation fix into session-manager adapter start.sh

unset TMUX and exec python3 app.py, ported from the deployed copy --
without this, launching the manager from inside a tmux pane binds it
and every session it spawns to that pane's tmux server, so killing
that server takes down all sessions. See vault: claude-config
2026-07-13 (session-manager tmux isolation)."
```

---

## Task 7: `sync.sh generate` — extend to the session-manager files

**Files:**
- Modify: `claude-config/scripts/sync.sh`

Unlike Pass 1's skill files (verbatim copy + one header line), two session-manager files can't be byte-identical-modulo-header between adapter and deployed:

- **`tmux.py`**: adapter uses `CLAUDE_BIN`/`PLUGIN_BASE` from env vars with generic fallbacks; deployed needs this host's real hardcoded values (or, better — see Step 1) the same env vars, actually set. Per Task 5, the adapter also does **not** define `DEFAULT_MODEL` or default `model or DEFAULT_MODEL`, which deployed's `app.py`/`tmux.py` still do.
- **`research_sources.py`**: works unmodified from Task 3 onward — the storage path is now env-var driven (`RESEARCH_SOURCES_PATH`), so the file itself is identical; only the *deployed `.env`* needs the var set. No special-casing needed for this file specifically.

- [ ] **Step 1: Resolve the `tmux.py`/`app.py` non-identical-copy problem**

Two options — pick based on what you find:

**Option A (preferred if it works cleanly):** Set `CLAUDE_BIN`, `CLAUDE_PLUGIN_BASE` in the *live* `~/.claude/settings.json` env block (extending Task 1's Pass-1 precedent — same file, same `setdefault` pattern) instead of hardcoding them in deployed's `tmux.py`. Then `tmux.py` becomes byte-identical between adapter and deployed (env-var code, working the same on both), and it generates cleanly like Pass 1's skill files. Verify: does `claude-config/scripts/bootstrap-wsl2.sh`'s env step (Task 1 of Pass 1) reach the session-manager process's environment, or does the session-manager (run via `restart.sh`, not through Claude Code's `~/.claude/settings.json`) need these set some other way (its own `.env` file, sourced by `start.sh`)? Session-manager's `start.sh` already sources a local `.env` — so add `CLAUDE_BIN`/`CLAUDE_PLUGIN_BASE` to deployed's real `.env` (not `.env.example`, not `~/.claude/settings.json` — that env block is Claude Code's own runtime, a different process) if they aren't already resolvable via `os.environ.get()`'s existing fallback. Check deployed's actual `.env` first:

```bash
grep -n "CLAUDE_BIN\|CLAUDE_PLUGIN_BASE" /mnt/c/Server/claude-config/services/session-manager/.env
```

If absent, add them there (not `.env.example`, which stays generic) with this host's real values (`/home/autoserver/bin/claude`, `/mnt/c/Users/ServerAdmin/.claude/plugins/cache/claude-plugins-official` — the values currently hardcoded in deployed's `tmux.py`).

**Option B (fallback if Option A can't fully close the gap, e.g. the `DEFAULT_MODEL` line):** Extend `do_generate` with a small per-file post-processing step for `tmux.py` and `app.py` specifically — after copying, apply a fixed sed/python substitution that re-adds deployed's `DEFAULT_MODEL` constant and `model or DEFAULT_MODEL` default. Keep this substitution tiny and explicitly commented in `sync.sh` (`# tmux.py needs this host's default-model fallback; the portable adapter deliberately omits it — see Pass 2 Task 5`), not a general templating system.

Try Option A first — if `CLAUDE_BIN`/`CLAUDE_PLUGIN_BASE` env vars alone close the `tmux.py` gap (they should, since that's the only non-`DEFAULT_MODEL` difference left after Tasks 1–6), you only need Option B's substitution for the single `DEFAULT_MODEL` line in `tmux.py` and the single `model or DEFAULT_MODEL` line in `app.py`. Decide and document which option(s) you used in the Task 8 commit message.

- [ ] **Step 2: Add `SESSION_MANAGER_GENERATE_ITEMS`**

In `claude-config/scripts/sync.sh`, after the existing `GENERATE_ITEMS` array:

```bash
# Session-manager source files, generated the same way as the skills above.
# Format: "source-relative-path:target-relative-path"
SESSION_MANAGER_GENERATE_ITEMS=(
    "session-manager/app.py:app.py"
    "session-manager/tmux.py:tmux.py"
    "session-manager/pane_parser.py:pane_parser.py"
    "session-manager/sessions.py:sessions.py"
    "session-manager/research_sources.py:research_sources.py"
    "session-manager/start.sh:start.sh"
)
SESSION_MANAGER_TARGET="$REPO_ROOT/services/session-manager"
```

Note `research_sources.py` and `sessions.py` are included even though they're currently identical modulo header — including them now means future drift on *those* files gets caught too, not just the two known-different ones.

- [ ] **Step 3: Extend `do_generate` for the session-manager set**

Add a second loop inside `do_generate` (after the existing `GENERATE_ITEMS` loop), using `#` as the Python comment marker instead of `<!-- -->`:

```bash
    for mapping in "${SESSION_MANAGER_GENERATE_ITEMS[@]}"; do
        local src_rel="${mapping%%:*}"
        local dst_rel="${mapping##*:}"
        local src="$IKEOS_REPO_PATH/adapters/claude-code/$src_rel"
        local dst="$SESSION_MANAGER_TARGET/$dst_rel"

        if [ ! -f "$src" ]; then
            log_error "Generate source not found: $src"
            exit 1
        fi

        local comment_marker="#"
        local header="$comment_marker GENERATED from ikeos/adapters/claude-code/$src_rel -- do not edit here. Edit the source and run: bash scripts/sync.sh generate"
        local tmp
        tmp=$(mktemp)
        printf '%s\n' "$header" > "$tmp"
        cat "$src" >> "$tmp"
        # Apply Task 7 Step 1's host-specific substitutions (Option A/B) here if used.

        if [ -f "$dst" ] && cmp -s "$tmp" "$dst"; then
            unchanged=$((unchanged + 1))
            rm "$tmp"
        else
            mv "$tmp" "$dst"
            log_info "Generated: services/session-manager/$dst_rel (from ikeos/adapters/claude-code/$src_rel)"
            changed=$((changed + 1))
        fi
    done
```

If Task 7 Step 1 used Option B, insert the actual substitution logic where the comment marks it — write it as a small `sed`/`python3 -c` step scoped to exactly `tmux.py`/`app.py`, not a generic mechanism.

A Python file starting with a `#`-comment header is syntactically valid (it's just a comment) — verify this doesn't break anything that parses the file's first line specially (it shouldn't; Python has no shebang-line special-casing beyond `#!`, and this header isn't a shebang).

- [ ] **Step 4: Run and verify**

```bash
cd /mnt/c/Server/claude-config
bash scripts/sync.sh generate
head -1 services/session-manager/{app,tmux,pane_parser,sessions,research_sources}.py services/session-manager/start.sh
bash scripts/sync.sh generate   # idempotency check
```

Expected: first run reports 6 generated files; header line present on each; second run reports all unchanged.

- [ ] **Step 5: Verify the generated files are actually correct**

```bash
cd /mnt/c/Server/claude-config/services/session-manager
python3 -m py_compile app.py tmux.py pane_parser.py sessions.py research_sources.py
diff <(tail -n +2 tmux.py) <(cat /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tmux.py)
```

Expected: `py_compile` succeeds (no syntax errors introduced by any Step 1 substitution). The `diff` is expected to show the `CLAUDE_BIN`/`PLUGIN_BASE`/`DEFAULT_MODEL` differences you deliberately introduced in Step 1 — confirm they're *only* those lines, nothing else.

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Server/claude-config
git add scripts/sync.sh services/session-manager/app.py services/session-manager/tmux.py services/session-manager/pane_parser.py services/session-manager/sessions.py services/session-manager/research_sources.py services/session-manager/start.sh
git commit -m "feat: sync.sh generate -- extend to session-manager source files

Extends the Pass 1 skills-generation mechanism to
services/session-manager/{app,tmux,pane_parser,sessions,
research_sources}.py and start.sh. tmux.py/app.py needed <Option A/B
from Task 7 Step 1 -- fill in which> to preserve this host's
CLAUDE_BIN/CLAUDE_PLUGIN_BASE/DEFAULT_MODEL values, which the
portable adapter deliberately doesn't hardcode."
```

Fill in which option before committing.

---

## Task 8: `check-drift.sh` — watch the session-manager boundary

**Files:**
- Modify: `claude-config/scripts/check-drift.sh`

- [ ] **Step 1: Extend the drift check**

Add a second `GENERATE_ITEMS`-style block mirroring Pass 1's Task 4 pattern exactly, but for `SESSION_MANAGER_GENERATE_ITEMS` against `$SCRIPT_DIR/../services/session-manager` instead of `$REPO/commands`. Reuse the same `diff -q <(tail -n +2 "$dst") "$src"` comparison shape, and the same `SKIP_EVALS=1 bash "$SCRIPT_DIR/sync.sh" generate` healing call — both `GENERATE_ITEMS` sets can be regenerated by the same single `sync.sh generate` invocation, so you don't need two separate `generate` calls if drift is found in either.

Note: if Task 7 Step 1 used Option B (sed/python substitution for `tmux.py`/`app.py`), the drift comparison for those two files needs to account for the substitution too — compare against what `generate` *would produce*, not a raw `diff` against the adapter source. The simplest correct approach: run `sync.sh generate` unconditionally at the top of `check-drift.sh` for the session-manager set (it's already idempotent and cheap — a handful of file compares) rather than trying to detect-then-heal for just this one boundary. Keep the skills boundary's existing detect-then-heal pattern (Pass 1 Task 4) unchanged — only the session-manager boundary needs this adjustment, and only if Option B was used.

- [ ] **Step 2: Verify no-drift silence**

```bash
bash /mnt/c/Server/claude-config/scripts/check-drift.sh
echo "exit: $?"
```

Expected: no output, exit 0 (everything in sync after Task 7).

- [ ] **Step 3: Verify detection/healing on the new boundary**

```bash
echo "# test drift" >> /mnt/c/Server/claude-config/global/../../projects/ikeos/adapters/claude-code/session-manager/pane_parser.py
```

Wait — don't dirty the ikeos source tree for a throwaway test. Instead, introduce drift on the *deployed* side and confirm generate overwrites it back (this also exercises the "deployed drifted, source of truth wins" direction, which is the actually-dangerous direction to get wrong):

```bash
echo "# manual edit that should be reverted" >> /mnt/c/Server/claude-config/services/session-manager/pane_parser.py
bash /mnt/c/Server/claude-config/scripts/check-drift.sh
tail -3 /mnt/c/Server/claude-config/services/session-manager/pane_parser.py
```

Expected: JSON drift-notification output, and the tail no longer shows the manual edit — `generate` overwrote it back to match the adapter source.

- [ ] **Step 4: Commit**

```bash
cd /mnt/c/Server/claude-config
git add scripts/check-drift.sh
git commit -m "feat: check-drift.sh watches session-manager boundary too

Extends Pass 2's generate mechanism into the SessionStart drift-check,
mirroring the skills boundary check-drift.sh already does."
```

---

## Task 9: Restart the live service and verify it actually works

**Files:** none (operational verification)

This is the step the design spec calls out explicitly: "after generation, it must be restarted and its live behavior... verified before considering the task done, not just its test suite."

- [ ] **Step 1: Note the current risky run state (informational, not fixed here)**

The live session-manager process is currently running as `tmux new-session -d -s session-manager ... python3 app.py` (started via `setup-startup.ps1`'s Task Scheduler action) — the exact anti-pattern `start.sh`'s `unset TMUX` comment and `restart.sh`'s header warn against ("never wrap start.sh in `tmux new-session`"). This plan does not change `setup-startup.ps1` (out of scope — Windows-only ops tooling, no adapter counterpart, not named in the design spec's Success Criteria). But Step 2 below uses `restart.sh`, which *will* move the running process off that tmux session onto a properly detached process — a real, positive side effect of this pass, not an accidental one. Flag this to the user as a discovered improvement, not a silent one.

- [ ] **Step 2: Restart via the documented safe path**

```bash
cd /mnt/c/Server/claude-config/services/session-manager
bash restart.sh
```

Expected: "stopped previous manager" (or "no previous manager running" if the tmux-hosted process doesn't match `restart.sh`'s cwd-based match — check this; if it doesn't stop the old one, you'll have two processes bound to :5010 and the new one will fail to bind — investigate and stop the old tmux-hosted process manually first if so: `tmux kill-session -t session-manager` only after confirming via Step 3 that the new detached process is healthy, so you don't kill the only working instance), then "session-manager healthy on :5010" within 30s.

- [ ] **Step 3: Verify it's the new code, not a stale process**

```bash
curl -s http://localhost:5010/sessions | python3 -m json.tool | head -20
pgrep -af 'app.py'
```

Confirm the process is running from `/mnt/c/Server/claude-config/services/session-manager` (restart.sh's cwd match target), and is NOT inside a tmux session this time (`ps -o pid,ppid,cmd -p $(pgrep -f 'app.py' | head -1)` — its parent shouldn't trace back to a tmux server).

- [ ] **Step 4: Real session lifecycle smoke test**

```bash
curl -s -X POST http://localhost:5010/sessions -H "Content-Type: application/json" \
  -d '{"name":"pass2-verify-test","project":"ikeos","project_dir":"/mnt/c/Server/projects/ikeos"}' | python3 -m json.tool
curl -s http://localhost:5010/sessions | python3 -c "import json,sys; d=json.load(sys.stdin); print([s for s in d if s['name']=='pass2-verify-test'])"
curl -s -X DELETE http://localhost:5010/sessions/$(curl -s http://localhost:5010/sessions | python3 -c "import json,sys; d=json.load(sys.stdin); print([s['id'] for s in d if s['name']=='pass2-verify-test'][0])")
tmux list-sessions | grep pass2-verify-test || echo "cleaned up"
```

Expected: session creates successfully, appears in the list with the new `model` field populated, deletes cleanly, and the underlying tmux session is gone.

- [ ] **Step 5: Verify `/research-sources` and `/sessions/<id>/keys` against the live service**

```bash
curl -s http://localhost:5010/research-sources | python3 -m json.tool
```

Expected: valid JSON (empty or populated `sources` list, not a 500 — confirms the `RESEARCH_SOURCES_PATH` env var from Task 3/7 resolved correctly against deployed's real `.env`, pointing at `claude-config/library/research-sources.json`, and that existing data survived the path-resolution change).

```bash
diff <(python3 -c "import json; print(json.load(open('/mnt/c/Server/claude-config/library/research-sources.json'))['sources'])") \
     <(curl -s http://localhost:5010/research-sources | python3 -c "import json,sys; print([{k:v for k,v in s.items() if k!='id'} for s in json.load(sys.stdin)['sources']])")
```

Expected: no meaningful diff (confirms the live service is still reading the *same* pre-existing data file post-restart, not a fresh empty one at the wrong path).

- [ ] **Step 6: Report**

Summarize in your final report: confirmed the new process is detached from tmux (a real fix, not just a reconciliation), the smoke test passed, and `/research-sources` is reading the correct pre-existing data file.

---

## Task 10: Close the loop (per design spec §7)

**Files:**
- Modify: `docs/COMPONENT_MODEL.md` §7
- Modify: `ikeos/.claude/DECISIONS.md`
- Modify: `claude-config`'s own decisions record (verify its location/format first — do not assume it matches `ikeos`'s `.claude/DECISIONS.md` convention)

Only do this task once Tasks 1–9 are fully committed and the live-service verification in Task 9 has passed — the design spec is explicit that closing the loop happens after passes 1 *and* 2 are both done and verified.

- [ ] **Step 1: Update `docs/COMPONENT_MODEL.md` §7**

Read the current §7 ("Known duplication / drift points (documented, not resolved)"). Change it to state that the skills (except `housekeeping.md`) and the session-manager are now resolved via the copy-and-regenerate mechanism (`claude-config/scripts/sync.sh generate` + `check-drift.sh`), with `housekeeping.md`/council-pipeline skills named as the one remaining open item (Pass 3, no date), pointing at the `DECISIONS.md` entries added in Step 2.

- [ ] **Step 2: Add the `ikeos` `DECISIONS.md` entry**

Record: the consolidation (both passes), the copy-and-regenerate mechanism, the recovered `feat/session-manager-adapter-sync` branch and why it existed, the TOCTOU-fix-preservation and `DEFAULT_MODEL`-omission decisions, the `RESEARCH_SOURCES_PATH` env var addition, and the `housekeeping.md`/Pass 3 deferral with its reason.

- [ ] **Step 3: Add the `claude-config` decisions record entry**

First check whether `claude-config` has an equivalent convention (search `claude-config/docs/` for a decisions log). Match its existing format if one exists; if none exists, note that in your report rather than inventing a new convention unilaterally — ask before creating one.

- [ ] **Step 4: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add docs/COMPONENT_MODEL.md .claude/DECISIONS.md
git commit -m "docs: close the loop on adapter/harness consolidation passes 1-2

COMPONENT_MODEL.md §7 and DECISIONS.md now reflect that skills (minus
housekeeping.md) and session-manager are resolved via sync.sh
generate/check-drift.sh. housekeeping.md + council skills remain the
one open item, deferred to Pass 3 (no date, blocked on the council
pipeline stabilizing)."
```

Commit the `claude-config` decisions entry separately, in that repo, matching whatever Step 3 found.
