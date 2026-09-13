from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def format_timestamp(ts_float_or_int: float) -> str:
    """Format Unix epoch timestamp into human readable format."""
    try:
        dt = datetime.fromtimestamp(ts_float_or_int)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "N/A"


def get_recent_sessions(
    storage_dir: str = "storage/sessions", limit: int = 30
) -> list[dict[str, Any]]:
    """Scan and list past telemetry sessions sorted from newest to oldest."""
    session_path = Path(storage_dir)
    if not session_path.exists():
        return []

    sessions: list[dict[str, Any]] = []
    for file_path in session_path.glob("*.json"):
        try:
            raw_text = file_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                continue

            # Parse timestamp from file name prefix or mtime
            file_stem = file_path.stem
            parts = file_stem.split("_", 1)
            ts = None
            if parts[0].isdigit():
                ts = int(parts[0])
            else:
                ts = int(file_path.stat().st_mtime)

            events = data.get("events", [])
            sessions.append(
                {
                    "filename": file_path.name,
                    "timestamp_epoch": ts,
                    "timestamp": format_timestamp(ts),
                    "repo": data.get("repo", "N/A") or "N/A",
                    "branch": data.get("branch", "main"),
                    "goal": data.get("goal", "") or "",
                    "status": data.get("status") or data.get("final_status") or "UNKNOWN",
                    "loops": data.get("loops", 0),
                    "feature_branch": data.get("feature_branch", ""),
                    "commit_sha": data.get("commit_sha", ""),
                    "pr_url": data.get("pr_url", ""),
                    "event_count": len(events) if isinstance(events, list) else 0,
                }
            )
        except Exception as e:
            logger.warning("Error reading session file %s: %s", file_path, e)

    # Sort descending by timestamp
    sessions.sort(key=lambda s: s["timestamp_epoch"], reverse=True)
    return sessions[:limit]


def load_session_details(
    filename: str, storage_dir: str = "storage/sessions"
) -> Optional[dict[str, Any]]:
    """Load full details including events for a specific session file."""
    file_path = Path(storage_dir) / filename
    if not file_path.exists():
        return None
    try:
        raw_text = file_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return data
        return None
    except Exception as e:
        logger.warning("Failed to load session %s: %s", filename, e)
        return None
