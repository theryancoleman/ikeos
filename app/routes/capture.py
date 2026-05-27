from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.services.vault import get_projects, write_entry

bp = Blueprint("capture", __name__)


@bp.route("/capture", methods=["GET"])
def capture_form():
    projects = get_projects()
    return render_template("capture.html", projects=projects)


@bp.route("/capture", methods=["POST"])
def capture_submit():
    entry_type = request.form["type"]
    data = {
        "type": entry_type,
        "project": request.form["project"],
        "title": request.form["title"],
        "body": request.form.get("body", ""),
    }
    if entry_type == "idea":
        data["priority"] = request.form.get("priority", "medium")
        data["effort"] = request.form.get("effort", "medium")
    elif entry_type == "bug":
        data["severity"] = request.form.get("severity", "medium")
        data["steps"] = request.form.get("steps", "")

    write_entry(data)
    flash("Entry saved.")
    return redirect(url_for("browse.dashboard"))
