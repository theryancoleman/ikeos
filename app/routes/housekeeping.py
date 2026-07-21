import os
import requests
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, request, jsonify

from app.routes.auth import require_capture_token
from app.services.blog_drafts import latest_draft_name, read_draft_bundle, save_draft
from app.services.capabilities import get_capabilities, is_enabled, update_capability
from app.services.driver import (
    publish_blog_draft,
    rewrite_blog_draft,
    run_housekeeping_task,
    run_platform_review,
)
from app.services.platform import project_slug
from app.services.research_findings import get_research_findings
from app.services.reviews import latest_review_name, read_latest_review
from app.services.scheduler import get_config_with_next_run, trigger_now, update_config
from app.services.session_client import get_session_status, list_active_session_names
from app.services.metrics import read_events_by_type
from app.services.vault import (
    delete_housekeeping_task,
    read_housekeeping_heartbeat,
    read_housekeeping_tasks,
)

bp = Blueprint("housekeeping", __name__)

CAPTURE_URL = os.environ.get("CAPTURE_URL", "http://host.docker.internal:5009")
CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "")


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
    if heartbeat.get("tasks_failed", "0") not in ("0", 0):
        return "failed"
    return "ok"


_STALL_THRESHOLD_MINUTES = 45
_OVERDUE_DAYS = 9


def _parse_dt(value: str | None) -> datetime | None:
    if not value or value == "null":
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _run_state(schedule: dict, heartbeat: dict) -> tuple[str, str, str]:
    """Returns (state, label, headline) describing overall housekeeping health."""
    if list_active_session_names("housekeeping-"):
        return "running", "Running", "Housekeeping is running now…"

    triggered_dt = _parse_dt(schedule.get("last_triggered"))
    last_run_dt = _parse_dt(heartbeat.get("last_run"))

    if triggered_dt is None and last_run_dt is None:
        return "never", "Never run", "Housekeeping has not run yet."

    if triggered_dt is not None and (last_run_dt is None or last_run_dt < triggered_dt):
        elapsed = datetime.now(timezone.utc) - triggered_dt
        if elapsed > timedelta(minutes=_STALL_THRESHOLD_MINUTES):
            return "stalled", "Stalled", (
                f"Triggered {_age_str(schedule.get('last_triggered'))} but never reported "
                f"completion — check session logs."
            )

    if heartbeat.get("tasks_failed", "0") not in ("0", 0):
        n = heartbeat.get("tasks_failed")
        return "failed", "Attention", f"{n} task(s) failed on the last run ({_age_str(heartbeat.get('last_run'))})."

    if last_run_dt is not None:
        if (datetime.now(timezone.utc) - last_run_dt).days > _OVERDUE_DAYS:
            return "overdue", "Overdue", f"No successful run since {_age_str(heartbeat.get('last_run'))}."

    return "ok", "Healthy", f"Last run completed successfully — {_age_str(heartbeat.get('last_run'))}."


@bp.route("/housekeeping")
def index():
    return render_template("housekeeping.html", **_housekeeping_context())


# Intentionally unauthenticated at this layer — the upstream capture API
# validates the payload. Task creation is lower-risk than mutation endpoints.
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
                "project": project_slug(),
                "title": title,
                "interval": interval,
                "success_definition": success_definition,
            },
            timeout=5,
        )
        if not resp.ok:
            return jsonify({"error": "Failed to create task"}), 502
    except requests.RequestException:
        return jsonify({"error": "IkeOS capture service unreachable"}), 502

    return jsonify({"ok": True}), 200


@bp.route("/housekeeping/tasks/<filename>/toggle", methods=["POST"])
@require_capture_token
def toggle_task(filename: str):
    tasks = read_housekeeping_tasks()
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    new_enabled = "false" if task.get("enabled") == "true" else "true"
    try:
        resp = requests.patch(
            f"{CAPTURE_URL}/entries/housekeeping",
            json={
                "project": task.get("project", project_slug()),
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
        return jsonify({"error": "IkeOS capture service unreachable"}), 502

    return jsonify({"ok": True, "enabled": new_enabled}), 200


@bp.route("/housekeeping/tasks/<filename>/reset", methods=["POST"])
@require_capture_token
def reset_task(filename: str):
    tasks = read_housekeeping_tasks()
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    try:
        resp = requests.patch(
            f"{CAPTURE_URL}/entries/housekeeping",
            json={
                "project": task.get("project", project_slug()),
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
        return jsonify({"error": "IkeOS capture service unreachable"}), 502

    return jsonify({"ok": True}), 200


@bp.route("/housekeeping/tasks/<filename>/delete", methods=["POST"])
@require_capture_token
def delete_task(filename: str):
    tasks = read_housekeeping_tasks()
    task = next((t for t in tasks if t.get("filename") == filename), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    deleted = delete_housekeeping_task(task.get("project", project_slug()), filename)
    if not deleted:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"ok": True}), 200


@bp.route("/housekeeping/tasks/<filename>/run", methods=["POST"])
@require_capture_token
def run_task(filename: str):
    result = run_housekeeping_task(filename)
    if result.already_running:
        return jsonify({"ok": True, "session_id": result.session_id, "already_running": True}), 200
    if not result.ok:
        return jsonify({"error": "Failed to create session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/housekeeping/blog-draft")
def blog_draft_editor():
    bundle = read_draft_bundle()
    if not bundle:
        return render_template("housekeeping.html", **_housekeeping_context(), no_draft=True)
    return render_template(
        "blog_draft.html",
        filename=bundle["filename"],
        content=bundle["content"],
        bluesky_text=bundle["bluesky_text"],
        bluesky_filename=bundle["bluesky_filename"],
        capture_token=CAPTURE_TOKEN,
    )


@bp.route("/housekeeping/blog-draft/save", methods=["POST"])
@require_capture_token
def blog_draft_save():
    content = request.form.get("content", "")
    bluesky_text = request.form.get("bluesky_text", "")
    try:
        filename = save_draft(content, bluesky_text)
    except FileNotFoundError:
        return jsonify({"error": "No draft found"}), 404
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "filename": filename}), 200


@bp.route("/housekeeping/blog-draft/publish", methods=["POST"])
@require_capture_token
def blog_draft_publish():
    bundle = read_draft_bundle()
    if not bundle:
        return jsonify({"error": "No draft found"}), 404
    result = publish_blog_draft(bundle["filename"], bundle["bluesky_filename"] or "")
    if not result.ok:
        return jsonify({"error": "Failed to create publish session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/housekeeping/blog-draft/rewrite", methods=["POST"])
@require_capture_token
def blog_draft_rewrite():
    bundle = read_draft_bundle()
    if not bundle:
        return jsonify({"error": "No draft found"}), 404
    feedback = request.form.get("feedback", "").strip()
    if not feedback:
        return jsonify({"error": "Feedback is required"}), 400
    result = rewrite_blog_draft(bundle["filename"], feedback)
    if result.already_running and result.ok:
        return jsonify({"ok": True, "session_id": result.session_id}), 200
    if not result.ok:
        return jsonify({"error": result.error or "Failed to create rewrite session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


def _housekeeping_context() -> dict:
    tasks = read_housekeeping_tasks()
    heartbeat = read_housekeeping_heartbeat(project_slug())
    schedule = get_config_with_next_run()
    run_state, run_state_label, run_state_headline = _run_state(schedule, heartbeat)
    findings = get_research_findings()
    return dict(
        tasks=tasks,
        heartbeat=heartbeat,
        hk_age=_age_str(heartbeat.get("last_run")),
        hk_status=_widget_status(heartbeat),
        run_state=run_state,
        run_state_label=run_state_label,
        run_state_headline=run_state_headline,
        schedule=schedule,
        capture_token=CAPTURE_TOKEN,
        blog_draft=latest_draft_name(),
        weekly_review_file=latest_review_name(),
        capabilities=get_capabilities(),
        recent_runs=read_events_by_type("housekeeping.run", limit=10),
        research_generated_at=findings["generated_at"] if findings else None,
        research_age_str=_age_str(findings["generated_at"]) if findings else None,
        research_source_count=len(findings["summaries"]) if findings else 0,
    )


@bp.route("/housekeeping/blog-draft/content")
def blog_draft_content():
    """Return current draft file content as JSON — used by JS to reload after rewrite."""
    bundle = read_draft_bundle()
    if not bundle:
        return jsonify({"error": "No draft found"}), 404
    return jsonify({
        "content": bundle["content"],
        "bluesky_text": bundle["bluesky_text"],
    })


@bp.route("/housekeeping/blog-draft/session-status")
def blog_draft_session_status():
    """Proxy session manager status for a given session_id."""
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        return jsonify({"active": False}), 200
    data = get_session_status(session_id)
    if data is None:
        return jsonify({"active": False})
    return jsonify({"active": data.get("status") == "active"})


@bp.route("/housekeeping/weekly-review")
def weekly_review():
    result = read_latest_review()
    if result is None:
        return render_template("weekly_review.html", content=None, filename=None,
                               capture_token=CAPTURE_TOKEN, capabilities=get_capabilities())
    filename, content = result
    return render_template("weekly_review.html", content=content, filename=filename,
                           capture_token=CAPTURE_TOKEN, capabilities=get_capabilities())


@bp.route("/housekeeping/weekly-review/run", methods=["POST"])
@require_capture_token
def weekly_review_run():
    if not is_enabled("weekly_platform_review"):
        return jsonify({"error": "weekly_platform_review capability is disabled"}), 403
    result = run_platform_review()
    if result.already_running:
        return jsonify({"ok": True, "session_id": result.session_id, "already_running": True}), 200
    if not result.ok:
        return jsonify({"error": "Failed to create review session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/housekeeping/research-findings")
def research_findings():
    findings = get_research_findings()
    if findings is None:
        return render_template("research_findings.html", generated_at=None, summaries=[])
    return render_template(
        "research_findings.html",
        generated_at=findings["generated_at"],
        summaries=findings["summaries"],
    )


@bp.route("/housekeeping/run", methods=["POST"])
@require_capture_token
def run_housekeeping():
    session_id = trigger_now()
    if session_id is None:
        return jsonify({"error": "Failed to start housekeeping session"}), 502
    return jsonify({"ok": True, "session_id": session_id}), 200


@bp.route("/housekeeping/run-status")
def housekeeping_run_status():
    """Poll whether a housekeeping session is still active and surface the latest heartbeat."""
    session_id = request.args.get("session_id", "").strip()
    active = False
    activity = None
    if session_id:
        data = get_session_status(session_id)
        if data is not None and data.get("status") == "active":
            active = True
            activity = data.get("activity")
    heartbeat = read_housekeeping_heartbeat(project_slug())
    return jsonify({
        "active": active,
        "activity": activity,
        "last_run": heartbeat.get("last_run"),
        "tasks_run": heartbeat.get("tasks_run", "0"),
        "tasks_failed": heartbeat.get("tasks_failed", "0"),
        "tasks_skipped": heartbeat.get("tasks_skipped", "0"),
    })


@bp.route("/housekeeping/schedule", methods=["GET"])
def get_schedule():
    return jsonify(get_config_with_next_run()), 200


@bp.route("/housekeeping/schedule", methods=["PATCH"])
@require_capture_token
def patch_schedule():
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


@bp.route("/housekeeping/capabilities")
def get_capabilities_route():
    return jsonify({"capabilities": get_capabilities()}), 200


@bp.route("/housekeeping/capabilities/<name>", methods=["PATCH"])
@require_capture_token
def patch_capability(name: str):
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = request.get_json(silent=True) or {}
    enabled_val = data.get("enabled")
    if not isinstance(enabled_val, bool):
        return jsonify({"error": "enabled must be a boolean"}), 400
    try:
        record = update_capability(name, enabled_val)
        return jsonify({"capability": record}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
