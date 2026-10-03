"""
prediction_service.py

Normal prediction reuses predictor.ElectricityPredictor.predict() exactly
as-is -- no reimplementation. As of this version, predictor.py's own
PredictorConfig.min_history_days defaults to 61 (not 30) -- the surface
check was corrected to match the pipeline's real requirement: 30 days
for DatasetBuilder's segmentation window plus 30 days for FeatureEngineer's
lag/rolling window, stacked (see the analysis in this module's git
history / project notes). Below is measured, not estimated: 60 days
still fails, 61 succeeds.

Force Prediction is the one place the Control Panel has to add a small
amount of orchestration rather than just calling into the existing code,
because ElectricityPredictor hard-blocks users below min_history_days.
That block is intentional product behavior in the existing pipeline, and
the spec explicitly asks for a "Force Prediction" override for exactly
this situation, so this module reuses every real component (DataProcessor,
DatasetBuilder, FeatureEngineer, the production ElectricityConsumptionModel,
the reference feature row fallback already in predictor.py) but pads
short histories up to a safe floor and documents that the result is
approximate. It never touches production data or the production model.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

import numpy as np
import pandas as pd

from . import paths
from . import log_service

paths.ensure_src_on_path()

from predictor import (
    build_db_predictor,
    ElectricityPredictor,
    PredictorConfig,
)

MIN_HISTORY_FOR_PREDICTION = PredictorConfig.__dataclass_fields__["min_history_days"].default
MIN_HISTORY_FOR_FORCE = 7        


def _run_in_thread(fn: Callable[[], dict[str, Any]], on_done: Callable[[dict[str, Any]], None]) -> threading.Thread:
    def _wrapper() -> None:
        try:
            result = fn()
        except Exception as exc:  
            result = {"ok": False, "error": str(exc)}
        on_done(result)

    t = threading.Thread(target=_wrapper, daemon=True)
    t.start()
    return t


def check_history(device_id: int) -> dict[str, Any]:
    """Pre-check history for the Prediction UI. Prefers DB; no CSV required."""
    # Try live DB day count first (prediction path source of truth).
    try:
        from env_config import apply_db_env
        apply_db_env()
        from database.connection import Database
        from database.repository import DatabaseDeviceDataSource
        db = Database()
        src = DatabaseDeviceDataSource(db, device_id=int(device_id))
        # repository API varies; try common methods
        hist = None
        for meth in ("get_device_history", "load_device_history", "get_history"):
            fn = getattr(src, meth, None)
            if callable(fn):
                hist = fn(int(device_id)) if meth != "get_device_history" else fn(int(device_id))
                break
        if hist is None and hasattr(src, "get_all_history"):
            hist = src.get_all_history()
        if hist is not None:
            import pandas as pd
            df = hist if not isinstance(hist, pd.DataFrame) else hist
            if isinstance(df, pd.DataFrame) and not df.empty:
                if "device_id" in df.columns:
                    df = df.loc[df["device_id"] == int(device_id)]
                day_col = "day" if "day" in df.columns else ("timestamp" if "timestamp" in df.columns else None)
                if day_col:
                    days = pd.to_datetime(df[day_col]).dt.normalize().nunique()
                    return {
                        "found": True,
                        "history_days": int(days),
                        "estimated_raw_history_days": int(days),
                        "sufficient": int(days) >= MIN_HISTORY_FOR_PREDICTION,
                        "source": "database",
                    }
    except Exception:
        pass

    from . import user_service
    detail = user_service.get_device_detail(device_id)
    if not detail.get("found"):
        return {"found": False, "history_days": 0, "estimated_raw_history_days": 0, "source": "fallback"}
    return {
        "found": True,
        "history_days": detail["history_days"],
        "estimated_raw_history_days": detail["estimated_raw_history_days"],
        "sufficient": detail["status"] == "READY",
        "source": "user_service_fallback",
    }


def predict_async(device_id: int, on_done: Callable[[dict[str, Any]], None]) -> threading.Thread:
    """Normal prediction path -- calls the real predictor unmodified."""

    def _run() -> dict[str, Any]:
        # Production path: history from device_data (DB), not CSV.
        predictor = build_db_predictor(device_id=device_id)
        result = predictor.predict(device_id)
        result["forced"] = False
        return {"ok": True, "result": result}

    return _run_in_thread(_run, on_done)


def force_predict_async(device_id: int, on_done: Callable[[dict[str, Any]], None]) -> threading.Thread:
    def _run() -> dict[str, Any]:
        result = _force_predict(device_id)
        log_service.log_event(
            "FORCED_PREDICTION",
            level="WARNING",
            component="prediction_service",
            device_id=device_id,
            message="Forced prediction executed for device with insufficient history.",
            extra={
                "history_days": result.get("history_days"),
                "required_history_days": MIN_HISTORY_FOR_PREDICTION,
                "padded_days": result.get("padded_days"),
                "backfilled_features": result.get("backfilled_features", []),
            },
        )
        return {"ok": True, "result": result}

    return _run_in_thread(_run, on_done)


FORCE_PAD_TARGET_DAYS = 65
"""
DatasetBuilder.build_daily_segments only emits a daily seg0-3 row for days
that themselves already have a full 30-day trailing window of raw hourly
data (segmentation needs 30 days of history to pick that day's adaptive
boundaries). FeatureEngineer then needs ~30 further consecutive daily rows
to fill lag_30/rolling_30 features for the target row without leaving any
NaNs (which get dropped as unusable). So the real floor for one fully
valid, NaN-free inference row is 61 days -- measured directly (60 fails,
61 succeeds) -- which is now also predictor.PredictorConfig's own
min_history_days default, so the surface check and the real requirement
match. Force Prediction still exists for anyone below that 61-day floor;
65 raw days leaves a small safety margin above it, verified against the
real pipeline.
"""


def _pad_user_history(user_df: pd.DataFrame, min_days: int = FORCE_PAD_TARGET_DAYS) -> tuple[pd.DataFrame, int]:
    """
    For users below the floor, Force Prediction pads their history
    backward by cyclically repeating their own earliest real day's hourly
    pattern with shifted dates, until the existing pipeline has enough
    days to run completely unmodified. Padded days are clearly reported
    back so the UI can show exactly how much of the result rests on real
    data vs. repeated fill.
    """
    days = sorted(user_df["day"].unique())
    if len(days) >= min_days:
        return user_df, 0

    needed = min_days - len(days)
    earliest_day = days[0]
    pattern_hours = user_df[user_df["day"] == earliest_day].copy()

    synthetic_blocks = []
    for i in range(1, needed + 1):
        block = pattern_hours.copy()
        block["timestamp"] = block["timestamp"] - pd.Timedelta(days=i)
        block["day"] = block["timestamp"].dt.date
        block["hour"] = block["timestamp"].dt.hour
        block["dayofweek"] = block["timestamp"].dt.dayofweek
        block["month"] = block["timestamp"].dt.month
        block["is_weekend"] = block["dayofweek"].isin([5, 6]).astype(int)
        synthetic_blocks.append(block)

    padded = pd.concat(list(reversed(synthetic_blocks)) + [user_df], ignore_index=True)
    padded = padded.sort_values("timestamp").reset_index(drop=True)
    return padded, needed


def _force_predict(device_id: int) -> dict[str, Any]:
    # Same DB-backed source as normal prediction / nightly job.
    predictor: ElectricityPredictor = build_db_predictor(device_id=device_id)

    processor = predictor.warm_history()

    real_user_df = processor.get_device_data(int(device_id))
    if real_user_df is None or real_user_df.empty:
        raise ValueError(f"No data found for device_id={device_id}.")

    real_user_df = real_user_df.copy()
    real_user_df["day"] = pd.to_datetime(real_user_df["day"]).dt.date
    available_days = real_user_df["day"].nunique()

    if available_days < MIN_HISTORY_FOR_FORCE:
        raise ValueError(
            f"Device {device_id} has only {available_days} days of data -- "
            f"even Force Prediction requires at least {MIN_HISTORY_FOR_FORCE} days."
        )

    user_df, padded_days = _pad_user_history(real_user_df, min_days=FORCE_PAD_TARGET_DAYS)
    user_df["day"] = pd.to_datetime(user_df["day"])

    predictor.processor = processor
    predictor.reference_feature_row = predictor._load_reference_feature_row(device_id)  # noqa: SLF001

    daily_history = predictor.build_daily_history(user_df)
    last_real_day = pd.Timestamp(sorted(real_user_df["day"].unique())[-1])

    dates = sorted(pd.to_datetime(user_df["day"]).dropna().unique())
    window = dates[-30:]
    history_window_df = user_df[user_df["day"].isin(window)].copy()
    segment_fit = predictor.builder.segmenter.fit_user(history_window_df)
    segments = segment_fit["segments"]

    working_daily = daily_history.copy()
    forecasts = []
    backfilled_features: set[str] = set()

    for step in range(1, predictor.config.forecast_days + 1):
        source_day = last_real_day + pd.Timedelta(days=step - 1)
        forecast_day = last_real_day + pd.Timedelta(days=step)
        placeholder_day = forecast_day + pd.Timedelta(days=1)


        temp = working_daily.copy()
        if not temp["day"].eq(source_day).any():
            raise RuntimeError(f"Source day {source_day.date()} is missing.")

        placeholder = {
            "device_id": int(device_id), "day": placeholder_day,
            "seg0": 0.0, "seg1": 0.0, "seg2": 0.0, "seg3": 0.0,
        }
        temp = pd.concat([temp, pd.DataFrame([placeholder])], ignore_index=True)
        temp = (
            temp.drop_duplicates(subset=["device_id", "day"], keep="last")
            .sort_values("day")
            .reset_index(drop=True)
        )

        inference_row = predictor._build_inference_row(temp, source_day)  # noqa: SLF001

        X = inference_row.copy()
        reference = predictor.reference_feature_row
        for column in predictor.model.feature_names_:
            if column not in X.columns:
                if reference is not None and column in reference.index:
                    X[column] = reference[column]
                else:
                    X[column] = 0.0
                backfilled_features.add(column)

        X = X[predictor.model.feature_names_].copy()
        for column in X.columns:
            X[column] = pd.to_numeric(X[column], errors="coerce")
        na_columns = X.columns[X.isna().any()].tolist()
        for column in na_columns:
            fallback = reference[column] if (reference is not None and column in reference.index) else 0.0
            X[column] = X[column].fillna(fallback)
            backfilled_features.add(column)

        prediction = predictor.model.predict(X)[0]
        prediction = np.maximum(np.asarray(prediction, dtype=float), 0.0)

        segment_output = predictor._segment_output(prediction, segments)  # noqa: SLF001
        peak_index = int(np.argmax(prediction))
        peak_segment = segments[peak_index]

        forecasts.append({
            "date": forecast_day.date().isoformat(),
            "segments": segment_output,
            "peak": {
                "segment": peak_index,
                "start_hour": int(peak_segment["start"]),
                "end_hour": int(peak_segment["end"]),
                "predicted_consumption_kwh": float(prediction[peak_index]),
            },
        })

        predicted_row = {
            "device_id": int(device_id),
            "day": forecast_day,
            "seg0": float(prediction[0]),
            "seg1": float(prediction[1]),
            "seg2": float(prediction[2]),
            "seg3": float(prediction[3]),
        }
        working_daily = pd.concat([working_daily, pd.DataFrame([predicted_row])], ignore_index=True)
        working_daily = (
            working_daily.drop_duplicates(subset=["device_id", "day"], keep="last")
            .sort_values("day")
            .reset_index(drop=True)
        )

    return {
        "device_id": int(device_id),
        "last_real_day": last_real_day.date().isoformat(),
        "history_days": available_days,
        "required_history_days": MIN_HISTORY_FOR_PREDICTION,
        "padded_days": padded_days,
        "forecast_days": forecasts,
        "forced": True,
        "backfilled_features": sorted(backfilled_features),
        "model": {
            "model_version": predictor.production_info.get("production_version"),
            "model_type": predictor.model.model_type,
            "n_features": predictor.model.n_features_in_,
            "model_path": str(predictor.model_path),
        },
        "segments": {
            str(seg_id): {"start_hour": int(s["start"]), "end_hour": int(s["end"])}
            for seg_id, s in segments.items()
        },
    }


# =================================================================
# STORED 3-DAY (NIGHTLY) PREDICTION READER
# =================================================================

def get_stored_3day_prediction(device_id: int) -> dict[str, Any]:
    """
    Load the *stored* 3-day forecast from nightly_predictions for
    device_id. Does NOT run ElectricityPredictor.

    Returns:
        {
          "found": True/False,
          "device_id": ...,
          "forecast_days": [today, tomorrow, day_after],  # parsed JSON
          "model_version": ...,
          "generated_at": ...,
        }
    or {"found": False, ...} when missing / error.
    """
    import json

    try:
        from database.connection import Database
        from database.repository import get_nightly_prediction
    except Exception as exc:
        return {"found": False, "error": str(exc)}

    try:
        db = Database()
        with db.connect() as conn:
            row = get_nightly_prediction(conn, int(device_id))
        if not row:
            return {"found": False}

        def _parse(raw):
            if raw is None:
                return None
            if isinstance(raw, (dict, list)):
                return raw
            return json.loads(raw)

        forecast_days = []
        for key in (
            "prediction_today",
            "prediction_tomorrow",
            "prediction_day_after_tomorrow",
        ):
            parsed = _parse(row.get(key))
            if parsed is not None:
                forecast_days.append(parsed)

        return {
            "found": True,
            "device_id": int(row["device_id"]),
            "forecast_days": forecast_days,
            "model_version": str(row.get("model_version") or "unknown"),
            "generated_at": str(row.get("generated_at") or ""),
            "forced": False,
            "stored": True,
        }
    except Exception as exc:
        return {"found": False, "error": str(exc)}


# =================================================================
# WEEKLY / MONTHLY PREDICTION READERS  (Stage 2 service integration)
# =================================================================
#
# These helpers expose the rows written by weekly_prediction_job /
# monthly_prediction_job so the Control Panel (Stage 3) and any
# other caller can retrieve them by device_id. They do not run
# predictions; they only read from MySQL.


def get_latest_weekly_prediction(device_id: int) -> dict[str, Any]:
    """
    Return the most recently generated weekly prediction for device_id,
    or {"found": False} when none exists / DB unavailable.
    """
    try:
        from database.connection import Database
        from database.repository import get_latest_weekly_predictions
    except Exception as exc:
        return {"found": False, "error": str(exc)}

    try:
        db = Database()
        with db.connect() as conn:
            rows = get_latest_weekly_predictions(conn, device_id=int(device_id))
        if not rows:
            return {"found": False}
        row = rows[0]
        return {
            "found": True,
            "device_id": int(row["device_id"]),
            "week_start": str(row["week_start"])[:10],
            "week_end": str(row["week_end"])[:10],
            "predicted_consumption_kwh": (
                None
                if row["predicted_consumption_kwh"] is None
                else float(row["predicted_consumption_kwh"])
            ),
            "model_version": str(row["model_version"]),
            "generated_at": str(row["generated_at"]),
        }
    except Exception as exc:
        return {"found": False, "error": str(exc)}


def get_latest_monthly_prediction(device_id: int) -> dict[str, Any]:
    """
    Return the most recently generated monthly prediction for device_id,
    or {"found": False} when none exists / DB unavailable.
    """
    try:
        from database.connection import Database
        from database.repository import get_latest_monthly_predictions
    except Exception as exc:
        return {"found": False, "error": str(exc)}

    try:
        db = Database()
        with db.connect() as conn:
            rows = get_latest_monthly_predictions(conn, device_id=int(device_id))
        if not rows:
            return {"found": False}
        row = rows[0]
        return {
            "found": True,
            "device_id": int(row["device_id"]),
            "month_start": str(row["month_start"])[:10],
            "month_end": str(row["month_end"])[:10],
            "predicted_consumption_kwh": (
                None
                if row["predicted_consumption_kwh"] is None
                else float(row["predicted_consumption_kwh"])
            ),
            "model_version": str(row["model_version"]),
            "generated_at": str(row["generated_at"]),
        }
    except Exception as exc:
        return {"found": False, "error": str(exc)}


# NOTE: human-readable formatting for weekly/monthly summaries lives in
# services/period_forecast_display.py (format_weekly_summary /
# format_monthly_summary) — that module is what the Control Panel page
# actually imports, so it stays the single source of truth here.
