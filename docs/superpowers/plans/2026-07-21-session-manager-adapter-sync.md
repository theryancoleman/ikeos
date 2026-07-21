# Session-Manager Reference-Copy Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `adapters/claude-code/session-manager/` (this repo's public reference implementation of the Session Driver API) back in sync with the deployed service at `claude-config/services/session-manager/`, without importing that service's homelab-specific hardcoded paths.

**Architecture:** The adapter is decoupled from the running app at runtime (the app talks to whichever session-manager is deployed over HTTP, per `docs/SESSION_DRIVER_API.md`) — this is a documentation/reference-quality gap, not a production bug. Three additions close it: (1) `tmux.py` gains `list_session_names()` and a `required_consecutive` idle-detection refinement, keeping the adapter's existing env-var-based `CLAUDE_BIN`/`CLAUDE_PLUGIN_BASE` config (do **not** copy the deployed service's hardcoded absolute host paths — those are this-host-specific, not reference-implementation material); (2) `sessions.py` and `tmux.py`'s `launch_session()` gain `model` parameter threading; (3) a new `research_sources.py` module plus three `/research-sources` routes in `app.py`, using the adapter's existing `Path.home()`-relative dotfile storage convention (not the deployed service's private-repo-relative `library/` path).

**Tech Stack:** Python (Flask), pytest, `pytest-mock`.

---

## File Structure

- Modify: `adapters/claude-code/session-manager/tmux.py` — add `list_session_names()`, `required_consecutive` param on `wait_until_idle()`/`send_prompt()`, `model` param on `launch_session()`.
- Modify: `adapters/claude-code/session-manager/sessions.py` — add `model` param on `create_session()`.
- Create: `adapters/claude-code/session-manager/research_sources.py` — new module, adapted to store data at `Path.home() / ".claude-research-sources.json"`.
- Modify: `adapters/claude-code/session-manager/app.py` — import and wire `list_session_names`, add `_reconcile_sessions()` startup step, thread `model` through `POST /sessions`, add the three `/research-sources` routes.
- Modify: `adapters/claude-code/session-manager/tests/test_tmux.py` — tests for `list_session_names()` and `required_consecutive`.
- Modify: `adapters/claude-code/session-manager/tests/test_sessions.py` — test for `model` param.
- Create: `adapters/claude-code/session-manager/tests/test_research_sources.py` — new test file mirroring `research_sources.py`'s behavior.
- Modify: `adapters/claude-code/README.md` — document the new `/research-sources` endpoints and `model` field in the endpoint reference table, if one exists there.

---

## Task 1: `tmux.py` — `list_session_names()` and idle-detection refinement

**Files:**
- Modify: `adapters/claude-code/session-manager/tmux.py`
- Modify: `adapters/claude-code/session-manager/tests/test_tmux.py`

- [ ] **Step 1: Write the failing tests**

Add to `adapters/claude-code/session-manager/tests/test_tmux.py`:

```python
def test_list_session_names_returns_set(mocker):
    mock_run = mocker.patch("tmux.subprocess.run")
    mock_run.return_value = mocker.Mock(returncode=0, stdout="alpha\nbeta\n")
    assert tmux.list_session_names() == {"alpha", "beta"}


def test_list_session_names_returns_empty_set_when_no_server(mocker):
    mock_run = mocker.patch("tmux.subprocess.run")
    mock_run.return_value = mocker.Mock(returncode=1, stdout="")
    assert tmux.list_session_names() == set()


def test_wait_until_idle_requires_consecutive_idle_readings(mocker):
    mocker.patch("tmux.has_session", return_value=True)
    mocker.patch("tmux.capture_pane", return_value="pane text")
    parse_mock = mocker.patch("tmux.parse_activity", side_effect=["idle", "working", "idle", "idle"])
    mocker.patch("tmux.time.sleep")
    result = tmux.wait_until_idle("s", timeout=60, poll_interval=0, required_consecutive=2)
    assert result is True
    assert parse_mock.call_count == 4
```

(`tmux` module is imported at the top of the existing test file — check the current import line and reuse it rather than adding a duplicate import.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker.exe exec ikeos pytest adapters/claude-code/session-manager/tests/test_tmux.py -k "list_session_names or consecutive" -v`
Expected: FAIL — `AttributeError: module 'tmux' has no attribute 'list_session_names'`

- [ ] **Step 3: Add `list_session_names()` — insert after the existing `has_session()` function**

In `adapters/claude-code/session-manager/tmux.py`, after the `has_session` function (currently ends around line 27, right before `def launch_session`), insert:

```python
def list_session_names() -> set[str]:
    """Return the set of currently live tmux session names.

    tmux exits non-zero with "no server running" when there are zero
    sessions — treat that as an empty set rather than an error.
    """
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}
```

- [ ] **Step 4: Add `required_consecutive` to `wait_until_idle()` and thread it through `send_prompt()`**

Find the existing `wait_until_idle` function in `tmux.py`:

```python
def wait_until_idle(
    name: str,
    *,
    timeout: float = 60.0,
    poll_interval: float = 3.0,
) -> bool:
    """Poll the pane until Claude Code is at an idle prompt. Returns True if idle before timeout."""
    deadline = time.monotonic() + timeout
    while True:
        if not has_session(name):
            return False
        if parse_activity(capture_pane(name)) == "idle":
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval)
```

Replace it with:

```python
def wait_until_idle(
    name: str,
    *,
    timeout: float = 60.0,
    poll_interval: float = 3.0,
    required_consecutive: int = 1,
) -> bool:
    """Poll the pane until Claude Code is at an idle prompt. Returns True if idle before timeout.

    required_consecutive: number of consecutive idle readings needed before returning True.
    Use >1 to avoid false positives during the brief gap between generation starting and
    the token counter appearing (parse_activity blind spot for plain text output).
    """
    deadline = time.monotonic() + timeout
    consecutive = 0
    while True:
        if not has_session(name):
            return False
        if parse_activity(capture_pane(name)) == "idle":
            consecutive += 1
            if consecutive >= required_consecutive:
                return True
        else:
            consecutive = 0
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval)
```

Find the existing `send_prompt` function's signature and its call to `wait_until_idle`:

```python
def send_prompt(
    name: str,
    command: str,
    *,
    min_delay: float = 5.0,
    timeout: float = 60.0,
    escape_first: bool = True,
) -> bool:
```

and the line inside it:

```python
    if not wait_until_idle(name, timeout=timeout):
        return False
```

Change the signature to add `required_consecutive: int = 1,` (placed after `timeout`, before `escape_first`), and update the inner call to `wait_until_idle(name, timeout=timeout, required_consecutive=required_consecutive)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker.exe exec ikeos pytest adapters/claude-code/session-manager/tests/test_tmux.py -v`
Expected: all tests pass (existing + 3 new)

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/session-manager/tmux.py adapters/claude-code/session-manager/tests/test_tmux.py
git commit -m "feat: sync list_session_names() and idle-detection refinement into session-manager adapter"
```

---

## Task 2: `model` parameter threading (`tmux.py` `launch_session`, `sessions.py` `create_session`)

**Files:**
- Modify: `adapters/claude-code/session-manager/tmux.py`
- Modify: `adapters/claude-code/session-manager/sessions.py`
- Modify: `adapters/claude-code/session-manager/tests/test_tmux.py`
- Modify: `adapters/claude-code/session-manager/tests/test_sessions.py`

- [ ] **Step 1: Write the failing tests**

Add to `adapters/claude-code/session-manager/tests/test_tmux.py`:

```python
def test_launch_session_overrides_model_when_given(mocker):
    mock_run = mocker.patch("tmux.subprocess.run")
    tmux.launch_session("my-session", "/home/user/projects/foo", model="claude-opus-4-8")
    args = mock_run.call_args[0][0]
    cmd_str = args[-1]
    assert "--model claude-opus-4-8" in cmd_str
```

Add to `adapters/claude-code/session-manager/tests/test_sessions.py`:

```python
def test_create_session_stores_model():
    s = create_session("test", "proj", "/dir", model="claude-opus-4-8")
    assert s["model"] == "claude-opus-4-8"


def test_create_session_model_defaults_none():
    s = create_session("test", "proj", "/dir")
    assert s["model"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker.exe exec ikeos pytest adapters/claude-code/session-manager/tests/test_tmux.py adapters/claude-code/session-manager/tests/test_sessions.py -k model -v`
Expected: FAIL — `TypeError: launch_session() got an unexpected keyword argument 'model'`

- [ ] **Step 3: Update `create_session()` in `sessions.py`**

Find:

```python
def create_session(name: str, project: str, project_dir: str,
                   remote_control: bool = False, ephemeral: bool = False) -> dict:
    session = {
        "id": str(uuid.uuid4()),
        "name": name,
```

Replace with:

```python
def create_session(name: str, project: str, project_dir: str,
                   remote_control: bool = False, ephemeral: bool = False,
                   model: str | None = None) -> dict:
    session = {
        "id": str(uuid.uuid4()),
        "name": name,
```

Then find the dict literal's `"ephemeral": ephemeral,` line inside the same function and add `"model": model,` immediately after it.

- [ ] **Step 4: Update `launch_session()` in `tmux.py`**

Find:

```python
def launch_session(name: str, project_dir: str, *, skip_permissions: bool = False) -> None:
    # Launch through a login shell so ~/.profile → ~/.bashrc →
    # ~/.claude/secrets.env runs and Claude inherits credentials that
    # WSL2 does not get from the Windows environment.
    cmd = CLAUDE_CMD + (["--dangerously-skip-permissions"] if skip_permissions else [])
```

Replace with:

```python
def launch_session(
    name: str, project_dir: str, *,
    skip_permissions: bool = False, model: str | None = None,
) -> None:
    # Launch through a login shell so ~/.profile → ~/.bashrc →
    # ~/.claude/secrets.env runs and Claude inherits credentials that
    # WSL2 does not get from the Windows environment.
    cmd = list(CLAUDE_CMD)
    if model:
        cmd[cmd.index("--model") + 1] = model
    cmd = cmd + (["--dangerously-skip-permissions"] if skip_permissions else [])
```

Do **not** touch `CLAUDE_BIN`, `PLUGIN_BASE`, or how `CLAUDE_CMD` is built at module level — those stay env-var-based (`os.environ.get(...)`), matching this adapter's public-distribution design. The deployed service's hardcoded absolute paths are homelab-specific and must not be ported here.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker.exe exec ikeos pytest adapters/claude-code/session-manager/tests/test_tmux.py adapters/claude-code/session-manager/tests/test_sessions.py -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/session-manager/tmux.py adapters/claude-code/session-manager/sessions.py \
        adapters/claude-code/session-manager/tests/test_tmux.py adapters/claude-code/session-manager/tests/test_sessions.py
git commit -m "feat: thread model parameter through session-manager adapter's launch/create path"
```

---

## Task 3: `research_sources.py` module + `/research-sources` routes

**Files:**
- Create: `adapters/claude-code/session-manager/research_sources.py`
- Create: `adapters/claude-code/session-manager/tests/test_research_sources.py`
- Modify: `adapters/claude-code/session-manager/app.py`

- [ ] **Step 1: Write the failing tests**

```bash
cat > /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/tests/test_research_sources.py << 'EOF'
import json

import research_sources


def test_list_sources_empty(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    assert research_sources.list_sources() == []


def test_add_source_persists(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    source = research_sources.add_source("https://example.com/feed", "Example Feed")
    assert source["url"] == "https://example.com/feed"
    assert source["label"] == "Example Feed"
    assert source["blacklisted"] is False
    assert "id" in source
    on_disk = json.loads(fake_file.read_text())
    assert len(on_disk["sources"]) == 1


def test_find_source_by_id(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    added = research_sources.add_source("https://example.com/feed", "Example Feed")
    found = research_sources.find_source(added["id"])
    assert found["url"] == "https://example.com/feed"


def test_find_source_unknown_returns_none(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    assert research_sources.find_source("nonexistent-id") is None


def test_set_blacklisted_toggles(tmp_path, monkeypatch):
    fake_file = tmp_path / "sources.json"
    monkeypatch.setattr(research_sources, "RESEARCH_SOURCES_FILE", fake_file)
    added = research_sources.add_source("https://example.com/feed", "Example Feed")
    updated = research_sources.set_blacklisted(added["id"], True)
    assert updated["blacklisted"] is True
EOF
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker.exe exec ikeos pytest adapters/claude-code/session-manager/tests/test_research_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research_sources'`

- [ ] **Step 3: Create `research_sources.py`**

```bash
cat > /mnt/c/Server/projects/ikeos/adapters/claude-code/session-manager/research_sources.py << 'EOF'
import base64
import json
import os
import threading
from datetime import date
from pathlib import Path

# Standalone reference-implementation storage: a home-directory dotfile,
# matching sessions.py's SESSIONS_FILE convention — no dependency on any
# specific host's private repo layout.
RESEARCH_SOURCES_FILE = Path.home() / ".claude-research-sources.json"

_lock = threading.Lock()


def _encode_id(url: str) -> str:
    """Derive a stable, URL-path-safe id from a source's URL (its natural key)."""
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def _decode_id(source_id: str) -> str | None:
    padded = source_id + "=" * (-len(source_id) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except Exception:
        return None


def _with_id(source: dict) -> dict:
    return {"id": _encode_id(source["url"]), **source}


def _load() -> dict:
    if not RESEARCH_SOURCES_FILE.exists():
        return {"_version": 1, "sources": []}
    return json.loads(RESEARCH_SOURCES_FILE.read_text())


def _save(data: dict) -> None:
    """Atomic write: write to a temp file in the same directory, then rename."""
    tmp_path = RESEARCH_SOURCES_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    os.replace(tmp_path, RESEARCH_SOURCES_FILE)


def list_sources() -> list[dict]:
    with _lock:
        data = _load()
    return [_with_id(s) for s in data.get("sources", [])]


def add_source(url: str, label: str) -> dict:
    with _lock:
        data = _load()
        source = {
            "url": url,
            "label": label,
            "status": "active",
            "last_fetched": None,
            "entries_generated": 0,
            "added": date.today().isoformat(),
            "blacklisted": False,
        }
        data.setdefault("sources", []).append(source)
        _save(data)
    return _with_id(source)


def find_source(source_id: str) -> dict | None:
    url = _decode_id(source_id)
    if url is None:
        return None
    with _lock:
        data = _load()
    source = next((s for s in data.get("sources", []) if s["url"] == url), None)
    return _with_id(source) if source else None


def set_blacklisted(source_id: str, blacklisted: bool) -> dict | None:
    url = _decode_id(source_id)
    if url is None:
        return None
    with _lock:
        data = _load()
        source = next((s for s in data.get("sources", []) if s["url"] == url), None)
        if source is None:
            return None
        source["blacklisted"] = blacklisted
        _save(data)
        return _with_id(source)
EOF
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker.exe exec ikeos pytest adapters/claude-code/session-manager/tests/test_research_sources.py -v`
Expected: all 5 tests pass

- [ ] **Step 5: Wire the routes into `app.py`**

In `adapters/claude-code/session-manager/app.py`, find the import block:

```python
from tmux import has_session, launch_session, kill_session, send_command, send_key, send_enter, capture_pane, send_prompt
```

Replace with (adding `list_session_names` and the new import line):

```python
from tmux import (
    has_session, launch_session, kill_session, send_command, send_key,
    send_enter, capture_pane, send_prompt, list_session_names,
)
from research_sources import (
    list_sources, add_source, find_source, set_blacklisted,
)
```

Find the end of the file:

```python
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010)
```

Replace with:

```python
def _reconcile_sessions() -> None:
    """Drop session records whose tmux session no longer exists.

    Runs once at startup so a server restart doesn't leave stale session
    records around from tmux sessions that died while the server was down.
    """
    live = list_session_names()
    for session in list_sessions():
        if session["tmux_session"] not in live:
            remove_session(session["id"])


@app.route("/research-sources", methods=["GET"])
def get_research_sources():
    return jsonify({"sources": list_sources()})


@app.route("/research-sources", methods=["POST"])
def create_research_source():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    label = (data.get("label") or "").strip()
    if not url or not label:
        return jsonify({"error": "url and label are required"}), 400
    if any(s["url"] == url for s in list_sources()):
        return jsonify({"error": "source already exists"}), 409
    source = add_source(url, label)
    return jsonify(source), 201


@app.route("/research-sources/<source_id>", methods=["PATCH"])
def toggle_research_source(source_id):
    source = find_source(source_id)
    if not source:
        abort(404)
    updated = set_blacklisted(source_id, not source["blacklisted"])
    return jsonify(updated)


if __name__ == "__main__":
    _reconcile_sessions()
    app.run(host="0.0.0.0", port=5010)
```

Note: `remove_session` must already be imported from `sessions` for `_reconcile_sessions` to work — check the existing `from sessions import (...)` line at the top of `app.py` and add `remove_session` to it if it's not already there.

- [ ] **Step 6: Thread `model` through the `POST /sessions` route**

Find, in `app.py`'s `create()` view function:

```python
    is_ephemeral = bool(data.get("initial_command"))
    try:
        launch_session(name, data["project_dir"], skip_permissions=is_ephemeral)
    except Exception as e:
        app.logger.error("Failed to launch tmux session %s: %s", name, e)
        return jsonify({"error": "Failed to launch session"}), 500

    session = create_session(
        name, data["project"],
        data["project_dir"], data.get("remote_control", False),
        ephemeral=is_ephemeral,
    )
```

Replace with:

```python
    is_ephemeral = bool(data.get("initial_command"))
    model = data.get("model")
    try:
        launch_session(name, data["project_dir"], skip_permissions=is_ephemeral, model=model)
    except Exception as e:
        app.logger.error("Failed to launch tmux session %s: %s", name, e)
        return jsonify({"error": "Failed to launch session"}), 500

    session = create_session(
        name, data["project"],
        data["project_dir"], data.get("remote_control", False),
        ephemeral=is_ephemeral,
        model=model,
    )
```

(The deployed service defaults to `model or DEFAULT_MODEL` here because it hardcodes a specific default model constant; the adapter has no such constant today and shouldn't invent a homelab-specific default — `model=model` with `None` falling through to `launch_session`'s own no-op default is the correct adapter-scoped behavior.)

- [ ] **Step 7: Run the full adapter test suite**

Run: `docker.exe exec ikeos pytest adapters/claude-code/session-manager/tests/ -v`
Expected: all tests pass, no regressions

- [ ] **Step 8: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/session-manager/research_sources.py \
        adapters/claude-code/session-manager/tests/test_research_sources.py \
        adapters/claude-code/session-manager/app.py
git commit -m "feat: add /research-sources endpoints and startup session reconciliation to session-manager adapter"
```

---

## Task 4: Update the adapter's README

**Files:**
- Modify: `adapters/claude-code/README.md`

- [ ] **Step 1: Read the current endpoint documentation**

Run: `grep -n "research-sources\|POST /sessions\|## \|### " /mnt/c/Server/projects/ikeos/adapters/claude-code/README.md`

Locate the session-manager endpoint list/table (if one exists) and the `POST /sessions` request-body documentation.

- [ ] **Step 2: Add the missing documentation**

Add a row/entry for each of `GET /research-sources`, `POST /research-sources`, `PATCH /research-sources/<id>`, matching whatever format (table or prose list) the existing endpoint docs use. Add `model` (optional string) to the documented `POST /sessions` request body fields.

- [ ] **Step 3: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add adapters/claude-code/README.md
git commit -m "docs: document /research-sources endpoints and model field in session-manager adapter README"
```

---

## Explicitly Out of Scope

- Building an ongoing automated sync mechanism (script, CI check, or deploy-config step) that diffs the adapter against the deployed service — the vault entry raised this as an option but the investigation found the drift only happens when someone forgets a manual step, not continuously; a periodic housekeeping-task reminder ("check adapter drift") is a lighter, sufficient follow-up if drift recurs, and isn't part of this pass. If drift recurs after this sync, that's the signal to build automation, not before.
- The test-collection collision between `adapters/claude-code/session-manager/tests/` and `tests/` — already fixed separately via `pytest.ini` `testpaths = tests` (see the bug entry "pytest collection error" and its commit).
