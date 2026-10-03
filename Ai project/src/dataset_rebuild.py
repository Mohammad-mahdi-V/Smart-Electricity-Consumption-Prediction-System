"""
dataset_rebuild.py

Shared data-prep chain used before training / Global Learning Cycle.

Runs the existing, unmodified scripts in order:

    export_electricity_csv_from_db.py  ->  data/electricity_data.csv
    build_full_daily_dataset.py        ->  processed/daily_dataset.csv
    build_full_feature_dataset.py      ->  processed/feature_dataset.csv

Any failure stops the chain immediately (no training on stale/partial data).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent

PIPELINE_SCRIPTS = (
    "export_electricity_csv_from_db.py",
    "build_full_daily_dataset.py",
    "build_full_feature_dataset.py",
)


def rebuild_datasets_from_db() -> None:
    """
    Refresh CSV datasets from the live database before training.

    Each script is the existing, unmodified script — this just runs
    them in order as subprocesses (same interpreter, same src/ dir).
    Any failure stops the chain immediately.
    """
    for script_name in PIPELINE_SCRIPTS:
        script_path = SRC_DIR / script_name

        if not script_path.exists():
            raise FileNotFoundError(
                f"Required pipeline script not found: {script_path}"
            )

        print()
        print("=" * 70)
        print(f"RUNNING: {script_name}")
        print("=" * 70)

        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(SRC_DIR),
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"{script_name} failed with exit code "
                f"{result.returncode}. Stopping before retraining."
            )
