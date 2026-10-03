"""
daily_actual_writer.py

Daily-actuals job.

nightly_predictor.py writes what the model *predicts* for the next
3 days (into nightly_predictions). This file writes the mirror
image: what actually happened on calendar days that already have
enough real hourly readings — no model involved.

On each run, for every device_id:

1. Determine which calendar days still need an actuals row:
   - any day from the backfill window up to yesterday
   - that does not already have a row in daily_actuals
2. For each such day, load device_data rows for that day.
3. Using AdaptiveBoundarySegmenter (segmenter.py):
   - find the real peak hour for that day
   - compute 4 segment boundaries from the last 30 days of history
   - sum actual kWh per segment for that day
4. Write segment_id / is_peak_hour onto that day's device_data rows.
5. Upsert one daily_actuals row per (device_id, day).

Each device is processed in its own transaction: a bad or incomplete
device is skipped without rolling back other devices.

Backfill behaviour:
  - Does NOT only process "yesterday".
  - Processes every day that (a) is on or before yesterday,
    (b) has not been written to daily_actuals yet, and
    (c) has at least MIN_VALID_HOURS_PER_DAY hourly readings.
  - Lookback is capped by MAX_BACKFILL_DAYS so a full historical
    scan is not repeated forever on every night.

Canonical device identity: device_id (NOT device_code, NOT Users).
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd


# ============================================================
# PATHS
# ============================================================

SRC_DIR = Path(__file__).resolve().parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ============================================================
# IMPORTS
# ============================================================

from database.connection import Database
from database.schema import validate_and_prepare_actuals
from database.repository import (
    get_devices,
    get_device_day_rows,
    get_recent_hourly_profile,
    get_first_available_date,
    get_last_available_date,
    get_device_actual_dates,
    update_device_data_segments,
    write_daily_actual,
)

from segmenter import AdaptiveBoundarySegmenter


# ============================================================
# CONFIG
# ============================================================

# Same threshold used elsewhere: below this we skip the day rather
# than write peak/segments from a mostly-missing day.
MIN_VALID_HOURS_PER_DAY = 20

# History window for segment boundaries (matches DatasetBuilder).
BOUNDARY_WINDOW_DAYS = 30

# Maximum number of calendar days to look back when filling gaps.
# Prevents unbounded scans on every scheduler run.
MAX_BACKFILL_DAYS = 90


# ============================================================
# LOG
# ============================================================

def log(message: str) -> None:

    timestamp = datetime.now().isoformat(
        timespec="seconds"
    )

    print(
        f"[{timestamp}] {message}",
        flush=True,
    )


# ============================================================
# DAY SELECTION (backfill)
# ============================================================

def _iter_days(start: date, end: date):
    """Inclusive calendar-day range from start to end."""
    cur = start
    while cur <= end:
        yield cur
        cur = cur + timedelta(days=1)


def days_needing_actuals(
    conn,
    device_id: int,
    as_of: date | None = None,
) -> list[date]:
    """
    Return sorted list of calendar days that still need a
    daily_actuals row for this device.

    Upper bound is always yesterday relative to as_of (default: today).
    Lower bound is the later of:
      - first day with device_data
      - (yesterday - MAX_BACKFILL_DAYS + 1)
    Days already present in daily_actuals are excluded.
    """
    if as_of is None:
        as_of = date.today()

    yesterday = as_of - timedelta(days=1)

    last_data = get_last_available_date(conn, device_id)
    first_data = get_first_available_date(conn, device_id)

    if last_data is None or first_data is None:
        return []

    # Never process a day beyond yesterday or beyond last available data.
    end = min(yesterday, last_data)

    window_start = yesterday - timedelta(days=MAX_BACKFILL_DAYS - 1)
    start = max(first_data, window_start)

    if start > end:
        return []

    already = get_device_actual_dates(conn, device_id, start=start, end=end)

    missing = [d for d in _iter_days(start, end) if d not in already]
    return missing


# ============================================================
# PER-DEVICE / PER-DAY PROCESSING
# ============================================================

def _find_segment_for_hour(
    segments: dict[int, dict[str, int]],
    hour: int,
) -> int:

    for seg_id, seg in segments.items():
        if seg["start"] <= hour <= seg["end"]:
            return seg_id

    # Boundaries always cover 0-23 by construction; fail loudly if not.
    raise RuntimeError(
        f"Hour {hour} does not fall inside any segment: {segments}"
    )


def process_device_day(
    conn,
    segmenter: AdaptiveBoundarySegmenter,
    device_id: int,
    target_day: date,
) -> str:
    """
    Process one (device_id, target_day).

    Returns "written", "skipped", or raises on a real DB error.
    """

    # --------------------------------------------------------
    # 1. Raw rows for this device on target_day
    # --------------------------------------------------------

    day_rows = get_device_day_rows(
        conn, device_id, target_day
    )

    if len(day_rows) < MIN_VALID_HOURS_PER_DAY:

        log(
            f"Device {device_id}: only {len(day_rows)} "
            f"hourly readings for {target_day} "
            f"(need {MIN_VALID_HOURS_PER_DAY}+). Skipping."
        )

        return "skipped"

    # --------------------------------------------------------
    # 2. Actual peak hour of the day
    # --------------------------------------------------------

    day_profile: dict[int, list[float]] = {}
    for row in day_rows:
        day_profile.setdefault(row["hour"], []).append(
            row["consumption_kwh"]
        )

    day_series = pd.Series(
        {h: sum(v) / len(v) for h, v in day_profile.items()}
    ).reindex(range(24))

    day_series = day_series.fillna(day_series.mean())

    peak_hour, peak_value = segmenter.detect_peak(day_series)

    # --------------------------------------------------------
    # 3. Segment boundaries (last 30 days up to target_day)
    # --------------------------------------------------------

    history = get_recent_hourly_profile(
        conn, device_id, target_day, BOUNDARY_WINDOW_DAYS
    )

    if history.empty:
        history_profile = day_series
    else:
        history = history.copy()
        history["hour"] = history["timestamp"].dt.hour
        history_profile = segmenter.build_hour_profile(history)

    boundaries = segmenter.find_boundaries(history_profile)
    segments = segmenter.create_segments(boundaries)

    peak_segment = _find_segment_for_hour(segments, peak_hour)

    seg_totals = {seg_id: 0.0 for seg_id in segments}
    for row in day_rows:
        seg_id = _find_segment_for_hour(segments, row["hour"])
        seg_totals[seg_id] += row["consumption_kwh"]

    # --------------------------------------------------------
    # 4. Tag device_data rows for this day
    # --------------------------------------------------------

    assignments = []
    for row in day_rows:
        seg_id = _find_segment_for_hour(segments, row["hour"])
        is_peak = row["hour"] == peak_hour
        assignments.append((row["id"], seg_id, is_peak))

    update_device_data_segments(conn, assignments)

    # --------------------------------------------------------
    # 5. Upsert daily_actuals summary
    # --------------------------------------------------------

    write_daily_actual(
        conn,
        {
            "device_id": device_id,
            "actual_date": target_day,
            "actual_seg0": seg_totals.get(0, 0.0),
            "actual_seg1": seg_totals.get(1, 0.0),
            "actual_seg2": seg_totals.get(2, 0.0),
            "actual_seg3": seg_totals.get(3, 0.0),
            "peak_hour": peak_hour,
            "peak_value": peak_value,
            "peak_segment": peak_segment,
        },
    )

    log(
        f"Device {device_id}: {target_day} peak hour "
        f"{peak_hour:02d}:00 (segment {peak_segment}), "
        f"{len(day_rows)} readings tagged."
    )

    return "written"


# ============================================================
# RUN DAILY ACTUALS
# ============================================================

def run_daily_actuals(
    target_day: date | None = None,
    as_of: date | None = None,
) -> int:
    """
    Fill missing daily_actuals for all devices.

    Parameters
    ----------
    target_day :
        If set, only attempt this single day (legacy / manual mode).
        If None (default), backfill every missing day up to yesterday.
    as_of :
        Reference "today" for computing yesterday and the backfill
        window. Defaults to date.today().
    """

    if as_of is None:
        as_of = date.today()

    log("=" * 70)
    log("ELECTRICITY MODEL — DAILY ACTUALS WRITER")
    if target_day is not None:
        log(f"Mode: single day = {target_day}")
    else:
        log(
            f"Mode: backfill missing days "
            f"(as_of={as_of}, window={MAX_BACKFILL_DAYS}d, "
            f"up to yesterday={as_of - timedelta(days=1)})"
        )
    log("=" * 70)

    db = Database()
    segmenter = AdaptiveBoundarySegmenter()

    with db.connect() as conn:
        validate_and_prepare_actuals(conn)
        devices = get_devices(conn)

    log(f"Devices found: {len(devices)}")

    if not devices:
        log("No devices found.")
        return 0

    written = 0
    skipped = 0
    failed = 0

    for device_id in devices:

        try:

            with db.transaction() as conn:

                if target_day is not None:
                    days = [target_day]
                else:
                    days = days_needing_actuals(
                        conn, device_id, as_of=as_of
                    )

                if not days:
                    continue

                log(
                    f"Device {device_id}: "
                    f"{len(days)} day(s) to process "
                    f"({days[0]} … {days[-1]})."
                )

                for day in days:

                    result = process_device_day(
                        conn, segmenter, device_id, day
                    )

                    if result == "written":
                        written += 1
                    else:
                        skipped += 1

        except Exception as exc:

            failed += 1

            log(
                f"ERROR device {device_id}: {exc}"
            )

    log("=" * 70)

    log(
        f"Daily actuals completed. "
        f"written={written} skipped={skipped} failed={failed}"
    )

    log("=" * 70)

    return 1 if failed else 0


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    try:

        exit_code = run_daily_actuals()

        sys.exit(exit_code)

    except Exception as exc:

        log(
            f"FATAL: daily actuals writer failed: {exc}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
