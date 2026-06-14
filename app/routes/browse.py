from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from app.services.vault import (
    get_projects_with_meta, read_entries, read_entry,
    update_entry_status, write_project_meta,
    get_vault_graph,
)
from app.services.umbrella import get_components
from app.services.skills import get_skills_by_category

bp = Blueprint("browse", __name__)

ACTIVE_STATUSES = ["new", "open", "in-progress"]


@bp.route("/tasks")
def tasks():
    projects = get_projects_with_meta()
    all_entries = read_entries()

    project_stats = {}
    for p in projects:
        slug = p["slug"]
        p_entries = [e for e in all_entries if e.get("project") == slug]
        active = [e for e in p_entries if e.get("status") in ACTIVE_STATUSES]
        project_stats[slug] = {
            "bugs": len([e for e in active if e.get("type") == "bug"]),
            "ideas": len([e for e in active if e.get("type") == "idea"]),
            "notes": len([e for e in active if e.get("type") == "note"]),
            "new": len([e for e in p_entries if e.get("status") == "new"]),
        }

    in_flight = [e for e in all_entries if e.get("status") == "in-progress"]
    needs_triage = [e for e in all_entries if e.get("status") == "new"]

    return render_template(
        "dashboard.html",
        projects=projects,
        project_stats=project_stats,
        in_flight=in_flight,
        needs_triage=needs_triage,
    )


@bp.route("/projects/<name>")
def project(name):
    show_all = request.args.get("show_all") == "true"
    component_filter = request.args.get("component", "").strip() or None
    status_filter = None if show_all else ACTIVE_STATUSES
    entries = read_entries(project=name, status_filter=status_filter, component=component_filter)

    bugs = [e for e in entries if e.get("type") == "bug"]
    ideas = [e for e in entries if e.get("type") == "idea"]
    notes = [e for e in entries if e.get("type") == "note"]

    all_projects = get_projects_with_meta(include_hidden=True)
    project_meta = next((p for p in all_projects if p["slug"] == name), None)
    display_name = project_meta["name"] if project_meta else name
    visible_projects = [p for p in all_projects if not p["hidden"]]
    components = get_components(name)

    return render_template(
        "project.html",
        name=name,
        display_name=display_name,
        bugs=bugs,
        ideas=ideas,
        notes=notes,
        show_all=show_all,
        projects=visible_projects,
        components=components,
        active_component=component_filter,
    )


@bp.route("/projects/<name>/<slug>")
def entry(name, slug):
    e = read_entry(name, slug)
    if e is None:
        abort(404)
    return render_template("entry.html", entry=e, project=name)


@bp.route("/projects/<name>/<slug>/status", methods=["POST"])
def update_status(name, slug):
    new_status = request.form.get("status", "")
    success = update_entry_status(name, slug, new_status)
    flash("Status updated." if success else "Could not update status.")
    next_url = request.form.get("next") or url_for("browse.project", name=name)
    return redirect(next_url)


@bp.route("/settings")
def settings():
    projects = get_projects_with_meta(include_hidden=True)
    return render_template("settings.html", projects=projects)


@bp.route("/projects/<slug>/settings", methods=["POST"])
def update_project_settings(slug):
    valid_slugs = {p["slug"] for p in get_projects_with_meta(include_hidden=True)}
    if slug not in valid_slugs:
        abort(404)
    name = request.form.get("name", "").strip() or slug
    description = request.form.get("description", "").strip()
    hidden = request.form.get("hidden") == "on"
    success = write_project_meta(slug, name, description, hidden)
    if success:
        flash(f"'{name}' settings saved.")
    else:
        flash(f"Could not save settings for '{slug}'.")
    return redirect(url_for("browse.settings"))


@bp.route("/skills")
def skills():
    categories = get_skills_by_category()
    return render_template("skills.html", categories=categories)


@bp.route("/graph")
def graph():
    return render_template("graph.html")


@bp.route("/api/graph")
def api_graph():
    return jsonify(get_vault_graph())
