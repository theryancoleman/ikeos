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


def parse_activity(pane_output: str) -> str:
    """Return 'thinking' | 'working' | 'idle' based on visible pane content."""
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
