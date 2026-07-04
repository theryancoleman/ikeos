# Phase 2 — adapters/claude-code/ Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rotate the CAPTURE_TOKEN (security gate), then extract the IkeOS-coupled Claude Code skills and session-manager service into `adapters/claude-code/` inside the ikeos repo, fully parameterized so any user can deploy them by setting five env vars.

**Architecture:** All hardcoded homelab paths (`/mnt/c/Server/obsidian-vault`, `http://localhost:5009`, `/mnt/c/Server/claude-config/library`, personal IPs) become env vars read at runtime. The session-manager is copied verbatim except for one sanitization. The five skills and stophook are copied and updated in-place. An `adapters/claude-code/.env.example` documents every configurable value.

**Tech Stack:** Python 3.11, Flask, bash, Claude Code `~/.claude/commands/` skill format, tmux, Docker.

**Env vars contract (IKEOS_URL · CAPTURE_TOKEN · VAULT_PATH · CLAUDE_CONFIG_DIR · BLOG_NOTES_DIR):**
| Var | Purpose | Required |
|-----|---------|---------|
| `IKEOS_URL` | IkeOS capture API base URL | Yes (default `http://localhost:5009`) |
| `CAPTURE_TOKEN` | Auth token for mutation endpoints | Yes |
| `VAULT_PATH` | Absolute path to the Obsidian vault root | Yes |
| `CLAUDE_CONFIG_DIR` | Path to the directory containing `library/weak-signals.json` | No (disables reflection features if unset) |
| `BLOG_NOTES_DIR` | Path to blog weekly-notes directory | No (disables blog capture in close-session if unset) |

Session-manager env vars (set in `adapters/claude-code/session-manager/.env`):
| Var | Purpose |
|-----|---------|
| `PORT` | Listen port (default 5010) |
| `IKEOS_METRICS_URL` | IkeOS `/metrics/event` endpoint (optional) |
| `IKEOS_CAPTURE_TOKEN` | Token for IkeOS metrics posts (optional) |
| `PROTECTED_CONTAINERS` | Comma-separated container names to protect (optional) |
| `INFRASTRUCTURE_MACHINES` | JSON array `[{"name":"...","host":"..."}]` (optional, default `[]`) |

---

## File Map

**New files (all under `adapters/claude-code/`):**
- `adapters/claude-code/README.md` — install + configuration guide
- `adapters/claude-code/.env.example` — all vars with explanations
- `adapters/claude-code/session-manager/app.py` — copy of `claude-config/services/session-manager/app.py`, with `INFRASTRUCTURE_MACHINES` list replaced by env-driven load
- `adapters/claude-code/session-manager/sessions.py` — copy verbatim
- `adapters/claude-code/session-manager/tmux.py` — copy verbatim
- `adapters/claude-code/session-manager/pane_parser.py` — copy verbatim
- `adapters/claude-code/session-manager/requirements.txt` — copy verbatim
- `adapters/claude-code/session-manager/start.sh` — copy verbatim
- `adapters/claude-code/session-manager/.env.example` — clean example
- `adapters/claude-code/session-manager/.gitignore` — ensure `.env` is listed
- `adapters/claude-code/session-manager/tests/` — copy all test files verbatim
- `adapters/claude-code/skills/housekeeping.md` — copy + parameterize
- `adapters/claude-code/skills/triage.md` — copy + parameterize
- `adapters/claude-code/skills/close-session.md` — copy + parameterize
- `adapters/claude-code/skills/schema-check.md` — copy + parameterize
- `adapters/claude-code/skills/promote.md` — copy + parameterize (minimal changes)
- `adapters/claude-code/hooks/stophook-reflection.sh` — copy + parameterize

**Modified files (ikeos repo):**
- `ikeos/.env` — rotate CAPTURE_TOKEN value (security gate, Task 0)
- `ikeos/.claude/DECISIONS.md` — append extraction decision

---

## Task 0: Token Rotation (Security Gate)

**Goal:** Invalidate the current CAPTURE_TOKEN before any public content is committed.

**Files:** `/mnt/c/Server/projects/ikeos/.env`, `/mnt/c/Server/claude-config/services/session-manager/.env`

- [x] **Step 1: Generate a new 48-character token**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(36))"
```

Copy the output. This is `NEW_TOKEN`.

- [x] **Step 2: Update ikeos .env**

Read `/mnt/c/Server/projects/ikeos/.env`, find the `CAPTURE_TOKEN=` line, replace the value with `NEW_TOKEN`. Save using the Edit tool. Ensure the line has no trailing `\r` (use Unix line endings only on this line — it was causing gunicorn to reject the header).

- [x] **Step 3: Update session-manager .env**

Read `/mnt/c/Server/claude-config/services/session-manager/.env`, find `IKEOS_CAPTURE_TOKEN=`, replace value with `NEW_TOKEN`. Save.

- [x] **Step 4: Restart ikeos container**

```bash
docker.exe compose -f /mnt/c/Server/projects/ikeos/docker-compose.yml up --build -d ikeos
```

Wait for container to be healthy:
```bash
docker.exe ps --filter name=ikeos --format "{{.Status}}"
```
Expected: `Up ... (healthy)`

- [x] **Step 5: Restart session-manager**

The session-manager runs as a bare Python process in a tmux pane. Find and restart it:
```bash
tmux ls 2>/dev/null
```
Identify the session-manager pane (look for a session running `python3 app.py` or `start.sh`). Restart it:
```bash
tmux send-keys -t <session-name> "C-c" Enter
tmux send-keys -t <session-name> "bash /mnt/c/Server/claude-config/services/session-manager/start.sh" Enter
```

- [x] **Step 6: Verify PATCH /entries works with new token**

```bash
NEW_TOKEN=$(grep CAPTURE_TOKEN /mnt/c/Server/projects/ikeos/.env | cut -d= -f2 | tr -d '\r')
curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $NEW_TOKEN" \
  -d "project=ikeos" -d "type=note" \
  -d "filename=2026-07-03-driver-consolidation-complete-resumption-context-f.md" \
  -d "status=open"
```

Expected: `{"message":"Status updated"}` (200). If 401: the container didn't pick up the new token — check docker logs.

- [x] **Step 7: Sweep ikeos git history for old token**

```bash
OLD_TOKEN=<the token that was in ikeos/.env BEFORE this task>
git -C /mnt/c/Server/projects/ikeos log --all --oneline | wc -l
git -C /mnt/c/Server/projects/ikeos log -p --all --source -- . | grep -c "$OLD_TOKEN" || echo "0 matches"
```

Expected: 0 matches. If any found: stop and report — the history needs BFG/filter-repo cleanup before extraction.

- [x] **Step 8: Sweep claude-config git history for old token**

```bash
OLD_TOKEN=<same old token>
git -C /mnt/c/Server/claude-config log -p --all --source -- . | grep -c "$OLD_TOKEN" || echo "0 matches"
```

Expected: 0 matches.

- [x] **Step 9: Update claude-config vault entry to done**

```bash
CAPTURE_TOKEN=$(grep CAPTURE_TOKEN /mnt/c/Server/projects/ikeos/.env | cut -d= -f2 | tr -d '\r')
curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=claude-config" -d "type=idea" \
  -d "filename=2026-07-02-rotate-ikeos-capture-token-and-sweep-repo-historie.md" \
  -d "status=done"
```

Expected: `{"message":"Status updated"}`

- [x] **Step 10: Commit ikeos .env change (NO — .env is gitignored)**

`.env` is gitignored. Nothing to commit for Task 0. Verify:
```bash
git -C /mnt/c/Server/projects/ikeos status
```
Expected: no `.env` in the output.

---

## Task 1: Scaffold adapters/claude-code/ + Session-Manager Files

**Goal:** Create the directory tree and copy the session-manager service, sanitizing the one hardcoded infrastructure list.

**Files (create):** `adapters/claude-code/session-manager/` — all files listed in File Map above

- [x] **Step 1: Create directory structure**

```bash
mkdir -p /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tests
mkdir -p /mnt/c/Server/projects/ikeos/adapters/claude-code/skills
mkdir -p /mnt/c/Server/projects/ikeos/adapters/claude-code/hooks
```

- [x] **Step 2: Read session-manager app.py**

Read `/mnt/c/Server/claude-config/services/session-manager/app.py` in full.

- [x] **Step 3: Write sanitized app.py**

Write `adapters/claude-code/session-manager/app.py`. The content is identical to the source **except** replace the hardcoded `INFRASTRUCTURE_MACHINES` block (lines ~181–184):

```python
# BEFORE (remove this):
INFRASTRUCTURE_MACHINES = [
    {"name": "home-server", "host": "192.168.1.77"},
    {"name": "cottage",     "host": "100.74.204.42"},
]
```

Replace with:

```python
def _load_infrastructure_machines() -> list:
    """Load infrastructure machines from INFRASTRUCTURE_MACHINES env var (JSON array)."""
    raw = os.environ.get("INFRASTRUCTURE_MACHINES", "[]")
    try:
        machines = json.loads(raw)
        if not isinstance(machines, list):
            return []
        return [m for m in machines if isinstance(m, dict) and "name" in m and "host" in m]
    except json.JSONDecodeError:
        return []

INFRASTRUCTURE_MACHINES = _load_infrastructure_machines()
```

All other lines are copied exactly. No other changes.

- [x] **Step 4: Copy remaining session-manager files verbatim**

```bash
cp /mnt/c/Server/claude-config/services/session-manager/sessions.py \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/sessions.py
cp /mnt/c/Server/claude-config/services/session-manager/tmux.py \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tmux.py
cp /mnt/c/Server/claude-config/services/session-manager/pane_parser.py \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/pane_parser.py
cp /mnt/c/Server/claude-config/services/session-manager/requirements.txt \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/requirements.txt
cp /mnt/c/Server/claude-config/services/session-manager/start.sh \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/start.sh
cp /mnt/c/Server/claude-config/services/session-manager/tests/__init__.py \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tests/__init__.py 2>/dev/null || true
cp /mnt/c/Server/claude-config/services/session-manager/tests/test_app.py \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tests/test_app.py
cp /mnt/c/Server/claude-config/services/session-manager/tests/test_pane_parser.py \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tests/test_pane_parser.py
cp /mnt/c/Server/claude-config/services/session-manager/tests/test_sessions.py \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tests/test_sessions.py
cp /mnt/c/Server/claude-config/services/session-manager/tests/test_tmux.py \
   /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tests/test_tmux.py
```

- [x] **Step 5: Write session-manager .env.example**

Write `adapters/claude-code/session-manager/.env.example`:

```
# Session Manager Configuration
# Copy this to .env and fill in your values.

# Flask listen port (default: 5010)
PORT=5010

# Optional: IkeOS metrics integration
# Set both to enable session.created/removed events in the /metrics view.
IKEOS_METRICS_URL=http://localhost:5009/metrics/event
IKEOS_CAPTURE_TOKEN=your-capture-token-here

# Optional: containers that cannot be restarted or stopped via the API
PROTECTED_CONTAINERS=

# Optional: JSON array of SSH-reachable machines shown in the IkeOS infrastructure panel
# Example: [{"name":"homelab","host":"192.168.1.100"},{"name":"vps","host":"10.0.0.1"}]
INFRASTRUCTURE_MACHINES=[]
```

- [x] **Step 6: Write session-manager .gitignore**

Write `adapters/claude-code/session-manager/.gitignore`:

```
.env
__pycache__/
*.pyc
*.pyo
.pytest_cache/
```

- [x] **Step 7: Run session-manager tests against the sanitized copy**

The tests run against the source tree, not the destination. Since the session-manager imports use relative imports (no package), the tests must run from within the adapter directory:

```bash
cd /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager
pip install -r requirements.txt -q
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All tests pass (same as source). If any test fails due to `INFRASTRUCTURE_MACHINES` change, fix the test to patch the env var instead of the global.

- [x] **Step 8: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add adapters/claude-code/session-manager/
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add adapters/claude-code/session-manager — reference driver implementation

Copied from claude-config services/session-manager. Infrastructure machines list
replaced by INFRASTRUCTURE_MACHINES env var (JSON array) to remove personal homelab
IPs from the public repo."
```

---

## Task 2: Parameterize and Copy housekeeping Skill

**Goal:** Copy `housekeeping.md` to `adapters/claude-code/skills/housekeeping.md`, replacing all hardcoded paths with env var reads.

**Source:** `/mnt/c/Server/claude-config/global/commands/housekeeping.md` (353 lines)

**Replacements required:**

| Location | Old | New |
|----------|-----|-----|
| Header comment | `CAPTURE_API: http://localhost:5009` | `CAPTURE_API: ${IKEOS_URL:-http://localhost:5009}` |
| Header comment | `Schema reference: ~/server/claude-config/docs/housekeeping-schema.md` | `Schema reference: see adapters/claude-code/README.md` |
| Python Phase 1 | `VAULT_ROOT = Path("/mnt/c/Server/obsidian-vault")` | See code block below |
| Every `http://localhost:5009/capture` in curl/python | → `{IKEOS_URL}/capture` (env-based) |
| Every `http://localhost:5009/entries/housekeeping` in curl/python | → `{IKEOS_URL}/entries/housekeeping` (env-based) |

**Phase 1 Python VAULT_ROOT replacement:**

```python
# OLD:
VAULT_ROOT = Path("/mnt/c/Server/obsidian-vault")

# NEW:
import os
_vault = os.environ.get("VAULT_PATH", "")
if not _vault:
    print("Error: VAULT_PATH environment variable is not set.")
    print("Set it to the absolute path of your Obsidian vault root.")
    sys.exit(1)
VAULT_ROOT = Path(_vault)
```

**IKEOS_URL in Python scripts (Phase 3, 6, 7):**

Every Python script that calls `http://localhost:5009/...` must instead read:
```python
IKEOS_URL = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
```
Then use `f"{IKEOS_URL}/capture"`, `f"{IKEOS_URL}/entries/housekeeping"` etc.

**IKEOS_URL in curl commands:**

Every `curl ... http://localhost:5009/...` becomes:
```bash
IKEOS_URL="${IKEOS_URL:-http://localhost:5009}"
curl ... "${IKEOS_URL}/capture"
```

- [x] **Step 1: Read source file**

Read `/mnt/c/Server/claude-config/global/commands/housekeeping.md` in full.

- [x] **Step 2: Write parameterized version**

Write `adapters/claude-code/skills/housekeeping.md` with all replacements above applied. The file should be functionally identical to the source except every hardcoded path/URL reads from env.

Update the frontmatter description to:
```yaml
description: Run the periodic housekeeping routine — discover vault tasks, run due ones as subagents, update vault state. Requires VAULT_PATH, IKEOS_URL, and CAPTURE_TOKEN env vars.
```

- [x] **Step 3: Spot-check the output**

```bash
grep -n "obsidian-vault\|localhost:5009\|claude-config/library\|192.168\|ryancoleman\|C:\\\\Server" \
  /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/housekeeping.md
```

Expected: 0 matches. If any remain, fix them.

- [x] **Step 4: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add adapters/claude-code/skills/housekeeping.md
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add adapters/claude-code/skills/housekeeping — parameterized skill"
```

---

## Task 3: Parameterize and Copy triage Skill

**Source:** `/mnt/c/Server/claude-config/global/commands/triage.md` (163 lines)

**Replacements required:**

| Location | Old | New |
|----------|-----|-----|
| Python Step 0, path discovery loop | `for r in ['/mnt/c', '/c']: candidate = f'{r}/Server/claude-config/library'` | Read from `CLAUDE_CONFIG_DIR` env |
| Step 1 text | `C:\Server\obsidian-vault\projects\<project>\` | `$VAULT_PATH/projects/<project>/` |
| Step 1 text | `C:\Server\obsidian-vault\decisions\` | `$VAULT_PATH/decisions/` |
| curl commands | `http://localhost:5009/entries` | `${IKEOS_URL:-http://localhost:5009}/entries` |
| curl commands | `http://localhost:5009/capture` | `${IKEOS_URL:-http://localhost:5009}/capture` |

**CLAUDE_CONFIG_DIR replacement in Python:**

```python
# OLD:
base = None
for r in ['/mnt/c', '/c']:
    candidate = f'{r}/Server/claude-config/library'
    if os.path.isdir(candidate):
        base = candidate
        break

# NEW:
import os
base = os.environ.get("CLAUDE_CONFIG_DIR")
if base and not os.path.isdir(base):
    print(f"Warning: CLAUDE_CONFIG_DIR={base} not found — reflection digest skipped")
    base = None
```

**IKEOS_URL in Python scripts:**
```python
IKEOS_URL = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
```

**VAULT_PATH for Python file scans:**
```python
VAULT = Path(os.environ.get("VAULT_PATH", ""))
if not VAULT or not VAULT.exists():
    print("Error: VAULT_PATH not set or does not exist."); sys.exit(1)
```

- [x] **Step 1: Read source file**

Read `/mnt/c/Server/claude-config/global/commands/triage.md` in full.

- [x] **Step 2: Write parameterized version**

Write `adapters/claude-code/skills/triage.md` with all replacements applied. Update frontmatter description to note required env vars.

- [x] **Step 3: Spot-check**

```bash
grep -n "obsidian-vault\|localhost:5009\|Server/claude-config\|192.168\|ryancoleman\|C:\\\\Server" \
  /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/triage.md
```

Expected: 0 matches.

- [x] **Step 4: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add adapters/claude-code/skills/triage.md
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add adapters/claude-code/skills/triage — parameterized skill"
```

---

## Task 4: Parameterize and Copy close-session Skill

**Source:** `/mnt/c/Server/claude-config/global/commands/close-session.md` (201 lines)

**Replacements required:**

| Location | Old | New |
|----------|-----|-----|
| Option B Python | `SIGNALS = '/mnt/c/Server/claude-config/library/weak-signals.json'` | Read from `CLAUDE_CONFIG_DIR` env |
| Option B Python (check block) | `data = json.load(open('/mnt/c/Server/claude-config/library/weak-signals.json'))` | Same |
| Phase 5a blog append | `/mnt/c/Server/projects/aios-blog/weekly-notes/<YYYY-Wxx>.md` | Read from `BLOG_NOTES_DIR` env |
| curl capture calls | `http://localhost:5009/capture` | `${IKEOS_URL:-http://localhost:5009}/capture` |
| curl PATCH calls | `http://localhost:5009/entries` | `${IKEOS_URL:-http://localhost:5009}/entries` |
| Phase 4 vault scan text | `C:\Server\obsidian-vault\projects\<project>\{bugs,ideas,notes}\` | `$VAULT_PATH/projects/<project>/{bugs,ideas,notes}/` |

**CLAUDE_CONFIG_DIR in Python (Option B, close-session):**

```python
# OLD:
SIGNALS = '/mnt/c/Server/claude-config/library/weak-signals.json'

# NEW:
import os
_config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "")
SIGNALS = os.path.join(_config_dir, "library", "weak-signals.json") if _config_dir else ""
if not SIGNALS or not os.path.exists(SIGNALS):
    print("CLAUDE_CONFIG_DIR not set or weak-signals.json not found — skipping signal update")
    # exit or continue depending on context — for close-session, continue silently
```

**BLOG_NOTES_DIR in Phase 5a:**

```python
# OLD:
# Appends to /mnt/c/Server/projects/aios-blog/weekly-notes/<YYYY-Wxx>.md

# NEW:
import os
blog_dir = os.environ.get("BLOG_NOTES_DIR", "")
if not blog_dir:
    print("BLOG_NOTES_DIR not set — skipping blog notes capture")
    # Skip the blog append step
```

Replace the hardcoded blog path with `os.path.join(blog_dir, f"{year}-W{week:02d}.md")`.

- [x] **Step 1: Read source file**

Read `/mnt/c/Server/claude-config/global/commands/close-session.md` in full.

- [x] **Step 2: Write parameterized version**

Write `adapters/claude-code/skills/close-session.md` with all replacements applied. Update frontmatter description.

- [x] **Step 3: Spot-check**

```bash
grep -n "obsidian-vault\|localhost:5009\|Server/claude-config\|aios-blog\|192.168\|ryancoleman\|C:\\\\Server\|/mnt/c/Server" \
  /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/close-session.md
```

Expected: 0 matches.

- [x] **Step 4: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add adapters/claude-code/skills/close-session.md
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add adapters/claude-code/skills/close-session — parameterized skill"
```

---

## Task 5: Parameterize and Copy schema-check Skill

**Source:** `/mnt/c/Server/claude-config/global/commands/schema-check.md` (217 lines)

**Replacements required:**

| Location | Old | New |
|----------|-----|-----|
| Step 1 Python | `VAULT = Path("/mnt/c/Server/obsidian-vault")` | Read from `VAULT_PATH` env |
| Description text | `C:\Server\obsidian-vault\meta\vault-schema.md` | `$VAULT_PATH/meta/vault-schema.md` |
| PATCH curl/python | `http://localhost:5009/entries` | env-driven |
| Python PATCH token line | `token = os.environ.get("CAPTURE_TOKEN", "")` | already correct ✓ |

**VAULT_PATH replacement:**

```python
# OLD:
VAULT = Path("/mnt/c/Server/obsidian-vault")

# NEW:
import os
_vault = os.environ.get("VAULT_PATH", "")
if not _vault:
    print("Error: VAULT_PATH environment variable is not set."); sys.exit(1)
VAULT = Path(_vault)
```

**IKEOS_URL in Python PATCH block:**

```python
# OLD:
req = urllib.request.Request("http://localhost:5009/entries", data=data, method="PATCH")

# NEW:
_ikeos = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
req = urllib.request.Request(f"{_ikeos}/entries", data=data, method="PATCH")
```

- [x] **Step 1: Read source file**

Read `/mnt/c/Server/claude-config/global/commands/schema-check.md` in full.

- [x] **Step 2: Write parameterized version**

Write `adapters/claude-code/skills/schema-check.md` with all replacements applied. Update frontmatter description.

- [x] **Step 3: Spot-check**

```bash
grep -n "obsidian-vault\|localhost:5009\|Server/claude-config\|192.168\|ryancoleman\|C:\\\\Server\|/mnt/c/Server" \
  /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/schema-check.md
```

Expected: 0 matches.

- [x] **Step 4: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add adapters/claude-code/skills/schema-check.md
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add adapters/claude-code/skills/schema-check — parameterized skill"
```

---

## Task 6: Parameterize and Copy promote Skill + stophook

**Sources:**
- `/mnt/c/Server/claude-config/global/commands/promote.md` (41 lines)
- `/mnt/c/Server/claude-config/scripts/stophook-reflection.sh` (~60 lines)

**promote.md replacements:**

| Location | Old | New |
|----------|-----|-----|
| Step 3 curl | `http://localhost:5009/capture` | `${IKEOS_URL:-http://localhost:5009}/capture` |
| Step 1 text | `C:\Users\ServerAdmin\.claude\memory\<name>.md` | `~/.claude/memory/<name>.md` (already generic enough) |

**stophook-reflection.sh replacements:**

The path discovery loop:
```bash
# OLD:
for r in /mnt/c /c; do
    candidate="$r/Server/claude-config/library/weak-signals.json"
    if [ -f "$candidate" ]; then
        SIGNALS_FILE="$candidate"
        break
    fi
done

# NEW:
SIGNALS_FILE=""
if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
    candidate="${CLAUDE_CONFIG_DIR}/library/weak-signals.json"
    [ -f "$candidate" ] && SIGNALS_FILE="$candidate"
fi
# Fallback: try common WSL2 paths if env var not set
if [ -z "$SIGNALS_FILE" ]; then
    for r in /mnt/c /c; do
        candidate="$r/Server/claude-config/library/weak-signals.json"
        if [ -f "$candidate" ]; then
            SIGNALS_FILE="$candidate"
            break
        fi
    done
fi
```

- [x] **Step 1: Read promote.md source**

Read `/mnt/c/Server/claude-config/global/commands/promote.md` in full.

- [x] **Step 2: Write parameterized promote.md**

Write `adapters/claude-code/skills/promote.md`. Replace `http://localhost:5009/capture` with `${IKEOS_URL:-http://localhost:5009}/capture` in the curl command. Update `C:\Users\ServerAdmin\.claude\memory\` references to `~/.claude/memory/`. All other content is identical.

- [x] **Step 3: Read stophook-reflection.sh source**

Read `/mnt/c/Server/claude-config/scripts/stophook-reflection.sh` in full.

- [x] **Step 4: Write parameterized stophook-reflection.sh**

Write `adapters/claude-code/hooks/stophook-reflection.sh` with the path discovery replacement above. Everything else is identical.

- [x] **Step 5: Spot-check both files**

```bash
grep -n "obsidian-vault\|localhost:5009\|/mnt/c/Server/claude-config\|192.168\|ryancoleman\|C:\\\\Server\|ServerAdmin" \
  /mnt/c/Server/projects/ikeos/adapters/claude-code/skills/promote.md \
  /mnt/c/Server/projects/ikeos/adapters/claude-code/hooks/stophook-reflection.sh
```

Expected: 0 matches.

- [x] **Step 6: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add adapters/claude-code/skills/promote.md adapters/claude-code/hooks/
git -C /mnt/c/Server/projects/ikeos commit -m "feat: add adapters/claude-code/skills/promote and hooks/stophook — parameterized"
```

---

## Task 7: Write Install Docs and .env.example

**Goal:** A new user can clone the repo, follow `adapters/claude-code/README.md`, and have a working setup.

**Files (create):**
- `adapters/claude-code/README.md`
- `adapters/claude-code/.env.example`

- [x] **Step 1: Write adapters/claude-code/.env.example**

```bash
# IkeOS Claude Code Adapter — environment variables
# Copy this to ~/.claude/.env (or set in your shell profile) and fill in your values.

# Required: Base URL of your IkeOS instance
IKEOS_URL=http://localhost:5009

# Required: Capture token (must match CAPTURE_TOKEN in your IkeOS .env)
CAPTURE_TOKEN=your-capture-token-here

# Required: Absolute path to your Obsidian vault root
# Linux/WSL2 example:  VAULT_PATH=/mnt/c/Users/you/Obsidian/MyVault
# macOS example:       VAULT_PATH=/Users/you/Documents/MyVault
VAULT_PATH=/path/to/your/obsidian/vault

# Optional: Directory containing your claude-config library/ folder
# Enables reflection health digest in triage and close-session.
# Set to the directory that contains a library/weak-signals.json file.
# CLAUDE_CONFIG_DIR=/path/to/your/claude-config

# Optional: Blog weekly-notes directory for close-session blog capture
# Set to the directory where weekly digest notes should be written.
# BLOG_NOTES_DIR=/path/to/your/blog/weekly-notes
```

- [x] **Step 2: Write adapters/claude-code/README.md**

Write `adapters/claude-code/README.md` with these sections:

```markdown
# IkeOS — Claude Code Adapter

This adapter connects Claude Code to an IkeOS instance. It provides:

- **Session manager** — the reference implementation of the [IkeOS Session Driver API](../../docs/SESSION_DRIVER_API.md). Runs as a lightweight Flask server that manages Claude Code sessions in tmux.
- **Skills** — Claude Code slash commands (`/housekeeping`, `/triage`, `/close-session`, `/schema-check`, `/promote`) that integrate with IkeOS's capture API and Obsidian vault.
- **Hooks** — a StopHook script that logs session reflection signals.

## Prerequisites

- An IkeOS instance running and reachable (see root `README.md`)
- Claude Code CLI installed
- tmux installed (session manager uses it to run Claude Code)
- Python 3.11+

## Quick Start

### 1. Configure env vars

```bash
cp adapters/claude-code/.env.example ~/.claude/.env
# Edit ~/.claude/.env with your values
```

Set at minimum: `IKEOS_URL`, `CAPTURE_TOKEN`, `VAULT_PATH`.

### 2. Run the session manager

```bash
cd adapters/claude-code/session-manager
cp .env.example .env
# Edit .env: set IKEOS_METRICS_URL and IKEOS_CAPTURE_TOKEN to match your IkeOS instance
bash start.sh
```

The session manager listens on `PORT` (default 5010). Point your IkeOS `SESSION_MANAGER_URL` env var at it.

### 3. Install skills

```bash
mkdir -p ~/.claude/commands
cp adapters/claude-code/skills/*.md ~/.claude/commands/
```

Skills read `IKEOS_URL`, `CAPTURE_TOKEN`, and `VAULT_PATH` from your environment at runtime.

### 4. Install the StopHook (optional)

```bash
cp adapters/claude-code/hooks/stophook-reflection.sh ~/bin/stophook-reflection.sh
chmod +x ~/bin/stophook-reflection.sh
```

Register it in your Claude Code hooks config (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "bash ~/bin/stophook-reflection.sh"}]}]
  }
}
```

## Environment Variables Reference

| Var | Required | Default | Purpose |
|-----|---------|---------|---------|
| `IKEOS_URL` | Yes | `http://localhost:5009` | IkeOS capture API base URL |
| `CAPTURE_TOKEN` | Yes | — | Auth token for mutation endpoints |
| `VAULT_PATH` | Yes | — | Absolute path to Obsidian vault root |
| `CLAUDE_CONFIG_DIR` | No | — | Directory containing `library/weak-signals.json` |
| `BLOG_NOTES_DIR` | No | — | Blog weekly-notes directory (close-session) |

**Session manager vars** (set in `adapters/claude-code/session-manager/.env`):

| Var | Required | Default | Purpose |
|-----|---------|---------|---------|
| `PORT` | No | 5010 | Listen port |
| `IKEOS_METRICS_URL` | No | — | IkeOS metrics endpoint |
| `IKEOS_CAPTURE_TOKEN` | No | — | Token for metrics posts |
| `PROTECTED_CONTAINERS` | No | — | Comma-separated protected container names |
| `INFRASTRUCTURE_MACHINES` | No | `[]` | JSON array `[{"name":"...","host":"..."}]` |
```

- [x] **Step 3: Commit**

```bash
git -C /mnt/c/Server/projects/ikeos add adapters/claude-code/README.md adapters/claude-code/.env.example
git -C /mnt/c/Server/projects/ikeos commit -m "docs: add adapters/claude-code README and .env.example"
```

---

## Task 8: Update DECISIONS.md + Vault Entries + Final Verification

**Goal:** Record the extraction decision, mark vault entries done, verify no sensitive data leaked into the committed tree.

- [x] **Step 1: Append to DECISIONS.md**

Read `/mnt/c/Server/projects/ikeos/.claude/DECISIONS.md`, then append:

```markdown
## 2026-07-03: adapters/claude-code/ created — skills and session-manager extracted from claude-config

Execution of the 2026-07-02 decision (Skills and session-manager move INTO ikeos). All IkeOS-coupled Claude Code artifacts now live in `adapters/claude-code/`: five parameterized skills (/housekeeping, /triage, /close-session, /schema-check, /promote), the stophook reflection script, and the session-manager service (reference implementation of the SESSION_DRIVER_API). Parameterization contract: IKEOS_URL, CAPTURE_TOKEN, VAULT_PATH, CLAUDE_CONFIG_DIR, BLOG_NOTES_DIR. The single code change in session-manager: INFRASTRUCTURE_MACHINES is now loaded from an env var (JSON array) instead of being hardcoded. CAPTURE_TOKEN was rotated before extraction; both repo git histories were swept for the old token (0 matches found). install docs in adapters/claude-code/README.md.
```

- [x] **Step 2: Commit DECISIONS.md**

```bash
git -C /mnt/c/Server/projects/ikeos add .claude/DECISIONS.md
git -C /mnt/c/Server/projects/ikeos commit -m "docs: record adapter extraction decision in DECISIONS.md"
```

- [x] **Step 3: Final sensitive-data sweep across entire adapters/ tree**

```bash
grep -rn "192.168\|100.74\|ryancoleman\|ServerAdmin\|C:\\\\Server\|/mnt/c/Server\|localhost:5009" \
  /mnt/c/Server/projects/ikeos/adapters/ 2>/dev/null
```

Expected: 0 matches. If any found: fix the file, re-verify, re-commit.

- [x] **Step 4: Mark vault entries done**

```bash
CAPTURE_TOKEN=$(grep CAPTURE_TOKEN /mnt/c/Server/projects/ikeos/.env | cut -d= -f2 | tr -d '\r')

# Mark Phase 2 idea done
curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=idea" \
  -d "filename=2026-07-02-phase-2-extract-adaptersclaude-code-skills-session.md" \
  -d "status=done"

# Mark resumption context note done
curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=note" \
  -d "filename=2026-07-03-driver-consolidation-complete-resumption-context-f.md" \
  -d "status=done"

# Mark Phase 2 why-note done
curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=note" \
  -d "filename=2026-07-03-why-phase-2-extract-adaptersclaude-code.md" \
  -d "status=done"
```

- [x] **Step 5: Final git log review**

```bash
git -C /mnt/c/Server/projects/ikeos log --oneline -15
```

Expected: 8+ commits starting from "feat: add adapters/claude-code/session-manager...". Confirm all tasks are represented.

---

## Self-Review

**Spec coverage check:**
- ✅ CAPTURE_TOKEN rotated (Task 0)
- ✅ Repo history swept for old token (Task 0)
- ✅ session-manager extracted + sanitized (Task 1)
- ✅ /housekeeping parameterized (Task 2)
- ✅ /triage parameterized (Task 3)
- ✅ /close-session parameterized (Task 4)
- ✅ /schema-check parameterized (Task 5)
- ✅ /promote parameterized + stophook (Task 6)
- ✅ Install docs written (Task 7)
- ✅ DECISIONS.md updated (Task 8)
- ✅ Vault entries marked done (Task 8)
- ✅ Final sensitive-data sweep (Task 8)

**Gaps identified:**
- The vault idea mentions "capability-gate and document the ephemeral permission-skipping behavior" — this is already documented in `docs/SESSION_DRIVER_API.md` (Ephemeral semantics section) and in `DECISIONS.md` (2026-06-30 entry). No additional code change needed; the adapter README references SESSION_DRIVER_API.md.
- The `housekeeping-schema.md` reference in the skill header will become a pointer to the adapter README — this is covered in Task 2's frontmatter update.

**Placeholder scan:** No TBDs or "implement later" text found in any task.

**Type consistency:** No type definitions span tasks. Session-manager copy is verbatim (no API changes).
