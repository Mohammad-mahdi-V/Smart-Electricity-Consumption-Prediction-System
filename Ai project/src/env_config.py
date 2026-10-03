"""
env_config.py

Persistent database environment configuration for the AI Project.

Values are stored in a single project file and applied to os.environ
(and every Control Panel subprocess) so prediction/training never depend
on the operator having exported vars in a random shell session.

File:  processed/diagnostics/setup/db_env.json
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
SETUP_DIR = PROJECT_ROOT / "processed" / "diagnostics" / "setup"
DB_ENV_PATH = SETUP_DIR / "db_env.json"

REQUIRED_KEYS = ("DB_HOST", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD")
OPTIONAL_DEFAULTS = {
    "DB_PORT": "3306",
    "DB_CHARSET": "utf8mb4",
    "DB_CONNECT_TIMEOUT": "10",
}


def ensure_setup_dir() -> Path:
    SETUP_DIR.mkdir(parents=True, exist_ok=True)
    return SETUP_DIR


def load_db_env() -> dict:
    ensure_setup_dir()
    if not DB_ENV_PATH.exists():
        return {}
    try:
        data = json.loads(DB_ENV_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_db_env(values: dict[str, Any], *, apply: bool = True) -> dict[str, str]:
    """Persist DB env vars and optionally apply them to the current process."""
    ensure_setup_dir()
    cleaned: dict[str, str] = {}
    for key in list(REQUIRED_KEYS) + list(OPTIONAL_DEFAULTS.keys()):
        if key in values and values[key] is not None and str(values[key]).strip() != "":
            cleaned[key] = str(values[key]).strip()
    for k, default in OPTIONAL_DEFAULTS.items():
        cleaned.setdefault(k, default)

    payload = {
        "updated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "platform": platform.system(),
        "values": cleaned,
    }
    DB_ENV_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Also write a simple .env for operators / external tools
    env_lines = [f"{k}={v}" for k, v in cleaned.items()]
    (PROJECT_ROOT / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    if apply:
        apply_db_env(cleaned)
    return cleaned


def apply_db_env(values: dict[str, str] | None = None) -> dict[str, str]:
    """Push DB vars into os.environ for this process."""
    values = values if values is not None else load_db_env_values()
    for k, v in values.items():
        os.environ[k] = v
    return values


def load_db_env_values() -> dict[str, str]:
    raw = load_db_env()
    if "values" in raw and isinstance(raw["values"], dict):
        return {str(k): str(v) for k, v in raw["values"].items()}
    # backward: flat file
    return {k: v for k, v in raw.items() if k.startswith("DB_")}


def is_db_configured() -> bool:
    vals = load_db_env_values()
    if all(vals.get(k) for k in REQUIRED_KEYS):
        return True
    # fall back to live process env
    return all(os.environ.get(k) for k in REQUIRED_KEYS)


def merged_environ() -> dict[str, str]:
    """os.environ + persistent DB env (persistent wins for DB_*)."""
    env = os.environ.copy()
    for k, v in load_db_env_values().items():
        env[k] = v
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def set_permanent_user_env(values: dict[str, str]) -> list[str]:
    """
    Best-effort permanent OS user env (in addition to project files).

    - Windows: setx for each key (user scope)
    - Linux/macOS: append/update ~/.config/ai_project_db_env.sh and print
      instruction; also try writing to a project-local setenv script.

    Returns list of human-readable notes about what was done.
    """
    notes: list[str] = []
    system = platform.system().lower()
    values = {**OPTIONAL_DEFAULTS, **values}

    # Always persist project-local files first
    save_db_env(values, apply=True)
    notes.append(f"Saved project env file: {DB_ENV_PATH}")
    notes.append(f"Saved project .env: {PROJECT_ROOT / '.env'}")

    if system == "windows":
        import subprocess
        for k, v in values.items():
            try:
                subprocess.run(
                    ["setx", k, v],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                notes.append(f"Windows setx {k}=***")
            except Exception as exc:
                notes.append(f"setx {k} failed: {exc}")
        notes.append(
            "Windows user env updated via setx. Open a new terminal for system-wide effect; "
            "this process and Control Panel subprocesses already see the values."
        )
    else:
        # POSIX: write a small env file the user can source; also export in current shell is done via apply
        posix_path = Path.home() / ".config" / "ai_project_db_env.sh"
        try:
            posix_path.parent.mkdir(parents=True, exist_ok=True)
            lines = ["# AI Project DB environment (auto-generated)", ""]
            for k, v in values.items():
                # escape single quotes
                safe = str(v).replace("'", "'\"'\"'")
                lines.append(f"export {k}='{safe}'")
            posix_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            notes.append(f"Wrote {posix_path} — add 'source {posix_path}' to your shell profile if desired.")
        except OSError as exc:
            notes.append(f"Could not write POSIX env helper: {exc}")
        notes.append(
            "Linux/macOS: project .env + db_env.json are the source of truth for the Control Panel."
        )

    return notes
