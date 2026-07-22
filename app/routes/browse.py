from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from app.services.vault import (
    get_projects_with_meta, read_entries, read_entry,
    update_entry_status, write_project_meta,
    get_vault_graph, read_housekeeping_heartbeat,
    project_health_signals, ENTRY_TYPE_CONFIG, DECISION_STATUSES,
)
from app.services.umbrella import get_components
from app.services.skills import get_skills_by_category
from app.services.blog_drafts import latest_draft_name
from app.services.platform import project_slug
from app.services.reflection import get_reflection_health, get_weak_signals

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
            "grill_me": len([e for e in active if e.get("type") == "grill-me"]),
            "experiments": len([e for e in p_entries if e.get("type") == "experiment" and e.get("status") == "running"]),
            "new": len([e for e in p_entries if e.get("status") == "new"]),
        }

    in_flight = [e for e in all_entries if e.get("status") == "in-progress"]
    needs_triage = [e for e in all_entries if e.get("status") == "new"]
    running_experiments = [e for e in all_entries if e.get("type") == "experiment" and e.get("status") == "running"]

    from app.routes.housekeeping import _age_str, _widget_status
    heartbeat = read_housekeeping_heartbeat(project_slug())
    hk_age = _age_str(heartbeat.get("last_run"))
    hk_status = _widget_status(heartbeat)
    blog_draft = latest_draft_name()
    reflection_health = get_reflection_health()

    return render_template(
        "dashboard.html",
        projects=projects,
        project_stats=project_stats,
        in_flight=in_flight,
        needs_triage=needs_triage,
        running_experiments=running_experiments,
        housekeeping_heartbeat=heartbeat,
        hk_age=hk_age,
        hk_status=hk_status,
        blog_draft=blog_draft,
        reflection_health=reflection_health,
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
    grill_me = [e for e in entries if e.get("type") == "grill-me"]

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
        grill_me=grill_me,
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
    health = project_health_signals(name)
    if e.get("type") == "decision":
        valid_statuses = DECISION_STATUSES
    else:
        valid_statuses = ENTRY_TYPE_CONFIG.get(e.get("type"), {}).get("valid_statuses", ())
    return render_template(
        "entry.html", entry=e, project=name, health=health,
        valid_statuses=valid_statuses,
    )


@bp.route("/projects/<name>/<slug>/status", methods=["POST"])
def update_status(name, slug):
    new_status = request.form.get("status", "")
    success = update_entry_status(name, slug, new_status)
    flash("Status updated." if success else "Could not update status.")
    next_raw = request.form.get("next", "")
    next_url = next_raw if next_raw.startswith("/") else url_for("browse.project", name=name)
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


@bp.route("/weak-signals")
def weak_signals():
    signals = get_weak_signals()
    return render_template("weak_signals.html", signals=signals)


@bp.route("/graph")
def graph():
    return render_template("graph.html")


@bp.route("/api/graph")
def api_graph():
    return jsonify(get_vault_graph())
