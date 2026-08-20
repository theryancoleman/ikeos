#!/bin/bash
# Run from WSL2: bash start.sh
cd "$(dirname "$0")"

# Load local env vars if .env exists (IKEOS_METRICS_URL, IKEOS_CAPTURE_TOKEN, etc.)
if [ -f .env ]; then
    set -a; source .env; set +a
fi

# CRITICAL — isolation from the tmux server that hosts the code sessions.
# The manager spawns each Claude session with a bare `tmux new-session`, which
# targets the server named in $TMUX. If this process runs inside a tmux pane
# (e.g. an agent restarts it from its own session), $TMUX would bind both the
# manager AND every session it creates to that one server — so killing or
# crashing that server takes down all sessions. Unsetting $TMUX forces spawned
# sessions onto the default socket and keeps the manager itself outside any
# killable tmux server. See vault: claude-config 2026-07-13 (session-manager
# tmux isolation).
unset TMUX

pip install -r requirements.txt -q
exec python3 app.py
