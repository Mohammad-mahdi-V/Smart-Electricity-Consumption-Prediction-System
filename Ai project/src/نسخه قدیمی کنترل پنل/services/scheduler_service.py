"""
scheduler_service.py

Scheduler Monitor page data. scheduler.py itself is invoked by systemd
(a timer, external to this whole project) -- the Control Panel cannot
know whether that timer is actually enabled/running, especially on
Windows where systemd doesn't exist at all. So this module only ever
reports what scheduler.py's own state file and log say about its last
runs, plus a platform check for whether systemd could even apply here.
It never fabricates a "Running" status.
"""

from __future__ import annotations

import json
import platform
from typing import Any

from . import paths


def _read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_scheduler_state() -> dict[str, Any]:
    state = _read_json(paths.SCHEDULER_STATE)
    if state is None:
        return {"available": False}

    state = dict(state)
    state["available"] = True
    return state


def get_systemd_status() -> str:
    if platform.system() != "Linux":
        return "Not Available on Windows"

    import shutil
    if shutil.which("systemctl") is None:
        return "systemd not found on this system"

    return "systemd present (service enable/status not queried by the Control Panel)"


def get_recent_log_lines(limit: int = 200) -> list[str]:
    from . import log_service
    return log_service.read_scheduler_log_lines(limit)
