# IkeOS Engineering Experiment Framework

_Status: Format defined — vault entry type pending_

---

## Why This Exists

"Reflection transforms experience into knowledge." — IkeOS Philosophy

Not every decision IkeOS makes is obvious. Some are bets: we hypothesise that X will work, we try it, and we find out. Without a format to capture the hypothesis, measurement, and outcome, the lesson dissolves. We make the same bet again, or we never revisit a decision that deserved reconsideration.

The experiment framework makes bets explicit, measurements honest, and decisions durable.

---

## When to Use an Experiment

An experiment is appropriate when:
- The right answer is genuinely uncertain before trying
- There is a measurable signal that would distinguish success from failure
- The outcome would change future decisions if it went the other way

An experiment is NOT appropriate for:
- Decisions with an obvious correct answer
- Pure preference choices (style, naming) with no measurable outcome
- Decisions that cannot be reversed — commit to those as decisions, not experiments

---

## Format

Experiments live as vault entries with `type: experiment`. Frontmatter holds the structured fields; the body holds narrative context.

### Frontmatter schema

```yaml
---
type: experiment
title: "One sentence describing the bet"
hypothesis: "If we do X, then Y will happen"
expected_outcome: "Specific, measurable result if the hypothesis is correct"
measurement: "How we will know — what we will observe or measure"
success_criteria: "The threshold that counts as success"
timebox: "How long we will run before deciding"
status: running   # running | complete | abandoned
result: ""        # fill in when complete
decision: ""      # adopt | reject | pivot — fill in when complete
project: project-slug
created: 'YYYY-MM-DDTHH:MM:SS'
---
```

### Body template

```markdown
## Context

Why this experiment was started. What problem or uncertainty prompted it.

## What we tried

Brief description of the implementation or change made.

## What we observed

Actual measurements, log excerpts, or user feedback. Specific, not vague.

## Decision rationale

Why we chose to adopt, reject, or pivot — based on what we observed.
```

---

## Example: In-Memory Cache for Vault Reads

_Retrospective — this experiment was run and decided in June 2026._

```yaml
---
type: experiment
title: "Global in-memory cache for vault reads on WSL2"
hypothesis: "If we cache all vault entries in-process with a 10-minute TTL, page load times will drop below 200ms on WSL2"
expected_outcome: "Per-project page loads under 200ms after first cache warm-up"
measurement: "Browser DevTools network timing for /projects/<slug> — cold vs warm cache"
success_criteria: "Warm-cache response under 200ms; cold-cache miss under 2000ms"
timebox: "One session — measure during implementation"
status: complete
result: "Cold-cache miss: ~1.1s (scans all entries). Warm-cache hit: <50ms. Both within criteria."
decision: adopt
project: ikeos
created: '2026-06-13T00:00:00'
---
```

**Context**

WSL2 bind-mounts incur a ~20× I/O penalty vs native Linux. With 174+ vault entries, per-project reads were taking ~1.1s on cold load — noticeable on every navigation.

**What we tried**

Changed `read_entries()` to always populate a global `_entries_cache` on miss, then filter in-memory for per-project requests. Cache TTL: 10 minutes. Writes call `_invalidate_cache()`.

**What we observed**

Cold-cache miss (first request after invalidation): ~1.1s — acceptable for the vault size and miss frequency. Warm-cache hit: <50ms. The tradeoff: a cold miss now scans all entries instead of just one project's files. In practice, cache warm-up happens on first page load and persists for the session.

**Decision rationale**

Adopted. The tradeoff is well-understood, documented in DECISIONS.md, and the warm-cache performance justifies it. Cache invalidation on writes prevents stale reads. The constraint (WSL2 bind-mount penalty) is environmental, not architectural — this is the right mitigation given the constraint.

---

## Vault Integration (Deferred)

Adding `experiment` as a first-class vault entry type requires:
1. Adding `"experiment"` to `VALID_TYPES` and `TYPE_FOLDERS` in `vault.py`
2. Creating an `experiments/` folder in the project vault directory
3. Adding an experiment capture form or API endpoint

This is deferred to Session 4+. Until then, experiments can be written as `notes/` entries with `type: experiment` in the body, or as Markdown files in `docs/`.
