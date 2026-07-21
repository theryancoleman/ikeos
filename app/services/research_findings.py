import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CLAUDE_CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR", "")


def get_research_findings() -> dict | None:
    """Return the latest weekly research findings, or None if unavailable.

    Returns a dict with `generated_at` (str) and `summaries` (list of
    {url, label, key_points, notable_updates}) — a direct pass-through of
    research-summaries-latest.json's shape.
    """
    if not CLAUDE_CONFIG_DIR:
        return None
    path = Path(CLAUDE_CONFIG_DIR) / "library" / "research-summaries-latest.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("unexpected JSON root type")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to read research findings file: %s", exc)
        return None
    return {
        "generated_at": data.get("generated_at"),
        "summaries": data.get("summaries", []),
    }
