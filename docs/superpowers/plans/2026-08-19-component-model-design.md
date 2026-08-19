# IkeOS Component Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `docs/COMPONENT_MODEL.md` — a single canonical, purpose-sectioned map of every component in the IkeOS ecosystem (Interface, Vault, Harness, Adapters, Self-Improvement) across both the `ikeos` and `claude-config` repos — and make it discoverable from `README.md`, `CLAUDE.md`, and `.claude/DECISIONS.md`.

**Architecture:** Documentation-only change, two tasks. Task 1 creates the component-model document itself with all content specified in the spec, verified against real repo paths. Task 2 wires discoverability: one link each in `README.md` and `CLAUDE.md`, plus a dated `.claude/DECISIONS.md` entry recording why the doc exists and that the drift points it documents are deliberately left unresolved.

**Tech Stack:** Markdown only. No code, no tests in the pytest sense — "verification" here means grepping the repo to confirm every path/file cited in the doc actually exists, and confirming the new cross-links resolve.

**Spec:** `docs/superpowers/specs/2026-08-19-component-model-design.md`

## Global Constraints

- Documentation-only: no files moved, no code changed, no drift fixed, no new scripts/tooling written.
- Every path cited in `docs/COMPONENT_MODEL.md` must be verified to exist in the repo at plan-execution time, not copied blindly from the spec (repo state may have shifted since the spec was written).
- The "Known duplication / drift points" section must state the drift as a documented fact and explicitly defer resolution — do not propose or hint at a fix.
- No placeholders (TBD/TODO) anywhere in the delivered doc.

---

## File Structure

- Create: `docs/COMPONENT_MODEL.md` — the canonical component-model document (8 sections, per spec).
- Modify: `README.md` — one new line near the existing `CLAUDE.md` architecture pointer.
- Modify: `CLAUDE.md` — one new line in the header block, alongside the existing `PHILOSOPHY.md` / `DECISIONS.md` references.
- Modify: `.claude/DECISIONS.md` — one new dated entry, appended (append-only file, never edit prior entries).

---

## Task 1: Create `docs/COMPONENT_MODEL.md`

**Files:**
- Create: `docs/COMPONENT_MODEL.md`

**Interfaces:**
- Produces: `docs/COMPONENT_MODEL.md`, a Markdown file with top-level headings `## 1. Overview` through `## 8. Cross-links`. Task 2 links to this file by its repo-relative path `docs/COMPONENT_MODEL.md` and does not depend on its internal heading structure.

- [ ] **Step 1: Verify every path the doc will cite still exists**

Run this from the `ikeos` repo root and confirm each line prints a path (no "No such file or directory" errors):

```bash
ls -d app/ adapters/claude-code/ adapters/claude-code/skills/ adapters/claude-code/session-manager/ app/services/scheduler.py app/services/driver.py app/services/metrics.py app/services/reflection.py app/services/research_findings.py app/services/reviews.py app/services/vault.py docs/SESSION_DRIVER_API.md
ls -d /mnt/c/Server/claude-config/global/ /mnt/c/Server/claude-config/services/session-manager/ /mnt/c/Server/claude-config/library/ /mnt/c/Server/claude-config/evals/ /mnt/c/Server/claude-config/scripts/check-drift.sh /mnt/c/Server/claude-config/scripts/stophook-reflection.sh
```

If any path is missing or renamed, update the corresponding reference in Step 2's content before writing it — do not write a stale path.

- [ ] **Step 2: Write `docs/COMPONENT_MODEL.md`**

Create the file with exactly this content (adjust only if Step 1 found a stale path):

````markdown
# IkeOS Component Model

> Canonical map of every component in the IkeOS ecosystem — what each one is, where it lives, what it depends on, and what it must never do. See `PHILOSOPHY.md` for the principles this model operationalizes, and `.claude/DECISIONS.md` for why this document exists.

## 1. Overview

IkeOS is not one repo — it's five components spread across two git repos. This document exists because that split had never been written down in one place, and two of the components had quietly drifted apart as a result (see §7).

| Component | Repo / Path |
|---|---|
| Interface | `ikeos/app/` |
| Vault | Obsidian vault filesystem (not code) |
| Harness | `claude-config/global/` → deployed to `~/.claude` |
| Adapters | `ikeos/adapters/claude-code/` |
| Self-Improvement | `ikeos/app/services/{scheduler,driver,metrics,reflection,research_findings,reviews}.py` + `claude-config/{library,evals}/` |

## 2. Interface

- **What it is:** The Flask web app — dashboard, vault browser, capture UI, housekeeping UI. The human-facing surface and "platform brain" per `CLAUDE.md`.
- **Where it lives:** `ikeos/app/` (routes/services/templates/static).
- **Depends on:** Vault (via `app/services/vault.py`, the sole file-I/O owner), Adapters (session driver client, capture API contract), Self-Improvement data (reads `claude-config/library/*.json` read-only via the `CLAUDE_CONFIG_PATH` mount).
- **Must not:** Touch the filesystem outside `vault.py`; embed Claude-Code-specific (harness) logic — that belongs in Adapters.

## 3. Vault

- **What it is:** The Obsidian Markdown store — the storage layer (no database, per `.claude/DECISIONS.md` 2026-05-26).
- **Where it lives:** Host filesystem, mounted read-write into `ikeos` via `VAULT_PATH`.
- **Depends on:** Nothing — it's the ground truth other components read and write against.
- **Must not:** Be written directly by agents — all writes go through the capture API (`POST /capture`, `PATCH /entries`), per the 2026-06-11 decision.

## 4. Harness

- **What it is:** The deployed Claude Code configuration that shapes agent behavior day to day — rules, slash-command skills, permission baseline, hooks wiring.
- **Where it lives:** `claude-config/global/` (commands, rules, settings.json), synced by `scripts/sync.sh apply` to the live `~/.claude` runtime directory. This is the actual analog to a standalone conventions repo like a colleague's `agentharness`.
- **Depends on:** Nothing IkeOS-specific in principle — most of `claude-config/global/commands/` (e.g. blog, deploy-cottage, wire-remote) has nothing to do with IkeOS at all. The subset that *is* IkeOS-specific (triage, housekeeping, promote, schema-check, close-session) is derived from Adapters (see §5).
- **Must not:** Be the only place an IkeOS-specific skill's logic exists — the portable version belongs in Adapters, so IkeOS can be stood up elsewhere without this deployment's hardcoded paths.

## 5. Adapters

- **What it is:** The portable contract/reference-implementation connecting an external AI coding tool (currently Claude Code) to an IkeOS instance — env-var-driven skill definitions, a reference session-manager (Session Driver API), a reference StopHook script. This is what `PHILOSOPHY.md`'s "Adapter Principle" refers to: replaceable, defines the contract, not coupled to one deployment.
- **Where it lives:** `ikeos/adapters/claude-code/` (`skills/`, `session-manager/`, `hooks/`).
- **Depends on:** Documents the Session Driver API (`docs/SESSION_DRIVER_API.md`) that Interface also implements against.
- **Must not:** Contain one specific deployment's hardcoded paths or hostnames — must stay env-var driven (`VAULT_PATH`, `IKEOS_URL`, `CLAUDE_CONFIG_DIR`) so it's usable as a template by anyone else deploying IkeOS.

## 6. Self-Improvement (the "utilities" layer)

- **What it is:** The housekeeping/reflection/metrics instrumentation that lets IkeOS observe and improve its own operation over time — distinct from Harness (which shapes behavior) and Interface (which displays state).
- **Where it lives, split across both repos:**
  - `ikeos` side computes/serves: `app/services/scheduler.py` (APScheduler cron), `app/services/driver.py` (spawns scheduled housekeeping sessions), `app/services/metrics.py`, `app/services/reflection.py`, `app/services/research_findings.py`, `app/services/reviews.py`.
  - `claude-config` side generates/stores the raw signal: `library/{metrics.json, weak-signals.json, research-*.json}` (mounted read-only into `ikeos` via `CLAUDE_CONFIG_PATH`), `evals/` (runner/judge/baselines — agent quality over time), `scripts/stophook-reflection.sh` (the hook that captures weak signals at session end).
- **Depends on:** Harness (the StopHook is wired via `claude-config` hook config) and Interface (renders the dashboards).
- **Must not:** Have `ikeos` write to `claude-config/library/*.json` directly — it's a read-only mount; the hook and eval runner are the only writers.

## 7. Known duplication / drift points (documented, not resolved)

- **Skills:** `ikeos/adapters/claude-code/skills/*.md` (portable, env-var driven) and `claude-config/global/commands/*.md` (deployed, hardcoded to this deployment's paths) are two independently-maintained copies of the same five skills (triage, housekeeping, promote, schema-check, close-session). Confirmed diverged as of 2026-08-19 — the deployed `triage.md` was found missing a `CLAUDE_CONFIG_DIR` fallback present in the adapter copy.
- **Session Manager:** `ikeos/adapters/claude-code/session-manager/` (reference) and `claude-config/services/session-manager/` (deployed) follow the same pattern. One prior sync effort exists (`.claude/DECISIONS.md`, 2026-07-22; `docs/superpowers/plans/2026-07-21-session-manager-adapter-sync.md`) — it documents a single sync event, not a standing process.
- **No tooling watches this boundary.** `claude-config/scripts/check-drift.sh` only diffs `claude-config/global/` against the deployed `~/.claude` — it has no awareness of `ikeos/adapters/` at all.
- Resolving this — choosing a sync direction, building drift detection, or physically consolidating — is a deferred follow-up decision. It is intentionally out of scope here.

## 8. Cross-links

- `README.md` links to this document from its architecture section.
- `CLAUDE.md` links to this document from its header block.
- `.claude/DECISIONS.md` records why this document was created.
````

- [ ] **Step 3: Verify the file was written correctly**

```bash
test -f docs/COMPONENT_MODEL.md && grep -c "^## " docs/COMPONENT_MODEL.md
```

Expected: `docs/COMPONENT_MODEL.md` exists and the heading count is `8`.

- [ ] **Step 4: Commit**

```bash
git add docs/COMPONENT_MODEL.md
git commit -m "docs: add canonical IkeOS component model

Maps Interface/Vault/Harness/Adapters/Self-Improvement across the
ikeos and claude-config repos, and documents the confirmed drift
between adapters/claude-code/ reference copies and claude-config's
deployed copies as an open, deliberately-deferred item."
```

---

## Task 2: Wire discoverability (README, CLAUDE.md, DECISIONS.md)

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `.claude/DECISIONS.md`

**Interfaces:**
- Consumes: `docs/COMPONENT_MODEL.md` from Task 1 (must exist at that exact path before this task's links are added).

- [ ] **Step 1: Find the exact insertion point in `README.md`**

```bash
grep -n "Claude Code adapter contract" README.md
```

This should print one line, e.g. `105:See [CLAUDE.md](CLAUDE.md) for the full architecture and Claude Code adapter contract.` — use the printed line's exact text as the anchor for Step 2 (the line number may differ from 105 if the file has changed).

- [ ] **Step 2: Add the README link**

Using the Edit tool, insert a new line immediately after the line found in Step 1, matching the surrounding style (a plain Markdown link sentence):

```markdown
See [docs/COMPONENT_MODEL.md](docs/COMPONENT_MODEL.md) for a map of every component in the IkeOS ecosystem — Interface, Vault, Harness, Adapters, and Self-Improvement — and how they relate.
```

- [ ] **Step 3: Add the CLAUDE.md link**

`CLAUDE.md`'s header currently reads:

```markdown
> This file is the IkeOS adapter configuration for Claude Code.
> It tells Claude Code how to operate within IkeOS principles.
> Read `PHILOSOPHY.md` before making architectural decisions.
> Before proposing changes, read `.claude/DECISIONS.md`.
```

Using the Edit tool, add one line to this block, immediately after the `PHILOSOPHY.md` line:

```markdown
> Read `docs/COMPONENT_MODEL.md` for how IkeOS's components (Interface, Vault, Harness, Adapters, Self-Improvement) fit together across repos.
```

- [ ] **Step 4: Add the `.claude/DECISIONS.md` entry**

`.claude/DECISIONS.md` is append-only — add this as a new entry at the end of the file (do not edit or reorder any existing entry):

```markdown
## 2026-08-19: Canonical component model documented at docs/COMPONENT_MODEL.md

Comparing IkeOS to an external colleague's static conventions/hooks repo surfaced that IkeOS itself had no single place documenting its own components, and that `adapters/claude-code/` (portable reference) and `claude-config` (deployed, hardcoded harness) had quietly diverged — confirmed by diffing `triage.md` in both locations, where the deployed copy was missing a `CLAUDE_CONFIG_DIR` fallback present in the adapter copy. `docs/COMPONENT_MODEL.md` now documents all five components (Interface, Vault, Harness, Adapters, Self-Improvement) and names this drift explicitly. Resolving the drift (sync direction, drift-detection tooling, or physical consolidation) is deliberately deferred to a future decision — this entry only records that the model now exists and the drift is a known, open item.
```

- [ ] **Step 5: Verify all three links/entries landed**

```bash
grep -n "COMPONENT_MODEL" README.md CLAUDE.md .claude/DECISIONS.md
```

Expected: one matching line printed for each of the three files.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md .claude/DECISIONS.md
git commit -m "docs: link the component model from README, CLAUDE.md, and DECISIONS.md"
```
