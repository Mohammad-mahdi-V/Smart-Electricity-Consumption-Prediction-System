"""
setup_service.py

Control Panel service for two-phase Setup (training machine → production machine).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import paths
from .paths import ensure_src_on_path

ensure_src_on_path()

from env_config import (  # noqa: E402
    apply_db_env,
    is_db_configured,
    load_db_env_values,
    save_db_env,
    set_permanent_user_env,
    REQUIRED_KEYS,
    OPTIONAL_DEFAULTS,
)
from setup_status import load_status, is_setup_complete  # noqa: E402

WORKER_SCRIPT = Path(__file__).resolve().parent / "_setup_worker.py"


@dataclass
class SetupHandle:
    process: subprocess.Popen
    thread: threading.Thread


def get_status() -> dict[str, Any]:
    return load_status()


def get_db_env() -> dict[str, str]:
    return load_db_env_values()


def save_database_env(values: dict[str, Any], *, permanent: bool = False) -> dict[str, Any]:
    """Save DB credentials from the Setup / Edit Env UI."""
    if permanent:
        notes = set_permanent_user_env({str(k): str(v) for k, v in values.items() if v is not None})
        return {"values": load_db_env_values(), "notes": notes}
    cleaned = save_db_env(values, apply=True)
    return {"values": cleaned, "notes": ["Saved and applied to current process."]}


def already_configured() -> bool:
    return is_setup_complete()


def run_setup_phase(
    phase: str,
    on_line: Callable[[str], None],
    on_done: Callable[[dict[str, Any] | None, int], None],
) -> SetupHandle:
    if phase not in ("training", "production"):
        raise ValueError(f"Unknown setup phase: {phase}")

    # Ensure child sees persisted env
    env = paths.subprocess_env()

    process = subprocess.Popen(
        [sys.executable, str(WORKER_SCRIPT), "--phase", phase],
        cwd=str(paths.SRC_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        bufsize=1,
    )

    def _pump() -> None:
        result: dict[str, Any] | None = None
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            if line.startswith("__RESULT_JSON__:"):
                try:
                    result = json.loads(line[len("__RESULT_JSON__:"):])
                except json.JSONDecodeError:
                    result = None
                continue
            on_line(line)
        process.wait()
        on_done(result, process.returncode)

    thread = threading.Thread(target=_pump, daemon=True)
    thread.start()
    return SetupHandle(process=process, thread=thread)
