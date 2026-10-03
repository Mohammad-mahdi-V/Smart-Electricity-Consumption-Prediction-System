
"""
_setup_worker.py

Setup worker (two-phase). Invoked as a subprocess from the Control Panel.

Phases
------
training:
  - Apply DB env (already saved by UI before launch)
  - rebuild datasets from that DB
  - run global_learning_cycle --promote (initial models)
  - write setup_status.json → training_complete / transfer_pending

production:
  - Apply permanent production DB env (already saved by UI)
  - mark setup_status.json → complete
  - optional quick DB connectivity check

Does NOT require CSV on the prediction path; CSV is only produced as a
training artifact on the training machine.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

SRC_DIR = Path(__file__).resolve().parent.parent.parent
BASE_DIR = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from env_config import apply_db_env, load_db_env_values, is_db_configured, set_permanent_user_env
from setup_status import load_status, save_status, update_status
from dataset_rebuild import rebuild_datasets_from_db
from schedule_install import install_daily_scheduler


def emit_result(payload: dict) -> None:
    print("__RESULT_JSON__:" + json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def _run_glc_promote() -> int:
    script = SRC_DIR / "global_learning_cycle.py"
    # Datasets already rebuilt in this worker; skip second rebuild inside GLC.
    cmd = [sys.executable, str(script), "--promote", "--skip-rebuild"]
    print("Running:", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(SRC_DIR)).returncode


def phase_training() -> dict:
    st = load_status()
    print("=" * 70)
    print("SETUP — PHASE: TRAINING SYSTEM")
    print("=" * 70)

    if not is_db_configured():
        raise RuntimeError(
            "Database environment is not configured. "
            "Save DB_HOST / DB_DATABASE / DB_USERNAME / DB_PASSWORD first."
        )

    apply_db_env()
    print("DB env applied for training machine.", flush=True)
    st = update_status(
        phase="training_env_configured",
        training={"env_configured": True},
        last_error=None,
    )

    print("Rebuilding datasets from training database...", flush=True)
    rebuild_datasets_from_db()
    st = update_status(training={"datasets_built": True})

    print("Training initial models via Global Learning Cycle...", flush=True)
    code = _run_glc_promote()
    if code != 0:
        # Setup must never report success when one or more horizon models failed.
        raise RuntimeError(f"Initial Global Learning Cycle failed (exit code {code}). Check the training log; models were not marked complete.")

    st = update_status(
        phase="transfer_pending",
        training={
            "models_built": True,
            "completed_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "notes": [
                "Initial models and CSV training artifacts built from the training DB.",
                "Copy the entire 'Ai project' folder to the production server, then run Setup phase: Production.",
            ],
        },
        transfer_message_shown=True,
        last_error=None,
    )

    msg = (
        "\n"
        "======================================================================\n"
        "TRAINING PHASE COMPLETE\n"
        "======================================================================\n"
        "1. Copy the entire AI Project folder to the production server.\n"
        "2. On the production server open Control Panel → Setup.\n"
        "3. Enter THAT server's database credentials and run Production phase.\n"
        "Prediction uses the DB only (no CSV required at runtime).\n"
    )
    print(msg, flush=True)
    return {"ok": True, "phase": "transfer_pending", "status": st}


def phase_production() -> dict:
    print("=" * 70)
    print("SETUP — PHASE: PRODUCTION SYSTEM")
    print("=" * 70)

    if not is_db_configured():
        raise RuntimeError(
            "Production database environment is not configured. "
            "Save production DB credentials first."
        )

    values = load_db_env_values()
    notes = set_permanent_user_env(values)
    for n in notes:
        print(n, flush=True)

    # Connectivity check
    try:
        from database.connection import Database, DatabaseConfig
        cfg = DatabaseConfig.from_env()
        db = Database(cfg)
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        print("Production DB connectivity: OK", flush=True)
    except Exception as exc:
        print(f"WARNING: DB connectivity check failed: {exc}", flush=True)
        # Still allow completing setup if models already exist; operator can fix env later
        update_status(last_error=f"DB connectivity: {exc}")

    print("Installing daily OS schedule for scheduler.py at 00:10 (24:10)...", flush=True)
    schedule_result = install_daily_scheduler()
    for n in schedule_result.get("notes") or []:
        print(n, flush=True)
    if schedule_result.get("ok"):
        notes.append(
            f"Daily schedule OK ({schedule_result.get('method')} @ {schedule_result.get('time')})"
        )
        print("Daily scheduler installed successfully.", flush=True)
    else:
        err = schedule_result.get("error") or "unknown schedule error"
        notes.append(f"Schedule install failed: {err}")
        print(f"WARNING: could not install daily schedule: {err}", flush=True)
        # Do not fail the whole Production phase — env is set; operator can fix schedule manually.

    st = update_status(
        phase="complete",
        production={
            "env_configured": True,
            "completed_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "notes": notes,
            "schedule": schedule_result,
        },
        last_error=None if schedule_result.get("ok") else f"schedule: {schedule_result.get('error')}",
    )
    print("SETUP COMPLETE — system ready for DB-backed prediction.", flush=True)
    return {
        "ok": True,
        "phase": "complete",
        "status": st,
        "schedule": schedule_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=["training", "production"],
        required=True,
    )
    args = parser.parse_args()
    try:
        if args.phase == "training":
            result = phase_training()
        else:
            result = phase_production()
        emit_result(result)
        return 0
    except Exception as exc:
        traceback.print_exc()
        try:
            update_status(last_error=str(exc))
        except Exception:
            pass
        emit_result({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
