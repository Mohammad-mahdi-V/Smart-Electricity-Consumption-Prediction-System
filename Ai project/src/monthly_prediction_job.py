"""
monthly_prediction_job.py

Runtime job that generates TOTAL kWh forecasts for the next complete
**Jalali (Shamsi)** month for every device_id present in device_data.

Schedule (enforced by scheduler.py):
    Run when the first day of a new Jalali month begins (local application timezone).
    Target period = that complete Jalali month (1st → last day of the Shamsi month).

Behaviour mirrors nightly_predictor.py / weekly_prediction_job.py:
    - Device discovery: DISTINCT device_id FROM device_data (never Users)
    - History: MySQL only
    - No CSV dependency at runtime
    - Schema ensure + atomic transaction
    - Upsert into monthly_predictions (UNIQUE device_id, month_start)
    - Insufficient history or missing ML model → predicted_consumption_kwh = NULL

Does NOT touch the 3-day predictor, segmentation, or 61-day requirement.
ML only – statistical fallback removed.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from database.connection import Database
from database.schema import validate_and_prepare_monthly
from database.repository import (
    get_devices,
    get_all_history,
    write_monthly_predictions,
)
from monthly_predictor import MonthlyPredictor
from jalali_calendar import next_complete_jalali_month as next_complete_month


def log(message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


def run_monthly_predictions(as_of: date | None = None) -> int:
    """
    Generate and upsert monthly total predictions for all devices.

    Parameters
    ----------
    as_of : date, optional
        Reference date for determining the target month.
        Defaults to today (local date).

    Returns
    -------
    int
        Number of device rows written (including NULL predictions).
    """
    if as_of is None:
        as_of = datetime.now().date()

    month_start, month_end = next_complete_month(as_of)

    log("=" * 70)
    log("ELECTRICITY MODEL — MONTHLY PREDICTOR")
    log("=" * 70)
    log(f"as_of={as_of.isoformat()}")
    log(f"Target Jalali month: {month_start.isoformat()} → {month_end.isoformat()}")
    log("Model: ML only (no statistical fallback)")

    db = Database()
    predictor = MonthlyPredictor()

    log("Loading history for all devices from MySQL...")
    with db.connect() as conn:
        history = get_all_history(conn)

    n_rows = 0 if history is None or history.empty else len(history)
    n_hist_devices = (
        0
        if history is None or history.empty
        else int(history["device_id"].nunique())
    )
    log(f"History ready: {n_hist_devices} devices, {n_rows} hourly rows.")

    with db.transaction() as conn:
        validate_and_prepare_monthly(conn)

        devices = get_devices(conn)
        log(f"Devices found: {len(devices)}")

        if not devices:
            log("No devices found.")
            return 0

        records = []
        n_ok = 0
        n_null = 0

        for device_id in devices:
            try:
                record = predictor.predict_to_record(
                    device_id,
                    history,
                    as_of=as_of,
                )
                record["month_start"] = month_start
                record["month_end"] = month_end
                records.append(record)

                if record["predicted_consumption_kwh"] is None:
                    n_null += 1
                    log(
                        f"Device {device_id}: insufficient history "
                        f"→ predicted_consumption_kwh=NULL"
                    )
                else:
                    n_ok += 1
                    log(
                        f"Device {device_id}: "
                        f"predicted {record['predicted_consumption_kwh']} kWh "
                        f"for {month_start} → {month_end}"
                    )
            except Exception as exc:
                log(f"ERROR device {device_id}: {exc}")
                records.append(
                    {
                        "device_id": int(device_id),
                        "month_start": month_start,
                        "month_end": month_end,
                        "predicted_consumption_kwh": None,
                        "model_version": "monthly-ml-none",
                        "generated_at": datetime.utcnow(),
                    }
                )
                n_null += 1

        inserted = write_monthly_predictions(conn, records)
        log(
            f"monthly_predictions upserted: {inserted} rows "
            f"(ok={n_ok}, null={n_null})."
        )

    log(
        f"Monthly prediction completed. "
        f"{len(records)} devices processed for month "
        f"{month_start} → {month_end}."
    )
    log("=" * 70)
    return len(records)


def main() -> None:
    try:
        run_monthly_predictions()
        sys.exit(0)
    except Exception as exc:
        log(f"FATAL: monthly prediction failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
