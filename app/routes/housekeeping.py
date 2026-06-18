import os
import requests
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify

from app.services.scheduler import get_config_with_next_run, update_config

bp = Blueprint("housekeeping", __name__)

CAPTURE_URL = os.environ.get("CAPTURE_URL", "http://host.docker.internal:5009")
CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "")
SESSION_MANAGER_URL = os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")


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
    from app.services.vault import read_housekeeping_tasks, read_housekeeping_heartbeat
    tasks = read_housekeeping_tasks("claude-config")
    heartbeat = read_housekeeping_heartbeat("claude-config")
    schedule = get_config_with_next_run()
    return render_template(
        "housekeeping.html",
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
        schedule=schedule,
    )


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
    tasks = read_housekeeping_tasks("claude-config")
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    new_enabled = "false" if task.get("enabled") == "true" else "true"
    try:
        resp = requests.patch(
            f"{CAPTURE_URL}/entries/housekeeping",
            json={
                "project": "claude-config",
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
    tasks = read_housekeeping_tasks("claude-config")
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    try:
        resp = requests.patch(
            f"{CAPTURE_URL}/entries/housekeeping",
            json={
                "project": "claude-config",
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


@bp.route("/housekeeping/tasks/<filename>/run", methods=["POST"])
def run_task(filename: str):
    session_name = f"housekeeping-{filename}"
    command = f"/housekeeping run in scheduled mode {filename}"
    try:
        create_resp = requests.post(
            f"{SESSION_MANAGER_URL}/sessions",
            json={"name": session_name},
            timeout=5,
        )
        if not create_resp.ok:
            return jsonify({"error": "Failed to create session"}), 502
        session_id = create_resp.json().get("id")
        if not session_id:
            return jsonify({"error": "No session ID returned"}), 502

        cmd_resp = requests.post(
            f"{SESSION_MANAGER_URL}/sessions/{session_id}/command",
            json={"command": command},
            timeout=5,
        )
        if not cmd_resp.ok:
            return jsonify({"error": "Session created but command failed"}), 502
    except requests.RequestException:
        return jsonify({"error": "Session manager unreachable"}), 502

    return jsonify({"ok": True, "session_id": session_id}), 200


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
