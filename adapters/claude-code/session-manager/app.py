import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, abort

from sessions import (
    list_sessions, get_session, create_session,
    update_session, remove_session, _save,
)
from tmux import (
    has_session, launch_session, kill_session, send_command, send_key,
    send_enter, capture_pane, send_prompt, list_session_names,
)
from research_sources import (
    list_sources, add_source, find_source, set_blacklisted,
)
from pane_parser import (
    parse_remote_control_state, parse_rc_dialog_open, parse_message_count,
    parse_compaction_detected, parse_activity, compute_health, parse_token_usage,
)

app = Flask(__name__)

_DONE_DIR = Path("/tmp/ikeos-done")


def _sentinel_for_session(tmux_session: str) -> Path:
    """Map a tmux session name to its sentinel file path.

    Skills write to a fixed path per session type (they don't know the
    date-suffixed session name). Sessions are deduplicated by name so only
    one housekeeping or platform-review session runs at a time — no collision.
    """
    if tmux_session.startswith("housekeeping-"):
        return _DONE_DIR / "housekeeping"
    if tmux_session.startswith("weekly-platform-review-"):
        return _DONE_DIR / "platform-review"
    if tmux_session.startswith("blog-publish-"):
        return _DONE_DIR / "blog-publish"
    if tmux_session.startswith("blog-rewrite-"):
        return _DONE_DIR / "blog-rewrite"
    return _DONE_DIR / tmux_session


def _refresh(session: dict) -> dict:
    name = session["tmux_session"]
    session["status"] = "active" if has_session(name) else "stopped"
    if session["status"] == "active":
        try:
            pane = capture_pane(name)
            session["message_count"] = parse_message_count(pane)
            session["activity"] = parse_activity(pane)
            was_compacted = session.get("compaction_detected", False)
            session["compaction_detected"] = parse_compaction_detected(pane)
            if session.get("autonomous_mode") and not was_compacted and session["compaction_detected"]:
                send_command(name, "/auto")
            rc_state = parse_remote_control_state(pane)
            if rc_state is not None:
                session["remote_control"] = rc_state == "enabled"
                session["remote_control_confirmed"] = True
            token_data = parse_token_usage(pane)
            session["tokens_remaining"] = token_data["tokens_remaining"]
            session["context_pct"] = token_data["context_pct"]
            session["last_pane_check"] = datetime.now().isoformat()
        except Exception as e:
            app.logger.debug("pane refresh failed for %s: %s", name, e)
    session["health"] = compute_health(session)
    return session


def _wait_for_completion_and_remove(tmux_session: str, session_id: str, project: str = "") -> None:
    """Watch for a sentinel file written by the skill on successful completion.

    The skill writes /tmp/ikeos-done/<type> (e.g. "housekeeping", "platform-review")
    as its final step. _sentinel_for_session() maps the session name to that path.

    Falls through to cleanup after a 4-hour TTL or if the tmux session disappears.
    If the skill fails before writing the sentinel the session stays alive in tmux
    so it can be inspected — the TTL is the only cleanup in that case.
    """
    _DONE_DIR.mkdir(parents=True, exist_ok=True)
    sentinel = _sentinel_for_session(tmux_session)
    # Remove any stale sentinel left by a previous run.
    sentinel.unlink(missing_ok=True)

    deadline = time.monotonic() + 14400  # 4-hour TTL
    while time.monotonic() < deadline:
        time.sleep(5)
        if not has_session(tmux_session):
            _post_metric("agent.session_end", {
                "session_id": session_id,
                "project": project,
                "name": tmux_session,
                "reason": "session_disappeared",
            })
            remove_session(session_id)
            sentinel.unlink(missing_ok=True)
            return
        if sentinel.exists():
            sentinel.unlink(missing_ok=True)
            _post_metric("agent.session_end", {
                "session_id": session_id,
                "project": project,
                "name": tmux_session,
                "reason": "completed",
            })
            kill_session(tmux_session)
            remove_session(session_id)
            return

    # TTL expired: clean up regardless.
    sentinel.unlink(missing_ok=True)
    if has_session(tmux_session):
        kill_session(tmux_session)
    _post_metric("agent.session_end", {
        "session_id": session_id,
        "project": project,
        "name": tmux_session,
        "reason": "timeout",
    })
    remove_session(session_id)


def _run_session_startup(
    *,
    tmux_session: str,
    rename: str,
    remote_control: bool,
    initial_command: str | None,
    session_id: str | None,
    project: str = "",
) -> None:
    """Send post-launch commands in sequence, each waiting for idle pane state.

    Runs in a daemon thread. If session_id is provided, calls
    _wait_for_completion_and_remove after the initial command (ephemeral mode).
    """
    if not send_prompt(tmux_session, f"/rename {rename}"):
        app.logger.warning("_run_session_startup: send_prompt timed out sending /rename to %s", tmux_session)
        return
    if remote_control:
        if not send_prompt(tmux_session, "/remote-control"):
            app.logger.warning("_run_session_startup: send_prompt timed out sending /remote-control to %s", tmux_session)
            return
    if initial_command:
        if not send_prompt(tmux_session, initial_command, escape_first=False):
            app.logger.warning("_run_session_startup: send_prompt timed out sending initial_command to %s", tmux_session)
            return
        if session_id:
            _wait_for_completion_and_remove(tmux_session, session_id, project)


_CONTAINER_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$')

_IKEOS_METRICS_URL = os.environ.get("IKEOS_METRICS_URL", "")
_IKEOS_CAPTURE_TOKEN = os.environ.get("IKEOS_CAPTURE_TOKEN", "")


def _post_metric(event_type: str, payload: dict) -> None:
    if not _IKEOS_METRICS_URL or not _IKEOS_CAPTURE_TOKEN:
        return
    try:
        body = json.dumps({"event": event_type, **payload}).encode()
        req = urllib.request.Request(
            _IKEOS_METRICS_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Capture-Token": _IKEOS_CAPTURE_TOKEN,
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


_PROTECTION_FILE = Path.home() / ".claude-protected-containers.json"


def _load_protected() -> set:
    defaults = {n for n in os.environ.get("PROTECTED_CONTAINERS", "").split(",") if n}
    try:
        if _PROTECTION_FILE.exists():
            data = json.loads(_PROTECTION_FILE.read_text())
            return set(data.get("protected", [])) | defaults
    except Exception:
        pass
    return defaults


def _save_protected(names: set) -> None:
    _PROTECTION_FILE.write_text(json.dumps({"protected": sorted(names)}, indent=2))


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


def _list_docker_containers() -> list:
    try:
        result = subprocess.run(
            ["bash", "-c", 'docker.exe ps -a --format "{{json .}}"'],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            app.logger.warning("docker ps exited %d: %s", result.returncode, result.stderr)
            return []
        containers = []
        for line in result.stdout.strip().splitlines():
            if line.strip():
                containers.append(json.loads(line))
        return containers
    except Exception as e:
        app.logger.error("docker ps failed: %s", e)
        return []


def _ping(host: str) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", host],
            capture_output=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_machines() -> list:
    machines = [dict(m) for m in INFRASTRUCTURE_MACHINES]
    for m in machines:
        m["reachable"] = _ping(m["host"])
    return machines


@app.route("/sessions", methods=["GET"])
def get_sessions():
    sessions = list_sessions()
    refreshed = [_refresh(s) for s in sessions]
    _save(refreshed)
    return jsonify(refreshed)


@app.route("/sessions", methods=["POST"])
def create():
    data = request.get_json()
    name = data["name"]

    if has_session(name):
        existing = next((s for s in list_sessions() if s.get("tmux_session") == name), None)
        if existing:
            return jsonify({"error": "session already running", "session": existing}), 409
        return jsonify({"error": "session already running"}), 409

    is_ephemeral = bool(data.get("initial_command"))
    model = data.get("model")
    try:
        launch_session(name, data["project_dir"], skip_permissions=is_ephemeral, model=model)
    except Exception as e:
        app.logger.error("Failed to launch tmux session %s: %s", name, e)
        return jsonify({"error": "Failed to launch session"}), 500

    session = create_session(
        name, data["project"],
        data["project_dir"], data.get("remote_control", False),
        ephemeral=is_ephemeral,
        model=model,
    )
    _post_metric("agent.session_start", {
        "session_id": session["id"],
        "project": session["project"],
        "name": session["name"],
    })
    threading.Thread(
        target=_run_session_startup,
        kwargs={
            "tmux_session": name,
            "rename": name,
            "remote_control": bool(data.get("remote_control")),
            "initial_command": data.get("initial_command"),
            "session_id": session["id"] if is_ephemeral else None,
            "project": session["project"],
        },
        daemon=True,
    ).start()
    return jsonify(session), 201


@app.route("/sessions/<session_id>", methods=["DELETE"])
def stop(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    if has_session(session["tmux_session"]):
        kill_session(session["tmux_session"])
    update_session(session_id, status="stopped")
    return jsonify({"ok": True})


@app.route("/sessions/<session_id>/remove", methods=["DELETE"])
def remove(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    _post_metric("agent.session_end", {
        "session_id": session_id,
        "project": session.get("project", ""),
        "name": session.get("name", ""),
    })
    if has_session(session["tmux_session"]):
        kill_session(session["tmux_session"])
    remove_session(session_id)
    return jsonify({"ok": True})


@app.route("/sessions/<session_id>/reset", methods=["POST"])
def reset(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    name = session["tmux_session"]
    if has_session(name):
        kill_session(name)
    launch_session(name, session["project_dir"], skip_permissions=session.get("ephemeral", False))
    update_session(session_id,
                   status="active", message_count=0,
                   compaction_detected=False, remote_control_confirmed=False,
                   autonomous_mode=False)
    return jsonify(get_session(session_id))


@app.route("/sessions/<session_id>/remote_control", methods=["PATCH"])
def toggle_remote_control(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    send_command(session["tmux_session"], "/remote-control")
    time.sleep(1)
    pane = capture_pane(session["tmux_session"])
    if parse_rc_dialog_open(pane):
        send_enter(session["tmux_session"])
        time.sleep(0.5)
        pane = capture_pane(session["tmux_session"])
    rc_state = parse_remote_control_state(pane)
    new_state = not session["remote_control"]
    confirmed = False
    if rc_state is not None:
        new_state = rc_state == "enabled"
        confirmed = True
    updated = update_session(session_id,
                             remote_control=new_state,
                             remote_control_confirmed=confirmed)
    return jsonify(updated)


@app.route("/sessions/<session_id>/remote_control_state", methods=["PATCH"])
def correct_remote_control_state(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    new_state = bool(request.get_json()["remote_control"])
    updated = update_session(session_id,
                             remote_control=new_state,
                             remote_control_confirmed=False)
    return jsonify(updated)


@app.route("/sessions/<session_id>/autonomous_mode", methods=["PATCH"])
def toggle_autonomous_mode(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    new_state = not session.get("autonomous_mode", False)
    if new_state:
        send_command(session["tmux_session"], "/auto")
    updated = update_session(session_id, autonomous_mode=new_state)
    return jsonify(updated)


@app.route("/sessions/<session_id>/command", methods=["POST"])
def send_slash_command(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    data = request.get_json()
    command = data["command"]
    # raw=True or bare digit (permission response) → bypass idle-wait and Escape so
    # the keystroke lands directly without dismissing a permission dialog first.
    is_raw = data.get("raw", False) or re.match(r'^\d+$', command.strip())
    if is_raw:
        send_command(session["tmux_session"], command)
    else:
        def _send():
            if not send_prompt(session["tmux_session"], command, min_delay=0.5):
                app.logger.warning("send_slash_command: send_prompt timed out for command %r on session %s",
                                   command, session["tmux_session"])
        threading.Thread(target=_send, daemon=True).start()
    if command in ("/clear", "/compact"):
        update_session(session_id, message_count=0, compaction_detected=False)
    return jsonify({"ok": True})


@app.route("/sessions/<session_id>/rename", methods=["POST"])
def rename_session(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    body = request.get_json(silent=True) or {}
    new_name = (body.get("name") or "").strip()
    if not new_name:
        return jsonify({"error": "name is required"}), 400
    if has_session(session["tmux_session"]):
        send_command(session["tmux_session"], f"/rename {new_name}")
    updated = update_session(session_id, name=new_name)
    return jsonify(updated)


@app.route("/sessions/<session_id>/pane")
def get_pane(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    if not has_session(session["tmux_session"]):
        return jsonify({"lines": [], "active": False})
    try:
        output = capture_pane(session["tmux_session"])
        lines = output.splitlines()[-40:]
        return jsonify({"lines": lines, "active": True})
    except Exception as e:
        app.logger.debug("capture_pane failed for %s: %s", session["tmux_session"], e)
        return jsonify({"lines": [], "active": False})


@app.route("/infrastructure", methods=["GET"])
def get_infrastructure():
    containers = _list_docker_containers()
    protected = _load_protected()
    for c in containers:
        c["protected"] = c["Names"].lstrip("/") in protected
    return jsonify({
        "containers": containers,
        "machines":   _check_machines(),
    })


@app.route("/infrastructure/containers/<name>/protection", methods=["PATCH"])
def toggle_container_protection(name):
    if not _CONTAINER_NAME_RE.match(name):
        return jsonify({"error": "invalid container name"}), 400
    protected = _load_protected()
    if name in protected:
        protected.discard(name)
        new_state = False
    else:
        protected.add(name)
        new_state = True
    _save_protected(protected)
    return jsonify({"ok": True, "protected": new_state})


@app.route("/infrastructure/containers/<name>/restart", methods=["POST"])
def restart_container(name):
    if not _CONTAINER_NAME_RE.match(name):
        return jsonify({"error": "invalid container name"}), 400
    if name in _load_protected():
        return jsonify({"error": "container is protected — remove protection before restarting"}), 403
    result = subprocess.run(["bash", "-c", f"docker.exe restart {name}"],
                            capture_output=True, text=True, timeout=30)
    return jsonify({"ok": result.returncode == 0, "output": result.stderr})


@app.route("/infrastructure/containers/<name>/stop", methods=["POST"])
def stop_container(name):
    if not _CONTAINER_NAME_RE.match(name):
        return jsonify({"error": "invalid container name"}), 400
    if name in _load_protected():
        return jsonify({"error": "container is protected — remove protection before stopping"}), 403
    result = subprocess.run(["bash", "-c", f"docker.exe stop {name}"],
                            capture_output=True, text=True, timeout=30)
    return jsonify({"ok": result.returncode == 0, "output": result.stderr})


@app.route("/infrastructure/containers/<name>/start", methods=["POST"])
def start_container(name):
    if not _CONTAINER_NAME_RE.match(name):
        return jsonify({"error": "invalid container name"}), 400
    result = subprocess.run(["bash", "-c", f"docker.exe start {name}"],
                            capture_output=True, text=True, timeout=30)
    return jsonify({"ok": result.returncode == 0, "output": result.stderr})


def _reconcile_sessions() -> None:
    """Drop session records whose tmux session no longer exists.

    Runs once at startup so a server restart doesn't leave stale session
    records around from tmux sessions that died while the server was down.
    """
    live = list_session_names()
    for session in list_sessions():
        if session["tmux_session"] not in live:
            _post_metric("agent.session_end", {
                "session_id": session["id"],
                "project": session.get("project", ""),
                "name": session.get("name", ""),
                "reason": "session_disappeared",
            })
            remove_session(session["id"])


@app.route("/research-sources", methods=["GET"])
def get_research_sources():
    return jsonify({"sources": list_sources()})


@app.route("/research-sources", methods=["POST"])
def create_research_source():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    label = (data.get("label") or "").strip()
    if not url or not label:
        return jsonify({"error": "url and label are required"}), 400
    source = add_source(url, label)
    if source is None:
        return jsonify({"error": "source already exists"}), 409
    return jsonify(source), 201


@app.route("/research-sources/<source_id>", methods=["PATCH"])
def toggle_research_source(source_id):
    source = find_source(source_id)
    if not source:
        abort(404)
    updated = set_blacklisted(source_id, not source["blacklisted"])
    return jsonify(updated)


if __name__ == "__main__":
    _reconcile_sessions()
    app.run(host="0.0.0.0", port=5010)
