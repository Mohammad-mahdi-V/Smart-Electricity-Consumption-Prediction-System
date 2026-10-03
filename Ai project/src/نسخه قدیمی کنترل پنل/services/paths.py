"""
paths.py

Single source of truth for every filesystem path the Control Panel
touches. Nothing else in control_panel should hardcode a path.

Layout (unchanged, existing project):

    Ai project/
    ├── data/electricity_data.csv
    ├── processed/
    │   ├── feature_dataset.csv
    │   ├── daily_dataset.csv
    │   ├── models/  (production.json, electricity_model_*.joblib, <version>/)
    │   └── diagnostics/
    │       ├── monthly_retraining/monthly_retraining_report.json
    │       ├── production_validation/production_validation_report.json
    │       └── scheduler/ (scheduler.log, scheduler_state.json)
    └── src/
        ├── ...existing modules...
        └── control_panel/   <- this package
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# control_panel/services/paths.py -> control_panel -> src -> "Ai project"
CONTROL_PANEL_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = CONTROL_PANEL_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_CSV = DATA_DIR / "electricity_data.csv"

PROCESSED_DIR = PROJECT_ROOT / "processed"
FEATURE_DATASET_CSV = PROCESSED_DIR / "feature_dataset.csv"
DAILY_DATASET_CSV = PROCESSED_DIR / "daily_dataset.csv"

MODELS_DIR = PROCESSED_DIR / "models"
PRODUCTION_JSON = MODELS_DIR / "production.json"

DIAGNOSTICS_DIR = PROCESSED_DIR / "diagnostics"
MONTHLY_RETRAINING_DIR = DIAGNOSTICS_DIR / "monthly_retraining"
MONTHLY_RETRAINING_REPORT = MONTHLY_RETRAINING_DIR / "monthly_retraining_report.json"

PRODUCTION_VALIDATION_DIR = DIAGNOSTICS_DIR / "production_validation"
PRODUCTION_VALIDATION_REPORT = PRODUCTION_VALIDATION_DIR / "production_validation_report.json"
PRODUCTION_VALIDATION_SUMMARY = PRODUCTION_VALIDATION_DIR / "production_validation_summary.json"

SCHEDULER_DIR = DIAGNOSTICS_DIR / "scheduler"
SCHEDULER_LOG = SCHEDULER_DIR / "scheduler.log"
SCHEDULER_STATE = SCHEDULER_DIR / "scheduler_state.json"

# The Control Panel's own operational log (separate file, does not
# touch the project's existing logging).
CONTROL_PANEL_LOG_DIR = DIAGNOSTICS_DIR / "control_panel"
CONTROL_PANEL_LOG = CONTROL_PANEL_LOG_DIR / "control_panel.log"

SETUP_DIR = DIAGNOSTICS_DIR / "setup"
SETUP_STATUS_JSON = SETUP_DIR / "setup_status.json"
DB_ENV_JSON = SETUP_DIR / "db_env.json"


def ensure_src_on_path() -> None:
    """Make the existing project's src/ modules importable."""
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))


def python_executable() -> str:
    return sys.executable


def subprocess_env() -> dict:
    """Environment for child Python processes spawned by the Control Panel.

    Forces UTF-8 stdio and injects permanently saved DB_* vars from
    processed/diagnostics/setup/db_env.json when present.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        from env_config import load_db_env_values
        for k, v in load_db_env_values().items():
            env[k] = v
    except Exception:
        pass
    return env
