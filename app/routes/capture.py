import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.services.vault import get_projects_with_meta, write_entry, update_entry_status_generic, update_housekeeping_fields
from app.services.umbrella import get_components

bp = Blueprint("capture", __name__)


def _get_capture_token():
    """Get CAPTURE_TOKEN from environment, return None if unset."""
    return os.environ.get("CAPTURE_TOKEN")


def _validate_token(token):
    """Validate the provided token against CAPTURE_TOKEN. Return (is_valid, status_code)."""
    env_token = _get_capture_token()
    if env_token is None:
        return False, 503  # Service unavailable - token not configured
    if token != env_token:
        return False, 401  # Unauthorized
    return True, 200


def _reject_path_traversal(filename):
    """Check if filename contains path separators or traversal patterns. Return True if safe."""
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    return True


@bp.route("/capture", methods=["GET"])
def capture_form():
    projects = get_projects_with_meta()
    for p in projects:
        p["components"] = get_components(p["slug"])
    selected_project = request.args.get("project", "")
    return render_template("capture.html", projects=projects, selected_project=selected_project)


@bp.route("/capture", methods=["POST"])
def capture_submit():
    entry_type = request.form["type"]
    data = {
        "type": entry_type,
        "title": request.form["title"],
        "body": request.form.get("body", ""),
        "domains": request.form.getlist("domains"),
    }

    # Decision entries don't require a project in the form
    if entry_type == "decision":
        project = request.form.get("project", "")
        if project:
            data["project"] = project
    else:
        project = request.form["project"]
        if project == "__future__":
            project = request.form.get("future_project_name", "").strip() or "future"
        data["project"] = project
        component = request.form.get("component", "").strip() or None
        if component:
            data["component"] = component

    if entry_type == "idea":
        data["priority"] = request.form.get("priority", "medium")
        data["effort"] = request.form.get("effort", "medium")
    elif entry_type == "bug":
        data["severity"] = request.form.get("severity", "medium")
        data["steps"] = request.form.get("steps", "")

    write_entry(data)
    flash("Saved. The vault remembers.")

    if request.form.get("stay") == "1":
        return redirect(url_for("capture.capture_form", project=project if entry_type != "decision" else ""))
    return redirect(url_for("browse.tasks"))


@bp.route("/entries", methods=["PATCH"])
def patch_entries():
    """Update entry status via PATCH with token authentication."""
    # Extract token from header
    token = request.headers.get("X-Capture-Token", "")
    is_valid, status_code = _validate_token(token)
    if not is_valid:
        return jsonify({"error": "Unauthorized" if status_code == 401 else "Service unavailable"}), status_code

    # Parse request data (form or JSON)
    if request.is_json:
        req_data = request.get_json()
    else:
        req_data = request.form.to_dict()

    # Extract parameters
    project = req_data.get("project", "").strip()
    entry_type = req_data.get("type", "").strip()
    filename = req_data.get("filename", "").strip()
    status = req_data.get("status", "").strip()

    # Validate path traversal
    if not _reject_path_traversal(filename):
        return jsonify({"error": "Invalid filename"}), 400

    # Validate entry_type
    if entry_type not in ("bug", "idea", "note", "decision", "grill-me"):
        return jsonify({"error": "Invalid entry type"}), 400

    # Validate status against the lifecycle for this entry type
    valid_statuses = (
        ("proposed", "accepted", "rejected", "superseded")
        if entry_type == "decision"
        else ("new", "open", "in-progress", "done", "deferred")
    )
    if status not in valid_statuses:
        return jsonify({"error": f"Invalid status for {entry_type}"}), 400

    # For decisions, project is optional
    if entry_type == "decision":
        if not project:
            project = None  # Will be checked in update function
    else:
        if not project:
            return jsonify({"error": "Project required for this entry type"}), 400

    # Attempt to update
    success = update_entry_status_generic(entry_type, project, filename, status)
    if not success:
        return jsonify({"error": "Entry not found or invalid status"}), 404

    return jsonify({"message": "Status updated"}), 200


@bp.route("/entries/housekeeping", methods=["PATCH"])
def patch_housekeeping():
    """Update housekeeping runtime fields. JSON body only."""
    token = request.headers.get("X-Capture-Token", "")
    is_valid, status_code = _validate_token(token)
    if not is_valid:
        return jsonify({"error": "Unauthorized" if status_code == 401 else "Service unavailable"}), status_code

    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    req_data = request.get_json(silent=True)
    if req_data is None:
        return jsonify({"error": "Invalid or empty JSON body"}), 400
    project = req_data.get("project", "").strip()
    entry_type = req_data.get("type", "").strip()
    filename = req_data.get("filename", "").strip()
    fields = req_data.get("fields")

    if not isinstance(fields, dict) or not fields:
        return jsonify({"error": "fields must be a non-empty object"}), 400

    if not _reject_path_traversal(filename):
        return jsonify({"error": "Invalid filename"}), 400

    if entry_type not in ("housekeeping-task", "housekeeping-heartbeat"):
        return jsonify({"error": "type must be housekeeping-task or housekeeping-heartbeat"}), 400

    if not project:
        return jsonify({"error": "project is required"}), 400

    success = update_housekeeping_fields(entry_type, project, filename, fields)
    if not success:
        return jsonify({"error": "Entry not found or no valid fields provided"}), 404

    return jsonify({"message": "Updated"}), 200


@bp.route("/capture/json", methods=["POST"])
def capture_json():
    req = request.get_json(silent=True) or {}
    entry_type = req.get("type", "")
    project = req.get("project", "")
    title = req.get("title", "")

    if not title:
        return jsonify({"error": "title is required"}), 400
    if entry_type not in ("note", "idea", "bug", "grill-me", "housekeeping-task", "housekeeping-heartbeat"):
        return jsonify({"error": "type must be note, idea, bug, grill-me, housekeeping-task, or housekeeping-heartbeat"}), 400
    if not project:
        return jsonify({"error": "project is required"}), 400

    data = {
        "type": entry_type,
        "project": project,
        "title": title,
        "body": req.get("body", ""),
        "domains": [],
    }
    component = req.get("component", "").strip() or None
    if component:
        data["component"] = component
    if entry_type == "idea":
        data["priority"] = req.get("priority", "medium")
        data["effort"] = req.get("effort", "medium")
    elif entry_type == "bug":
        data["severity"] = req.get("severity", "medium")
        data["steps"] = req.get("steps", "")
    elif entry_type == "housekeeping-task":
        data["interval"] = req.get("interval", "weekly")
        data["success_definition"] = req.get("success_definition", "")

    write_entry(data)
    return jsonify({"ok": True}), 200
