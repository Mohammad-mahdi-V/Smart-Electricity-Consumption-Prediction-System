"""
monthly_predictor.py

Separate monthly total-consumption forecaster.

Predicts TOTAL consumption_kwh for the next complete **Jalali (Shamsi)** month.
Completely independent of the 3-day segment predictor and of the weekly predictor.

Canonical identity: device_id.
Runtime history: MySQL device_data via repository (no CSV).

Model
-----
**ML only**. Statistical fallback has been removed.
Uses the production monthly ML model from HorizonModelStore.
If no ML model is available or features cannot be built → predicted_consumption_kwh = None.

Minimum history: MIN_COMPLETE_MONTHS complete Jalali months with data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from cluster_runtime import load_cluster_bundle, adaptive_daily_from_history, select_cluster_model

from jalali_calendar import (
    jalali_month_start,
    jalali_month_end,
    next_complete_jalali_month,
    iter_complete_jalali_months,
    to_jalali,
    from_jalali,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MONTHLY_ML_MODEL_VERSION_PREFIX = "monthly-ml"

def _try_load_monthly_ml_model():
    try:
        from pathlib import Path as _P
        from horizon_model_store import HorizonModelStore
        import joblib
        base = _P(__file__).resolve().parent.parent
        store = HorizonModelStore(
            "monthly",
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


def _ml_monthly_features(daily: pd.DataFrame, month_start: date) -> dict[str, float] | None:
    """Build causal features using **Jalali** months."""
    if daily is None or daily.empty:
        return None
    d = daily.copy()
    if "day" not in d.columns:
        return None
    d["day"] = pd.to_datetime(d["day"])
    if "daily_total" not in d.columns:
        if "consumption_kwh" in d.columns:
            d["daily_total"] = d["consumption_kwh"]
        elif "consumption" in d.columns:
            d["daily_total"] = d["consumption"]
        else:
            return None

    # Group by Jalali year-month
    def _j_period(ts):
        jy, jm, _ = to_jalali(ts.date() if hasattr(ts, "date") else ts)
        return f"{jy:04d}-{jm:02d}"

    d["j_month"] = d["day"].apply(_j_period)
    monthly = (
        d.groupby("j_month", as_index=False)["daily_total"]
        .sum()
        .rename(columns={"daily_total": "month_total"})
        .sort_values("j_month")
    )

    target_jy, target_jm, _ = to_jalali(month_start)
    target_key = f"{target_jy:04d}-{target_jm:02d}"
    hist = monthly[monthly["j_month"] < target_key]["month_total"].values
    if len(hist) < 2:
        return None

    return {
        "prev_month": float(hist[-1]),
        "prev_2month_mean": float(np.mean(hist[-2:])),
        "prev_3month_mean": float(np.mean(hist[-3:])) if len(hist) >= 3 else float(np.mean(hist)),
        "prev_6month_mean": float(np.mean(hist[-6:])) if len(hist) >= 6 else float(np.mean(hist)),
        "prev_12month_mean": float(np.mean(hist[-12:])) if len(hist) >= 12 else float(np.mean(hist)),
        "prev_month_std": float(np.std(hist[-3:])) if len(hist) >= 2 else 0.0,
        "trend_3": float(hist[-1] - hist[-3]) if len(hist) >= 3 else 0.0,
        "trend_1": float(hist[-1] - hist[-2]) if len(hist) >= 2 else 0.0,
        "month_num": int(target_jm),          # Jalali month 1-12
        "n_hist_months": int(len(hist)),
        "hist_min": float(np.min(hist)),
        "hist_max": float(np.max(hist)),
        "hist_mean": float(np.mean(hist)),
    }


MIN_COMPLETE_MONTHS = 2
RECENT_MONTHS_WINDOW = 12


# ---------------------------------------------------------------------------
# History aggregation
# ---------------------------------------------------------------------------

def _daily_totals(history: pd.DataFrame) -> pd.Series:
    if history is None or history.empty:
        return pd.Series(dtype="float64")

    df = history.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["day"] = df["timestamp"].dt.date
    daily = df.groupby("day", sort=True)["consumption_kwh"].sum()
    daily.index = pd.Index(daily.index, name="day")
    return daily.astype("float64")


def _month_total(daily: pd.Series, m_start: date, m_end: date) -> float | None:
    """Sum daily totals over [m_start, m_end]. None if any day missing."""
    days = pd.date_range(m_start, m_end, freq="D").date
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
class MonthlyPredictionResult:
    device_id: int
    month_start: date
    month_end: date
    predicted_consumption_kwh: float | None
    model_version: str
    generated_at: datetime
    n_history_months: int | None = None
    cluster_id: int = -1


class MonthlyPredictor:
    """
    ML-only monthly total forecaster using Jalali (Shamsi) months.
    """

    def predict(
        self,
        device_id: int,
        history: pd.DataFrame,
        as_of: date | None = None,
    ) -> MonthlyPredictionResult:
        if as_of is None:
            as_of = datetime.utcnow().date()

        m_start, m_end = next_complete_jalali_month(as_of)
        generated_at = datetime.utcnow()

        empty_result = MonthlyPredictionResult(
            device_id=int(device_id),
            month_start=m_start,
            month_end=m_end,
            predicted_consumption_kwh=None,
            model_version="monthly-ml-none",
            generated_at=generated_at,
            n_history_months=0,
        )

        if history is None or history.empty:
            return empty_result

        if "device_id" in history.columns:
            hist = history.loc[history["device_id"] == int(device_id)].copy()
        else:
            hist = history.copy()

        daily = _daily_totals(hist)

        # ML only – no statistical fallback
        ml_model, ml_meta = _try_load_monthly_ml_model()
        cluster_id = -1
        if isinstance(ml_model, dict) and ml_model.get("bundle_type") == "adaptive_clustered_horizon_model":
            adaptive_daily = adaptive_daily_from_history(hist)
            ml_model, cluster_id = select_cluster_model(ml_model, adaptive_daily)
        if ml_model is None:
            return empty_result

        daily_for_ml = daily.rename("daily_total").reset_index()
        ml_feat = _ml_monthly_features(daily_for_ml, m_start)
        if ml_feat is None:
            return empty_result

        feature_names = (ml_meta.get("metadata") or {}).get("feature_names")
        if not feature_names:
            feature_names = list(ml_feat.keys())
        X = pd.DataFrame([{k: ml_feat.get(k, 0.0) for k in feature_names}])

        try:
            pred_ml = float(np.asarray(ml_model.predict(X)).ravel()[0])
            ver = (ml_meta or {}).get("production_version") or "ml"
            return MonthlyPredictionResult(
                device_id=int(device_id),
                month_start=m_start,
                month_end=m_end,
                predicted_consumption_kwh=round(max(0.0, pred_ml), 3),
                model_version=f"{MONTHLY_ML_MODEL_VERSION_PREFIX}-{ver}",
                generated_at=generated_at,
                n_history_months=int(ml_feat["n_hist_months"]),
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
        r = self.predict(device_id, history, as_of=as_of)
        return {
            "device_id": r.device_id,
            "month_start": r.month_start,
            "month_end": r.month_end,
            "predicted_consumption_kwh": r.predicted_consumption_kwh,
            "model_version": r.model_version,
            "generated_at": r.generated_at,
            "cluster_id": r.cluster_id,
        }


def predict_monthly_for_device(
    device_id: int,
    history: pd.DataFrame,
    as_of: date | None = None,
) -> dict[str, Any]:
    return MonthlyPredictor().predict_to_record(device_id, history, as_of=as_of)
