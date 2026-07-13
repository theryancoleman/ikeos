import re
from datetime import datetime, timedelta, timezone

COMPACTION_PATTERNS = [
    r"compacted",
    r"context window",
    r"tokens remaining",
    r"approaching limit",
]


def parse_remote_control_state(pane_output: str) -> str | None:
    """Return 'enabled', 'disabled', or None — uses last matching line."""
    result = None
    for line in pane_output.splitlines():
        lower = line.lower()
        if re.search(r"remote control enabled", lower):
            result = "enabled"
        elif re.search(r"remote control disabled", lower):
            result = "disabled"
        elif re.search(r"claude\.ai/code/session_", line):
            result = "enabled"
    return result


def parse_rc_dialog_open(pane_output: str) -> bool:
    """Return True if the /remote-control TUI dialog is currently blocking the pane."""
    return "Enter to select" in pane_output and "claude.ai/code/session_" in pane_output


_IDLE_STATUS = "? for shortcuts"      # status bar when Claude is at the input prompt
_IDLE_STATUS_BYPASS = "bypass permissions on"  # status bar in --dangerously-skip-permissions mode
_ACTIVE_STATUS = "esc to interrupt"   # status bar when Claude is generating/thinking/working


def parse_activity(pane_output: str) -> str:
    """Return 'not_started' | 'thinking' | 'working' | 'idle' based on visible pane content.

    Status bar anchors the state machine:
      - Neither string: Claude Code TUI hasn't initialised yet → 'not_started'
      - 'esc to interrupt': Claude is actively processing → at least 'working'
      - '? for shortcuts' or 'bypass permissions on': Claude is at the idle input
        prompt → 'idle' (unless a more specific active pattern is also present)

    Using the status bar prevents firing startup commands into an uninitialised pane,
    which previously caused ESC to be prepended to slash commands, stripping the '/'
    and turning them into plain user text.
    """
    # Not started: Claude Code TUI hasn't shown any status bar variant yet.
    is_idle_bar = _IDLE_STATUS in pane_output or _IDLE_STATUS_BYPASS in pane_output
    if not is_idle_bar and _ACTIVE_STATUS not in pane_output:
        return "not_started"
    # Extended thinking: ✻ with active (duration) format, e.g. "✻ Razzmatazzing… (2m 6s)"
    # Excludes completion lines like "✻ Brewed for 21s" which use "for Xs" not "(Xs)"
    if re.search(r"✻ .+\(\d", pane_output) or "almost done thinking" in pane_output:
        return "thinking"
    # Tool execution: tool call waiting for result
    if "⎿  Waiting" in pane_output:
        return "working"
    # Active subagent (◯ name  Xs) or token stream (↓ N) in bottom lines
    tail = "\n".join(pane_output.splitlines()[-6:])
    if re.search(r"◯ .+\d+s", tail) or re.search(r"↓\s+\d", tail):
        return "working"
    # 'esc to interrupt' present but no specific active pattern = generating plain text.
    # This closes the blind spot where text generation looked idle to the old parser.
    if _ACTIVE_STATUS in pane_output:
        return "working"
    # '? for shortcuts' or 'bypass permissions on' = genuinely idle at the input prompt.
    return "idle"


def parse_message_count(pane_output: str) -> int:
    """Count '> ' prompt lines as a proxy for conversation turns."""
    return sum(1 for line in pane_output.splitlines() if line.strip() == ">")


def parse_compaction_detected(pane_output: str) -> bool:
    lower = pane_output.lower()
    return any(re.search(p, lower) for p in COMPACTION_PATTERNS)


def parse_token_usage(pane_output: str) -> dict:
    """Parse context window usage from pane output.
    Returns {'tokens_remaining': str|None, 'context_pct': int|None}.
    """
    result = {"tokens_remaining": None, "context_pct": None}
    lower = pane_output.lower()

    m = re.search(r"(\d[\d,.]*k?)\s+tokens?\s+remaining", lower)
    if m:
        result["tokens_remaining"] = m.group(1)

    m = re.search(r"context[:\s]+(?:window\s+)?(?:usage\s+)?[:\s]*(\d+)\s*%", lower)
    if not m:
        m = re.search(r"(\d+)\s*%\s+(?:of\s+)?context", lower)
    if m:
        result["context_pct"] = int(m.group(1))

    return result


def compute_health(session: dict) -> str:
    """Return 'fresh', 'aging', or 'heavy' based on age, messages, compaction."""
    started_at = datetime.fromisoformat(session["started_at"])
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - started_at).total_seconds() / 3600
    messages = session.get("message_count", 0)
    compaction = session.get("compaction_detected", False)

    if age_hours > 3 or messages > 50:
        return "heavy"
    if age_hours > 1 or messages > 20 or compaction:
        return "aging"
    return "fresh"
