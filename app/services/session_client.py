import logging
import os
from dataclasses import dataclass

import requests

from app.services.metrics import append_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionResult:
    session_id: str
    already_running: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def session_manager_url() -> str:
    return os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")


def create_session(
    *,
    name: str,
    project: str,
    project_dir: str,
    initial_command: str | None = None,
    model: str | None = None,
) -> SessionResult:
    sm_url = session_manager_url()
    payload = {
        "name": name,
        "project": project,
        "project_dir": project_dir,
        "initial_command": initial_command,
    }
    if model is not None:
        payload["model"] = model
    try:
        response = requests.post(
            f"{sm_url}/sessions",
            json=payload,
            timeout=5,
        )
    except requests.RequestException:
        return SessionResult(session_id="", error="Session manager unreachable")

    if response.status_code == 409:
        existing_id = response.json().get("session", {}).get("id", "")
        return SessionResult(session_id=existing_id, already_running=True)

    if not response.ok:
        return SessionResult(
            session_id="", error=f"Session manager returned {response.status_code}"
        )

    session_id = response.json().get("id", "")
    try:
        append_event(
            "session.created",
            {"session_id": session_id, "name": name, "project": project},
        )
    except Exception:
        logger.warning("Failed to emit session.created metric for session %s", session_id, exc_info=True)

    return SessionResult(session_id=session_id)


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


@dataclass(frozen=True)
class ResearchSourcesResult:
    sources: list[dict] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class ResearchSourceResult:
    source: dict | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def list_research_sources() -> ResearchSourcesResult:
    """GET /research-sources from the session manager."""
    try:
        resp = requests.get(f"{session_manager_url()}/research-sources", timeout=5)
    except requests.RequestException:
        return ResearchSourcesResult(error="Session manager unreachable")
    if not resp.ok:
        return ResearchSourcesResult(error=f"Session manager returned {resp.status_code}")
    return ResearchSourcesResult(sources=resp.json().get("sources", []))


def add_research_source(*, url: str, label: str) -> ResearchSourceResult:
    """POST /research-sources to the session manager."""
    try:
        resp = requests.post(
            f"{session_manager_url()}/research-sources",
            json={"url": url, "label": label},
            timeout=5,
        )
    except requests.RequestException:
        return ResearchSourceResult(error="Session manager unreachable")
    if resp.status_code == 409:
        return ResearchSourceResult(error="A source with that URL already exists")
    if resp.status_code == 400:
        return ResearchSourceResult(error="url and label are required")
    if not resp.ok:
        return ResearchSourceResult(error=f"Session manager returned {resp.status_code}")
    return ResearchSourceResult(source=resp.json())


def toggle_research_source(source_id: str) -> ResearchSourceResult:
    """PATCH /research-sources/<id> on the session manager — toggles blacklisted."""
    try:
        resp = requests.patch(
            f"{session_manager_url()}/research-sources/{source_id}",
            timeout=5,
        )
    except requests.RequestException:
        return ResearchSourceResult(error="Session manager unreachable")
    if resp.status_code == 404:
        return ResearchSourceResult(error="Source not found")
    if not resp.ok:
        return ResearchSourceResult(error=f"Session manager returned {resp.status_code}")
    return ResearchSourceResult(source=resp.json())


def get_session_status(session_id: str) -> dict | None:
    """Session object from the driver, or None if unknown/unreachable.

    The session manager exposes GET /sessions (list) but not GET /sessions/<id>,
    so we filter the list client-side.
    """
    try:
        resp = requests.get(
            f"{session_manager_url()}/sessions",
            timeout=3,
        )
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    sessions = resp.json()
    return next((s for s in sessions if s.get("id") == session_id), None)


def list_active_session_names(prefix: str) -> list[str]:
    """Names of currently-active sessions whose name starts with `prefix`."""
    try:
        resp = requests.get(f"{session_manager_url()}/sessions", timeout=3)
    except requests.RequestException:
        return []
    if not resp.ok:
        return []
    sessions = resp.json()
    return [
        s.get("name", "") for s in sessions
        if s.get("status") == "active" and s.get("name", "").startswith(prefix)
    ]
