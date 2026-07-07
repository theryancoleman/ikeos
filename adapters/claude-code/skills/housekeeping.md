---
name: housekeeping
description: Run the periodic housekeeping routine — discover vault tasks, run due ones as subagents, update vault state. Requires VAULT_PATH, IKEOS_URL, and CAPTURE_TOKEN environment variables.
---

# Housekeeping Routine

**Vault task path:** `$VAULT_PATH/projects/claude-config/housekeeping/`  
**Capture API:** `${IKEOS_URL:-http://localhost:5009}`  
**CAPTURE_TOKEN:** read from `$CAPTURE_TOKEN` environment variable  
**Schema reference:** See `adapters/claude-code/README.md` in the ikeos repo

---

## Phase 1: Discover and parse task entries

Write the following Python to `/tmp/hk_phase1.py` using the Write tool, then run `python3 /tmp/hk_phase1.py`. Do not run it as a heredoc or with `-c`.

```python
import glob, datetime, json, sys, os
from pathlib import Path

_vault = os.environ.get("VAULT_PATH", "")
if not _vault:
    print("Error: VAULT_PATH environment variable is not set.")
    print("Set it to the absolute path of your Obsidian vault root.")
    sys.exit(1)
VAULT_ROOT = Path(_vault)
THRESHOLDS = {"weekly": 6, "monthly": 27, "quarterly": 83, "annually": 364}

def parse_frontmatter(path):
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, ""
    end = text.index("---", 3)
    fm_raw = text[3:end].strip()
    body = text[end+3:].strip()
    fm = {}
    for line in fm_raw.split("\n"):
        if ": " in line:
            k, v = line.split(": ", 1)
            fm[k.strip()] = v.strip().strip("'\"")
    return fm, body

today = datetime.date.today()
tasks = []

for path in sorted(VAULT_ROOT.glob("projects/*/housekeeping/*.md")):
    if path.name == "last-run.md":
        continue
    fm, body = parse_frontmatter(path)
    if not fm or fm.get("type") != "housekeeping-task":
        continue
    if fm.get("enabled", "true").lower() != "true":
        continue

    last_run_str = fm.get("last_run", "null")
    last_run = None if last_run_str in ("null", "", None) else datetime.date.fromisoformat(last_run_str)
    interval = fm.get("interval", "weekly")
    threshold = THRESHOLDS.get(interval, 6)

    if last_run is None:
        is_due = True
        days_since = None
        warn_missing = interval in ("monthly", "quarterly", "annually")
    else:
        days_since = (today - last_run).days
        is_due = days_since >= threshold
        warn_missing = False

    tasks.append({
        "filename": path.name,
        "project": fm.get("project", "claude-config"),
        "title": fm.get("title", path.stem),
        "interval": interval,
        "last_run": str(last_run) if last_run else "never",
        "days_since": days_since,
        "is_due": is_due and not warn_missing,
        "warn_missing": warn_missing,
        "success_definition": fm.get("success_definition", ""),
        "instructions": body,
        "consecutive_failures": int(fm.get("consecutive_failures", "0") or "0"),
        "last_error": fm.get("last_error", "null"),
    })

if not tasks:
    print("\nNo housekeeping tasks found in vault.")
    print("Create entries via the IkeOS management page or:")
    print("  POST /capture with type=housekeeping-task in any projects/*/housekeeping/ folder")
    sys.exit(0)

# Print summary table
header = "{:<4} {:<42} {:<12} {:<14} {}".format("#", "Task", "Interval", "Last Run", "Status")
print("\n" + header)
print("─" * 85)
for i, t in enumerate(tasks, 1):
    if t["warn_missing"]:
        status = "WARN (no history)"
    elif t["is_due"]:
        status = "DUE"
    else:
        remaining = THRESHOLDS[t["interval"]] - (t["days_since"] or 0)
        status = f"in {remaining}d"
    title, interval, last_run = t["title"], t["interval"], t["last_run"]
    print(f"{i:<4} {title:<42} {interval:<12} {last_run:<14} {status}")

with open("/tmp/hk_tasks.json", "w") as f:
    json.dump(tasks, f, indent=2)
print("Task data written to /tmp/hk_tasks.json")
```

After running, read `/tmp/hk_tasks.json` with the Read tool to get the task list for subsequent phases.

---

## Phase 2: Determine run mode

**Single-task mode** (invoked by IkeOS with a slug argument — prompt contains `run <slug>`):
- Extract the slug from the prompt (the word immediately after `run`)
- Match it against each task's filename stem: strip the date prefix (`YYYY-MM-DD-`) and `.md` extension from the filename
- If no task matches the slug, print an error and stop
- Add the matched task to the run list regardless of `is_due` or `warn_missing` status
- Do not ask for user confirmation
- Skip Phase 3 entirely for this run
- Skip Phase 7 (heartbeat update) — single-task runs don't update the routine's overall heartbeat
- Phase 6 behaviour is identical to scheduled mode: advance `last_run` on pass, update `last_error`/`consecutive_failures` on fail

**Scheduled mode** (invoked by IkeOS session scheduler — the prompt will say "run in scheduled mode"):
- Tasks with `is_due: true` → add to run list automatically
- Tasks with `warn_missing: true` → skip and warn (Phase 3)
- Do not ask for user confirmation

**Manual mode** (invoked directly by the user — no "run in scheduled mode" and no slug argument):
- Display the table from Phase 1
- Prompt the user:

```
Which tasks would you like to run?
  • Enter numbers (e.g. "1 3") to run specific tasks — does not affect the schedule clock
  • Enter "due" to run all currently due tasks
  • Enter "none" to cancel

Selection:
```

Wait for the user's response. Build the run list accordingly.

If the user selects a task with `warn_missing: true`, add it to the run list and **skip the Phase 3 warning for that specific task** — the user has explicitly confirmed they intend to run it.

---

## Phase 3: Warn on missing state for long-interval tasks

For each task where `warn_missing: true`, write the following Python to `/tmp/hk_phase3_warn.py` (substituting `TASK_TITLE` and `INTERVAL` with actual values), then run `python3 /tmp/hk_phase3_warn.py`:

```python
import urllib.request, urllib.parse, os

_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")

data = urllib.parse.urlencode({
    "type": "bug",
    "project": "claude-config",
    "severity": "medium",
    "title": f"Housekeeping: cannot confirm if '{TASK_TITLE}' ({INTERVAL}) is due — no run history",
    "body": (
        f"The housekeeping routine found no last_run date for the {INTERVAL} task '{TASK_TITLE}'. "
        "This may indicate the first run ever or a loss of vault state. "
        "The task was skipped to avoid an unintended run. To run it deliberately: "
        "use /housekeeping (manual mode) and select it from the table, "
        "or use the IkeOS housekeeping management page to reset its timer."
    ),
}).encode()
urllib.request.urlopen(urllib.request.Request(f"{_ikeos_url}/capture", data=data))
```

---

## Phase 4: Execute each task in the run list

For each task in the run list, dispatch a **subagent** with this prompt (fill in the placeholders):

> You are executing a scheduled housekeeping task. Follow the instructions below exactly.
> 
> **Task:** $TASK_TITLE  
> **Success definition:** $SUCCESS_DEFINITION  
> 
> **Autonomous execution:** This is an automated, unattended run — no user is present. Do not ask for confirmation, approval, or user input at any point. If the task instructions say to create vault entries, create them directly. If an invoked skill asks "Would you like to...?" or "Shall I apply...?" or presents options for the user to choose from, skip the ask and execute the most autonomous action the task instructions permit. Complete all work without pausing for input.
> 
> **Instructions:**  
> $INSTRUCTIONS_FROM_VAULT_BODY  
> 
> When complete, return ONLY a JSON object on the final line of your response:  
> `{"status": "ok", "summary": "one sentence describing what was done"}`  
> or  
> `{"status": "error", "reason": "what failed and why"}`  
> No other trailing text.

Capture the subagent's **complete raw output** — this is `$SUBAGENT_FULL_OUTPUT`, the entire text response, and is what you pass to the judge in Phase 5. Also extract the final JSON line separately as `$SUBAGENT_STATUS_JSON` for your own bookkeeping.

---

## Phase 5: Judge each task result

For each completed subagent, dispatch a **judge subagent** with this prompt:

> You are evaluating whether a housekeeping task succeeded.
> 
> **Task:** $TASK_TITLE  
> **Success definition:** $SUCCESS_DEFINITION  
> **Task output:** $SUBAGENT_FULL_OUTPUT  
> *(This is the complete output from the task subagent — evaluate the entire response, not just the final status line.)*
> 
> Does the task output satisfy the success definition?  
> Return ONLY a JSON object:  
> `{"pass": true, "confidence": "high|medium|low"}`  
> or  
> `{"pass": false, "reason": "what is missing or wrong according to the success definition"}`

As you process each task, also maintain a `TASK_RESULTS` list to pass to Phase 7. Append one entry per task outcome:

- **Pass:** `{"name": "<task title>", "project": "<task project>", "outcome": "ok"}`
- **Fail:** `{"name": "<task title>", "project": "<task project>", "outcome": "failed", "error": "<judge reason>"}`
- **Skip (not due):** `{"name": "<task title>", "project": "<task project>", "outcome": "skipped"}`

---

## Phase 6: Update vault state

> **TOOL REQUIREMENT — READ FIRST:** Always use the **Write tool** to write these scripts to `/tmp/` files, then run them with `python3 /tmp/<file>.py`. **Never use `python3 << 'PYEOF'` bash heredoc syntax** — it triggers the security scanner and stalls the run. If you are updating multiple tasks, you may combine them into one script, but you MUST still write it with the Write tool first.

**On pass (`"pass": true`):**

Write the following Python to `/tmp/hk_phase6_pass.py` (substituting `TASK_PROJECT` and `TASK_FILENAME` from the task's `project` and `filename` fields), then run `python3 /tmp/hk_phase6_pass.py`:

```python
import urllib.request, json, os, datetime

token = os.environ.get("CAPTURE_TOKEN", "")
_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
payload = {
    "project": TASK_PROJECT,
    "type": "housekeeping-task",
    "filename": TASK_FILENAME,
    "fields": {"last_run": datetime.date.today().isoformat(), "last_error": "null", "consecutive_failures": 0},
}
req = urllib.request.Request(f"{_ikeos_url}/entries/housekeeping", method="PATCH")
req.add_header("X-Capture-Token", token)
req.add_header("Content-Type", "application/json")
req.data = json.dumps(payload).encode()
urllib.request.urlopen(req)
```

**On fail (`"pass": false`):**

Step 6a — update state: write the following Python to `/tmp/hk_phase6a.py` (substituting `TASK_PROJECT`, `TASK_FILENAME`, `JUDGE_REASON`, `CURRENT_CONSECUTIVE_FAILURES`), then run `python3 /tmp/hk_phase6a.py`:

```python
import urllib.request, json, os

token = os.environ.get("CAPTURE_TOKEN", "")
_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
failures = CURRENT_CONSECUTIVE_FAILURES + 1
payload = {
    "project": TASK_PROJECT,
    "type": "housekeeping-task",
    "filename": TASK_FILENAME,
    "fields": {"last_error": JUDGE_REASON, "consecutive_failures": failures},
}
req = urllib.request.Request(f"{_ikeos_url}/entries/housekeeping", method="PATCH")
req.add_header("X-Capture-Token", token)
req.add_header("Content-Type", "application/json")
req.data = json.dumps(payload).encode()
urllib.request.urlopen(req)
```

Step 6b — raise immediate bug entry: write the following Python to `/tmp/hk_phase6b.py` (substituting `TASK_TITLE`, `INTERVAL`, `JUDGE_REASON`, `failures` from step 6a, `SUCCESS_DEFINITION`), then run `python3 /tmp/hk_phase6b.py`:

```python
import urllib.request, urllib.parse, datetime, os

_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
today = datetime.date.today().isoformat()
body = (
    f"The {INTERVAL} housekeeping task '{TASK_TITLE}' failed on {today}.\n\n"
    f"Failure reason: {JUDGE_REASON}\n"
    f"Consecutive failures: {failures}\n"
    f"Success definition: {SUCCESS_DEFINITION}\n\n"
    "Run manually via /housekeeping (manual mode) or the IkeOS housekeeping management page."
)
data = urllib.parse.urlencode({
    "type": "bug",
    "project": "claude-config",
    "severity": "high",
    "title": f"Housekeeping task failed: {TASK_TITLE}",
    "body": body,
}).encode()
urllib.request.urlopen(urllib.request.Request(f"{_ikeos_url}/capture", data=data))
```

---

## Phase 7: Update heartbeat

> **Skip this phase in single-task mode.** Targeted force-runs do not update the routine's overall heartbeat — only full scheduled and manual runs do.

> **TOOL REQUIREMENT:** Use the **Write tool** to write each script below to a `/tmp/` file, then run it with `python3 /tmp/<file>.py`. Never use bash heredoc syntax — it triggers the security scanner.

The heartbeat always lives at `last-run.md` (the capture API creates it as a singleton without a date prefix). If it somehow doesn't exist, create it first — write the following Python to `/tmp/hk_phase7_check.py` and run `python3 /tmp/hk_phase7_check.py`:

```python
import urllib.request, urllib.parse, os
from pathlib import Path

_vault = os.environ.get("VAULT_PATH", "")
_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
heartbeat = Path(_vault) / "projects/claude-config/housekeeping/last-run.md" if _vault else Path("")
if not heartbeat.exists():
    data = urllib.parse.urlencode({
        "type": "housekeeping-heartbeat",
        "project": "claude-config",
        "title": "Housekeeping Last Run",
        "body": "Heartbeat entry updated automatically by the housekeeping routine after each run.",
    }).encode()
    urllib.request.urlopen(urllib.request.Request(f"{_ikeos_url}/capture", data=data))
```

Then update it — write the following Python to `/tmp/hk_phase7_update.py` (substituting `TASKS_RUN_COUNT`, `TASKS_FAILED_COUNT`, `TASKS_SKIPPED_COUNT`, and `TASK_RESULTS` with the actual values collected during Phase 5), then run `python3 /tmp/hk_phase7_update.py`:

```python
import urllib.request, json, os, datetime

token = os.environ.get("CAPTURE_TOKEN", "")
_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
payload = {
    "project": "claude-config",
    "type": "housekeeping-heartbeat",
    "filename": "last-run.md",
    "fields": {
        "last_run": now,
        "tasks_run": TASKS_RUN_COUNT,
        "tasks_failed": TASKS_FAILED_COUNT,
        "tasks_skipped": TASKS_SKIPPED_COUNT,
        "task_results": TASK_RESULTS,
    },
}
req = urllib.request.Request(f"{_ikeos_url}/entries/housekeeping", method="PATCH")
req.add_header("X-Capture-Token", token)
req.add_header("Content-Type", "application/json")
req.data = json.dumps(payload).encode()
urllib.request.urlopen(req)
```

---

## Phase 8: Report

Print a summary:

```
Housekeeping run complete — YYYY-MM-DD

  ✓  Research cycle (weekly)
  ✓  Vault schema check (weekly)
  ✗  Weak signals review (weekly) — FAILED: [reason from judge]
  —  Skills audit (monthly) — not due (in 14d)
  ⚠  Memory consolidation (monthly) — skipped, no run history

Tasks run: 3   Passed: 2   Failed: 1
Tasks skipped (not due): 1
Tasks warned (no history): 1
```

> **Consistency check:** The ✓/✗/— symbols in this Phase 8 report must match the `outcome` values in `TASK_RESULTS` sent in Phase 7. A task that shows ✗ here must have `"outcome": "failed"` in TASK_RESULTS, and vice versa.
