"""
project_service.py

Dashboard data aggregation.

Device-related numbers come from MySQL/MariaDB (device_data,
nightly_predictions, daily_actuals) via user_service and direct
queries — not from CSV on disk.

Model / scheduler / log sections still read their existing project
files (production.json, scheduler state, control-panel log).
"""

from __future__ import annotations

from typing import Any

from . import log_service, model_service, paths, scheduler_service, user_service

paths.ensure_src_on_path()


def _database_stats() -> dict[str, Any]:
    """
    Lightweight counts from the live database for the dashboard.
    """
    from database.connection import Database

    stats: dict[str, Any] = {
        "available": False,
        "device_count": 0,
        "device_data_rows": 0,
        "nightly_predictions_rows": 0,
        "daily_actuals_rows": 0,
        "last_prediction_at": None,
        "last_actual_at": None,
    }

    try:
        db = Database()
        with db.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(DISTINCT device_id) AS device_count,
                        COUNT(*) AS row_count
                    FROM device_data
                    WHERE device_id IS NOT NULL
                    """
                )
                row = cursor.fetchone() or {}
                stats["device_count"] = int(row.get("device_count") or 0)
                stats["device_data_rows"] = int(row.get("row_count") or 0)

                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt,
                           MAX(generated_at) AS last_at
                    FROM nightly_predictions
                    """
                )
                row = cursor.fetchone() or {}
                stats["nightly_predictions_rows"] = int(row.get("cnt") or 0)
                last_pred = row.get("last_at")
                if last_pred is not None:
                    stats["last_prediction_at"] = str(last_pred)

                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt,
                           MAX(computed_at) AS last_at
                    FROM daily_actuals
                    """
                )
                row = cursor.fetchone() or {}
                stats["daily_actuals_rows"] = int(row.get("cnt") or 0)
                last_act = row.get("last_at")
                if last_act is not None:
                    stats["last_actual_at"] = str(last_act)

        stats["available"] = True
    except Exception as exc:  # noqa: BLE001
        stats["error"] = str(exc)

    return stats


def get_dashboard_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {}

    # ---- Devices + DB (source of truth for operational counts) ----
    try:
        snapshot["users"] = user_service.summary_counts()
        snapshot["devices"] = snapshot["users"]  # alias for clarity
    except Exception as exc:  # noqa: BLE001
        snapshot["users"] = {"error": str(exc)}
        snapshot["devices"] = snapshot["users"]

    try:
        snapshot["database"] = _database_stats()
    except Exception as exc:  # noqa: BLE001
        snapshot["database"] = {"available": False, "error": str(exc)}

    # ---- Model artifacts on disk (unchanged) ----
    try:
        snapshot["production"] = model_service.get_production_info()
    except Exception as exc:  # noqa: BLE001
        snapshot["production"] = {"available": False, "error": str(exc)}

    try:
        snapshot["last_validation"] = model_service.get_last_validation_report()
    except Exception as exc:  # noqa: BLE001
        snapshot["last_validation"] = None
        snapshot.setdefault("errors", []).append(str(exc))

    try:
        snapshot["scheduler"] = scheduler_service.get_scheduler_state()
    except Exception as exc:  # noqa: BLE001
        snapshot["scheduler"] = {"available": False, "error": str(exc)}

    try:
        errors = log_service.all_error_events(limit=500)
        recent_errors = [e for e in errors if e.get("level") == "ERROR"]
        snapshot["recent_error_count"] = len(recent_errors)
        snapshot["recent_errors"] = recent_errors[-5:]
    except Exception as exc:  # noqa: BLE001
        snapshot["recent_error_count"] = 0
        snapshot["recent_errors"] = []
        snapshot.setdefault("errors", []).append(str(exc))

    production = snapshot.get("production", {})
    db = snapshot.get("database", {})
    devices = snapshot.get("devices") or snapshot.get("users") or {}

    if devices.get("error") or (db and not db.get("available") and db.get("error")):
        snapshot["system_status"] = "ERROR"
    elif not production.get("available"):
        snapshot["system_status"] = "ERROR"
    elif not production.get("healthy", False):
        snapshot["system_status"] = "WARNING"
    elif snapshot.get("recent_error_count", 0) > 0:
        snapshot["system_status"] = "WARNING"
    else:
        snapshot["system_status"] = "HEALTHY"

    return snapshot


def get_system_timeline(limit: int = 50) -> list[dict[str, Any]]:
    events = log_service.all_error_events(limit=limit)
    return events[-limit:]
