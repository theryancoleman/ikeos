import requests
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request

bp = Blueprint("agents", __name__)

SESSION_MANAGER_URL = "http://host.docker.internal:5010"


def _proxy(method: str, path: str, **kwargs):
    url = f"{SESSION_MANAGER_URL}{path}"
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


@bp.route("/agents/sessions/<session_id>/pane")
def session_pane(session_id):
    data, status = _proxy("GET", f"/sessions/{session_id}/pane")
    return jsonify(data), status
