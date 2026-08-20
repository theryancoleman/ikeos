import os
import shlex
import subprocess
import time

from pane_parser import parse_activity

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
PLUGIN_BASE = os.environ.get(
    "CLAUDE_PLUGIN_BASE",
    os.path.expanduser("~/.claude/plugins/cache/claude-plugins-official"),
)
CLAUDE_CMD = [
    CLAUDE_BIN,
    "--model", "claude-sonnet-5",
    "--plugin-dir", f"{PLUGIN_BASE}/superpowers/5.1.0",
    "--plugin-dir", f"{PLUGIN_BASE}/frontend-design/unknown",
    "--plugin-dir", f"{PLUGIN_BASE}/github/unknown",
]


def has_session(name: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True
    )
    return result.returncode == 0


def list_session_names() -> set[str]:
    """Return the set of currently live tmux session names.

    tmux exits non-zero with "no server running" when there are zero
    sessions — treat that as an empty set rather than an error.
    """
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def launch_session(
    name: str, project_dir: str, *,
    skip_permissions: bool = False, model: str | None = None,
) -> None:
    # Launch through a login shell so ~/.profile → ~/.bashrc →
    # ~/.claude/secrets.env runs and Claude inherits credentials that
    # WSL2 does not get from the Windows environment.
    cmd = list(CLAUDE_CMD)
    if model:
        cmd[cmd.index("--model") + 1] = model
    cmd = cmd + (["--dangerously-skip-permissions"] if skip_permissions else [])
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", name, "-c", project_dir,
         "bash", "-lc", shlex.join(cmd)],
        check=True
    )


def kill_session(name: str) -> None:
    subprocess.run(
        ["tmux", "kill-session", "-t", name],
        check=True
    )


def send_key(name: str, key: str) -> None:
    """Send a single tmux key event (e.g. 'Escape', 'Enter') without any text."""
    subprocess.run(
        ["tmux", "send-keys", "-t", name, key],
        check=True
    )


def send_command(name: str, command: str) -> None:
    subprocess.run(
        ["tmux", "send-keys", "-t", name, command, "Enter"],
        check=True
    )


def send_enter(name: str) -> None:
    subprocess.run(
        ["tmux", "send-keys", "-t", name, "Enter"],
        check=True
    )


def capture_pane(name: str) -> str:
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", name, "-p"],
        capture_output=True,
        text=True
    )
    return result.stdout


def wait_until_idle(
    name: str,
    *,
    timeout: float = 60.0,
    poll_interval: float = 3.0,
    required_consecutive: int = 1,
) -> bool:
    """Poll the pane until Claude Code is at an idle prompt. Returns True if idle before timeout.

    required_consecutive: number of consecutive idle readings needed before returning True.
    Use >1 to avoid false positives during the brief gap between generation starting and
    the token counter appearing (parse_activity blind spot for plain text output).
    """
    deadline = time.monotonic() + timeout
    consecutive = 0
    while True:
        if not has_session(name):
            return False
        if parse_activity(capture_pane(name)) == "idle":
            consecutive += 1
            if consecutive >= required_consecutive:
                return True
        else:
            consecutive = 0
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval)


def send_prompt(
    name: str,
    command: str,
    *,
    min_delay: float = 5.0,
    timeout: float = 60.0,
    required_consecutive: int = 1,
    escape_first: bool = True,
) -> bool:
    """Send a command to a Claude Code session when the pane is at an idle prompt.

    Waits min_delay seconds, polls for idle state, optionally sends Escape to
    dismiss any open panel, polls for idle again, then sends the command.
    Returns True if sent, False if the session disappeared or timed out.

    escape_first should be False when the previous command's Enter may not yet
    have been processed — sending Escape in that gap cancels the pending Enter
    and causes the two commands' text to merge in Claude Code's input buffer.
    """
    time.sleep(min_delay)
    if not wait_until_idle(name, timeout=timeout, required_consecutive=required_consecutive):
        return False
    if escape_first:
        send_key(name, "Escape")
        if not wait_until_idle(name, timeout=5.0, poll_interval=0.5):
            return False
    send_command(name, command)
    # Brief pause so Claude has a moment to start processing before the caller
    # re-checks for idle. Without this, parse_activity returns "idle" in the
    # gap between keystroke delivery and Claude's first pane update, causing
    # the next send_prompt to fire before the previous command is handled.
    time.sleep(2.0)
    return True
