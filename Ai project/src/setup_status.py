"""
setup_status.py

Single JSON file describing Setup progress for the AI Project.

Path: processed/diagnostics/setup/setup_status.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
SETUP_DIR = PROJECT_ROOT / "processed" / "diagnostics" / "setup"
STATUS_PATH = SETUP_DIR / "setup_status.json"

# Phases:
#   not_started
#   training_env_configured   - DB env for training machine saved
#   training_complete         - datasets + models built from training DB
#   transfer_pending          - user told to move folder to production
#   production_env_configured - production DB env saved permanently
#   complete


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_status() -> dict[str, Any]:
    return {
        "version": 1,
        "phase": "not_started",
        "updated_at": None,
        "training": {
            "env_configured": False,
            "datasets_built": False,
            "models_built": False,
            "completed_at": None,
            "notes": [],
        },
        "production": {
            "env_configured": False,
            "completed_at": None,
            "notes": [],
        },
        "transfer_message_shown": False,
        "last_error": None,
    }


def load_status() -> dict[str, Any]:
    SETUP_DIR.mkdir(parents=True, exist_ok=True)
    if not STATUS_PATH.exists():
        st = default_status()
        save_status(st)
        return st
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_status()
        base = default_status()
        base.update({k: v for k, v in data.items() if k in base or k in data})
        return data
    except (OSError, json.JSONDecodeError):
        return default_status()


def save_status(status: dict[str, Any]) -> dict[str, Any]:
    SETUP_DIR.mkdir(parents=True, exist_ok=True)
    status = dict(status)
    status["updated_at"] = _utc()
    STATUS_PATH.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return status


def update_status(**patch: Any) -> dict[str, Any]:
    st = load_status()
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(st.get(k), dict):
            st[k] = {**st[k], **v}
        else:
            st[k] = v
    return save_status(st)


def is_setup_complete() -> bool:
    st = load_status()
    return st.get("phase") == "complete"
