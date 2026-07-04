import datetime
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CLAUDE_CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR", "")
_ABRUPT_PATTERN = "Session ended without reflection via /close-session"
_ACTIVE_DAYS = 45
_PROMOTION_THRESHOLD = 3


def get_reflection_health() -> dict | None:
    """Return reflection health metrics from claude-config library files, or None if unavailable."""
    if not CLAUDE_CONFIG_DIR:
        return None
    lib = Path(CLAUDE_CONFIG_DIR) / "library"
    signals_path = lib / "weak-signals.json"
    metrics_path = lib / "metrics.json"
    if not signals_path.exists() or not metrics_path.exists():
        return None

    try:
        sig_data = json.loads(signals_path.read_text(encoding="utf-8"))
        met_data = json.loads(metrics_path.read_text(encoding="utf-8"))
        if not isinstance(sig_data, dict) or not isinstance(met_data, dict):
            raise ValueError("unexpected JSON root type")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to read reflection health files: %s", exc)
        return None

    cutoff = (datetime.date.today() - datetime.timedelta(days=_ACTIVE_DAYS)).isoformat()
    signals = sig_data.get("signals", [])
    active = [s for s in signals if s.get("last_seen", "") >= cutoff]
    pending = [s for s in active if s.get("occurrences", 0) >= _PROMOTION_THRESHOLD]

    abrupt = next((s for s in signals if s.get("pattern") == _ABRUPT_PATTERN), None)
    abrupt_count = abrupt.get("occurrences", 0) if abrupt else 0

    snapshots = met_data.get("snapshots", [])
    latest = snapshots[-1] if snapshots else None
    acceptance_rate = latest.get("reflection_acceptance_rate") if latest else None
    last_week = latest.get("week") if latest else None

    return {
        "active_signals": len(active),
        "pending_promotion": len(pending),
        "acceptance_rate": acceptance_rate,
        "last_snapshot_week": last_week,
        "abrupt_endings": abrupt_count,
    }
