# IkeOS — Claude Code Adapter

This adapter connects Claude Code to an IkeOS instance. It provides the session manager (reference implementation of the Session Driver API), five Claude Code slash-command skills, and a StopHook script.

---

## Prerequisites

- An IkeOS instance running and accessible (see root README)
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- tmux installed
- Python 3.11+

---

## Quick Start

### 1. Configure env vars

```bash
cp adapters/claude-code/.env.example ~/.claude/.env
# Edit ~/.claude/.env with your values
```

> Claude Code loads `~/.claude/.env` automatically at startup.

### 2. Run the session manager

```bash
cd adapters/claude-code/session-manager
cp .env.example .env
# Edit .env: set IKEOS_METRICS_URL and IKEOS_CAPTURE_TOKEN to match your IkeOS instance
bash start.sh
```

The session manager listens on PORT (default 5010). Set `SESSION_MANAGER_URL=http://localhost:5010` in your IkeOS `.env`.

### 3. Install skills

```bash
mkdir -p ~/.claude/commands
cp adapters/claude-code/skills/*.md ~/.claude/commands/
```

After copying, restart Claude Code. The skills will appear as `/housekeeping`, `/triage`, `/close-session`, `/schema-check`, `/promote`.

### 4. Install the StopHook (optional)

```bash
cp adapters/claude-code/hooks/stophook-reflection.sh ~/bin/stophook-reflection.sh
chmod +x ~/bin/stophook-reflection.sh
```

Register in Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "bash ~/bin/stophook-reflection.sh"}]}]
  }
}
```

---

## Environment Variables

### Skills & hooks

Set in `~/.claude/.env` or your shell profile.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IKEOS_URL` | Yes | `http://localhost:5009` | IkeOS base URL |
| `CAPTURE_TOKEN` | Yes | — | Auth token (matches `CAPTURE_TOKEN` in IkeOS `.env`) |
| `VAULT_PATH` | Yes | — | Absolute path to Obsidian vault root |
| `CLAUDE_CONFIG_DIR` | No | — | Directory containing `library/weak-signals.json` |
| `BLOG_NOTES_DIR` | No | — | Blog weekly-notes directory (used by `/close-session`) |

### Session manager

Set in `adapters/claude-code/session-manager/.env`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No | 5010 | Listen port |
| `IKEOS_METRICS_URL` | No | — | IkeOS `/metrics/event` endpoint |
| `IKEOS_CAPTURE_TOKEN` | No | — | Token for metrics posts |
| `PROTECTED_CONTAINERS` | No | — | Comma-separated protected container names |
| `INFRASTRUCTURE_MACHINES` | No | `[]` | JSON array `[{"name":"...","host":"..."}]` |
| `CLAUDE_BIN` | No | `claude` | Path to the Claude Code CLI binary |
| `CLAUDE_PLUGIN_BASE` | No | `~/.claude/plugins` | Claude Code plugin directory |

---

## Capture API

Skills and hooks post to the IkeOS capture API via `curl`. Use `--data-urlencode` (not `-d`) for any field that may contain non-ASCII characters (em-dashes, curly quotes, Unicode, etc.). Raw UTF-8 bytes in a URL-encoded body cause a 400 error.

```bash
# Correct — safe for any content
curl -s -X POST "$IKEOS_URL/capture" \
  --data-urlencode "type=note" \
  --data-urlencode "project=my-project" \
  --data-urlencode "title=Some title with an em—dash" \
  --data-urlencode "body=Body text with 'curly quotes'"

# Wrong — raw UTF-8 bytes will fail
curl -s -X POST "$IKEOS_URL/capture" \
  -d "type=note" -d "project=my-project" \
  -d "title=title with em—dash"
```

---

## Driver API

The session manager implements the IkeOS Session Driver API. For the full contract (endpoints, request/response shapes, ephemeral session semantics), see [`docs/SESSION_DRIVER_API.md`](../../docs/SESSION_DRIVER_API.md).

---

## Research Sources API

The session manager also exposes a small API for managing the RSS/URL sources used by `deep-research-weekly` and `/housekeeping`. Sources are persisted to `~/.claude-research-sources.json`.

### GET /research-sources
Returns `{"sources": [...]}` — each source has `id`, `url`, `label`, `status`, `last_fetched`, `entries_generated`, `added`, `blacklisted`.

### POST /research-sources
Body: `{"url": "<url>", "label": "<label>"}`. Both fields required. `201` with the created source on success, `409` if a source with this URL already exists, `400` if `url` or `label` is missing.

### PATCH /research-sources/{id}
Toggles `blacklisted` for the source with this id. `200` with the updated source, `404` if unknown.
