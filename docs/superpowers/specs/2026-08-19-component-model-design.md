# IkeOS Component Model — Design Spec

**Date:** 2026-08-19
**Status:** proposed
**Trigger:** Comparing IkeOS to a colleague's `agentharness` project (a static conventions/hooks repo) surfaced that IkeOS itself has no single place documenting what its own components are, where each lives, and how they relate. In particular, `ikeos/adapters/claude-code/` (a portable reference implementation) and `claude-config` (the deployed, hardcoded harness) had quietly diverged — confirmed by diffing `triage.md` in both locations — with no tooling watching that boundary.

---

## Purpose

Produce one canonical, purpose-sectioned document, `docs/COMPONENT_MODEL.md`, inside the `ikeos` repo, that:

1. Names and defines every component in the IkeOS ecosystem, across both `ikeos` and `claude-config` repos.
2. States what each component owns, what it depends on, and what it must never do.
3. Names the known duplication/drift points explicitly, so they're documented facts rather than tribal knowledge — without resolving them (that's an explicitly deferred follow-up).
4. Is discoverable from the existing entry-point docs (`README.md`, `CLAUDE.md`) and recorded as a decision in `.claude/DECISIONS.md`.

This is a **documentation-only** change. No code moves, no repo restructuring, no drift fixed. Physical consolidation of the duplicated pieces is an explicit future decision, not in scope here.

---

## Non-goals

- Do not merge `claude-config` into `ikeos` or move any files between repos.
- Do not fix the `triage.md` / session-manager drift found during research — only document that it exists.
- Do not build drift-detection tooling (e.g., extending `claude-config/scripts/check-drift.sh` to also watch `ikeos/adapters/`) — worth flagging as a candidate follow-up, not building now.

---

## Content of `docs/COMPONENT_MODEL.md`

### 1. Overview

One paragraph stating the five components and a one-line table mapping each to its owning repo/path:

| Component | Repo / Path |
|---|---|
| Interface | `ikeos/app/` |
| Vault | Obsidian vault filesystem (not code) |
| Harness | `claude-config/global/` → deployed to `~/.claude` |
| Adapters | `ikeos/adapters/claude-code/` |
| Self-Improvement | `ikeos/app/services/{scheduler,driver,metrics,reflection,research_findings,reviews}.py` + `claude-config/{library,evals}/` |

### 2. Interface

- **What it is:** The Flask web app — dashboard, vault browser, capture UI, housekeeping UI. The human-facing surface and "platform brain" per `CLAUDE.md`.
- **Where it lives:** `ikeos/app/` (routes/services/templates/static).
- **Depends on:** Vault (via `app/services/vault.py`, the sole file-I/O owner), Adapters (session driver client, capture API contract), Self-Improvement data (reads `claude-config/library/*.json` read-only via `CLAUDE_CONFIG_PATH` mount).
- **Must not:** Touch the filesystem outside `vault.py`; embed Claude-Code-specific (harness) logic — that belongs in Adapters.

### 3. Vault

- **What it is:** The Obsidian Markdown store — the storage layer (no DB, per `.claude/DECISIONS.md` 2026-05-26).
- **Where it lives:** Host filesystem, mounted read-write into `ikeos` via `VAULT_PATH`.
- **Depends on:** Nothing — it's the ground truth other components read/write against.
- **Must not:** Be written directly by agents — all writes go through the capture API (`POST /capture`, `PATCH /entries`), per the 2026-06-11 decision.

### 4. Harness

- **What it is:** The deployed Claude Code configuration that shapes agent behavior day to day — rules, slash-command skills, permission baseline, hooks wiring.
- **Where it lives:** `claude-config/global/` (commands, rules, settings.json), synced by `scripts/sync.sh apply` to the live `~/.claude` runtime directory. This is the actual analog to a project like `agentharness`.
- **Depends on:** Nothing IkeOS-specific in principle — most of `claude-config/global/commands/` (blog, deploy-cottage, wire-remote, etc.) has nothing to do with IkeOS at all. The subset that *is* IkeOS-specific (triage, housekeeping, promote, schema-check, close-session) is derived from Adapters (see §6).
- **Must not:** Be the only place an IkeOS-specific skill's logic exists — the portable version belongs in Adapters so IkeOS can be stood up elsewhere without this user's hardcoded paths.

### 5. Adapters

- **What it is:** The portable contract/reference-implementation connecting an external AI coding tool (currently Claude Code) to an IkeOS instance — env-var-driven skill definitions, a reference session-manager (Session Driver API), a reference StopHook script. This is what `PHILOSOPHY.md`'s "Adapter Principle" refers to: replaceable, defines the contract, not coupled to one deployment.
- **Where it lives:** `ikeos/adapters/claude-code/` (`skills/`, `session-manager/`, `hooks/`).
- **Depends on:** Documents the Session Driver API (`docs/SESSION_DRIVER_API.md`) that Interface also implements against.
- **Must not:** Contain this user's hardcoded paths (`C:\Server\...`, `localhost:5009` literals) — must stay env-var driven (`VAULT_PATH`, `IKEOS_URL`, `CLAUDE_CONFIG_DIR`) so it's usable as a template by anyone else deploying IkeOS.

### 6. Self-Improvement (the "utilities" layer)

- **What it is:** The housekeeping/reflection/metrics instrumentation that lets IkeOS observe and improve its own operation over time — distinct from Harness (which shapes behavior) and Interface (which displays state).
- **Where it lives, split across both repos:**
  - `ikeos` side computes/serves: `app/services/scheduler.py` (APScheduler cron), `driver.py` (spawns scheduled housekeeping sessions), `metrics.py`, `reflection.py`, `research_findings.py`, `reviews.py`.
  - `claude-config` side generates/stores the raw signal: `library/{metrics.json, weak-signals.json, research-*.json}` (mounted read-only into `ikeos` via `CLAUDE_CONFIG_PATH`), `evals/` (runner/judge/baselines — agent quality over time), `scripts/stophook-reflection.sh` (the hook that captures weak signals at session end).
- **Depends on:** Harness (the StopHook is wired via `claude-config` hook config) and Interface (renders the dashboards).
- **Must not:** Have `ikeos` write to `claude-config/library/*.json` directly — it's a read-only mount; the hook and eval runner are the only writers.

### 7. Known duplication / drift points (documented, not resolved)

State plainly, as facts:

- **Skills:** `ikeos/adapters/claude-code/skills/*.md` (portable, env-var driven) vs `claude-config/global/commands/*.md` (deployed, hardcoded to this user's paths) are two independently-maintained copies of the same five skills (triage, housekeeping, promote, schema-check, close-session). Confirmed diverged as of 2026-08-19 — the deployed `triage.md` is missing a `CLAUDE_CONFIG_DIR` fallback present in the adapter copy.
- **Session Manager:** `ikeos/adapters/claude-code/session-manager/` (reference) vs `claude-config/services/session-manager/` (deployed) — same pattern. One prior sync decision exists (`.claude/DECISIONS.md`, 2026-07-22) documenting a single sync event, not a standing process.
- **No tooling watches this boundary.** `claude-config/scripts/check-drift.sh` only diffs `claude-config/global/` against the deployed `~/.claude` — it has no awareness of `ikeos/adapters/` at all.
- Note explicitly: resolving this (choosing a sync direction, building drift detection, or physically consolidating) is a deferred follow-up decision, not part of this change.

### 8. Cross-links

- `README.md`: add one line near the existing `CLAUDE.md` architecture pointer (line ~105) referencing `docs/COMPONENT_MODEL.md` as the full ecosystem map.
- `CLAUDE.md`: add a pointer in the header block alongside the existing `PHILOSOPHY.md`/`DECISIONS.md` references.
- `.claude/DECISIONS.md`: append a dated entry recording that this document now exists, why (the agentharness comparison + confirmed drift), and that the duplication points are deliberately left unresolved pending a follow-up decision.

---

## Success Criteria

- `docs/COMPONENT_MODEL.md` exists with all 8 sections above, using real paths verified against the current repo state (not placeholders).
- `README.md` and `CLAUDE.md` both link to it.
- `.claude/DECISIONS.md` has a new dated entry.
- No files moved, no drift fixed, no new scripts written.
