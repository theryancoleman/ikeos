from unittest.mock import patch

from app.services.driver import (
    publish_blog_draft,
    rewrite_blog_draft,
    run_housekeeping_task,
    run_platform_review,
    run_scheduled_housekeeping,
)
from app.services.session_client import SessionResult

OK = SessionResult(session_id="s1")
RUNNING = SessionResult(session_id="s1", already_running=True)


def test_scheduled_housekeeping_command_and_project(monkeypatch):
    monkeypatch.setenv("HOUSEKEEPING_PROJECT_DIR", "/mnt/c/Server/claude-config")
    with patch("app.services.driver.create_session", return_value=OK) as cs:
        result = run_scheduled_housekeeping()
    assert result.ok
    kw = cs.call_args.kwargs
    assert kw["initial_command"] == "/housekeeping — run in scheduled mode"
    assert kw["project"] == "claude-config"
    assert kw["name"].startswith("housekeeping-")


def test_housekeeping_task_strips_date_prefix():
    with patch("app.services.driver.create_session", return_value=OK) as cs:
        run_housekeeping_task("2026-06-14-review-weak-signals.md")
    kw = cs.call_args.kwargs
    assert kw["initial_command"] == "/housekeeping run review-weak-signals.md"
    assert kw["name"] == "housekeeping-2026-06-14-review-weak-signals.md"


def test_platform_review_command():
    with patch("app.services.driver.create_session", return_value=OK) as cs:
        run_platform_review()
    assert cs.call_args.kwargs["initial_command"] == "/platform-review"
    assert cs.call_args.kwargs["name"].startswith("weekly-platform-review-")


def test_publish_blog_draft_builds_deploy_prompt(monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_PROJECT_DIR", "/mnt/c/Server/projects/aios-blog")
    with patch("app.services.driver.create_session", return_value=OK) as cs:
        publish_blog_draft("2026-07-01-weekly-draft.md", "2026-07-01-weekly-bluesky.txt")
    kw = cs.call_args.kwargs
    assert "bash deploy.sh content/posts/2026-07-01-weekly-draft.md" in kw["initial_command"]
    assert kw["project"] == "aios-blog"
    assert kw["name"] == "blog-publish-2026-07-01-weekly-draft"


def test_rewrite_resends_command_when_already_running(monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_PROJECT_DIR", "/blog")
    with patch("app.services.driver.create_session", return_value=RUNNING):
        with patch("app.services.driver.send_command", return_value=True) as sc:
            result = rewrite_blog_draft("2026-07-01-weekly-draft.md", "make it shorter")
    assert result.ok and result.already_running
    assert sc.call_args.args[0] == "s1"
    assert "make it shorter" in sc.call_args.args[1]
    assert sc.call_args.kwargs["escape_first"] is True


def test_rewrite_reports_error_when_resend_fails(monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_PROJECT_DIR", "/blog")
    with patch("app.services.driver.create_session", return_value=RUNNING):
        with patch("app.services.driver.send_command", return_value=False):
            result = rewrite_blog_draft("2026-07-01-weekly-draft.md", "fb")
    assert result.ok is False


def test_rewrite_new_session_ok(monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_PROJECT_DIR", "/blog")
    with patch("app.services.driver.create_session", return_value=OK) as cs:
        result = rewrite_blog_draft("2026-07-01-weekly-draft.md", "add more examples")
    assert result.ok
    kw = cs.call_args.kwargs
    assert "add more examples" in kw["initial_command"]
    assert kw["name"] == "blog-rewrite-2026-07-01-weekly-draft"
