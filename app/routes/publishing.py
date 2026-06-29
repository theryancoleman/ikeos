import os

from flask import Blueprint, render_template

from app.services.publishing import read_blog_posts, read_bluesky_posts

bp = Blueprint("publishing", __name__)

AIOS_BLOG_POSTS_DIR = os.environ.get("AIOS_BLOG_POSTS_DIR", "")
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")


@bp.route("/publishing")
def index():
    posts = read_blog_posts(AIOS_BLOG_POSTS_DIR) if AIOS_BLOG_POSTS_DIR else []
    bluesky_posts = read_bluesky_posts(BLUESKY_HANDLE) if BLUESKY_HANDLE else []
    return render_template(
        "publishing.html",
        posts=posts,
        bluesky_posts=bluesky_posts,
        bluesky_handle=BLUESKY_HANDLE,
    )
