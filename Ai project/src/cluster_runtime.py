"""cluster_runtime.py - inference-side helpers for clustered horizon models."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from dataset_builder import DatasetBuilder

BUNDLE_TYPE = "adaptive_clustered_horizon_model"
NO_CLUSTER = -1
RECENT_DAYS = 30


def is_cluster_bundle(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("bundle_type") == BUNDLE_TYPE


def load_cluster_bundle(path: str | Path) -> dict[str, Any] | None:
    try:
        obj = joblib.load(path)
    except Exception:
        return None
    return obj if is_cluster_bundle(obj) else None


def load_any_model(path: str | Path):
    """Load a production artefact: cluster bundle dict OR a plain model object."""
    return joblib.load(path)


def adaptive_daily_from_history(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame()
    df = history.copy()
    if "day" not in df.columns:
        if "timestamp" not in df.columns:
            return pd.DataFrame()
        ts = pd.to_datetime(df["timestamp"], utc=True)
        df["day"] = ts.dt.date
        df["hour"] = ts.dt.hour
    if "hour" not in df.columns:
        df["hour"] = pd.to_datetime(df["timestamp"], utc=True).dt.hour
    if "device_id" not in df.columns:
        return pd.DataFrame()
    if "consumption_kwh" not in df.columns:
        return pd.DataFrame()
    df["day"] = pd.to_datetime(df["day"])
    builder = DatasetBuilder()
    return builder.build_daily_segments(df)


def select_cluster_model_detail(bundle: dict[str, Any], adaptive_daily: pd.DataFrame) -> dict[str, Any]:
    """Pick the model for ONE device.

    Returns {"model", "cluster_id", "source", "reason"} where source is
      "cluster"  - the device's own cluster model is used
      "fallback" - global model is used. cluster_id is the real cluster when the
                   device was clustered but its cluster has no model (too small),
                   and -1 when the device is not clustered at all.
    A device that has fewer than ``clusterer.min_days`` recent days is never
    pushed through the clusterer (its profile would be meaningless).
    """
    fallback = bundle["fallback"]

    def _fb(reason: str, cluster: int = NO_CLUSTER) -> dict[str, Any]:
        return {"model": fallback, "cluster_id": int(cluster), "source": "fallback", "reason": reason}

    if adaptive_daily is None or adaptive_daily.empty:
        return _fb("no_history")
    clusterer = bundle.get("clusterer")
    if clusterer is None:
        return _fb("no_clusterer")
    min_days = int(getattr(clusterer, "min_days", 1))
    # Window must be at least min_days long, otherwise a clusterer fitted with
    # min_days > RECENT_DAYS could never accept any device at inference time.
    recent = adaptive_daily.sort_values("day").tail(max(RECENT_DAYS, min_days)).copy()
    if recent.empty:
        return _fb("no_history")
    if recent["day"].nunique() < min_days:
        return _fb("below_min_days")
    try:
        profiles = clusterer.build_device_profiles(recent)
        if hasattr(clusterer, "is_outlier") and bool(clusterer.is_outlier(profiles)[0]):
            return _fb("outlier_device")
        cluster = int(clusterer.predict_cluster(profiles)[0])
    except Exception as exc:  # noqa: BLE001
        return _fb(f"cluster_error:{type(exc).__name__}")
    model = bundle.get("models", {}).get(cluster)
    if model is None:
        return _fb("cluster_has_no_model", cluster)
    return {"model": model, "cluster_id": cluster, "source": "cluster", "reason": "ok"}


def select_cluster_model(bundle: dict[str, Any], adaptive_daily: pd.DataFrame):
    """Backward-compatible wrapper used by the weekly/monthly predictors."""
    d = select_cluster_model_detail(bundle, adaptive_daily)
    return d["model"], d["cluster_id"]
