# Adapter/Harness Drift Consolidation — Design Spec

**Date:** 2026-08-19
**Status:** proposed
**Repos affected:** `ikeos` (this repo) and `claude-config` (sibling repo at `/mnt/c/Server/claude-config`)
**Trigger:** `docs/COMPONENT_MODEL.md` §7 (merged to `ikeos` main at `7f138c2`) documented, but deliberately deferred resolving, confirmed drift between `ikeos/adapters/claude-code/{skills,session-manager}/` (portable reference copies) and `claude-config/{global/commands,services/session-manager}/` (deployed, hardcoded copies). This spec resolves that deferral.

---

## What was found (grounding for this design)

Diffing every duplicated pair confirmed the drift is **bidirectional and substantive** — not just path/hardcoding differences:

- **`triage.md`** (26 changed lines): adapter has a `CLAUDE_CONFIG_DIR` existence-check fallback the deployed copy lacks.
- **`housekeeping.md`** (275 changed lines, largest): deployed has a real bug fix (YAML plain-scalar line-folding — continuation lines were being silently discarded, truncating wrapped frontmatter values) and an operational discovery (`$CAPTURE_TOKEN` is not reliably available in non-interactive agent shells, so the deployed copy reads `.env` directly instead) that don't exist in the adapter at all.
- **`promote.md`** (11 changed lines): mostly path-only; adapter references `templates/adr.md`, deployed doesn't.
- **`schema-check.md`** (17 changed lines): deployed lacks the adapter's `VAULT_PATH`-unset guard clause.
- **`close-session.md`** (75 changed lines): deployed has a documented methodology decision (a footnote citing an external memory-retention study justifying "selective, not exhaustive" capture) and a different, simpler blog-notes-append implementation that the adapter lacks entirely; both copies also differ in how they read `weak-signals.json`.
- **`code-review.md`**: exists only in the adapter — no deployed counterpart today.
- **Session-manager**: deployed has an entire extra module (`research_sources.py` + test) and extra ops scripts (`restart.sh`, `setup-startup.ps1`) absent from the adapter. Every shared `.py` file differs.
- **No tooling watches either boundary.** `claude-config/scripts/check-drift.sh` only diffs `claude-config/global/` against the deployed `~/.claude` runtime.
- **Root cause for part of the skills drift:** `claude-config/global/settings.json` has no `env` block, even though Claude Code's settings.json format supports one — so `VAULT_PATH`/`IKEOS_URL`/`CAPTURE_TOKEN` were never reliably available to non-interactive agent shells, forcing the deployed copies to work around it locally.

## Goal

Make `ikeos/adapters/claude-code/{skills,session-manager}/` the single source of truth for the 5 duplicated skills and the shared session-manager code, with the deployed copies **generated** (never hand-edited) from that source — eliminating this class of drift by construction, while preserving every real improvement currently living on either side.

## Non-goals

- Do not touch the ~25 generic (non-IkeOS) commands in `claude-config/global/commands/` (`grill-me.md`, `blog.md`, `deploy-cottage.md`, etc.) — they have no adapter counterpart and are out of scope.
- Do not add `code-review.md` as a deployed command — it stays adapter-only unless a separate decision adds it.
- Do not pursue the "generic skills as a versioned library" idea raised during this brainstorm — filed as a vault idea (`claude-config` project) for a separate future decision.
- Do not use symlinks for the deployment mechanism (see Design §4 for why).
- Do not attempt to reconcile `claude-config/services/session-manager`'s deployment-local files (`.env`, `.gitignore`, `.pytest_cache`, `restart.sh`, `setup-startup.ps1`) — they are legitimately per-deployment and stay as-is.

---

## Design

### 1. Root-cause fix: `claude-config/global/settings.json` gains an `env` block

Add `VAULT_PATH`, `IKEOS_URL`, `CAPTURE_TOKEN` to a new top-level `env` key in `claude-config/global/settings.json` (deployed via the existing `sync.sh apply` to `~/.claude/settings.json`), so these are reliably present in every Claude Code session's shell environment — including non-interactive ones.

This does **not** mean removing the `.env`-file-read fallback that the deployed `housekeeping.md`/`close-session.md` currently use — that fallback was discovered empirically, under real failure conditions, and the settings.json fix is unverified in practice until it's been running for a while. The reconciled skills keep both: read the env var first, fall back to reading `.env` directly if unset. This is additive robustness, not a replacement.

### 2. Reconcile the 5 duplicated skills, once

For each of `triage.md`, `housekeeping.md`, `promote.md`, `schema-check.md`, `close-session.md`, produce one merged version living at `ikeos/adapters/claude-code/skills/<name>.md` that:

- Keeps every genuine improvement found on the deployed side (the `housekeeping.md` YAML-fold bug fix; the `close-session.md` memory-retention-study footnote; the `POST /capture` 302-response notes in both `housekeeping.md` and `close-session.md`).
- Keeps every genuine improvement found on the adapter side (the `triage.md` `CLAUDE_CONFIG_DIR` fallback; the `promote.md` `templates/adr.md` reference; the `schema-check.md` `VAULT_PATH`-unset guard).
- Uses env-var-primary, `.env`-fallback for `VAULT_PATH`/`IKEOS_URL`/`CAPTURE_TOKEN` throughout (per §1).
- For hunks that are **not** obviously one-sided (the differing `weak-signals.json`-reading approach and the differing blog-notes-append implementation in `close-session.md`) — this is a judgment call requiring investigation, not something to decide here. The implementation task must read both versions in full, determine which approach is more correct/robust (or whether to merge behaviors), and document the decision in its report. Do not silently pick one side without checking whether the other's approach exists for a reason.

`code-review.md` is not part of this reconciliation (no deployed counterpart exists; out of scope per above).

### 3. Reconcile session-manager, once

In `ikeos/adapters/claude-code/session-manager/`:

- Promote `research_sources.py` (and `tests/test_research_sources.py`) from deployed-only into the adapter as canonical — this is general functionality (a `/research-sources` API), not homelab-specific, and there's no reason it should only exist in the deployed copy.
- Merge the diffs in `app.py`, `sessions.py`, `tmux.py`, `pane_parser.py`, `start.sh` — read both versions in full for each file (do not rely on the diff alone; a large diff can hide a small real change inside noise, and a small diff can hide something significant). The `docs/superpowers/plans/2026-07-21-session-manager-adapter-sync.md` plan already did one round of this for `tmux.py`/`sessions.py` (adding `list_session_names()`, `model` param threading, idle-detection refinement) — check whether that round's changes are still present and current in both copies, since it predates this reconciliation.
- Deployment-local files stay in `claude-config/services/session-manager/` only, never touched by generation: `.env`, `.gitignore`, `.pytest_cache/`, `restart.sh`, `setup-startup.ps1`.

### 4. Deployment mechanism: copy-and-regenerate, not symlinks

`claude-config/scripts/sync.sh` gains a new `generate` step (in addition to its existing `apply` step) that **copies** files from `ikeos/adapters/claude-code/` into `claude-config`:

- `ikeos/adapters/claude-code/skills/{triage,housekeeping,promote,schema-check,close-session}.md` → `claude-config/global/commands/<name>.md`, each stamped with a leading HTML comment: `<!-- GENERATED from ikeos/adapters/claude-code/skills/<name>.md — do not edit here. Edit the source and run: bash scripts/sync.sh generate -->`
- `ikeos/adapters/claude-code/session-manager/{app.py,sessions.py,tmux.py,pane_parser.py,research_sources.py,start.sh,tests/}` → the corresponding paths under `claude-config/services/session-manager/`, excluding the deployment-local files listed in §3. Non-markdown files get an equivalent comment in their native comment syntax at the top.

**Why not symlinks**, even though both repos share a filesystem: both repos live on a `/mnt/c` drvfs (Windows-drive) mount — earlier exploration in this project found every file on this mount reporting `777` permissions regardless of actual intent, which suggests this mount's fidelity for non-trivial filesystem features (symlinks included) is not something to trust without a dedicated spike, and there's no reason to take that risk on a live-running service's deploy path when a plain copy step is simple, portable, and git-diffable (a generated file's diff shows up cleanly in a PR; a symlink's don't).

`claude-config/scripts/check-drift.sh` gets extended to also diff each generated file against its `ikeos` source (in addition to its existing `global/` → `~/.claude` check) and auto-heal via `sync.sh generate` when they differ — this exactly mirrors its current, already-working pattern one hop earlier in the chain.

### 5. New cross-repo coupling, made explicit

`claude-config/scripts/sync.sh` needs to know where `ikeos` lives on disk to run `generate`. Add a config value (e.g. `IKEOS_REPO_PATH`, default `/mnt/c/Server/projects/ikeos`, matching the existing homelab convention that projects live under `~/server/projects/`) rather than hardcoding the path inline in the script. If the path doesn't exist when `generate` runs, fail loudly with a clear message rather than silently skipping.

### 6. Rollout sequencing

Two separate implementation passes, both following from this one spec:

1. **Skills first.** Lower risk (prompt text, not running code), validates the `generate`/`check-drift.sh` mechanism end-to-end before it's trusted with a live service.
2. **Session-manager second.** Applies the proven mechanism to `claude-config/services/session-manager`, which is a live-running Flask service — after generation, it must be restarted and its live behavior (session creation, tmux interaction) verified before considering the task done, not just its test suite.

Each pass gets its own implementation plan (`docs/superpowers/plans/...`) and its own subagent-driven-development run, per this project's standing execution preference.

### 7. Close the loop

Once both passes are complete and verified:

- Update `docs/COMPONENT_MODEL.md` §7 in `ikeos`: change from "documented, not resolved" to a short note that this is resolved, with a pointer to the `DECISIONS.md` entries below.
- Add a dated entry to `ikeos/.claude/DECISIONS.md` recording the consolidation and the copy-and-regenerate mechanism.
- Add a corresponding dated entry to `claude-config`'s own decisions record (if one exists at `claude-config/docs/` — verify the convention there before assuming it matches `ikeos`'s `.claude/DECISIONS.md` format).

---

## Success Criteria

- `claude-config/global/settings.json` (and deployed `~/.claude/settings.json`) has the `env` block; `.env`-fallback reading is preserved, not removed, in the reconciled skills.
- `ikeos/adapters/claude-code/skills/*.md` (6 files) each contain the real improvements previously found only on one side or the other, with no content silently dropped.
- `ikeos/adapters/claude-code/session-manager/` contains `research_sources.py` + its test, and its shared `.py`/`start.sh` files reflect a deliberate merge (documented in the implementer's report), not a coin-flip pick of one side.
- `claude-config/scripts/sync.sh generate` exists, is idempotent, and produces byte-identical output to the current `ikeos` source on every run.
- `claude-config/scripts/check-drift.sh` detects and auto-heals drift between `ikeos/adapters/` and the generated copies, the same way it already does for `global/` → `~/.claude`.
- The 5 generated `claude-config/global/commands/*.md` files and the generated session-manager files carry the "do not edit, generated from..." header.
- `claude-config/services/session-manager` is running the regenerated code and has been verified live (not just via its test suite) after the second pass.
- `docs/COMPONENT_MODEL.md` §7 and both repos' decision logs reflect the resolution.
