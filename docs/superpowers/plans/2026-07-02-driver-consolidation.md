# Driver Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the session-manager HTTP contract the documented v0 driver interface, route all session-manager traffic through one client, lift Claude-specific prompt construction into a single adapter module, guard the scheduler against multi-worker duplication, and de-hardcode the platform project slug.

**Architecture:** No `DriverBase` protocol — the HTTP API is the driver interface (per accepted decision, Fable review 2026-07-02). `session_client.py` becomes the sole wire-level client; a new `driver.py` holds every slash-command/prompt string (intent → command mapping); routes and scheduler call intent functions only. New `platform.py` centralizes the platform project slug and config-version path.

**Tech Stack:** Flask, requests, APScheduler, pytest (existing suite in `tests/`, mock-based, no live session-manager needed).

## Global Constraints

- Repo: `C:\Server\projects\ikeos`. Work on branch `feat/driver-consolidation` (create from `main` before Task 1). No pushing; merge to main only at the final checkpoint with user confirmation (no PRs — direct merge is this project's convention).
- Conventional commits: `feat:`, `refactor:`, `docs:`, `test:`, `chore:`.
- Services must not import Flask (`request`/`g`/`current_app`) — CLAUDE.md rule.
- Routes stay thin: parse request, call service, return response.
- Test runner: **neither checked-in venv has pytest — do not use `.venv/` or `venv/`.** For fast iteration run under WSL2 system python (has pytest 8.3.4): `wsl.exe -e bash -c "cd /mnt/c/Server/projects/ikeos && python3 -m pytest <args>"`. The canonical documented runner is in-container: `docker.exe exec ikeos pytest tests/ -q` (CONTRIBUTING.md) — but the container runs *built* code with no bind mount, so it only reflects changes after `docker.exe compose up --build -d`; use it as the final gate (Task 12), not for TDD loops. Establish a green baseline (`-q`, full suite, WSL2 runner) before Task 1 and record the pass count.
- Wire-behavior freeze: the JSON bodies sent to the session-manager must be byte-identical to current behavior except for the additive optional `model` key. The em dash in `"/housekeeping — run in scheduled mode"` is existing live behavior — preserve it exactly.
- After the final task, rebuild the running container (`docker.exe compose up --build -d`) — the app has no bind mount for code.

---

### Task 1: Driver contract document (SESSION_DRIVER_API.md v0)

**Files:**
- Create: `docs/SESSION_DRIVER_API.md`
- Modify: `README.md` (add one line pointing to the new doc, in the section that currently references the "Claude Code adapter contract")

**Interfaces:**
- Produces: the public v0 wire contract that Tasks 2–4 implement and that the Phase-2 extraction plan depends on.

- [ ] **Step 1: Write the document.** Content must cover, precisely:

````markdown
# IkeOS Session Driver API — v0

IkeOS never talks to an AI coding engine directly. It talks to a **session driver**:
an HTTP service that owns engine sessions. Anyone can implement this contract to
drive a different engine. The reference implementation drives Claude Code in tmux.

Base URL: `SESSION_MANAGER_URL` (default `http://host.docker.internal:5010`).

## POST /sessions — create (or find) a session

Request body (JSON):

| field             | type          | meaning                                                                 |
|-------------------|---------------|-------------------------------------------------------------------------|
| `name`            | string        | Session identity AND dedup key. Creating a session whose `name` matches a live session returns 409. |
| `project`         | string        | Project slug, used for grouping/display and vault attribution.          |
| `project_dir`     | string        | Working directory the engine session starts in (host path).             |
| `initial_command` | string / null | Free text handed to the engine on start. See "Ephemeral semantics".     |
| `model`           | string / null | OPTIONAL, driver-defined opaque string selecting the engine model. IkeOS never interprets it; drivers without model selection may ignore it. |

Responses:
- `200/201` → `{"id": "<session-id>", ...}` — the new session's id.
- `409` → `{"session": {"id": "<existing-id>", ...}}` — a live session with this `name` already exists. Callers treat this as success-with-reuse.
- Any other non-2xx → error; IkeOS surfaces it and does not retry.

## Ephemeral semantics (contract-level warning)

`initial_command` **present** ⇒ the session is ephemeral/unattended ⇒ the reference
driver launches the engine with permission prompts disabled
(`--dangerously-skip-permissions` for Claude Code). Implementers MUST document their
equivalent, and deployers MUST treat any endpoint that creates command-bearing
sessions as privileged (IkeOS gates them behind capability flags and the capture token).
`initial_command` **absent** ⇒ interactive session, normal permission behavior.

## GET /sessions — list live sessions
Returns a JSON array; each element includes at least `id`, `name` (`tmux_session` in
the reference driver), `project`, `status` (`"active"` when running), `started_at` (ISO 8601).

## GET /sessions/{id} — inspect one session
`200` with the session object (`status` field as above), `404` if unknown.

## POST /sessions/{id}/command — send text to a live session
Body: `{"command": "<text>", "escape_first": bool}`. `escape_first` clears any
partially-typed input before sending. `2xx` on success.

## Lifecycle & UI endpoints (v0, reference-driver shaped)
`DELETE /sessions/{id}` (stop), `DELETE /sessions/{id}/remove`,
`POST /sessions/{id}/reset`, `POST /sessions/{id}/rename`,
`PATCH /sessions/{id}/remote_control`, `PATCH /sessions/{id}/autonomous_mode`,
`PATCH /sessions/{id}/remote_control_state`, `GET /sessions/{id}/pane`.
These power the IkeOS Sessions UI via a pass-through proxy. A minimal driver may
return `501` for any of them; create/list/inspect/command are the required core.

## Versioning
This is v0: shaped by the Claude Code reference driver. Breaking changes will bump
to `/v1/` paths. Additive optional request fields (like `model`) are non-breaking.
````

- [ ] **Step 2: Add README pointer.** In `README.md`, where the architecture/adapter contract is referenced, add: `The wire contract for session drivers is documented in [docs/SESSION_DRIVER_API.md](docs/SESSION_DRIVER_API.md).`

- [ ] **Step 3: Commit**

```bash
git add docs/SESSION_DRIVER_API.md README.md
git commit -m "docs: publish session driver API contract v0"
```

---

### Task 2: `platform.py` — platform slug + config-version helpers

**Files:**
- Create: `app/services/platform.py`
- Test: `tests/test_platform.py`

**Interfaces:**
- Produces: `project_slug() -> str` (env `PLATFORM_PROJECT_SLUG`, default `"claude-config"`); `config_version_path() -> str` (env `CONFIG_VERSION_PATH`, default `"/claude-config/VERSION"`, empty string means "disabled"). Tasks 4, 5, 8, 11 consume these.

- [ ] **Step 1: Write failing tests** (`tests/test_platform.py`):

```python
from app.services.platform import config_version_path, project_slug


def test_project_slug_default(monkeypatch):
    monkeypatch.delenv("PLATFORM_PROJECT_SLUG", raising=False)
    assert project_slug() == "claude-config"


def test_project_slug_env_override(monkeypatch):
    monkeypatch.setenv("PLATFORM_PROJECT_SLUG", "my-config")
    assert project_slug() == "my-config"


def test_config_version_path_default(monkeypatch):
    monkeypatch.delenv("CONFIG_VERSION_PATH", raising=False)
    assert config_version_path() == "/claude-config/VERSION"


def test_config_version_path_blank_disables(monkeypatch):
    monkeypatch.setenv("CONFIG_VERSION_PATH", "")
    assert config_version_path() == ""
```

- [ ] **Step 2: Run to verify failure.** `python3 -m pytest tests/test_platform.py -v` — expect `ModuleNotFoundError`/import error.

- [ ] **Step 3: Implement** `app/services/platform.py`:

```python
"""Identity of the platform's own configuration project.

IkeOS stores its operational state (housekeeping schedule, capabilities)
under one vault project. That slug and the deployed-config VERSION path
are deployment-specific; both are env-tunable with backward-compatible
defaults.
"""
import os


def project_slug() -> str:
    return os.environ.get("PLATFORM_PROJECT_SLUG", "claude-config")


def config_version_path() -> str:
    """Path to the deployed agent-config VERSION file. Empty string disables the badge."""
    return os.environ.get("CONFIG_VERSION_PATH", "/claude-config/VERSION")
```

- [ ] **Step 4: Run tests — expect 4 passed.**

- [ ] **Step 5: Commit**

```bash
git add app/services/platform.py tests/test_platform.py
git commit -m "feat: add platform config helpers for project slug and version path"
```

---

### Task 3: Widen `session_client.py` — url helper, `model` param, `send_command`, `get_session_status`

**Files:**
- Modify: `app/services/session_client.py`
- Test: `tests/test_session_client.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces (Tasks 4, 8, 9 rely on these exact signatures):
  - `session_manager_url() -> str`
  - `create_session(*, name: str, project: str, project_dir: str, initial_command: str | None = None, model: str | None = None) -> SessionResult`
  - `send_command(session_id: str, command: str, *, escape_first: bool = False) -> bool`
  - `get_session_status(session_id: str) -> dict | None`

- [ ] **Step 1: Write failing tests** — append to `tests/test_session_client.py` (match the file's existing mock style):

```python
from app.services.session_client import (
    get_session_status,
    send_command,
    session_manager_url,
)


def test_session_manager_url_default(monkeypatch):
    monkeypatch.delenv("SESSION_MANAGER_URL", raising=False)
    assert session_manager_url() == "http://host.docker.internal:5010"


def test_create_session_omits_model_when_none(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "abc"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp) as mock_post:
        with patch("app.services.session_client.append_event"):
            create_session(name="t", project="p", project_dir="/tmp")
    assert "model" not in mock_post.call_args.kwargs["json"]


def test_create_session_passes_model_when_set(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "abc"}
    with patch("app.services.session_client.requests.post", return_value=mock_resp) as mock_post:
        with patch("app.services.session_client.append_event"):
            create_session(name="t", project="p", project_dir="/tmp", model="claude-fable-5")
    assert mock_post.call_args.kwargs["json"]["model"] == "claude-fable-5"


def test_send_command_success(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    with patch("app.services.session_client.requests.post", return_value=mock_resp) as mock_post:
        assert send_command("sess1", "hello", escape_first=True) is True
    assert mock_post.call_args.args[0] == "http://mock-sm/sessions/sess1/command"
    assert mock_post.call_args.kwargs["json"] == {"command": "hello", "escape_first": True}


def test_send_command_unreachable_returns_false(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    with patch("app.services.session_client.requests.post",
               side_effect=req_lib.RequestException("boom")):
        assert send_command("sess1", "hello") is False


def test_get_session_status_found(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "s1", "status": "active"}
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        assert get_session_status("s1") == {"id": "s1", "status": "active"}


def test_get_session_status_missing_or_down(monkeypatch):
    monkeypatch.setenv("SESSION_MANAGER_URL", "http://mock-sm")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    with patch("app.services.session_client.requests.get", return_value=mock_resp):
        assert get_session_status("nope") is None
    with patch("app.services.session_client.requests.get",
               side_effect=req_lib.RequestException("down")):
        assert get_session_status("s1") is None
```

- [ ] **Step 2: Run — expect ImportError failures** on the three new names.

- [ ] **Step 3: Implement.** In `app/services/session_client.py`: add `session_manager_url()`; use it inside `create_session` (replacing the inline `sm_url = os.environ.get(...)` at line 30); add `model` keyword to `create_session` and include `payload["model"] = model` only when `model is not None`; add `send_command` and `get_session_status`:

```python
def session_manager_url() -> str:
    return os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")
```

```python
def create_session(
    *,
    name: str,
    project: str,
    project_dir: str,
    initial_command: str | None = None,
    model: str | None = None,
) -> SessionResult:
    payload = {
        "name": name,
        "project": project,
        "project_dir": project_dir,
        "initial_command": initial_command,
    }
    if model is not None:
        payload["model"] = model
    try:
        response = requests.post(f"{session_manager_url()}/sessions", json=payload, timeout=5)
    except requests.RequestException:
        return SessionResult(session_id="", error="Session manager unreachable")
    # ... (409 / non-ok / success handling unchanged from current lines 45-63)
```

```python
def send_command(session_id: str, command: str, *, escape_first: bool = False) -> bool:
    """Send text to a live session. Returns True on 2xx."""
    try:
        resp = requests.post(
            f"{session_manager_url()}/sessions/{session_id}/command",
            json={"command": command, "escape_first": escape_first},
            timeout=5,
        )
    except requests.RequestException:
        return False
    return resp.ok


def get_session_status(session_id: str) -> dict | None:
    """Session object from the driver, or None if unknown/unreachable."""
    try:
        resp = requests.get(f"{session_manager_url()}/sessions/{session_id}", timeout=3)
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    return resp.json()
```

- [ ] **Step 4: Run the whole file — all old and new tests pass.** `python3 -m pytest tests/test_session_client.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/services/session_client.py tests/test_session_client.py
git commit -m "feat: session client gains url helper, model param, send_command, get_session_status"
```

---

### Task 4: `driver.py` — the intent layer (all slash-commands move here)

**Files:**
- Create: `app/services/driver.py`
- Test: `tests/test_driver.py`

**Interfaces:**
- Consumes: `create_session`, `send_command`, `SessionResult` (Task 3); `project_slug` (Task 2).
- Produces (Tasks 5 and 8 rely on these exact signatures, all returning `SessionResult`):
  - `run_scheduled_housekeeping(model: str | None = None) -> SessionResult`
  - `run_housekeeping_task(filename: str, model: str | None = None) -> SessionResult`
  - `run_platform_review(model: str | None = None) -> SessionResult`
  - `publish_blog_draft(draft_name: str, bluesky_name: str, model: str | None = None) -> SessionResult`
  - `rewrite_blog_draft(draft_name: str, feedback: str, model: str | None = None) -> SessionResult`

- [ ] **Step 1: Write failing tests** (`tests/test_driver.py`). Patch `app.services.driver.create_session` / `app.services.driver.send_command`:

```python
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
    assert cs.call_args.kwargs["name"] == "weekly-platform-review"


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
```

- [ ] **Step 2: Run — expect import errors.**

- [ ] **Step 3: Implement** `app/services/driver.py`:

```python
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
        name="weekly-platform-review",
        project=project_slug(),
        project_dir=_housekeeping_project_dir(),
        initial_command="/platform-review",
        model=model,
    )


def publish_blog_draft(draft_name: str, bluesky_name: str, model: str | None = None) -> SessionResult:
    command = (
        f"Run `bash deploy.sh content/posts/{draft_name}` in {_blog_project_dir()}. "
        f"The Bluesky companion text is in content/posts/{bluesky_name}. "
        "Build the Hugo site, deploy via rsync, and post to Bluesky."
    )
    stem = draft_name.rsplit(".", 1)[0]
    return create_session(
        name=f"blog-publish-{stem[:30]}",
        project="aios-blog",
        project_dir=_blog_project_dir(),
        initial_command=command,
        model=model,
    )


def rewrite_blog_draft(draft_name: str, feedback: str, model: str | None = None) -> SessionResult:
    command = (
        f"Rewrite the blog draft at content/posts/{draft_name} based on this feedback: "
        f"{feedback} — keep the same frontmatter, voice, and section structure from the /blog skill. "
        "Overwrite the file in place when done."
    )
    stem = draft_name.rsplit(".", 1)[0]
    result = create_session(
        name=f"blog-rewrite-{stem[:30]}",
        project="aios-blog",
        project_dir=_blog_project_dir(),
        initial_command=command,
        model=model,
    )
    if result.already_running:
        if not send_command(result.session_id, command, escape_first=True):
            return SessionResult(session_id=result.session_id,
                                 error="Rewrite session running but failed to send command")
    return result
```

- [ ] **Step 4: Run `tests/test_driver.py` — 7 passed.**

- [ ] **Step 5: Commit**

```bash
git add app/services/driver.py tests/test_driver.py
git commit -m "feat: add driver intent layer owning all engine prompt construction"
```

---

### Task 5: Rewire `scheduler.py` through the driver + platform slug

**Files:**
- Modify: `app/services/scheduler.py`
- Test: `tests/test_scheduler.py` (update patch targets)

**Interfaces:**
- Consumes: `run_scheduled_housekeeping` (Task 4), `project_slug` (Task 2).
- Produces: `trigger_now() -> str | None` (unchanged signature — routes keep calling it).

- [ ] **Step 1: Modify `scheduler.py`.** Replace the import of `create_session` with `from app.services.driver import run_scheduled_housekeeping` and `from app.services.platform import project_slug`. `_schedule_path()` becomes:

```python
def _schedule_path() -> Path:
    vault = Path(os.environ.get("VAULT_PATH", "/vault"))
    return vault / "projects" / project_slug() / "housekeeping" / "schedule.json"
```

`trigger_now()` (current lines 115-142) becomes:

```python
def trigger_now() -> str | None:
    result = run_scheduled_housekeeping()
    if not result.ok:
        logger.error("Failed to create housekeeping session: %s", result.error)
        return None
    session_id = result.session_id
    config = get_config()
    config["last_triggered"] = datetime.now().isoformat(timespec="seconds")
    try:
        _write_config(config)
    except OSError:
        logger.exception("Failed to write last_triggered after scheduling housekeeping session")

    append_event("housekeeping.trigger", {
        "trigger": "scheduled" if _scheduler else "manual",
        "session_id": session_id,
        "project": project_slug(),
    })
    return session_id
```

Session naming and `HOUSEKEEPING_PROJECT_DIR` handling now live in the driver — delete them here.

- [ ] **Step 2: Update `tests/test_scheduler.py`.** Read the file; wherever it patches `app.services.scheduler.create_session`, patch `app.services.scheduler.run_scheduled_housekeeping` instead, returning `SessionResult(session_id=...)` as before. Assertions about session name/command move to `tests/test_driver.py` (already covered by Task 4) — delete any duplicates here rather than porting them.

- [ ] **Step 3: Run.** `python3 -m pytest tests/test_scheduler.py tests/test_driver.py -v` — all pass.

- [ ] **Step 4: Commit**

```bash
git add app/services/scheduler.py tests/test_scheduler.py
git commit -m "refactor: scheduler triggers housekeeping via driver intent layer"
```

---

### Task 6: `blog_drafts.py` + `reviews.py` — file I/O out of routes

**Files:**
- Create: `app/services/blog_drafts.py`, `app/services/reviews.py`
- Test: `tests/test_blog_drafts.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (Task 8 relies on these):
  - `blog_drafts.latest_draft_paths() -> tuple[Path | None, Path | None]`
  - `blog_drafts.latest_draft_name() -> str | None`
  - `blog_drafts.read_draft_bundle() -> dict | None` — `{"filename", "content", "bluesky_text", "bluesky_filename"}`
  - `blog_drafts.save_draft(content: str, bluesky_text: str) -> str` — returns filename, raises `FileNotFoundError` if no draft, `OSError` on write failure
  - `reviews.latest_review_name() -> str | None`
  - `reviews.read_latest_review() -> tuple[str, str] | None` — `(filename, content)`

- [ ] **Step 1: Write failing tests** (`tests/test_blog_drafts.py`), using `tmp_path` and `monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", ...)` / `("WEEKLY_REVIEW_OUTPUT_DIR", ...)`:

```python
import pytest

from app.services import blog_drafts, reviews


@pytest.fixture
def posts_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    return tmp_path


def test_latest_draft_none_when_empty(posts_dir):
    assert blog_drafts.latest_draft_paths() == (None, None)
    assert blog_drafts.latest_draft_name() is None


def test_latest_draft_picks_newest_with_bluesky(posts_dir):
    (posts_dir / "2026-06-01-weekly-draft.md").write_text("old", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("new", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-bluesky.txt").write_text("sky", encoding="utf-8")
    draft, bluesky = blog_drafts.latest_draft_paths()
    assert draft.name == "2026-07-01-weekly-draft.md"
    assert bluesky.name == "2026-07-01-weekly-bluesky.txt"


def test_read_draft_bundle(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("body", encoding="utf-8")
    bundle = blog_drafts.read_draft_bundle()
    assert bundle == {
        "filename": "2026-07-01-weekly-draft.md",
        "content": "body",
        "bluesky_text": "",
        "bluesky_filename": "",
    }


def test_save_draft_round_trip(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("v1", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-bluesky.txt").write_text("s1", encoding="utf-8")
    name = blog_drafts.save_draft("v2", "s2")
    assert name == "2026-07-01-weekly-draft.md"
    assert (posts_dir / name).read_text(encoding="utf-8") == "v2"
    assert (posts_dir / "2026-07-01-weekly-bluesky.txt").read_text(encoding="utf-8") == "s2"


def test_save_draft_no_draft_raises(posts_dir):
    with pytest.raises(FileNotFoundError):
        blog_drafts.save_draft("x", "")


def test_latest_review(tmp_path, monkeypatch):
    monkeypatch.setenv("WEEKLY_REVIEW_OUTPUT_DIR", str(tmp_path))
    assert reviews.latest_review_name() is None
    (tmp_path / "2026-06-28-weekly-review.md").write_text("r", encoding="utf-8")
    assert reviews.latest_review_name() == "2026-06-28-weekly-review.md"
    assert reviews.read_latest_review() == ("2026-06-28-weekly-review.md", "r")
```

- [ ] **Step 2: Run — expect import errors.**

- [ ] **Step 3: Implement.** `app/services/blog_drafts.py` — port `_blog_draft_paths` logic from `housekeeping.py:23-38`, but read `AIOS_BLOG_POSTS_DIR` at **call time** (the current module-level read makes tests and container reconfiguration brittle):

```python
"""Blog draft file access — sole owner of aios-blog post file I/O."""
import os
from pathlib import Path


def _posts_dir() -> Path | None:
    raw = os.environ.get("AIOS_BLOG_POSTS_DIR", "")
    return Path(raw) if raw else None


def latest_draft_paths() -> tuple[Path | None, Path | None]:
    posts_dir = _posts_dir()
    if posts_dir is None or not posts_dir.exists():
        return None, None
    drafts = sorted(posts_dir.glob("*-weekly-draft.md"), reverse=True)
    if not drafts:
        return None, None
    draft = drafts[0]
    bluesky = draft.with_name(draft.stem.replace("-weekly-draft", "-weekly-bluesky") + ".txt")
    return draft, bluesky if bluesky.exists() else None


def latest_draft_name() -> str | None:
    draft, _ = latest_draft_paths()
    return draft.name if draft else None


def read_draft_bundle() -> dict | None:
    draft, bluesky = latest_draft_paths()
    if not draft:
        return None
    return {
        "filename": draft.name,
        "content": draft.read_text(encoding="utf-8"),
        "bluesky_text": bluesky.read_text(encoding="utf-8") if bluesky else "",
        "bluesky_filename": bluesky.name if bluesky else "",
    }


def save_draft(content: str, bluesky_text: str) -> str:
    draft, bluesky = latest_draft_paths()
    if not draft:
        raise FileNotFoundError("No draft found")
    draft.write_text(content, encoding="utf-8")
    if bluesky and bluesky_text:
        bluesky.write_text(bluesky_text, encoding="utf-8")
    return draft.name
```

`app/services/reviews.py` — port `_latest_weekly_review` from `housekeeping.py:41-48`, call-time env read:

```python
"""Weekly platform review file access."""
import os
from pathlib import Path


def _review_dir() -> Path | None:
    raw = os.environ.get("WEEKLY_REVIEW_OUTPUT_DIR", "")
    return Path(raw) if raw else None


def _latest() -> Path | None:
    review_dir = _review_dir()
    if review_dir is None or not review_dir.exists():
        return None
    found = sorted(review_dir.glob("*-weekly-review.md"), reverse=True)
    return found[0] if found else None


def latest_review_name() -> str | None:
    latest = _latest()
    return latest.name if latest else None


def read_latest_review() -> tuple[str, str] | None:
    latest = _latest()
    if not latest:
        return None
    return latest.name, latest.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run `tests/test_blog_drafts.py` — 6 passed.**

- [ ] **Step 5: Commit**

```bash
git add app/services/blog_drafts.py app/services/reviews.py tests/test_blog_drafts.py
git commit -m "feat: move blog draft and weekly review file I/O into services"
```

---

### Task 7: Shared capture-token auth decorator

**Files:**
- Create: `app/routes/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces: `require_capture_token` decorator (Tasks 8, 9 apply it). Reads `CAPTURE_TOKEN` at request time; returns `503 {"error": "Service unavailable"}` when unset, `401 {"error": "Unauthorized"}` on mismatch — byte-identical JSON to the current inline checks in `housekeeping.py:85-90` and `agents.py:193-196`.

- [ ] **Step 1: Write failing tests** (`tests/test_auth.py`) using a throwaway Flask app:

```python
from flask import Flask, jsonify

from app.routes.auth import require_capture_token


def make_app():
    app = Flask(__name__)

    @app.route("/protected", methods=["POST"])
    @require_capture_token
    def protected():
        return jsonify({"ok": True}), 200

    return app.test_client()


def test_missing_server_token_gives_503(monkeypatch):
    monkeypatch.delenv("CAPTURE_TOKEN", raising=False)
    assert make_app().post("/protected").status_code == 503


def test_wrong_token_gives_401(monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "right")
    resp = make_app().post("/protected", headers={"X-Capture-Token": "wrong"})
    assert resp.status_code == 401


def test_correct_token_passes(monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "right")
    resp = make_app().post("/protected", headers={"X-Capture-Token": "right"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run — expect import error.**

- [ ] **Step 3: Implement** `app/routes/auth.py`:

```python
"""Shared request auth for vault-mutating and session-spawning endpoints."""
import os
from functools import wraps

from flask import jsonify, request


def require_capture_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = os.environ.get("CAPTURE_TOKEN", "")
        if not token:
            return jsonify({"error": "Service unavailable"}), 503
        if request.headers.get("X-Capture-Token", "") != token:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper
```

- [ ] **Step 4: Run `tests/test_auth.py` — 3 passed.**

- [ ] **Step 5: Commit**

```bash
git add app/routes/auth.py tests/test_auth.py
git commit -m "feat: shared capture-token auth decorator"
```

---

### Task 8: Rewire `housekeeping.py` — thin routes over driver + services

**Files:**
- Modify: `app/routes/housekeeping.py`
- Test: `tests/test_housekeeping.py` (update patch targets; behavior unchanged)

**Interfaces:**
- Consumes: `driver.run_housekeeping_task/run_platform_review/publish_blog_draft/rewrite_blog_draft` (Task 4), `blog_drafts.*`, `reviews.*` (Task 6), `require_capture_token` (Task 7), `session_client.get_session_status` (Task 3), `platform.project_slug` (Task 2).
- Produces: identical HTTP behavior on every route (same paths, same status codes, same JSON shapes).

- [ ] **Step 1: Rewrite the module.** The full mapping — every other route/helper keeps its current body:
  - Delete module constants `SESSION_MANAGER_URL`, `AIOS_BLOG_POSTS_DIR`, `AIOS_BLOG_PROJECT_DIR`, `WEEKLY_REVIEW_OUTPUT_DIR`, `HOUSEKEEPING_PROJECT_DIR`, the `import requests` usage for session-manager calls, and helpers `_blog_draft_paths`, `_latest_blog_draft`, `_latest_weekly_review`, `_check_auth` (lines 16-20, 23-48, 85-90). Keep `CAPTURE_URL`/`CAPTURE_TOKEN` (still used for capture-API proxying and template context) and `_capture_headers`, `_age_str`, `_widget_status`.
  - New imports: `from app.routes.auth import require_capture_token`; `from app.services import blog_drafts, reviews`; `from app.services.driver import publish_blog_draft as driver_publish, rewrite_blog_draft as driver_rewrite, run_housekeeping_task, run_platform_review`; `from app.services.platform import project_slug`; `from app.services.session_client import get_session_status`. Drop `from app.services.session_client import create_session` and `from pathlib import Path`.
  - Every route that called `_check_auth()` (toggle_task, reset_task, delete_task, blog_draft_save, blog_draft_publish, blog_draft_rewrite, weekly_review_run, patch_schedule, patch_capability) instead gets `@require_capture_token` directly under its `@bp.route` line, and the two-line auth block is deleted from the body.
  - `create_task` (line 114): `"project": "claude-config"` → `"project": project_slug()`. Same for the `task.get("project", "claude-config")` defaults at lines 145, 176, 202 and the heartbeat read at line 332.
  - `run_task` (lines 208-224) body becomes:

```python
@bp.route("/housekeeping/tasks/<filename>/run", methods=["POST"])
def run_task(filename: str):
    result = run_housekeeping_task(filename)
    if result.already_running:
        return jsonify({"ok": True, "session_id": result.session_id, "already_running": True}), 200
    if not result.ok:
        return jsonify({"error": "Failed to create session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200
```

  - `blog_draft_editor`: use `bundle = blog_drafts.read_draft_bundle()`; if `None` render the no-draft fallback as now; else `render_template("blog_draft.html", capture_token=CAPTURE_TOKEN, **bundle)` (template variables `filename`, `content`, `bluesky_text`, `bluesky_filename` match the bundle keys — verify against `blog_draft.html` before committing).
  - `blog_draft_save`: replace the Path writes with `try: name = blog_drafts.save_draft(content, bluesky_text)` / `except FileNotFoundError: return jsonify({"error": "No draft found"}), 404` / `except OSError as e: return jsonify({"error": str(e)}), 500`.
  - `blog_draft_publish`: get `draft, bluesky = blog_drafts.latest_draft_paths()`; keep the 404 and the `AIOS_BLOG_PROJECT_DIR`-unset 503 guard (`if not os.environ.get("AIOS_BLOG_PROJECT_DIR")`); then `result = driver_publish(draft.name, bluesky.name if bluesky else "")` and map to JSON as now.
  - `blog_draft_rewrite` (lines 288-326) collapses — the resend logic lives in the driver now:

```python
@bp.route("/housekeeping/blog-draft/rewrite", methods=["POST"])
@require_capture_token
def blog_draft_rewrite():
    draft, _ = blog_drafts.latest_draft_paths()
    if not draft:
        return jsonify({"error": "No draft found"}), 404
    if not os.environ.get("AIOS_BLOG_PROJECT_DIR"):
        return jsonify({"error": "AIOS_BLOG_PROJECT_DIR not configured"}), 503
    feedback = request.form.get("feedback", "").strip()
    if not feedback:
        return jsonify({"error": "Feedback is required"}), 400
    result = driver_rewrite(draft.name, feedback)
    if not result.ok:
        return jsonify({"error": result.error or "Failed to create rewrite session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200
```

  - `blog_draft_content`: use `blog_drafts.read_draft_bundle()`.
  - `blog_draft_session_status` (lines 359-372): replace the raw `requests.get` with `status = get_session_status(session_id)`; return `jsonify({"active": bool(status and status.get("status") == "active")})`.
  - `weekly_review` + `_latest_weekly_review` usages: use `reviews.read_latest_review()` / `reviews.latest_review_name()`.
  - `weekly_review_run`: keep the capability gate; session creation becomes `result = run_platform_review()`.

- [ ] **Step 2: Update `tests/test_housekeeping.py`.** Read it; update patch targets per this table (assertions/status codes stay identical):

| old patch target | new patch target |
|---|---|
| `app.routes.housekeeping.create_session` | `app.services.driver.create_session` (or the specific `app.routes.housekeeping.run_housekeeping_task` / `run_platform_review` / `driver_publish` / `driver_rewrite` name — prefer patching the name the route imports) |
| `app.routes.housekeeping._check_auth` (if patched) | remove — set/patch `CAPTURE_TOKEN` env instead |
| module constants `AIOS_BLOG_POSTS_DIR` etc. (if monkeypatched as attributes) | `monkeypatch.setenv(...)` — services read env at call time now |
| `app.routes.housekeeping.requests` (session-status/rewrite paths) | `app.routes.housekeeping.get_session_status` / driver functions |

- [ ] **Step 3: Run.** `python3 -m pytest tests/test_housekeeping.py -v` — all pass. Then full suite `-q` — no regressions.

- [ ] **Step 4: Commit**

```bash
git add app/routes/housekeeping.py tests/test_housekeeping.py
git commit -m "refactor: housekeeping routes are thin — driver intents, file services, shared auth"
```

---

### Task 9: `agents.py` — unified base URL + shared auth

**Files:**
- Modify: `app/routes/agents.py`
- Test: `tests/test_agents.py` (update patch targets if they touch the URL constant)

**Interfaces:**
- Consumes: `session_manager_url` (Task 3), `require_capture_token` (Task 7).
- Produces: identical proxy behavior; the hardcoded `SESSION_MANAGER_URL` module constant (line 11) is gone.

- [ ] **Step 1: Modify.** Delete line 11 (`SESSION_MANAGER_URL = "http://host.docker.internal:5010"`) and the module-level `CAPTURE_TOKEN` (line 12). Add `from app.services.session_client import session_manager_url` and `from app.routes.auth import require_capture_token`. `_proxy` becomes:

```python
def _proxy(method: str, path: str, **kwargs):
    url = f"{session_manager_url()}{path}"
    resp = requests.request(method, url, timeout=5, **kwargs)
    return resp.json(), resp.status_code
```

`metrics_event` (lines 191-206): add `@require_capture_token` under the route decorator and delete the inline token checks (lines 193-196).

- [ ] **Step 2: Update `tests/test_agents.py`** if it references the deleted constant or patches the inline auth — same substitution rules as Task 8.

- [ ] **Step 3: Run `tests/test_agents.py` + full suite — pass.**

- [ ] **Step 4: Commit**

```bash
git add app/routes/agents.py tests/test_agents.py
git commit -m "refactor: agents proxy uses shared session-manager url and auth decorator"
```

---

### Task 10: Scheduler multi-worker guard

**Files:**
- Modify: `app/services/scheduler.py`
- Test: `tests/test_scheduler.py` (extend)

**Interfaces:**
- Produces: `_acquire_scheduler_lock(path: Path) -> bool` (module-internal but unit-tested); `start(app)` refuses to start a second scheduler in the same deployment.

Rationale: with gunicorn `--workers N>1`, each worker starts its own APScheduler and the housekeeping job fires N times — N unattended permission-skipping sessions. The Dockerfile pins `--workers 1` today; this guard makes the failure loud instead of silent if that ever changes.

- [ ] **Step 1: Write failing test** (append to `tests/test_scheduler.py`):

```python
import sys

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl lock is POSIX-only; container runtime is Linux")
def test_scheduler_lock_is_exclusive(tmp_path):
    from app.services.scheduler import _acquire_scheduler_lock
    lock_file = tmp_path / "sched.lock"
    assert _acquire_scheduler_lock(lock_file) is True
    assert _acquire_scheduler_lock(lock_file) is False  # second acquisition in-process fails
```

- [ ] **Step 2: Run — expect ImportError on `_acquire_scheduler_lock`** (POSIX) or SKIPPED (Windows — in that case verify the implementation inside the container in Task 12 instead).

- [ ] **Step 3: Implement.** In `scheduler.py`, add near the top:

```python
_lock_handle = None  # keeps the scheduler lock fd alive for process lifetime


def _acquire_scheduler_lock(path: Path) -> bool:
    """True if this process now holds the exclusive scheduler lock.

    POSIX-only (fcntl); on platforms without fcntl we allow start —
    the deployed runtime is the Linux container.
    """
    global _lock_handle
    try:
        import fcntl
    except ImportError:
        return True
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _lock_handle = handle
    return True
```

In `start(app)`, immediately after the `TESTING` early-return:

```python
    lock_path = Path(os.environ.get("SCHEDULER_LOCK_PATH", "/tmp/ikeos-scheduler.lock"))
    if not _acquire_scheduler_lock(lock_path):
        logger.error(
            "Another worker already runs the housekeeping scheduler — refusing to start a duplicate. "
            "Run gunicorn with --workers 1 (see DECISIONS.md 2026-06-18)."
        )
        return
```

Keep the existing `--workers 1` warning log.

- [ ] **Step 4: Run `tests/test_scheduler.py` — passes (or skips on Windows).**

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler refuses to start twice under multi-worker gunicorn"
```

---

### Task 11: De-hardcode platform slug + version path everywhere else; env + doc alignment

**Files:**
- Modify: `app/__init__.py`, `app/services/capabilities.py`, `app/routes/browse.py:38`, `.env.example`, `CONTRIBUTING.md`
- Test: `tests/test_platform.py` (extend), existing suites must stay green

**Interfaces:**
- Consumes: `platform.project_slug`, `platform.config_version_path` (Task 2).

- [ ] **Step 1: `app/__init__.py`** — replace the context processor (lines 70-77):

```python
    from app.services.platform import config_version_path

    @app.context_processor
    def inject_config_version():
        path = config_version_path()
        if not path:
            return {"config_version": None}
        try:
            with open(path) as f:
                return {"config_version": f.read().strip()}
        except OSError:
            return {"config_version": None}
```

- [ ] **Step 2: `capabilities.py`** — `_capabilities_path()` (line 27-29) uses `project_slug()`:

```python
from app.services.platform import project_slug


def _capabilities_path() -> Path:
    vault = Path(os.environ.get("VAULT_PATH", "/vault"))
    return vault / "projects" / project_slug() / "housekeeping" / "capabilities.json"
```

- [ ] **Step 3: `browse.py:38`** — `read_housekeeping_heartbeat("claude-config")` → `read_housekeeping_heartbeat(project_slug())` (add the import).

- [ ] **Step 4: `.env.example`** — append:

```
# Vault project slug that stores the platform's own housekeeping/config state
PLATFORM_PROJECT_SLUG=claude-config
# Path (inside the container) to your agent-config VERSION file; leave blank to hide the version badge
CONFIG_VERSION_PATH=/claude-config/VERSION
```

- [ ] **Step 5: `CONTRIBUTING.md` skills-registry section (lines ~124-137)** — the documented entry schema lists fields the code never reads. Align doc to code: the schema is exactly `command`, `category`, `description`, optional `added`/`updated` (dates drive the 14-day new/updated badges in `app/services/skills.py`). Shrink the doc; do not grow the code.

- [ ] **Step 6: Extend `tests/test_platform.py`** with a context-processor test:

```python
def test_version_badge_disabled_when_path_blank(monkeypatch, client):
    monkeypatch.setenv("CONFIG_VERSION_PATH", "")
    resp = client.get("/health")
    assert resp.status_code == 200  # app boots; badge suppression is render-level
```

- [ ] **Step 7: Full suite `-q` — green. Commit**

```bash
git add app/__init__.py app/services/capabilities.py app/routes/browse.py .env.example CONTRIBUTING.md tests/test_platform.py
git commit -m "feat: platform project slug and config version path are env-configurable"
```

---

### Task 12: Integration verification, deploy, merge checkpoint

**Files:** none new.

- [ ] **Step 1: Full suite.** `python3 -m pytest tests/ -q` — compare against the pre-Task-1 baseline count; every previously passing test still passes, plus the new ones.

- [ ] **Step 2: Grep gates.** All must return nothing:

```bash
grep -rn "initial_command" app/routes/ app/services/scheduler.py   # only driver.py + session_client.py may hit
grep -rn "host.docker.internal:5010" app/ --include="*.py" | grep -v session_client.py
grep -rn '"claude-config"' app/ --include="*.py" | grep -v platform.py
```

- [ ] **Step 3: Rebuild and smoke.** `docker.exe compose up --build -d` (use the compose file the running deployment actually uses — check `docker.exe compose ls` first). Then:
  - `curl -s http://localhost:5009/health` → `ok`
  - `curl -s http://localhost:5009/housekeeping | head -c 200` → HTML renders
  - Version badge still shows on any page (CONFIG_VERSION_PATH default unchanged)
  - Container logs clean: `docker.exe compose logs --tail=30`

- [ ] **Step 4: Close the vault loop.** PATCH the ikeos idea `2026-07-02-add-model-parameter-to-create-session-for-ai-model.md` to `status=done` via the capture API (the ikeos side is now implemented; the session-manager side remains tracked in claude-config).

- [ ] **Step 5: Merge checkpoint — STOP and confirm with the user** before `git merge` to main (repo convention: direct merge, no PR; merging requires explicit confirmation per git workflow rules). After merge, remind that `git push` also requires user confirmation.
