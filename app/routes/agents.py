import re
import requests
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request

from app.routes.auth import require_capture_token
from app.services.metrics import append_event, read_events
from app.services.session_client import session_manager_url

bp = Blueprint("agents", __name__)

_CONTAINER_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]+$')


def _proxy(method: str, path: str, **kwargs):
    url = f"{session_manager_url()}{path}"
    resp = requests.request(method, url, timeout=5, **kwargs)
    return resp.json(), resp.status_code


def _age_str(started_at: str | None) -> str:
    if not started_at:
        return "—"
    try:
        started = datetime.fromisoformat(started_at)
        delta = datetime.utcnow() - started
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return "—"


@bp.route("/")
def home():
    return render_template("loading.html")


@bp.route("/dashboard")
def dashboard():
    try:
        sessions, _ = _proxy("GET", "/sessions")
        for s in sessions:
            s["age_str"] = _age_str(s.get("started_at"))
    except Exception:
        sessions = []

    from app.services.vault import get_projects_with_meta
    projects = get_projects_with_meta()
    return render_template("workspace.html", sessions=sessions,
                           projects=projects, three_col=True)


@bp.route("/agents")
def agents():
    try:
        sessions, _ = _proxy("GET", "/sessions")
        for s in sessions:
            s["age_str"] = _age_str(s.get("started_at"))
    except Exception:
        sessions = []

    from app.services.vault import get_projects_with_meta
    projects = get_projects_with_meta()
    return render_template("workspace.html", sessions=sessions,
                           projects=projects, three_col=False)


@bp.route("/agents/sessions", methods=["GET"])
def list_sessions():
    data, status = _proxy("GET", "/sessions")
    return jsonify(data), status


@bp.route("/agents/sessions", methods=["POST"])
def create_session():
    data, status = _proxy("POST", "/sessions", json=request.get_json())
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>", methods=["DELETE"])
def stop_session(session_id):
    data, status = _proxy("DELETE", f"/sessions/{session_id}")
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>/remove", methods=["DELETE"])
def remove_session(session_id):
    data, status = _proxy("DELETE", f"/sessions/{session_id}/remove")
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>/reset", methods=["POST"])
def reset_session(session_id):
    data, status = _proxy("POST", f"/sessions/{session_id}/reset")
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>/remote_control", methods=["PATCH"])
def toggle_remote_control(session_id):
    data, status = _proxy("PATCH", f"/sessions/{session_id}/remote_control")
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>/autonomous_mode", methods=["PATCH"])
def toggle_autonomous_mode(session_id):
    data, status = _proxy("PATCH", f"/sessions/{session_id}/autonomous_mode")
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>/remote_control_state", methods=["PATCH"])
def correct_remote_control_state(session_id):
    data, status = _proxy("PATCH", f"/sessions/{session_id}/remote_control_state",
                          json=request.get_json())
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>/command", methods=["POST"])
def send_command(session_id):
    data, status = _proxy("POST", f"/sessions/{session_id}/command",
                          json=request.get_json())
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>/rename", methods=["POST"])
def rename_session(session_id):
    data, status = _proxy("POST", f"/sessions/{session_id}/rename",
                          json=request.get_json())
    return jsonify(data), status


@bp.route("/agents/sessions/<session_id>/pane")
def session_pane(session_id):
    data, status = _proxy("GET", f"/sessions/{session_id}/pane")
    return jsonify(data), status


@bp.route("/status")
def status_page():
    try:
        data, _ = _proxy("GET", "/infrastructure")
    except Exception:
        data = {"containers": [], "machines": []}
    return render_template("infrastructure.html", infra=data)


@bp.route("/infrastructure/containers/<name>/restart", methods=["POST"])
def infra_restart_container(name):
    if not _CONTAINER_NAME_RE.match(name):
        return jsonify({"error": "invalid container name"}), 400
    data, status = _proxy("POST", f"/infrastructure/containers/{name}/restart")
    return jsonify(data), status


@bp.route("/infrastructure/containers/<name>/stop", methods=["POST"])
def infra_stop_container(name):
    if not _CONTAINER_NAME_RE.match(name):
        return jsonify({"error": "invalid container name"}), 400
    data, status = _proxy("POST", f"/infrastructure/containers/{name}/stop")
    return jsonify(data), status


@bp.route("/infrastructure/containers/<name>/start", methods=["POST"])
def infra_start_container(name):
    if not _CONTAINER_NAME_RE.match(name):
        return jsonify({"error": "invalid container name"}), 400
    data, status = _proxy("POST", f"/infrastructure/containers/{name}/start")
    return jsonify(data), status


@bp.route("/infrastructure/containers/<name>/protection", methods=["PATCH"])
def infra_toggle_protection(name):
    if not _CONTAINER_NAME_RE.match(name):
        return jsonify({"error": "invalid container name"}), 400
    data, status = _proxy("PATCH", f"/infrastructure/containers/{name}/protection")
    return jsonify(data), status


@bp.route("/metrics")
def metrics_view() -> str:
    from app.services.capabilities import get_capabilities
    events = read_events(limit=50)
    capabilities = get_capabilities()
    return render_template("metrics.html", events=events, capabilities=capabilities)


@bp.route("/metrics/event", methods=["POST"])
@require_capture_token
def metrics_event() -> tuple:
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400
    data = dict(request.get_json(silent=True) or {})
    event_type = data.pop("event", None)
    if not event_type:
        return jsonify({"error": "event field required"}), 400
    ok = append_event(event_type, data)
    if not ok:
        return jsonify({"error": "Failed to write event"}), 500
    return jsonify({"ok": True}), 200
