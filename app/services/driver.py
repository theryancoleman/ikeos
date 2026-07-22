"""Claude Code adapter: maps IkeOS intents onto driver sessions.

Every slash-command and prompt string IkeOS ever sends lives in this module.
Nothing outside it may construct an initial_command. Session naming here is
load-bearing: the driver dedups live sessions by name (see
docs/SESSION_DRIVER_API.md).
"""
import os
import re
from datetime import datetime

from app.services.platform import project_slug
from app.services.session_client import SessionResult, create_session, send_command

_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def _housekeeping_project_dir() -> str:
    return os.environ.get("HOUSEKEEPING_PROJECT_DIR", "/mnt/c/Server/claude-config")


def _blog_project_dir() -> str:
    return os.environ.get("AIOS_BLOG_PROJECT_DIR", "")


def run_scheduled_housekeeping(model: str | None = None) -> SessionResult:
    return create_session(
        name=f"housekeeping-{datetime.now().strftime('%Y%m%d')}",
        project=project_slug(),
        project_dir=_housekeeping_project_dir(),
        initial_command="/housekeeping — run in scheduled mode",
        model=model,
    )


def run_housekeeping_task(filename: str, model: str | None = None) -> SessionResult:
    slug = _DATE_PREFIX.sub("", filename)
    return create_session(
        name=f"housekeeping-{filename}",
        project=project_slug(),
        project_dir=_housekeeping_project_dir(),
        initial_command=f"/housekeeping run {slug}",
        model=model,
    )


def run_platform_review(model: str | None = None) -> SessionResult:
    return create_session(
        name=f"weekly-platform-review-{datetime.now().strftime('%Y%m%d')}",
        project=project_slug(),
        project_dir=_housekeeping_project_dir(),
        initial_command="/platform-review",
        model=model,
    )


def run_eval_suite(model: str | None = None) -> SessionResult:
    return create_session(
        name="eval-suite-run",
        project=project_slug(),
        project_dir=_housekeeping_project_dir(),
        initial_command=(
            "Run `python3 evals/runner.py --notify` and report the pass/fail/regression "
            "summary when it finishes."
        ),
        model=model,
    )


def publish_blog_draft(draft_name: str, bluesky_name: str, model: str | None = None) -> SessionResult:
    project_dir = _blog_project_dir()
    command = (
        f"Run `bash deploy.sh content/posts/{draft_name}` in {project_dir}. "
        f"The Bluesky companion text is in content/posts/{bluesky_name}. "
        "Build the Hugo site, deploy via rsync, and post to Bluesky."
    )
    stem = draft_name.rsplit(".", 1)[0]
    return create_session(
        name=f"blog-publish-{stem[:30]}",
        project="aios-blog",
        project_dir=project_dir,
        initial_command=command,
        model=model,
    )


def rewrite_blog_draft(draft_name: str, feedback: str, model: str | None = None) -> SessionResult:
    project_dir = _blog_project_dir()
    command = (
        f"Rewrite the blog draft at content/posts/{draft_name} based on this feedback: "
        f"{feedback} — keep the same frontmatter, voice, and section structure from the /blog skill. "
        "Overwrite the file in place when done."
    )
    stem = draft_name.rsplit(".", 1)[0]
    result = create_session(
        name=f"blog-rewrite-{stem[:30]}",
        project="aios-blog",
        project_dir=project_dir,
        initial_command=command,
        model=model,
    )
    if result.already_running:
        if not send_command(result.session_id, command, escape_first=True):
            return SessionResult(
                session_id=result.session_id,
                error="Rewrite session running but failed to send command",
            )
    return result
