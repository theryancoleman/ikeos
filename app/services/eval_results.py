"""Read the claude-config eval suite's results — no execution here, read-only."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_EVALS_MOUNT = Path("/claude-config/evals")


def _last_run_path() -> Path:
    return _EVALS_MOUNT / "last_run.json"


def _baselines_path() -> Path:
    return _EVALS_MOUNT / "baselines.json"


def read_last_run() -> dict | None:
    """Read last_run.json, annotating each result with its baseline score and delta.

    Returns None if last_run.json doesn't exist (no run yet, or the mount is
    absent — degrades gracefully rather than raising).
    """
    path = _last_run_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read %s", path)
        return None

    baselines = {}
    baselines_path = _baselines_path()
    if baselines_path.exists():
        try:
            baselines = json.loads(baselines_path.read_text())
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read %s", baselines_path)

    for result in data.get("results", []):
        baseline = baselines.get(result["id"])
        baseline_score = baseline["score"] if baseline else None
        result["baseline_score"] = baseline_score
        result["delta"] = (result["score"] - baseline_score) if baseline_score is not None else None

    return data
