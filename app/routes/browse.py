from flask import Blueprint, render_template, request, abort
from app.services.vault import get_projects, read_entries, read_entry

bp = Blueprint("browse", __name__)

ACTIVE_STATUSES = ["new", "open", "in-progress"]


@bp.route("/")
def dashboard():
    entries = read_entries()[:50]
    return render_template("dashboard.html", entries=entries)


@bp.route("/projects/<name>")
def project(name):
    show_all = request.args.get("show_all") == "true"
    status_filter = None if show_all else ACTIVE_STATUSES
    entries = read_entries(project=name, status_filter=status_filter)

    bugs = [e for e in entries if e.get("type") == "bug"]
    ideas = [e for e in entries if e.get("type") == "idea"]
    notes = [e for e in entries if e.get("type") == "note"]

    return render_template(
        "project.html",
        name=name,
        bugs=bugs,
        ideas=ideas,
        notes=notes,
        show_all=show_all,
        projects=get_projects(),
    )


@bp.route("/projects/<name>/<slug>")
def entry(name, slug):
    e = read_entry(name, slug)
    if e is None:
        abort(404)
    return render_template("entry.html", entry=e, project=name)
