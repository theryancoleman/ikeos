# IkeOS Engineering Metrics Schema

_Status: Defined — not yet instrumented_
_Instrumentation phase: Session 4+_

---

## Why This Exists

"If it cannot be observed, it cannot be trusted." — IkeOS Philosophy

IkeOS has no current mechanism to verify its own quality. This schema defines what to measure and why. Instrumentation (write paths from agents, hooks, and the scheduler) follows in a later phase, once the schema is stable and validated against real questions.

Before implementing any metric, answer: **"What question does this answer, and would we act differently if the number changed?"** If the answer is no, the metric does not belong here.

---

## Storage Format

**Location:** `~/.claude/metrics/events.jsonl`

**Format:** JSON-lines — one JSON object per line, append-only.

```jsonl
{"timestamp": "2026-06-27T14:00:00Z", "event": "task.complete", "session_id": "abc123", "project": "ikeos", "task_size": "S", "duration_ms": 45000, "outcome": "success", "commit_sha": "abc1234"}
{"timestamp": "2026-06-27T14:05:00Z", "event": "verification.failure", "session_id": "abc123", "project": "ikeos", "stage": "health_check", "retry_count": 1, "error_summary": "container not healthy after rebuild"}
```

**Why JSON-lines:**
- Append-only (no locking, no transactions needed)
- Readable with `grep`, `jq`, Python — no tooling required
- Each line is self-contained (partial reads are safe)
- Works as a flat file forever; can be imported into SQLite when analysis needs grow

---

## Common Fields (all events)

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 string | When the event occurred (UTC) |
| `event` | string | Event type (see below) |
| `session_id` | string | Unique ID for the Claude Code session |
| `project` | string | Project slug (matches vault project slug) |

---

## Event Types

### `task.complete`

**Question answered:** Are tasks getting done, and how long do they take?

| Field | Type | Description |
|-------|------|-------------|
| `task_size` | `"S"` \| `"M"` \| `"L"` | Size classification from TASK.md |
| `duration_ms` | integer | Wall time from task start to commit; start time recorded when task is set to in-progress in TASK.md |
| `outcome` | `"success"` \| `"abandoned"` | Whether the task produced a commit |
| `commit_sha` | string \| null | Short SHA if committed, e.g., `"abc1234"` (minimum 7 chars, auto-expanded by git as repo grows) |
| `files_changed` | integer | Number of files in the commit |

---

### `verification.failure`

**Question answered:** Where do we fail most often, and are we improving?

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string (optional) | Task label from TASK.md for attribution, e.g. `"Task 3: Metrics schema"` |
| `stage` | `"build"` \| `"health_check"` \| `"tests"` \| `"lint"` | Verification stage where the failure occurred |
| `error_summary` | string | One-line description of the failure |
| `retry_count` | integer | How many times this verification was retried |
| `resolved` | boolean | Whether the failure was resolved in the same session |

---

### `deployment.attempt`

**Question answered:** How reliable is our deployment process?

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string (optional) | Task label from TASK.md for attribution, e.g. `"Task 3: Metrics schema"` |
| `service` | string | Docker service name |
| `outcome` | `"success"` \| `"failure"` | Result of `docker compose up --build` |
| `duration_ms` | integer | Time to deploy |
| `error_summary` | string \| null | Failure reason if outcome is failure |

---

### `housekeeping.run`

**Question answered:** Is the housekeeping scheduler actually working?

| Field | Type | Description |
|-------|------|-------------|
| `trigger` | `"scheduled"` \| `"manual"` | How the run was initiated |
| `tasks_run` | integer | Number of housekeeping tasks attempted |
| `tasks_succeeded` | integer | Tasks that completed without error |
| `tasks_failed` | integer | Tasks that failed or stalled |
| `duration_ms` | integer | Total run time |
| `stalled_on_permission` | boolean | Whether the run stalled on a Bash permission prompt |

---

### `session.end`

**Question answered:** How long do sessions run, and are they being closed cleanly?

| Field | Type | Description |
|-------|------|-------------|
| `duration_ms` | integer | Session wall time |
| `context_compacted` | boolean | Whether auto-compaction fired during the session |
| `closed_via_skill` | boolean | Whether `/close-session` was run (vs abrupt end) |
| `tasks_completed` | integer | Number of tasks marked done in this session |

---

### `agent.dispatch`

**Question answered:** Are subagents succeeding, and which task types fail most?

| Field | Type | Description |
|-------|------|-------------|
| `agent_type` | string | `"implementer"`, `"reviewer"`, `"debugger"`, etc. |
| `task_label` | string | Short description of what the agent was given |
| `outcome` | `"done"` \| `"done_with_concerns"` \| `"blocked"` \| `"needs_context"` | Agent's reported status |
| `duration_ms` | integer | Agent run time |
| `model` | string | Model used (e.g. `claude-sonnet-4-6`) |

---

### `manual.intervention`

**Question answered:** Where is the agent failing to work autonomously?

| Field | Type | Description |
|-------|------|-------------|
| `reason` | string | Why the human had to intervene, e.g. `"Agent kept referencing a non-existent file path"` |
| `context` | string | What the agent was doing when it needed help, e.g. `"Attempting Task 4, step 3: write failing test"` |
| `blocker_type` | string | `"permission"`, `"ambiguity"`, `"error"`, `"design_decision"` |

---

## Derived Signals

These are computed from raw events — not stored as events themselves.

| Signal | Derived from | Indicates |
|--------|-------------|-----------|
| Task completion rate | `task.complete` outcome | Are we shipping? |
| Verification failure rate | `verification.failure` per `task.complete` | Are we breaking things? |
| Housekeeping reliability | `tasks_succeeded / tasks_run` in `housekeeping.run` | Is the scheduler trustworthy? |
| Session clean-close rate | `closed_via_skill` in `session.end` | Are we reflecting? |
| Agent success rate | `done` / total in `agent.dispatch` | Are subagents effective? |
| Autonomous operation rate | `manual.intervention` per session | Is the platform getting more self-sufficient? |

---

## What Is Not Measured (and Why)

| Candidate | Decision | Reason |
|-----------|----------|--------|
| Lines of code added/removed | Rejected | Incentivises wrong behaviour; not correlated with quality |
| Number of commits | Rejected | Noisy; a sign of activity, not progress |
| Test coverage % | Deferred | Requires a consistent test runner; add when tests are more complete |
| Token usage per session | Deferred | Claude Code does not currently expose this directly |
