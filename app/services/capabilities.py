import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.services.metrics import append_event

logger = logging.getLogger(__name__)

DEFAULT_CAPABILITIES: dict = {
    "housekeeping_scheduler": {
        "enabled": False,
        "enabled_by": None,
        "enabled_at": None,
        "description": "Scheduled weekly housekeeping runs via session manager",
    },
    "weekly_platform_review": {
        "enabled": False,
        "enabled_by": None,
        "enabled_at": None,
        "description": "Weekly AI engineering platform review — researches ecosystem developments and scores platform health",
    },
}


def _capabilities_path() -> Path:
    vault = Path(os.environ.get("VAULT_PATH", "/vault"))
    return vault / "projects" / "claude-config" / "housekeeping" / "capabilities.json"


def get_capabilities() -> dict:
    path = _capabilities_path()
    result = {k: dict(v) for k, v in DEFAULT_CAPABILITIES.items()}
    if not path.exists():
        return result
    try:
        with open(path) as f:
            data = json.load(f)
        for name, record in data.items():
            if name in result:
                result[name].update(record)
        return result
    except (OSError, json.JSONDecodeError, ValueError):
        logger.exception("Failed to read capabilities from %s", path)
        return result


def is_enabled(name: str) -> bool:
    return bool(get_capabilities().get(name, {}).get("enabled", False))


def update_capability(name: str, enabled: bool, actor: str = "architect") -> dict:
    if name not in DEFAULT_CAPABILITIES:
        raise ValueError(f"Unknown capability: {name}")
    caps = get_capabilities()
    caps[name]["enabled"] = enabled
    caps[name]["enabled_by"] = actor if enabled else None
    caps[name]["enabled_at"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds") if enabled else None
    )
    path = _capabilities_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(caps, f, indent=2)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    event_type = "capability.enabled" if enabled else "capability.disabled"
    try:
        append_event(event_type, {"capability": name, "actor": actor})
    except Exception:
        logger.warning("Failed to emit %s event for capability %s", event_type, name)
    return caps[name]
