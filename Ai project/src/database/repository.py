"""
Repository layer.

All SQL lives here — model.py, predictor.py, and the rest of the
ML pipeline never see SQL and never talk to the database directly.

Column mapping notes (confirmed against the real schema):

    device_data.device_id         -> "device_id"        (canonical internal
                                                          device identity;
                                                          NOT Users.id,
                                                          NOT device_code)
    device_data.created_at        -> "timestamp"       MINUS 1 hour, because
                                                          created_at marks the
                                                          END of the 1-hour
                                                          measurement window,
                                                          not its start
    device_data.power_W / 1000.0  -> "consumption_kwh" (1-hour interval, so
                                                          W * 1h / 1000 = kWh)

The resulting DataFrame has exactly the columns DataProcessor
requires: device_id, timestamp, consumption_kwh.

Target engine: MySQL / MariaDB.
Canonical device identity: device_id everywhere.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import pandas as pd

from database.connection import Database


class RepositoryError(RuntimeError):
    pass


# =================================================================
# DEVICES
# =================================================================

def get_devices(conn: Any) -> list[int]:
    """
    All distinct device_ids present in device_data, ordered.

    Device discovery no longer goes through the Users table.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT device_id
            FROM device_data
            WHERE device_id IS NOT NULL
            ORDER BY device_id;
            """
        )
        return [int(row["device_id"]) for row in cursor.fetchall()]


# =================================================================
# HISTORY  (single device)
# =================================================================

def get_device_history(
    conn: Any,
    device_id: int,
) -> pd.DataFrame:
    """
    History for one device, shaped exactly like the CSV the ML
    pipeline already expects: columns device_id, timestamp,
    consumption_kwh.

    Identity is device_id (canonical). The DataFrame column is
    named device_id for DataProcessor / predictor.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT power_W, created_at
            FROM device_data
            WHERE device_id = %s
            ORDER BY created_at ASC;
            """,
            (device_id,),
        )
        rows = cursor.fetchall()
    return _rows_to_dataframe(device_id, rows)


# =================================================================
# HISTORY  (all devices, batched — for the nightly job)
# =================================================================

def get_all_history(conn: Any) -> pd.DataFrame:
    """
    History for every device in a single query.
    Returns the same three columns, for all devices, sorted by
    device_id then timestamp — i.e. the same shape CSVDataSource.load()
    would have returned.

    Identity column in the DataFrame is named device_id.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT device_id, power_W, created_at
            FROM device_data
            WHERE device_id IS NOT NULL
            ORDER BY device_id ASC, created_at ASC;
            """
        )
        rows = cursor.fetchall()

    if not rows:
        return pd.DataFrame(
            columns=["device_id", "timestamp", "consumption_kwh"]
        )

    frame = pd.DataFrame(rows)
    return _history_frame_from_raw(frame)



def get_last_available_date(
    conn: Any,
    device_id: int,
) -> date | None:
    """
    Most recent day with data for this device (after the -1h shift),
    used by the daily job's missing-data check. Returns None if the
    device has no history at all.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT MAX(created_at) AS last_created_at
            FROM device_data
            WHERE device_id = %s;
            """,
            (device_id,),
        )
        row = cursor.fetchone()

    if row is None or row["last_created_at"] is None:
        return None

    shifted = _shift_created_at(row["last_created_at"])
    return shifted.date()
def get_first_available_date(
    conn: Any,
    device_id: int,
) -> date | None:
    """
    Earliest day with data for this device (after the -1h shift).
    None if the device has no history.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT MIN(created_at) AS first_created_at
            FROM device_data
            WHERE device_id = %s;
            """,
            (device_id,),
        )
        row = cursor.fetchone()

    if row is None or row["first_created_at"] is None:
        return None

    shifted = _shift_created_at(row["first_created_at"])
    return shifted.date()


def get_device_actual_dates(
    conn: Any,
    device_id: int,
    start: date | None = None,
    end: date | None = None,
) -> set[date]:
    """
    Calendar dates already present in daily_actuals for this device.
    Optional start/end (inclusive) limit the scan.
    """
    clauses = ["device_id = %s"]
    params: list[Any] = [int(device_id)]
    if start is not None:
        clauses.append("actual_date >= %s")
        params.append(start.isoformat())
    if end is not None:
        clauses.append("actual_date <= %s")
        params.append(end.isoformat())

    sql = (
        "SELECT actual_date FROM daily_actuals WHERE "
        + " AND ".join(clauses)
    )

    with conn.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

    out: set[date] = set()
    for row in rows:
        d = row["actual_date"]
        if isinstance(d, datetime):
            out.add(d.date())
        elif isinstance(d, date):
            out.add(d)
        else:
            out.add(date.fromisoformat(str(d)[:10]))
    return out

# =================================================================
# NIGHTLY PREDICTIONS  (write side)
# =================================================================

def clear_nightly_predictions(conn: Any) -> int:
    """
    Deletes ALL rows from nightly_predictions. Intended to be called
    inside the same transaction as write_nightly_predictions so the
    replace is atomic.
    """
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM nightly_predictions;")
        return cursor.rowcount


def write_nightly_predictions(
    conn: Any,
    predictions: Iterable[dict[str, Any]],
) -> int:
    """
    Batch insert into nightly_predictions.

    Each item is the dict returned by Predictor.predict(), which must
    contain:
        device_id        canonical device identity
        forecast_days    list of 3 day payloads (today / tomorrow /
                         day-after-tomorrow), each already shaped as
                         the JSON object stored in the TEXT columns
        model            optional dict with model_version; falls back to "unknown"

    Uses INSERT ... ON DUPLICATE KEY UPDATE keyed on the unique
    device_id constraint.
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    payload = []
    for p in predictions:
        forecasts = p.get("forecast_days") or []
        if len(forecasts) != 3:
            raise RepositoryError(
                f"Expected 3 forecast days, got {len(forecasts)} "
                f"for device_id={p.get('device_id')}"
            )

        device_id = int(p["device_id"])
        model_info = p.get("model") or {}
        model_version = str(
            model_info.get("model_version")
            or p.get("model_version")
            or "unknown"
        )

        payload.append(
            (
                device_id,
                json.dumps(forecasts[0], ensure_ascii=False),
                json.dumps(forecasts[1], ensure_ascii=False),
                json.dumps(forecasts[2], ensure_ascii=False),
                model_version,
                now,
            )
        )

    if not payload:
        return 0

    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO nightly_predictions (
                device_id,
                prediction_today,
                prediction_tomorrow,
                prediction_day_after_tomorrow,
                model_version,
                generated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                prediction_today = VALUES(prediction_today),
                prediction_tomorrow = VALUES(prediction_tomorrow),
                prediction_day_after_tomorrow = VALUES(prediction_day_after_tomorrow),
                model_version = VALUES(model_version),
                generated_at = VALUES(generated_at);
            """,
            payload,
        )

    return len(payload)


def replace_all_predictions(
    conn: Any,
    predictions: Iterable[dict[str, Any]],
) -> int:
    """
    Convenience wrapper for the common nightly pattern: clear
    everything, then write the fresh batch, in one call. The caller
    is still responsible for wrapping this in db.transaction() so a
    mid-batch failure rolls back instead of leaving the table half
    empty.
    """
    clear_nightly_predictions(conn)
    return write_nightly_predictions(conn, predictions)


# =================================================================
# DAILY ACTUALS  (previous day's real peak hour + segments)
# =================================================================

def get_device_day_rows(
    conn: Any,
    device_id: int,
    day: date,
) -> list[dict[str, Any]]:
    """
    Raw device_data rows for one device on one calendar day, keyed
    by row id so the caller can write segment_id / is_peak_hour back
    onto the exact rows it read. Uses the same -1h shift as every
    other reader in this module, so "day" lines up with what the
    rest of the system calls that day.

    Returns a list of dicts sorted by hour, each with:
        id, hour (0-23), consumption_kwh
    """
    # created_at is the END of the measurement window (see module
    # docstring), so the window that shifts into `day` spans from
    # `day` 01:00 through `day + 1 day` 00:00 in raw created_at.
    day_start = datetime(day.year, day.month, day.day) + timedelta(hours=1)
    day_end = day_start + timedelta(days=1)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, power_W, created_at
            FROM device_data
            WHERE device_id = %s
              AND created_at >= %s
              AND created_at < %s
            ORDER BY created_at ASC;
            """,
            (
                device_id,
                day_start.strftime("%Y-%m-%d %H:%M:%S"),
                day_end.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        raw_rows = cursor.fetchall()

    rows = []
    for row in raw_rows:
        shifted = _shift_created_at(row["created_at"])
        rows.append(
            {
                "id": int(row["id"]),
                "hour": int(shifted.hour),
                "consumption_kwh": float(row["power_W"]) / 1000.0,
            }
        )

    return rows


def get_recent_hourly_profile(
    conn: Any,
    device_id: int,
    end_day: date,
    window_days: int = 30,
) -> pd.DataFrame:
    """
    Raw (device_id, timestamp, consumption_kwh) rows for one device,
    covering the `window_days` days up to and including end_day.
    Used to build the hour-of-day profile that segment boundaries
    are derived from — deliberately independent of DataProcessor's
    heavier cleaning pipeline, so this works even for devices that
    don't yet have the 61 days that pipeline requires.
    """
    window_start = datetime(
        end_day.year, end_day.month, end_day.day
    ) - timedelta(days=window_days - 1)
    window_end = datetime(
        end_day.year, end_day.month, end_day.day
    ) + timedelta(days=1)

    history = get_device_history(conn, device_id)

    if history.empty:
        return history

    mask = (history["timestamp"] >= pd.Timestamp(window_start, tz="UTC")) & (
        history["timestamp"] < pd.Timestamp(window_end, tz="UTC")
    )

    return history.loc[mask].reset_index(drop=True)


def update_device_data_segments(
    conn: Any,
    assignments: Iterable[tuple[int, int, bool]],
) -> int:
    """
    Writes segment_id / is_peak_hour back onto specific device_data
    rows by id. `assignments` is an iterable of
    (row_id, segment_id, is_peak_hour) tuples, e.g. as produced by
    daily_actual_writer.py after running the segmenter on one day.
    """
    payload = [
        (int(segment_id), 1 if is_peak else 0, int(row_id))
        for row_id, segment_id, is_peak in assignments
    ]

    if not payload:
        return 0

    with conn.cursor() as cursor:
        cursor.executemany(
            """
            UPDATE device_data
            SET segment_id = %s, is_peak_hour = %s
            WHERE id = %s;
            """,
            payload,
        )

    return len(payload)


def write_daily_actual(
    conn: Any,
    record: dict[str, Any],
) -> None:
    """
    Upserts one (device_id, actual_date) row into daily_actuals.
    `record` must have: device_id, actual_date (date or ISO
    string), actual_seg0..3, peak_hour, peak_value, peak_segment.

    Unlike write_nightly_predictions, this never clears the table
    first — each call only ever touches the one day it just
    computed, so a device's earlier days are never wiped by a later
    run.
    """
    actual_date = record["actual_date"]
    if isinstance(actual_date, (date, datetime)):
        actual_date = actual_date.isoformat()[:10]

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    device_id = int(record["device_id"])

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO daily_actuals (
                device_id, actual_date,
                actual_seg0, actual_seg1, actual_seg2, actual_seg3,
                peak_hour, peak_value, peak_segment, computed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                actual_seg0 = VALUES(actual_seg0),
                actual_seg1 = VALUES(actual_seg1),
                actual_seg2 = VALUES(actual_seg2),
                actual_seg3 = VALUES(actual_seg3),
                peak_hour = VALUES(peak_hour),
                peak_value = VALUES(peak_value),
                peak_segment = VALUES(peak_segment),
                computed_at = VALUES(computed_at);
            """,
            (
                device_id,
                actual_date,
                float(record["actual_seg0"]),
                float(record["actual_seg1"]),
                float(record["actual_seg2"]),
                float(record["actual_seg3"]),
                int(record["peak_hour"]),
                float(record["peak_value"]),
                int(record["peak_segment"]),
                now,
            ),
        )


# =================================================================
# INTERNAL HELPERS
# =================================================================

def _shift_created_at(created_at_raw: Any) -> pd.Timestamp:
    """
    device_data.created_at marks the END of the 1-hour measurement
    window, so we subtract 1 hour to align with the START of the
    window — matching what DataProcessor treats as "timestamp".
    """
    ts = pd.to_datetime(created_at_raw, utc=True)
    return ts - timedelta(hours=1)


def _history_frame_from_raw(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Vectorized mapping of raw device_data rows to the ML pipeline
    shape: device_id, timestamp, consumption_kwh.
    """
    if frame.empty:
        return pd.DataFrame(
            columns=["device_id", "timestamp", "consumption_kwh"]
        )

    out = pd.DataFrame(
        {
            "device_id": frame["device_id"].astype("int64"),
            "timestamp": (
                pd.to_datetime(frame["created_at"], utc=True)
                - pd.Timedelta(hours=1)
            ),
            "consumption_kwh": frame["power_W"].astype("float64") / 1000.0,
        }
    )
    return out.sort_values(["device_id", "timestamp"]).reset_index(drop=True)


def _rows_to_dataframe(
    device_id: int,
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=["device_id", "timestamp", "consumption_kwh"]
        )

    frame = pd.DataFrame(rows)
    frame["device_id"] = device_id
    return _history_frame_from_raw(frame)



# =================================================================
# NIGHTLY PREDICTIONS  (read side)
# =================================================================

def get_nightly_prediction(
    conn: Any,
    device_id: int,
) -> dict[str, Any] | None:
    """
    Fetch the stored 3-day prediction for one device from
    nightly_predictions. Returns None if no row exists.

    Columns prediction_today / prediction_tomorrow /
    prediction_day_after_tomorrow hold JSON payloads as written
    by the nightly job.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                device_id,
                prediction_today,
                prediction_tomorrow,
                prediction_day_after_tomorrow,
                model_version,
                generated_at
            FROM nightly_predictions
            WHERE device_id = %s
            LIMIT 1;
            """,
            (int(device_id),),
        )
        row = cursor.fetchone()

    if row is None:
        return None
    return dict(row)


# =================================================================
# WEEKLY PREDICTIONS  (write / read side)
# =================================================================

def write_weekly_prediction(
    conn: Any,
    record: dict[str, Any],
) -> None:
    """
    Upserts one (device_id, week_start) row into weekly_predictions.

    Required keys:
        device_id
        week_start          (date or ISO string YYYY-MM-DD)
        week_end            (date or ISO string YYYY-MM-DD)
        predicted_consumption_kwh  (float or None)
        model_version       (str)

    Optional:
        generated_at        (datetime or ISO string; defaults to utcnow)

    Unique on (device_id, week_start) — repeated scheduler runs
    replace the same target week rather than inserting duplicates.
    """
    week_start = record["week_start"]
    week_end = record["week_end"]
    if isinstance(week_start, (date, datetime)):
        week_start = week_start.isoformat()[:10]
    if isinstance(week_end, (date, datetime)):
        week_end = week_end.isoformat()[:10]

    generated_at = record.get("generated_at")
    if generated_at is None:
        generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(generated_at, datetime):
        generated_at = generated_at.strftime("%Y-%m-%d %H:%M:%S")

    pred = record.get("predicted_consumption_kwh")
    if pred is not None:
        pred = float(pred)

    device_id = int(record["device_id"])
    model_version = str(record.get("model_version") or "unknown")

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO weekly_predictions (
                device_id,
                week_start,
                week_end,
                predicted_consumption_kwh,
                model_version,
                generated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                week_end = VALUES(week_end),
                predicted_consumption_kwh = VALUES(predicted_consumption_kwh),
                model_version = VALUES(model_version),
                generated_at = VALUES(generated_at);
            """,
            (
                device_id,
                week_start,
                week_end,
                pred,
                model_version,
                generated_at,
            ),
        )


def clear_weekly_predictions(conn: Any) -> int:
    """
    Deletes ALL rows from weekly_predictions.
    Called before each weekly job run so no history is kept.
    """
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM weekly_predictions;")
        return cursor.rowcount


def write_weekly_predictions(
    conn: Any,
    predictions: Iterable[dict[str, Any]],
) -> int:
    """
    Replace-all: clear weekly_predictions, then write the fresh batch.
    No history is retained across runs.
    Returns number of rows written.
    """
    clear_weekly_predictions(conn)
    count = 0
    for record in predictions:
        write_weekly_prediction(conn, record)
        count += 1
    return count


def get_weekly_prediction(
    conn: Any,
    device_id: int,
    week_start: date | str,
) -> dict[str, Any] | None:
    """
    Fetch the prediction for one device and target week.
    Returns None if no row exists.
    """
    if isinstance(week_start, date):
        week_start = week_start.isoformat()[:10]

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                device_id,
                week_start,
                week_end,
                predicted_consumption_kwh,
                model_version,
                generated_at
            FROM weekly_predictions
            WHERE device_id = %s
              AND week_start = %s
            LIMIT 1;
            """,
            (int(device_id), week_start),
        )
        row = cursor.fetchone()

    if row is None:
        return None
    return dict(row)


def get_latest_weekly_predictions(
    conn: Any,
    device_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Return the most recently generated weekly prediction(s).
    If device_id is given, only that device; otherwise all devices
    (one row per device — the latest by generated_at then week_start).
    """
    with conn.cursor() as cursor:
        if device_id is not None:
            cursor.execute(
                """
                SELECT
                    id, device_id, week_start, week_end,
                    predicted_consumption_kwh, model_version, generated_at
                FROM weekly_predictions
                WHERE device_id = %s
                ORDER BY generated_at DESC, week_start DESC
                LIMIT 1;
                """,
                (int(device_id),),
            )
            rows = cursor.fetchall()
        else:
            cursor.execute(
                """
                SELECT w.id, w.device_id, w.week_start, w.week_end,
                       w.predicted_consumption_kwh, w.model_version,
                       w.generated_at
                FROM weekly_predictions w
                INNER JOIN (
                    SELECT device_id, MAX(generated_at) AS max_gen
                    FROM weekly_predictions
                    GROUP BY device_id
                ) latest
                  ON w.device_id = latest.device_id
                 AND w.generated_at = latest.max_gen
                ORDER BY w.device_id;
                """
            )
            rows = cursor.fetchall()
    return [dict(r) for r in rows]


# =================================================================
# MONTHLY PREDICTIONS  (write / read side)
# =================================================================

def write_monthly_prediction(
    conn: Any,
    record: dict[str, Any],
) -> None:
    """
    Upserts one (device_id, month_start) row into monthly_predictions.

    Required keys:
        device_id
        month_start         (date or ISO string YYYY-MM-DD, first of month)
        month_end           (date or ISO string YYYY-MM-DD, last of month)
        predicted_consumption_kwh  (float or None)
        model_version       (str)

    Optional:
        generated_at

    Unique on (device_id, month_start).
    """
    month_start = record["month_start"]
    month_end = record["month_end"]
    if isinstance(month_start, (date, datetime)):
        month_start = month_start.isoformat()[:10]
    if isinstance(month_end, (date, datetime)):
        month_end = month_end.isoformat()[:10]

    generated_at = record.get("generated_at")
    if generated_at is None:
        generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(generated_at, datetime):
        generated_at = generated_at.strftime("%Y-%m-%d %H:%M:%S")

    pred = record.get("predicted_consumption_kwh")
    if pred is not None:
        pred = float(pred)

    device_id = int(record["device_id"])
    model_version = str(record.get("model_version") or "unknown")

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO monthly_predictions (
                device_id,
                month_start,
                month_end,
                predicted_consumption_kwh,
                model_version,
                generated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                month_end = VALUES(month_end),
                predicted_consumption_kwh = VALUES(predicted_consumption_kwh),
                model_version = VALUES(model_version),
                generated_at = VALUES(generated_at);
            """,
            (
                device_id,
                month_start,
                month_end,
                pred,
                model_version,
                generated_at,
            ),
        )


def clear_monthly_predictions(conn: Any) -> int:
    """
    Deletes ALL rows from monthly_predictions.
    Called before each monthly job run so no history is kept.
    """
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM monthly_predictions;")
        return cursor.rowcount


def write_monthly_predictions(
    conn: Any,
    predictions: Iterable[dict[str, Any]],
) -> int:
    """
    Replace-all: clear monthly_predictions, then write the fresh batch.
    No history is retained across runs.
    Returns number of rows written.
    """
    clear_monthly_predictions(conn)
    count = 0
    for record in predictions:
        write_monthly_prediction(conn, record)
        count += 1
    return count


def get_monthly_prediction(
    conn: Any,
    device_id: int,
    month_start: date | str,
) -> dict[str, Any] | None:
    """Fetch the prediction for one device and target month. None if missing."""
    if isinstance(month_start, date):
        month_start = month_start.isoformat()[:10]

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                device_id,
                month_start,
                month_end,
                predicted_consumption_kwh,
                model_version,
                generated_at
            FROM monthly_predictions
            WHERE device_id = %s
              AND month_start = %s
            LIMIT 1;
            """,
            (int(device_id), month_start),
        )
        row = cursor.fetchone()

    if row is None:
        return None
    return dict(row)


def get_latest_monthly_predictions(
    conn: Any,
    device_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Return the most recently generated monthly prediction(s).
    If device_id is given, only that device; otherwise all devices.
    """
    with conn.cursor() as cursor:
        if device_id is not None:
            cursor.execute(
                """
                SELECT
                    id, device_id, month_start, month_end,
                    predicted_consumption_kwh, model_version, generated_at
                FROM monthly_predictions
                WHERE device_id = %s
                ORDER BY generated_at DESC, month_start DESC
                LIMIT 1;
                """,
                (int(device_id),),
            )
            rows = cursor.fetchall()
        else:
            cursor.execute(
                """
                SELECT m.id, m.device_id, m.month_start, m.month_end,
                       m.predicted_consumption_kwh, m.model_version,
                       m.generated_at
                FROM monthly_predictions m
                INNER JOIN (
                    SELECT device_id, MAX(generated_at) AS max_gen
                    FROM monthly_predictions
                    GROUP BY device_id
                ) latest
                  ON m.device_id = latest.device_id
                 AND m.generated_at = latest.max_gen
                ORDER BY m.device_id;
                """
            )
            rows = cursor.fetchall()
    return [dict(r) for r in rows]


# =================================================================
# DataSource ADAPTER  (for DataProcessor)
# =================================================================

class DatabaseDeviceDataSource:
    """
    Duck-type compatible with data_processor.DataSource (implements
    a no-arg .load() -> pd.DataFrame). Deliberately does NOT import
    from src/ so the database layer stays independent of the ML
    layer's internals — it only needs to match the interface shape.

    Drop-in replacement for CSVDataSource: DataProcessor(this).preprocess()
    works unchanged, because the returned columns
    (device_id, timestamp, consumption_kwh) are identical.

    Pass device_id to load a single device (CLI / control panel).
    Omit it to load every device (nightly job). load() is cached.
    """

    def __init__(
        self,
        db: Database,
        device_id: int | None = None,
    ) -> None:
        self.db = db
        self.device_id = device_id
        self._cached: pd.DataFrame | None = None

    def load(self) -> pd.DataFrame:
        if self._cached is None:
            with self.db.connect() as conn:
                if self.device_id is not None:
                    self._cached = get_device_history(
                        conn,
                        int(self.device_id),
                    )
                else:
                    self._cached = get_all_history(conn)
        return self._cached

