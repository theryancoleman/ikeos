# AIOS Engineering Standard

**Version:** 1.0 — July 2026
**Audience:** AI coding agents (Claude Code) and human engineers working in AIOS projects.

---

## 1. Introduction

This document defines the engineering standard for AIOS projects — software built through human-AI collaborative development. It is inspired by Robert C. Martin's *Clean Code* (2008) but evolved for a world where AI agents write the majority of implementation code. Clean Code taught us that code is read far more often than it is written; AIOS engineering adds a second reader — the AI agent — whose ability to navigate, reason about, and correctly modify code depends on structural clarity at least as much as a human's does. These are opinionated, prescriptive rules. When a rule conflicts with a clever solution, follow the rule. The clever solution is probably a future maintenance burden for both you and every agent that comes after.

---

## 2. Naming

Names are the primary interface between human intent and machine execution. A name should state what a thing does or holds, without requiring the reader to look at its implementation.

**Rules:**
- Python: `snake_case` for everything except classes (`PascalCase`).
- URLs and slugs: `kebab-case`. Never `snake_case` in URLs (`/vault-graph`, not `/vault_graph`).
- Boolean functions: prefix with `is_` or `has_` (e.g., `is_enabled`, `_reject_path_traversal`).
- No single-letter variables outside comprehensions. No `tmp`, `res`, `val`, `obj`.
- Abbreviations only when universally understood (`url`, `id`, `ts`) — never project-local shorthand.
- **AI searchability:** Names must survive a grep or semantic search. Functions named after their behavior (`update_entry_status_generic`) are findable; functions named after their position (`handler2`, `process_it`) are not.

**Example from IkeOS** — `_reject_path_traversal(filename)` in `capture.py`: the name tells you what it checks, what it rejects, and what it protects against, before you read a single line of body.

---

## 3. Function Design

Every function does one thing and does it completely. If you cannot describe what a function does in one sentence without using "and", split it.

**Rules:**
- ~20 lines of logic max. Comments and blank lines do not count toward the limit, but they often indicate the function is already too large.
- Use keyword-only arguments when a function takes three or more parameters: `def func(*, name, status, project)`.
- Return values, never mutate arguments.
- Services must be pure Python: no `request`, `g`, or `current_app`. If a service function imports from Flask, it belongs in a route.

**Thin-route pattern from IkeOS** — `capture.patch_entries()` in `app/routes/capture.py`:

```python
token = request.headers.get("X-Capture-Token", "")
is_valid, status_code = _validate_token(token)
if not is_valid:
    return jsonify({"error": "..."}), status_code
# ...
success = update_entry_status_generic(entry_type, project, filename, status)
if not success:
    return jsonify({"error": "Entry not found or invalid status"}), 404
return jsonify({"message": "Status updated"}), 200
```

The route parses the request, delegates all work to `_validate_token` and `update_entry_status_generic`, and returns the result. No business logic lives here.

---

## 4. File and Module Organization

A file is a unit of responsibility. When a file's imports or public API spans multiple unrelated concerns, split it.

**Rules:**
- One responsibility per file. If the filename requires "and" to describe it, split.
- Flat over nested: prefer `app/services/vault_entries.py` over `app/services/vault/entries.py` unless the package grows beyond five cohesive files.
- Layer separation is non-negotiable: routes call services; services call queries/storage; nothing calls upward.
- Keep `__init__.py` files thin — app factory wiring only, no logic.

**Decomposition example from IkeOS:** `vault.py` grew to encompass projects, entries, graph traversal, housekeeping, and a cache layer. It was split into `vault_cache.py`, `vault_projects.py`, `vault_entries.py`, `vault_graph.py`, and `vault_housekeeping.py`. The original `vault.py` now re-exports everything for backward compatibility — existing callers required no changes. This is the correct decomposition pattern: split by responsibility, preserve the public surface.

---

## 5. Comments and Documentation

A comment should explain *why*, never *what*. If the code needs a comment to explain what it does, the code is the problem.

**Rules:**
- Write a comment when the reader could not infer the decision from the code alone: a non-obvious constraint, a workaround for external behavior, a performance choice.
- Never restate the code: `# Increment counter` above `count += 1` is noise.
- No multi-line docstrings for internal functions. A one-line summary is enough if needed.
- No task IDs, PR references, or author names in code comments. That information belongs in git history.
- No commented-out code. Delete it; git remembers.

**Smell test:** Cover the comment with your hand. If the code below it is immediately obvious without the comment, delete the comment.

**Good example from IkeOS** — `vault_entries.py`, the singleton heartbeat file:

```python
filepath = target_dir / "last-run.md"  # singleton — fixed name, no date prefix
```

This comment explains *why* the filename is hardcoded, a decision that would otherwise look like an oversight.

---

## 6. Error Handling

Errors are expected cases, not surprises. Handle them explicitly at the layer where they can be meaningfully resolved.

**Rules:**
- Never use bare `except:`. Always catch a specific type; use `except Exception` only at system boundaries.
- Never swallow exceptions silently (`except: pass` is a bug waiting to surface in production).
- Use `logger.exception("message")` inside `except` blocks — it captures the full traceback without you re-raising.
- Validate inputs at the route layer. Trust internal service functions not to receive invalid data.
- Return typed results (booleans, `None`, typed dicts) from services; let routes map failures to HTTP status codes.

**Pattern from IkeOS** — `capabilities.py`:

```python
except (OSError, json.JSONDecodeError, ValueError):
    logger.exception("Failed to read capabilities from %s", path)
    return result
```

Specific exception types, structured log with context (the file path), and a safe fallback return. The caller never sees an exception; it sees the default capability state.

---

## 7. Testing

Tests are specifications. A test that breaks tells you what behavior changed, not just that something is wrong.

**Rules:**
- pytest only. No unittest subclasses.
- One logical assertion cluster per test. Test one behavior, assert one outcome — multiple `assert` statements are fine if they all verify the same behavior.
- Test names describe behavior: `test_write_entry_sets_status_new`, not `test_write_entry_1`.
- Never use the real vault in tests. Always patch `VAULT_PATH` to `tmp_path`.
- Fixture scope: use function-scope by default; only widen scope when the setup cost is measurably significant.

**Pattern from IkeOS** — `tests/test_vault_entries.py`:

```python
def test_write_entry_sets_status_new(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({"type": "note", "project": "myproj", "title": "Test", "body": ""})
    files = list((tmp_path / "projects" / "myproj" / "notes").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["status"] == "new"
```

Isolated, behavior-named, no real filesystem side effects.

---

## 8. Observability

Code that runs invisibly is code you cannot debug. Observability is not optional.

**Rules:**
- Use `logging`, never `print()`. Configure at the app factory with a consistent format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`.
- Log messages must include structured context: `logger.warning("Failed to write metrics event %s to %s", event_type, METRICS_PATH)` — not `logger.warning("Write failed")`.
- Metrics go to `events.jsonl` via `append_event()` in `metrics.py`. Each event has `event`, `timestamp`, and payload keys. This is the observability layer, not `print()`.
- The `/health` endpoint returns `"ok", 200` and nothing else. It is a liveness probe, not a diagnostics dump.
- Fire-and-forget metric emission: wrap `append_event()` in a try/except at the call site. A metrics write failure must never fail a business operation.

**Pattern from IkeOS** — `capabilities.py` calls `append_event` after a capability change, wrapped in a `try/except` with `logger.warning` on failure. The capability update succeeds regardless.

---

## 9. Configuration

All runtime behavior that varies between environments is configuration. Configuration lives in the environment, not in source files.

**Rules:**
- Every secret, URL, file path, and toggle is an environment variable. No exceptions.
- `.env` is always in `.gitignore`. Commit `.env.example` with placeholder values and a comment explaining each variable.
- Never hardcode `localhost`, port numbers, file paths, tokens, or service URLs in source files.
- Access environment variables at the service boundary: `os.environ.get("VAULT_PATH", "/vault")`. Don't thread `os.environ` calls through multiple layers.

**Pattern from IkeOS** — `.env.example` documents every variable with intent:

```
# Token protecting vault mutation endpoints (POST /capture, PATCH /entries)
# Use any secret string — treat it like a password
CAPTURE_TOKEN=your-capture-token-here
```

Each entry has a placeholder value and a comment explaining what it does and what constraints apply.

---

## 10. Security

Security is enforced at system boundaries — entry points where untrusted data enters the system. Internal code trusts that boundaries have been enforced.

**Rules:**
- Validate all user-supplied input at route handlers. Reject before processing.
- Reject path traversal on any user-supplied filename: check for `..`, `/`, `\` before using the value in a file path.
- Sanitize before rendering in Jinja2 templates. Use `|e` for untrusted strings; never use `|safe` on user-supplied content.
- Never log secrets, tokens, or passwords — not even partial values.
- Mutation endpoints require `X-Capture-Token` header validation. Read operations are unauthenticated.
- Docker containers run as non-root users. Mount secrets as read-only volumes (`ro`) where the container does not need to write.

**Pattern from IkeOS** — `_reject_path_traversal(filename)` in `capture.py` is called before any file operation involving a user-supplied filename. `_validate_token(token)` is called at the top of every mutation handler before any work is done.

---

## 11. Refactoring

Refactoring is behavior-preserving restructuring. It is not the same as rewriting, and it does not happen in the same commit as feature work.

**Rules:**
- Boy Scout Rule: leave the code you touch cleaner than you found it — one small improvement per visit.
- Never refactor during a feature or bug fix task. Separate commits, separate intent.
- Refactoring requires an existing test suite that passes before and after. If tests don't exist, write them first (a separate commit).
- Incremental: change one thing at a time. Large-batch refactors are hard to review and easy to break.
- When to refactor: when the same logic appears in three places, when a file exceeds its single responsibility, when a function name no longer matches what the function does.
- When to leave it: when the code works, tests pass, and the change would only satisfy aesthetic preference with no functional improvement.

---

## 12. AI-Native Engineering

This section has no equivalent in *Clean Code* (2008). It addresses constraints and failure modes that emerge when AI agents are primary implementers.

### Prompt quality
A prompt is a function call. Treat it as one: clear scope, explicit constraints, one task per invocation. "Improve the dashboard" is not a task; "add a widget showing the last housekeeping run time to the dashboard's top row" is. Vague prompts produce code that satisfies none of the implicit requirements and all of the explicit ones.

### Agent responsibility boundaries
Agents are like functions: one job, clear inputs and outputs, no side effects outside defined scope. An agent asked to fix a bug in `capture.py` should not refactor `vault.py` in the same response. Scope creep by agents is a review hazard — changed lines that were not requested are lines that were not verified.

### Context management
The context window is finite and degrades at the edges. Keep it clean: use skill files and tool contracts rather than embedding long instructions inline. Use subagents for isolation — a fresh context for each task prevents state from one task contaminating the next.

### Tool contracts
Tools (services, adapters, API clients) have explicit interfaces. Callers check return values. A function that returns `bool` must never raise on failure — the caller is not prepared to handle it. `append_event()` in `metrics.py` returns `False` on write failure; callers that ignore the return value are correct not to crash.

### Memory usage
Memory files hold user/project context: preferences, recurring patterns, known constraints. They do not hold architecture snapshots, implementation decisions, or code examples. Architecture decisions go in `.claude/DECISIONS.md`; durable knowledge goes in the vault via the capture API.

### Safety gates
Autonomous capabilities default to disabled. No agent-triggered action that creates side effects outside the current session should be enabled without explicit human action. IkeOS implements this with `capabilities.py`: `is_enabled("housekeeping_scheduler")` returns `False` until a human enables it. This is the correct pattern for any capability that interacts with external systems.

### Fire-and-forget pattern
Metric emission and cross-service notifications must not block critical paths. Wrap them in `try/except`, log on failure, and continue. A housekeeping heartbeat write failing should not abort the housekeeping run.

### Verification before completion
An agent that writes code without verifying the result has not finished the task — it has finished the typing. Verification means: run the tests, restart the service, observe the behavior. An implementation is complete only when the verification contract has been executed and passed.

---

## 13. Code Review

Code review is a quality gate, not a style debate. The reviewer's job is to find correctness issues, security gaps, and maintainability problems — not to impose preferences.

**What to look for (in priority order):**
1. **Correctness:** Does it do what was asked? Does it handle edge cases? Does it break existing behavior?
2. **Security:** Untrusted input reaching file paths, SQL, or templates? Secrets in logs? Missing auth checks?
3. **Simplicity:** Could this be half as long with the same result? Is an abstraction being introduced prematurely?
4. **Maintainability:** Does it follow layer separation? Are names clear? Will the next agent be able to understand it without reading three other files?

**How to report findings — the three tiers:**
- **Now:** Must fix before merge. Correctness or security issue. Cite file:line, explain why it matters, provide a suggested fix.
- **Soon:** Should fix in a follow-up task. Maintainability or clarity issue that will compound if left.
- **Later:** Optional improvement. Note it, do not block.

**What not to flag:** Style preferences with no functional impact. Hypothetical future issues that have no evidence of occurring. Personal taste about variable names that already meet the naming rules in this document.

---

## 14. Implementation Roadmap

This standard is a foundation. The following phases integrate it into the AIOS engineering workflow:

| Phase | Action | Owner |
|---|---|---|
| 1 | Publish this document to `docs/engineering/` | Done |
| 2 | Build a code-review skill in `skills_registry.yaml` that references this standard | Engineering |
| 3 | Update agent instructions in `claude-config` to cite this document at session start | Config |
| 4 | Run a full review of the IkeOS codebase against this standard | Agent |
| 5 | Fix all Now-tier findings from Phase 4 | Engineering |
| 6 | Add a review step to the PR workflow: every M/L task gets a review pass against this standard before merge | Process |

The standard is a living document. When a new pattern is established through repeated use, add it here. When a rule is found to cause more harm than good in practice, revise it. The goal is code that agents and humans can read, modify, and trust.
