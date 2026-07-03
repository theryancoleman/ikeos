#!/bin/bash
# StopHook: fires at every session end.
# If /close-session ran, it left ~/.claude/session-closed-flag — clean exit.
# Otherwise, log a friction-point signal (session ended without reflection).

set -euo pipefail

FLAG="$HOME/.claude/session-closed-flag"

# Find the signals file.
# Prefer CLAUDE_CONFIG_DIR if set (portable, works for any install location).
SIGNALS_FILE=""
if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
    candidate="${CLAUDE_CONFIG_DIR}/library/weak-signals.json"
    [ -f "$candidate" ] && SIGNALS_FILE="$candidate"
fi
# Fallback: try community-convention fallback paths for WSL2 homelab installs
# where CLAUDE_CONFIG_DIR is not set.
if [ -z "$SIGNALS_FILE" ]; then
    for r in /mnt/c /c; do
        candidate="$r/Server/claude-config/library/weak-signals.json"
        if [ -f "$candidate" ]; then
            SIGNALS_FILE="$candidate"
            break
        fi
    done
fi

# If close-session ran, remove the flag and exit cleanly
if [ -f "$FLAG" ]; then
    rm -f "$FLAG"
    exit 0
fi

# close-session was NOT run — emit a visible reminder and log the signal.
echo ""
echo "SESSION ENDED WITHOUT /close-session"
echo "Run /close-session to reflect, update vault entries, and save session notes."
echo ""

# If we can't find the signals file, exit after showing the reminder.
[ -z "$SIGNALS_FILE" ] && exit 0

# Increment (or create) the abrupt-ending friction-point signal
python3 - "$SIGNALS_FILE" <<'PYEOF'
import json, datetime, sys

signals_path = sys.argv[1]
today = datetime.date.today().isoformat()
target_pattern = "Session ended without reflection via /close-session"
target_category = "friction-point"

try:
    with open(signals_path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {"_version": 1, "signals": []}

signals = data.setdefault("signals", [])

found = False
for s in signals:
    if s.get("pattern") == target_pattern:
        s["occurrences"] = int(s.get("occurrences", 0)) + 1
        s["last_seen"] = today
        found = True
        break

if not found:
    signals.append({
        "category": target_category,
        "skill_referenced": None,
        "pattern": target_pattern,
        "occurrences": 1,
        "first_seen": today,
        "last_seen": today
    })

try:
    with open(signals_path, "w") as f:
        json.dump(data, f, indent=2)
except Exception:
    pass  # best-effort logger — never surface as a user-facing error
PYEOF
