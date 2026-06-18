import os
import requests
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify

bp = Blueprint("housekeeping", __name__)

CAPTURE_URL = os.environ.get("CAPTURE_URL", "http://host.docker.internal:5009")
CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "")
SESSION_MANAGER_URL = "http://host.docker.internal:5010"


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


@bp.route("/housekeeping")
def index():
    from app.services.vault import read_housekeeping_tasks, read_housekeeping_heartbeat
    tasks = read_housekeeping_tasks("claude-config")
    heartbeat = read_housekeeping_heartbeat("claude-config")
    return render_template(
        "housekeeping.html",
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
    )
