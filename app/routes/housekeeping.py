import os
import requests
from datetime import datetime
from pathlib import Path

from flask import Blueprint, render_template, request, jsonify

from app.services.scheduler import get_config_with_next_run, update_config

bp = Blueprint("housekeeping", __name__)

CAPTURE_URL = os.environ.get("CAPTURE_URL", "http://host.docker.internal:5009")
CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "")
SESSION_MANAGER_URL = os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")
HOUSEKEEPING_PROJECT_DIR = os.environ.get("HOUSEKEEPING_PROJECT_DIR", "/mnt/c/Server/claude-config")
AIOS_BLOG_POSTS_DIR = os.environ.get("AIOS_BLOG_POSTS_DIR", "")
AIOS_BLOG_PROJECT_DIR = os.environ.get("AIOS_BLOG_PROJECT_DIR", "")


def _blog_draft_paths() -> tuple[Path | None, Path | None]:
    """Return (draft_path, bluesky_path) for the latest weekly draft."""
    posts_dir = Path(AIOS_BLOG_POSTS_DIR)
    if not posts_dir.exists():
        return None, None
    drafts = sorted(posts_dir.glob("*-weekly-draft.md"), reverse=True)
    if not drafts:
        return None, None
    draft = drafts[0]
    bluesky = draft.with_name(draft.stem.replace("-weekly-draft", "-weekly-bluesky") + ".txt")
    return draft, bluesky if bluesky.exists() else None


def _latest_blog_draft() -> str | None:
    draft, _ = _blog_draft_paths()
    return draft.name if draft else None


def _capture_headers() -> dict:
    return {"X-Capture-Token": CAPTURE_TOKEN}


def _age_str(last_run: str | None) -> str:
    if not last_run or last_run == "null":
        return "Never"
    try:
        dt = datetime.fromisoformat(last_run)
        days = (datetime.now() - dt.replace(tzinfo=None)).days
        if days == 0:
            return "Today"
        if days == 1:
            return "Yesterday"
        return f"{days} days ago"
    except (ValueError, TypeError):
        return "Unknown"


def _widget_status(heartbeat: dict) -> str:
    last_run = heartbeat.get("last_run")
    if not last_run:
        return "overdue"
    try:
        dt = datetime.fromisoformat(last_run)
        if (datetime.now() - dt.replace(tzinfo=None)).days > 9:
            return "overdue"
    except (ValueError, TypeError):
        return "overdue"
    if heartbeat.get("tasks_failed", "0") != "0":
        return "failed"
    return "ok"


def _check_auth() -> tuple[bool, int]:
    if not CAPTURE_TOKEN:
        return False, 503
    if request.headers.get("X-Capture-Token", "") != CAPTURE_TOKEN:
        return False, 401
    return True, 200


@bp.route("/housekeeping")
def index():
    return render_template("housekeeping.html", **_housekeeping_context())


@bp.route("/housekeeping/tasks", methods=["POST"])
def create_task():
    title = request.form.get("title", "").strip()
    interval = request.form.get("interval", "weekly")
    success_definition = request.form.get("success_definition", "").strip()

    if not title or not success_definition:
        return jsonify({"error": "title and success_definition are required"}), 400
    if interval not in ("weekly", "monthly", "quarterly", "annually"):
        return jsonify({"error": "invalid interval"}), 400

    try:
        resp = requests.post(
            f"{CAPTURE_URL}/capture/json",
            json={
                "type": "housekeeping-task",
                "project": "claude-config",
                "title": title,
                "interval": interval,
                "success_definition": success_definition,
            },
            timeout=5,
        )
        if not resp.ok:
            return jsonify({"error": "Failed to create task"}), 502
    except requests.RequestException:
        return jsonify({"error": "obsidian-capture unreachable"}), 502

    return jsonify({"ok": True}), 200


@bp.route("/housekeeping/tasks/<filename>/toggle", methods=["POST"])
def toggle_task(filename: str):
    from app.services.vault import read_housekeeping_tasks
    tasks = read_housekeeping_tasks()
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    new_enabled = "false" if task.get("enabled") == "true" else "true"
    try:
        resp = requests.patch(
            f"{CAPTURE_URL}/entries/housekeeping",
            json={
                "project": task.get("project", "claude-config"),
                "type": "housekeeping-task",
                "filename": filename,
                "fields": {"enabled": new_enabled},
            },
            headers=_capture_headers(),
            timeout=5,
        )
        if not resp.ok:
            return jsonify({"error": "Failed to update task"}), 502
    except requests.RequestException:
        return jsonify({"error": "obsidian-capture unreachable"}), 502

    return jsonify({"ok": True, "enabled": new_enabled}), 200


@bp.route("/housekeeping/tasks/<filename>/reset", methods=["POST"])
def reset_task(filename: str):
    from app.services.vault import read_housekeeping_tasks
    tasks = read_housekeeping_tasks()
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    try:
        resp = requests.patch(
            f"{CAPTURE_URL}/entries/housekeeping",
            json={
                "project": task.get("project", "claude-config"),
                "type": "housekeeping-task",
                "filename": filename,
                "fields": {"last_run": "null", "consecutive_failures": "0"},
            },
            headers=_capture_headers(),
            timeout=5,
        )
        if not resp.ok:
            return jsonify({"error": "Failed to reset timer"}), 502
    except requests.RequestException:
        return jsonify({"error": "obsidian-capture unreachable"}), 502

    return jsonify({"ok": True}), 200


@bp.route("/housekeeping/tasks/<filename>/delete", methods=["POST"])
def delete_task(filename: str):
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    from app.services.vault import read_housekeeping_tasks, delete_housekeeping_task
    tasks = read_housekeeping_tasks()
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    deleted = delete_housekeeping_task(task.get("project", "claude-config"), filename)
    if not deleted:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"ok": True}), 200


@bp.route("/housekeeping/tasks/<filename>/run", methods=["POST"])
def run_task(filename: str):
    import re as _re
    session_name = f"housekeeping-{filename}"
    slug = _re.sub(r"^\d{4}-\d{2}-\d{2}-", "", filename)
    command = f"/housekeeping run {slug}"
    try:
        create_resp = requests.post(
            f"{SESSION_MANAGER_URL}/sessions",
            json={
                "name": session_name,
                "project": "claude-config",
                "project_dir": HOUSEKEEPING_PROJECT_DIR,
                "initial_command": command,
            },
            timeout=5,
        )
        if create_resp.status_code == 409:
            body = create_resp.json()
            existing = body.get("session", {})
            session_id = existing.get("id")
            return jsonify({"ok": True, "session_id": session_id, "already_running": True}), 200
        if not create_resp.ok:
            return jsonify({"error": "Failed to create session"}), 502
        session_id = create_resp.json().get("id")
        if not session_id:
            return jsonify({"error": "No session ID returned"}), 502
    except requests.RequestException:
        return jsonify({"error": "Session manager unreachable"}), 502

    return jsonify({"ok": True, "session_id": session_id}), 200


@bp.route("/housekeeping/blog-draft")
def blog_draft_editor():
    draft, bluesky = _blog_draft_paths()
    if not draft:
        return render_template("housekeeping.html", **_housekeeping_context(), no_draft=True)
    return render_template(
        "blog_draft.html",
        filename=draft.name,
        content=draft.read_text(encoding="utf-8"),
        bluesky_text=(bluesky.read_text(encoding="utf-8") if bluesky else ""),
        bluesky_filename=(bluesky.name if bluesky else ""),
    )


@bp.route("/housekeeping/blog-draft/save", methods=["POST"])
def blog_draft_save():
    draft, bluesky = _blog_draft_paths()
    if not draft:
        return jsonify({"error": "No draft found"}), 404
    content = request.form.get("content", "")
    bluesky_text = request.form.get("bluesky_text", "")
    try:
        draft.write_text(content, encoding="utf-8")
        if bluesky and bluesky_text:
            bluesky.write_text(bluesky_text, encoding="utf-8")
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "filename": draft.name}), 200


@bp.route("/housekeeping/blog-draft/publish", methods=["POST"])
def blog_draft_publish():
    draft, bluesky = _blog_draft_paths()
    if not draft:
        return jsonify({"error": "No draft found"}), 404
    if not AIOS_BLOG_PROJECT_DIR:
        return jsonify({"error": "AIOS_BLOG_PROJECT_DIR not configured"}), 503
    bluesky_file = bluesky.name if bluesky else ""
    command = (
        f"Run `bash deploy.sh content/posts/{draft.name}` in {AIOS_BLOG_PROJECT_DIR}. "
        f"The Bluesky companion text is in content/posts/{bluesky_file}. "
        "Build the Hugo site, deploy via rsync, and post to Bluesky."
    )
    try:
        resp = requests.post(
            f"{SESSION_MANAGER_URL}/sessions",
            json={
                "name": f"blog-publish-{draft.stem[:30]}",
                "project": "aios-blog",
                "project_dir": AIOS_BLOG_PROJECT_DIR,
                "initial_command": command,
            },
            timeout=5,
        )
        if not resp.ok:
            return jsonify({"error": "Failed to create publish session"}), 502
        return jsonify({"ok": True, "session_id": resp.json().get("id")}), 200
    except requests.RequestException:
        return jsonify({"error": "Session manager unreachable"}), 502


@bp.route("/housekeeping/blog-draft/rewrite", methods=["POST"])
def blog_draft_rewrite():
    draft, _ = _blog_draft_paths()
    if not draft:
        return jsonify({"error": "No draft found"}), 404
    if not AIOS_BLOG_PROJECT_DIR:
        return jsonify({"error": "AIOS_BLOG_PROJECT_DIR not configured"}), 503
    feedback = request.form.get("feedback", "").strip()
    if not feedback:
        return jsonify({"error": "Feedback is required"}), 400
    command = (
        f"Rewrite the blog draft at content/posts/{draft.name} based on this feedback: "
        f"{feedback} — keep the same frontmatter, voice, and section structure from the /blog skill. "
        "Overwrite the file in place when done."
    )
    try:
        resp = requests.post(
            f"{SESSION_MANAGER_URL}/sessions",
            json={
                "name": f"blog-rewrite-{draft.stem[:30]}",
                "project": "aios-blog",
                "project_dir": AIOS_BLOG_PROJECT_DIR,
                "initial_command": command,
            },
            timeout=5,
        )
        if resp.status_code == 409:
            # Session already running — send feedback directly to it
            existing = resp.json().get("session", {})
            session_id = existing.get("id")
            cmd_resp = requests.post(
                f"{SESSION_MANAGER_URL}/sessions/{session_id}/command",
                json={"command": command},
                timeout=5,
            )
            if not cmd_resp.ok:
                return jsonify({"error": "Rewrite session running but failed to send command"}), 502
            return jsonify({"ok": True, "session_id": session_id}), 200
        if not resp.ok:
            return jsonify({"error": "Failed to create rewrite session"}), 502
        return jsonify({"ok": True, "session_id": resp.json().get("id")}), 200
    except requests.RequestException:
        return jsonify({"error": "Session manager unreachable"}), 502


def _housekeeping_context() -> dict:
    from app.services.vault import read_housekeeping_tasks, read_housekeeping_heartbeat
    tasks = read_housekeeping_tasks()
    heartbeat = read_housekeeping_heartbeat("claude-config")
    schedule = get_config_with_next_run()
    return dict(
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
        schedule=schedule,
        capture_token=CAPTURE_TOKEN,
        blog_draft=_latest_blog_draft(),
    )


@bp.route("/housekeeping/blog-draft/content")
def blog_draft_content():
    """Return current draft file content as JSON — used by JS to reload after rewrite."""
    draft, bluesky = _blog_draft_paths()
    if not draft:
        return jsonify({"error": "No draft found"}), 404
    return jsonify({
        "content": draft.read_text(encoding="utf-8"),
        "bluesky_text": bluesky.read_text(encoding="utf-8") if bluesky else "",
    })


@bp.route("/housekeeping/blog-draft/session-status")
def blog_draft_session_status():
    """Proxy session manager status for a given session_id."""
    session_id = request.args.get("session_id", "").strip()
    if not session_id or not SESSION_MANAGER_URL:
        return jsonify({"active": False}), 200
    try:
        resp = requests.get(f"{SESSION_MANAGER_URL}/sessions/{session_id}", timeout=3)
        if resp.status_code == 404:
            return jsonify({"active": False})
        data = resp.json()
        return jsonify({"active": data.get("status") == "active"})
    except requests.RequestException:
        return jsonify({"active": False})


@bp.route("/housekeeping/schedule", methods=["GET"])
def get_schedule():
    return jsonify(get_config_with_next_run()), 200


@bp.route("/housekeeping/schedule", methods=["PATCH"])
def patch_schedule():
    ok, status = _check_auth()
    if not ok:
        return jsonify({"error": "Unauthorized" if status == 401 else "Service unavailable"}), status
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid or empty JSON body"}), 400
    allowed = {"enabled", "day_of_week", "hour", "minute"}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({"error": "No valid fields provided"}), 400
    try:
        update_config(fields)
        return jsonify(get_config_with_next_run()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
