"""
weekly_predictor.py

Separate weekly total-consumption forecaster.

Predicts TOTAL consumption_kwh for the next complete **Shamsi week**
(Saturday → Friday). Completely independent of the 3-day segment
predictor (ElectricityPredictor / nightly_predictor).

Canonical identity: device_id.
Runtime history: MySQL device_data via repository (no CSV).

Model
-----
**ML only**. Statistical fallback has been removed.
Uses the production weekly ML model from HorizonModelStore.
If no ML model is available or features cannot be built → predicted_consumption_kwh = None.

Minimum history: MIN_COMPLETE_WEEKS complete Sat–Fri weeks with data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from cluster_runtime import load_cluster_bundle, adaptive_daily_from_history, select_cluster_model

from jalali_calendar import (
    saturday_of_week,
    friday_of_week,
    next_complete_week,
    iter_complete_weeks,
    to_jalali,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEEKLY_ML_MODEL_VERSION_PREFIX = "weekly-ml"

def _try_load_weekly_ml_model():
    """Load production weekly ML model if present. Returns (model, meta) or (None, None)."""
    try:
        from pathlib import Path as _P
        from horizon_model_store import HorizonModelStore
        import joblib
        base = _P(__file__).resolve().parent.parent
        store = HorizonModelStore(
            "weekly",
            models_root=base / "processed" / "models",
            project_root=base,
        )
        path = store.resolve_model_path()
        if path is None or not path.exists():
            return None, None
        model = joblib.load(path)
        meta = store.get_production_metadata() or {}
        return model, meta
    except Exception:
        return None, None


def _ml_weekly_features(daily: pd.DataFrame, week_start: date) -> dict[str, float] | None:
    """Build the same causal feature vector used in WeeklyHorizonTrainer (Shamsi week)."""
    if daily is None or daily.empty:
        return None
    d = daily.copy()
    d["day"] = pd.to_datetime(d["day"] if "day" in d.columns else d.index)
    if "daily_total" not in d.columns:
        if "consumption_kwh" in d.columns:
            d["daily_total"] = d["consumption_kwh"]
        elif "consumption" in d.columns:
            d["daily_total"] = d["consumption"]
        else:
            return None
    d["week_start"] = d["day"].apply(
        lambda x: saturday_of_week(x.date() if hasattr(x, "date") else x)
    )
    weekly = (
        d.groupby("week_start", as_index=False)["daily_total"]
        .sum()
        .rename(columns={"daily_total": "week_total"})
        .sort_values("week_start")
    )
    # Only weeks strictly before target week_start.
    hist = weekly[weekly["week_start"] < week_start]["week_total"].values
    if len(hist) < 2:
        return None
    ws = pd.Timestamp(week_start)
    jy, jm, _ = to_jalali(week_start)
    return {
        "prev_week": float(hist[-1]),
        "prev_2week_mean": float(np.mean(hist[-2:])),
        "prev_4week_mean": float(np.mean(hist[-4:])) if len(hist) >= 4 else float(np.mean(hist)),
        "prev_8week_mean": float(np.mean(hist[-8:])) if len(hist) >= 8 else float(np.mean(hist)),
        "prev_week_std": float(np.std(hist[-4:])) if len(hist) >= 2 else 0.0,
        "trend_4": float(hist[-1] - hist[-4]) if len(hist) >= 4 else 0.0,
        "trend_2": float(hist[-1] - hist[-2]) if len(hist) >= 2 else 0.0,
        "month": int(jm),                 # Jalali month
        "weekofyear": int(ws.isocalendar()[1]),
        "n_hist_weeks": int(len(hist)),
        "hist_min": float(np.min(hist)),
        "hist_max": float(np.max(hist)),
        "hist_mean": float(np.mean(hist)),
    }


MIN_COMPLETE_WEEKS = 2
RECENT_WEEKS_WINDOW = 8


# ---------------------------------------------------------------------------
# History aggregation
# ---------------------------------------------------------------------------

def _daily_totals(history: pd.DataFrame) -> pd.Series:
    """
    Aggregate hourly (or sub-daily) history to daily total kWh.
    Expects columns: timestamp, consumption_kwh.
    Returns Series indexed by date (python date).
    """
    if history is None or history.empty:
        return pd.Series(dtype="float64")

    df = history.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["day"] = df["timestamp"].dt.date
    daily = df.groupby("day", sort=True)["consumption_kwh"].sum()
    daily.index = pd.Index(daily.index, name="day")
    return daily.astype("float64")


def _week_total(daily: pd.Series, week_start: date, week_end: date) -> float | None:
    """Sum daily totals over [week_start, week_end]. None if any day missing."""
    days = pd.date_range(week_start, week_end, freq="D").date
    vals = []
    for d in days:
        if d not in daily.index:
            return None
        vals.append(float(daily.loc[d]))
    return float(np.sum(vals))


# ---------------------------------------------------------------------------
# Public API – ML only
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WeeklyPredictionResult:
    device_id: int
    week_start: date
    week_end: date
    predicted_consumption_kwh: float | None
    model_version: str
    generated_at: datetime
    n_history_weeks: int | None = None
    cluster_id: int = -1


class WeeklyPredictor:
    """
    ML-only weekly total forecaster using Shamsi (Sat–Fri) weeks.
    """

    def predict(
        self,
        device_id: int,
        history: pd.DataFrame,
        as_of: date | None = None,
    ) -> WeeklyPredictionResult:
        """
        Predict total kWh for the next complete Shamsi week.
        Returns None when ML model is missing or history is insufficient.
        """
        if as_of is None:
            as_of = datetime.utcnow().date()

        week_start, week_end = next_complete_week(as_of)
        generated_at = datetime.utcnow()

        empty_result = WeeklyPredictionResult(
            device_id=int(device_id),
            week_start=week_start,
            week_end=week_end,
            predicted_consumption_kwh=None,
            model_version="weekly-ml-none",
            generated_at=generated_at,
            n_history_weeks=0,
        )

        if history is None or history.empty:
            return empty_result

        if "device_id" in history.columns:
            hist = history.loc[history["device_id"] == int(device_id)].copy()
        else:
            hist = history.copy()

        daily = _daily_totals(hist)

        # ML only – no statistical fallback
        ml_model, ml_meta = _try_load_weekly_ml_model()
        cluster_id = -1
        if isinstance(ml_model, dict) and ml_model.get("bundle_type") == "adaptive_clustered_horizon_model":
            adaptive_daily = adaptive_daily_from_history(hist)
            ml_model, cluster_id = select_cluster_model(ml_model, adaptive_daily)
        if ml_model is None:
            return empty_result

        daily_for_ml = daily.rename("daily_total").reset_index()
        ml_feat = _ml_weekly_features(daily_for_ml, week_start)
        if ml_feat is None:
            return empty_result

        feature_names = (ml_meta.get("metadata") or {}).get("feature_names")
        if not feature_names:
            feature_names = list(ml_feat.keys())
        X = pd.DataFrame([{k: ml_feat.get(k, 0.0) for k in feature_names}])

        try:
            pred_ml = float(np.asarray(ml_model.predict(X)).ravel()[0])
            ver = (ml_meta or {}).get("production_version") or "ml"
            return WeeklyPredictionResult(
                device_id=int(device_id),
                week_start=week_start,
                week_end=week_end,
                predicted_consumption_kwh=round(max(0.0, pred_ml), 3),
                model_version=f"{WEEKLY_ML_MODEL_VERSION_PREFIX}-{ver}",
                generated_at=generated_at,
                n_history_weeks=int(ml_feat["n_hist_weeks"]),
                cluster_id=int(cluster_id),
            )
        except Exception:
            return empty_result

    def predict_to_record(
        self,
        device_id: int,
        history: pd.DataFrame,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """Convenience: return a dict ready for repository.write_weekly_prediction."""
        r = self.predict(device_id, history, as_of=as_of)
        return {
            "device_id": r.device_id,
            "week_start": r.week_start,
            "week_end": r.week_end,
            "predicted_consumption_kwh": r.predicted_consumption_kwh,
            "model_version": r.model_version,
            "generated_at": r.generated_at,
            "cluster_id": r.cluster_id,
        }


def predict_weekly_for_device(
    device_id: int,
    history: pd.DataFrame,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Module-level helper matching the style of other project entry points."""
    return WeeklyPredictor().predict_to_record(device_id, history, as_of=as_of)
