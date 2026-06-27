import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

METRICS_PATH = Path(os.environ.get("METRICS_PATH", "/metrics/events.jsonl"))


def append_event(event_type: str, payload: dict) -> bool:
    """Append a JSON-lines event to METRICS_PATH. Returns False on write failure."""
    event = {
        **payload,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event_type,
    }
    try:
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(METRICS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        return True
    except OSError:
        logger.warning("Failed to write metrics event %s to %s", event_type, METRICS_PATH)
        return False
