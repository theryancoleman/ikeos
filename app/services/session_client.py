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


def create_session(
    *,
    name: str,
    project: str,
    project_dir: str,
    initial_command: str | None = None,
) -> SessionResult:
    sm_url = os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")
    try:
        response = requests.post(
            f"{sm_url}/sessions",
            json={
                "name": name,
                "project": project,
                "project_dir": project_dir,
                "initial_command": initial_command,
            },
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
