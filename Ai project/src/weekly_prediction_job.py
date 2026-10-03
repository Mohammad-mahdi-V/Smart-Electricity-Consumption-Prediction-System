"""
weekly_prediction_job.py

Runtime job that generates TOTAL kWh forecasts for the next complete
**Shamsi week** (Saturday→Friday) for every device_id present in device_data.

Schedule (enforced by scheduler.py):
    Run when Saturday begins (local application timezone).
    Target period = that Saturday through the following Friday.

Behaviour mirrors nightly_predictor.py where appropriate:
    - Device discovery: DISTINCT device_id FROM device_data (never Users)
    - History: MySQL only (repository.get_device_history / get_all_history)
    - No CSV dependency at runtime
    - Schema ensure + atomic transaction
    - Upsert into weekly_predictions (UNIQUE device_id, week_start)
      so repeated execution does not create duplicate rows
    - Insufficient history or missing ML model → predicted_consumption_kwh = NULL

Does NOT touch:
    - ElectricityPredictor / 3-day model
    - nightly_predictions table
    - segmentation / 61-day requirement

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
from database.schema import validate_and_prepare_weekly
from database.repository import (
    get_devices,
    get_all_history,
    write_weekly_predictions,
)
from weekly_predictor import WeeklyPredictor
from jalali_calendar import next_complete_week


def log(message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


def run_weekly_predictions(as_of: date | None = None) -> int:
    """
    Generate and upsert weekly total predictions for all devices.

    Parameters
    ----------
    as_of : date, optional
        Reference date for determining the target week.
        Defaults to today (local date). Pass explicitly in tests.

    Returns
    -------
    int
        Number of device rows written (including NULL predictions).
    """
    if as_of is None:
        as_of = datetime.now().date()

    week_start, week_end = next_complete_week(as_of)

    log("=" * 70)
    log("ELECTRICITY MODEL — WEEKLY PREDICTOR")
    log("=" * 70)
    log(f"as_of={as_of.isoformat()}")
    log(f"Target Shamsi week: {week_start.isoformat()} → {week_end.isoformat()}")
    log("Model: ML only (no statistical fallback)")

    db = Database()
    predictor = WeeklyPredictor()

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
        validate_and_prepare_weekly(conn)

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
                # Force the scheduled target week (consistent across devices)
                record["week_start"] = week_start
                record["week_end"] = week_end
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
                        f"for {week_start} → {week_end}"
                    )
            except Exception as exc:
                log(f"ERROR device {device_id}: {exc}")
                # Graceful: store NULL rather than aborting the whole batch
                records.append(
                    {
                        "device_id": int(device_id),
                        "week_start": week_start,
                        "week_end": week_end,
                        "predicted_consumption_kwh": None,
                        "model_version": "weekly-ml-none",
                        "generated_at": datetime.utcnow(),
                    }
                )
                n_null += 1

        inserted = write_weekly_predictions(conn, records)
        log(
            f"weekly_predictions upserted: {inserted} rows "
            f"(ok={n_ok}, null={n_null})."
        )

    log(
        f"Weekly prediction completed. "
        f"{len(records)} devices processed for week "
        f"{week_start} → {week_end}."
    )
    log("=" * 70)
    return len(records)


def main() -> None:
    try:
        run_weekly_predictions()
        sys.exit(0)
    except Exception as exc:
        log(f"FATAL: weekly prediction failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
