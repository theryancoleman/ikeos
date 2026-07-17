from flask import Blueprint, jsonify, render_template, request

from app.services.session_client import (
    add_research_source,
    list_research_sources,
    toggle_research_source,
)

bp = Blueprint("research_sources", __name__)


@bp.route("/research-sources")
def index():
    result = list_research_sources()
    return render_template(
        "research_sources.html",
        sources=result.sources or [],
        error=result.error,
    )


@bp.route("/research-sources", methods=["POST"])
def add():
    url = request.form.get("url", "").strip()
    label = request.form.get("label", "").strip()
    if not url or not label:
        return jsonify({"error": "url and label are required"}), 400

    result = add_research_source(url=url, label=label)
    if not result.ok:
        status = 502 if result.error == "Session manager unreachable" else 400
        return jsonify({"error": result.error}), status
    return jsonify({"ok": True, "source": result.source}), 201


@bp.route("/research-sources/<source_id>/toggle", methods=["POST"])
def toggle(source_id: str):
    result = toggle_research_source(source_id)
    if not result.ok:
        status = 502 if result.error == "Session manager unreachable" else 404
        return jsonify({"error": result.error}), status
    return jsonify({"ok": True, "source": result.source}), 200
