from flask import Blueprint, jsonify

from app.routes.auth import require_capture_token
from app.services import driver
from app.services.capabilities import is_enabled
from app.services.platform import project_slug
from app.services.vault import update_entry_status_generic

bp = Blueprint("council", __name__)


@bp.route("/council/<slug>/discuss", methods=["POST"])
@require_capture_token
def discuss(slug):
    if not is_enabled("council_pipeline"):
        return jsonify({"error": "council_pipeline capability is disabled"}), 403
    update_entry_status_generic("council-item", project_slug(), slug, "in-discussion")
    result = driver.run_council_discuss(slug)
    if not result.ok:
        return jsonify({"error": result.error or "Failed to create discuss session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/council/<slug>/approve", methods=["POST"])
@require_capture_token
def approve(slug):
    if not is_enabled("council_pipeline"):
        return jsonify({"error": "council_pipeline capability is disabled"}), 403
    update_entry_status_generic("council-item", project_slug(), slug, "approved")
    result = driver.run_council_action(slug)
    if not result.ok:
        return jsonify({"error": result.error or "Failed to create action session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/council/<slug>/decline", methods=["POST"])
@require_capture_token
def decline(slug):
    if not is_enabled("council_pipeline"):
        return jsonify({"error": "council_pipeline capability is disabled"}), 403
    success = update_entry_status_generic("council-item", project_slug(), slug, "declined")
    if not success:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"ok": True}), 200
