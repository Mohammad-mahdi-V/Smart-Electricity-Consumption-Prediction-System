"""
script_service.py

Script Runner page data + execution. The registry below was built by
reading each script's actual argparse definition (or confirming it has
none) -- see the audit notes next to each entry. No invented arguments.

Every script always runs as its own OS process (subprocess.Popen), never
imported into the GUI process, so a crash in any of them can't take the
Control Panel down.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from . import paths

# argparse audit (src/<file>):
#   global_learning_cycle.py : --promote (flag), --skip-rebuild (flag),
#                           --algorithm/--3day-algorithm/--weekly-algorithm/
#                           --monthly-algorithm (options), --params-json,
#                           --horizon-configs-json
#   predictor.py          : positional device_id (int) only -- forecast_days
#                           is fixed at 3 inside build_default_predictor(),
#                           not a CLI argument
#   nightly_predictor.py  : no CLI args (env-driven: DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD)
#   weekly_prediction_job.py : no CLI args (env-driven: DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD)
#   monthly_prediction_job.py : no CLI args (env-driven: DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD)
#   export_electricity_csv_from_db.py : no CLI args (env-driven: DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD)
#   build_full_daily_dataset.py : no CLI args
#   build_full_feature_dataset.py : no CLI args

SCRIPTS: dict[str, dict[str, Any]] = {
    "Prediction": {
        "file": "predictor.py",
        "description": "Run the production predictor for one user (same code path as the Predictions page).",
        "arguments": [
            {"name": "device_id", "kind": "positional", "type": "int", "label": "Device ID"},
        ],
    },
    "Global Learning Cycle": {
        "file": "global_learning_cycle.py",
        "description": "Run the unified multi-horizon Global Learning Cycle (3-day/weekly/monthly) end-to-end. Leave 'Skip dataset rebuild' unchecked only if a database (DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD) is configured -- otherwise check it to reuse the CSVs already on disk.",
        "arguments": [
            {"name": "promote", "kind": "flag", "flag": "--promote", "label": "Promote if candidate passes"},
            {"name": "skip_rebuild", "kind": "flag", "flag": "--skip-rebuild", "label": "Skip dataset rebuild"},
            {"name": "algorithm", "kind": "option", "flag": "--algorithm", "label": "Algorithm (all horizons)"},
        ],
    },
    "Nightly Prediction (DB)": {
        "file": "nightly_predictor.py",
        "description": "Runs the DB-backed nightly prediction job for all devices. Requires DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD.",
        "arguments": [],
        "requires_db": True,
    },
    "Weekly Prediction (DB)": {
        "file": "weekly_prediction_job.py",
        "description": "Runs the DB-backed weekly prediction job (next complete Saturday-Friday week) for all devices. Requires DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD.",
        "arguments": [],
        "requires_db": True,
    },
    "Monthly Prediction (DB)": {
        "file": "monthly_prediction_job.py",
        "description": "Runs the DB-backed monthly prediction job (next complete calendar month) for all devices. Requires DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD.",
        "arguments": [],
        "requires_db": True,
    },
    "daily actual writer (DB)": {
        "file": "daily_actual_writer.py",
        "description": "Runs the DB-backed daily actual writer (DB) job for all devices. Requires DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD.",
        "arguments": [],
        "requires_db": True,
    },
    "Export DB -> CSV": {
        "file": "export_electricity_csv_from_db.py",
        "description": "Export device history from the database into data/electricity_data.csv. Requires DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD.",
        "arguments": [],
        "requires_db": True,
    },
    "Build Daily Dataset": {
        "file": "build_full_daily_dataset.py",
        "description": "Rebuild processed/daily_dataset.csv from data/electricity_data.csv.",
        "arguments": [],
    },
    "Build Feature Dataset": {
        "file": "build_full_feature_dataset.py",
        "description": "Rebuild processed/feature_dataset.csv from processed/daily_dataset.csv.",
        "arguments": [],
    },
}


def registry_names() -> list[str]:
    return list(SCRIPTS.keys())


def get_script(name: str) -> dict[str, Any]:
    if name not in SCRIPTS:
        raise KeyError(f"'{name}' is not in the script registry.")
    return SCRIPTS[name]


def build_command(name: str, values: dict[str, Any]) -> list[str]:
    spec = get_script(name)
    script_path = paths.SRC_DIR / spec["file"]
    if not script_path.exists():
        raise FileNotFoundError(f"Registered script not found on disk: {script_path}")

    cmd = [sys.executable, str(script_path)]
    for arg in spec["arguments"]:
        kind = arg["kind"]
        value = values.get(arg["name"])

        if kind == "flag":
            if value:
                cmd.append(arg["flag"])
        elif kind == "positional":
            if value is None or value == "":
                raise ValueError(f"'{arg['label']}' is required.")
            cmd.append(str(value))
        elif kind == "option":
            if value is not None and value != "":
                cmd.extend([arg["flag"], str(value)])
    return cmd


@dataclass
class RunHandle:
    process: subprocess.Popen
    thread: threading.Thread


def run_script(
    name: str,
    values: dict[str, Any],
    on_line: Callable[[str], None],
    on_done: Callable[[int], None],
) -> RunHandle:
    cmd = build_command(name, values)

    process = subprocess.Popen(
        cmd,
        cwd=str(paths.SRC_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=paths.subprocess_env(),
        bufsize=1,
    )

    def _pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            on_line(line.rstrip("\n"))
        process.wait()
        on_done(process.returncode)

    thread = threading.Thread(target=_pump, daemon=True)
    thread.start()
    return RunHandle(process=process, thread=thread)