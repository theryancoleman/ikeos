from flask import Blueprint, render_template

bp = Blueprint("browse", __name__)


@bp.route("/", methods=["GET"])
def dashboard():
    return render_template("dashboard.html")
