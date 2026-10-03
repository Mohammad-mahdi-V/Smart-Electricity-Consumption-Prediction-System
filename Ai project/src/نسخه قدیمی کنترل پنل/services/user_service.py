"""
user_service.py

Devices page data (legacy module name kept for import stability).

Loads device list and status from the MySQL/MariaDB `device_data`
table using canonical `device_id` — not from CSV, and not from the
Laravel Users table.

Status thresholds (raw calendar days from device_data):
  - READY_THRESHOLD_DAYS = 61  (matches predictor.PredictorConfig.min_history_days)
  - MIN_DAYS_FOR_PREDICTION = 7
  - STALE_DAYS = 2
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import paths

paths.ensure_src_on_path()

from database.connection import Database  # noqa: E402


MIN_DAYS_FOR_PREDICTION = 7
READY_THRESHOLD_DAYS = 61
STALE_DAYS = 2


def _status_for(history_days: int, last_day: date, global_last_day: date) -> str:
    if history_days == 0:
        return "NO_DATA"
    if (global_last_day - last_day).days > STALE_DAYS:
        return "MISSING_RECENT_DATA"
    if history_days < MIN_DAYS_FOR_PREDICTION:
        return "NO_DATA"
    if history_days < READY_THRESHOLD_DAYS:
        return "LOW_DATA"
    return "READY"


def _shift_created_at_to_date(created_at_raw: Any) -> date | None:
    """
    device_data.created_at marks the END of the 1-hour window;
    subtract 1 hour then take the calendar date (same rule as repository).
    """
    if created_at_raw is None:
        return None
    if isinstance(created_at_raw, datetime):
        ts = created_at_raw
    else:
        ts = datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    return (ts - timedelta(hours=1)).date()


def _fetch_device_aggregates() -> list[dict[str, Any]]:
    """
    One query: per device_id, distinct calendar days (after -1h shift),
    first/last raw timestamps.
    """
    db = Database()
    with db.connect() as conn:
        with conn.cursor() as cursor:
            # MySQL: DATE(created_at - INTERVAL 1 HOUR) matches the
            # repository timestamp shift used by the ML pipeline.
            cursor.execute(
                """
                SELECT
                    device_id,
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT DATE(DATE_SUB(created_at, INTERVAL 1 HOUR)))
                        AS history_days,
                    MIN(created_at) AS first_created_at,
                    MAX(created_at) AS last_created_at
                FROM device_data
                WHERE device_id IS NOT NULL
                GROUP BY device_id
                ORDER BY device_id ASC
                """
            )
            return list(cursor.fetchall())


def list_devices(search: str = "", status_filter: str | None = None) -> list[dict[str, Any]]:
    rows_raw = _fetch_device_aggregates()

    if not rows_raw:
        return []

    parsed: list[dict[str, Any]] = []
    last_days: list[date] = []
    first_days: list[date] = []

    for r in rows_raw:
        first_day = _shift_created_at_to_date(r["first_created_at"])
        last_day = _shift_created_at_to_date(r["last_created_at"])
        if first_day is None or last_day is None:
            continue
        history_days = int(r["history_days"] or 0)
        parsed.append(
            {
                "device_id": int(r["device_id"]),
                "history_days": history_days,
                "first_day": first_day,
                "last_day": last_day,
            }
        )
        first_days.append(first_day)
        last_days.append(last_day)

    if not parsed:
        return []

    global_last_day = max(last_days)
    global_first_day = min(first_days)

    rows: list[dict[str, Any]] = []
    for p in parsed:
        last_day = p["last_day"]
        first_day = p["first_day"]
        history_days = p["history_days"]
        expected_days = (last_day - min(first_day, global_first_day)).days + 1
        missing_days = max(0, expected_days - history_days)
        status = _status_for(history_days, last_day, global_last_day)

        rows.append(
            {
                "device_id": p["device_id"],
                "history_days": history_days,
                "last_data": last_day.isoformat(),
                "missing_days": missing_days,
                "status": status,
            }
        )

    if search:
        needle = search.strip()
        rows = [r for r in rows if needle in str(r["device_id"])]

    if status_filter and status_filter != "ALL":
        rows = [r for r in rows if r["status"] == status_filter]

    rows.sort(key=lambda r: r["device_id"])
    return rows


def summary_counts() -> dict[str, int]:
    rows = list_devices()
    counts = {
        "total": len(rows),
        "READY": 0,
        "LOW_DATA": 0,
        "NO_DATA": 0,
        "MISSING_RECENT_DATA": 0,
    }
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def get_device_detail(device_id: int) -> dict[str, Any]:
    db = Database()
    with db.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT DATE(DATE_SUB(created_at, INTERVAL 1 HOUR)))
                        AS history_days,
                    MIN(created_at) AS first_created_at,
                    MAX(created_at) AS last_created_at
                FROM device_data
                WHERE device_id = %s
                """,
                (int(device_id),),
            )
            row = cursor.fetchone()

    if row is None or not row.get("row_count"):
        return {"device_id": device_id, "found": False}

    first_day = _shift_created_at_to_date(row["first_created_at"])
    last_day = _shift_created_at_to_date(row["last_created_at"])
    if first_day is None or last_day is None:
        return {"device_id": device_id, "found": False}

    history_days = int(row["history_days"] or 0)

    # global last day for status (cheap second query)
    with db.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT MAX(created_at) AS last_created_at
                FROM device_data
                WHERE device_id IS NOT NULL
                """
            )
            g = cursor.fetchone()
    global_last_day = _shift_created_at_to_date(
        g["last_created_at"] if g else None
    ) or last_day

    missing_hours = _count_missing_hours_from_db(device_id, first_day, last_day)

    return {
        "device_id": device_id,
        "found": True,
        "history_days": history_days,
        "estimated_raw_history_days": history_days,
        "first_data": first_day.isoformat(),
        "last_data": last_day.isoformat(),
        "status": _status_for(history_days, last_day, global_last_day),
        "missing_hours": missing_hours,
    }


def _count_missing_hours_from_db(
    device_id: int,
    first_day: date,
    last_day: date,
) -> int | None:
    """
    Expected hours in [first_day, last_day] vs actual hourly rows
    (after -1h shift alignment via created_at range used by repository).
    """
    expected_hours = ((last_day - first_day).days + 1) * 24
    # created_at window covering shifted first_day .. last_day
    window_start = datetime(first_day.year, first_day.month, first_day.day) + timedelta(
        hours=1
    )
    window_end = datetime(last_day.year, last_day.month, last_day.day) + timedelta(
        days=1, hours=1
    )

    db = Database()
    with db.connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM device_data
                WHERE device_id = %s
                  AND created_at >= %s
                  AND created_at < %s
                """,
                (
                    int(device_id),
                    window_start.strftime("%Y-%m-%d %H:%M:%S"),
                    window_end.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            row = cursor.fetchone()

    actual = int(row["cnt"]) if row else 0
    return max(0, expected_hours - actual)
