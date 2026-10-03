"""
log_service.py

1. Record Control Panel operations in its own JSONL log.
2. Read real events from project logs.
3. Maintain persistent Read/Unread/Delete state for Error Monitor.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from typing import Any

from . import paths

_lock = threading.Lock()

# State file belongs only to Error Monitor.
# It does NOT modify scheduler.log or control_panel JSONL log.
_STATE_FILE = paths.CONTROL_PANEL_LOG_DIR / "error_monitor_state.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ============================================================
# CONTROL PANEL LOGGING
# ============================================================

def log_event(
    event_type: str,
    level: str = "INFO",
    component: str = "control_panel",
    device_id: int | str | None = None,
    message: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one structured event to the Control Panel log."""

    paths.CONTROL_PANEL_LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "timestamp": _now_iso(),
        "level": level,
        "event_type": event_type,
        "component": component,
        "device_id": device_id,
        "message": message,
    }

    if extra:
        record["extra"] = extra

    line = json.dumps(
        record,
        ensure_ascii=False,
    )

    with _lock:
        with paths.CONTROL_PANEL_LOG.open(
            "a",
            encoding="utf-8",
        ) as f:
            f.write(line + "\n")


# ============================================================
# CONTROL PANEL EVENTS
# ============================================================

def read_control_panel_events(
    limit: int = 500,
) -> list[dict[str, Any]]:

    if not paths.CONTROL_PANEL_LOG.exists():
        return []

    events: list[dict[str, Any]] = []

    try:
        with paths.CONTROL_PANEL_LOG.open(
            "r",
            encoding="utf-8",
        ) as f:

            for line in f:

                line = line.strip()

                if not line:
                    continue

                try:
                    events.append(
                        json.loads(line)
                    )
                except json.JSONDecodeError:
                    continue

    except OSError:
        return []

    return events[-limit:]


# ============================================================
# SCHEDULER LOG
# ============================================================

def read_scheduler_log_lines(
    limit: int = 400,
) -> list[str]:

    if not paths.SCHEDULER_LOG.exists():
        return []

    try:
        with paths.SCHEDULER_LOG.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as f:
            lines = f.readlines()

    except OSError:
        return []

    return [
        line.rstrip("\n").rstrip("\r")
        for line in lines[-limit:]
    ]


def scheduler_log_as_events(
    limit: int = 400,
) -> list[dict[str, Any]]:

    """
    Convert scheduler.log lines into structured events.

    Example:

        [2026-08-26T23:41:13] ERROR something failed
    """

    events: list[dict[str, Any]] = []

    for line in read_scheduler_log_lines(limit):

        timestamp = ""
        message = line

        if line.startswith("[") and "]" in line:

            end = line.index("]")

            timestamp = line[1:end]

            message = line[end + 1:].strip()

        upper = message.upper()

        if (
            "FAILED" in upper
            or "ERROR" in upper
            or "❌" in message
        ):
            level = "ERROR"

        elif (
            "WARNING" in upper
            or "WARN" in upper
        ):
            level = "WARNING"

        else:
            level = "INFO"

        events.append(
            {
                "timestamp": timestamp,
                "level": level,
                "event_type": "SCHEDULER",
                "component": "scheduler",
                "device_id": None,
                "message": message,
            }
        )

    return events


# ============================================================
# PERSISTENT ERROR MONITOR STATE
# ============================================================

def _event_id(
    event: dict[str, Any],
) -> str:

    """
    Generate a stable ID for an event.

    The ID is based on the actual event contents so the
    Read/Deleted state survives Control Panel restarts.
    """

    data = {
        "timestamp": event.get("timestamp", ""),
        "level": event.get("level", ""),
        "event_type": event.get("event_type", ""),
        "component": event.get("component", ""),
        "device_id": event.get("device_id"),
        "message": event.get("message", ""),
    }

    raw = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]


def _load_error_state() -> dict[str, list[str]]:

    default_state = {
        "read": [],
        "deleted": [],
    }

    try:

        if not _STATE_FILE.exists():
            return default_state

        data = json.loads(
            _STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, dict):
            return default_state

        read_ids = data.get("read", [])
        deleted_ids = data.get("deleted", [])

        if not isinstance(read_ids, list):
            read_ids = []

        if not isinstance(deleted_ids, list):
            deleted_ids = []

        return {
            "read": [
                str(x)
                for x in read_ids
            ],
            "deleted": [
                str(x)
                for x in deleted_ids
            ],
        }

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        return default_state


def _save_error_state(
    state: dict[str, list[str]],
) -> None:

    paths.CONTROL_PANEL_LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = _STATE_FILE.with_suffix(
        ".tmp"
    )

    temp_file.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp_file.replace(
        _STATE_FILE
    )


# ============================================================
# ERROR MONITOR EVENTS
# ============================================================

def all_error_events(
    limit: int = 500,
) -> list[dict[str, Any]]:

    """
    Return events for Error Monitor.

    Each event gets:

        id
        is_read

    Deleted events are hidden from the Error Monitor.
    """

    state = _load_error_state()

    read_ids = set(
        state.get("read", [])
    )

    deleted_ids = set(
        state.get("deleted", [])
    )

    combined = (
        read_control_panel_events(limit)
        + scheduler_log_as_events(limit)
    )

    result: list[dict[str, Any]] = []

    for original in combined:

        event = dict(original)

        event_id = _event_id(event)

        # Hide deleted events.
        if event_id in deleted_ids:
            continue

        event["id"] = event_id

        event["is_read"] = (
            event_id in read_ids
        )

        result.append(event)

    # Oldest -> newest
    result.sort(
        key=lambda e: e.get("timestamp") or ""
    )

    return result[-limit:]


# ============================================================
# MARK ONE EVENT AS READ
# ============================================================

def mark_error_read(
    event: dict[str, Any],
) -> None:

    """
    Mark one Error Monitor event as read.
    """

    event_id = (
        event.get("id")
        or _event_id(event)
    )

    with _lock:

        state = _load_error_state()

        if event_id not in state["read"]:
            state["read"].append(
                event_id
            )

        _save_error_state(
            state
        )


# ============================================================
# MARK ONE EVENT AS UNREAD
# ============================================================

def mark_error_unread(
    event: dict[str, Any],
) -> None:

    """
    Mark one event as unread.
    """

    event_id = (
        event.get("id")
        or _event_id(event)
    )

    with _lock:

        state = _load_error_state()

        state["read"] = [
            item
            for item in state["read"]
            if item != event_id
        ]

        _save_error_state(
            state
        )


# ============================================================
# MARK ALL AS READ
# ============================================================

def mark_all_errors_read() -> int:

    """
    Mark every currently visible event as read.

    Returns number of newly-read events.
    """

    events = all_error_events(
        limit=5000
    )

    unread_events = [
        event
        for event in events
        if not event.get("is_read")
    ]

    if not unread_events:
        return 0

    with _lock:

        state = _load_error_state()

        existing = set(
            state["read"]
        )

        for event in unread_events:

            event_id = (
                event.get("id")
                or _event_id(event)
            )

            existing.add(
                event_id
            )

        state["read"] = list(
            existing
        )

        _save_error_state(
            state
        )

    return len(unread_events)


# ============================================================
# DELETE READ ERRORS
# ============================================================

def delete_read_errors() -> int:

    """
    Delete/hide all READ events from Error Monitor.

    IMPORTANT:
        scheduler.log is NOT modified.
        Control Panel JSONL log is NOT modified.

    Only the Error Monitor state file is changed.
    """

    events = all_error_events(
        limit=5000
    )

    read_events = [
        event
        for event in events
        if event.get("is_read")
    ]

    if not read_events:
        return 0

    with _lock:

        state = _load_error_state()

        deleted = set(
            state["deleted"]
        )

        for event in read_events:

            event_id = (
                event.get("id")
                or _event_id(event)
            )

            deleted.add(
                event_id
            )

        state["deleted"] = list(
            deleted
        )

        _save_error_state(
            state
        )

    return len(read_events)


# ============================================================
# OPTIONAL RESET
# ============================================================

def restore_deleted_errors() -> int:

    """
    Restore events previously deleted from Error Monitor.

    This does NOT touch the original log files.
    """

    with _lock:

        state = _load_error_state()

        count = len(
            state["deleted"]
        )

        state["deleted"] = []

        _save_error_state(
            state
        )

    return count