import os

from flask import Blueprint, jsonify, render_template, request

from app.routes.auth import require_capture_token
from app.services.capabilities import get_capabilities, is_enabled
from app.services.driver import run_eval_suite
from app.services.eval_results import read_last_run
from app.services.session_client import get_session_status

bp = Blueprint("evals", __name__)

CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "")


@bp.route("/evals")
def index():
    last_run = read_last_run()
    return render_template(
        "evals.html",
        last_run=last_run,
        capabilities=get_capabilities(),
        capture_token=CAPTURE_TOKEN,
    )


@bp.route("/evals/run", methods=["POST"])
@require_capture_token
def run():
    if not is_enabled("eval_suite_trigger"):
        return jsonify({"error": "eval_suite_trigger capability is disabled"}), 403
    result = run_eval_suite()
    if result.already_running:
        return jsonify({"ok": True, "session_id": result.session_id, "already_running": True}), 200
    if not result.ok:
        return jsonify({"error": "Failed to start eval suite session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/evals/session-status")
def session_status():
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        return jsonify({"active": False}), 200
    data = get_session_status(session_id)
    if data is None:
        return jsonify({"active": False})
    return jsonify({"active": data.get("status") == "active"})
