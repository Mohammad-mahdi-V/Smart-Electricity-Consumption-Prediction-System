"""cluster_modeling.py - training-side helpers for clustered horizon models.

A *cluster bundle* is a plain dict (joblib-serialisable) that holds:

    bundle_type      "adaptive_clustered_horizon_model"
    clusterer        fitted UserClusterer
    models           {cluster_id: fitted model}   (only clusters big enough)
    fallback         global model trained on ALL rows (used for devices that
                     were not clustered, or whose cluster is too small)
    device_clusters  {device_id: cluster_id}      (training-time assignment)
    feature_names    column order the models were trained on

Every training path in the pipeline (3day / weekly / monthly) goes through
``train_clustered_pair`` so that behaviour is identical for all horizons.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd

from clusterer import NoValidKError, UserClusterer

SEGMENTS = ["seg0", "seg1", "seg2", "seg3"]
BUNDLE_TYPE = "adaptive_clustered_horizon_model"
NO_CLUSTER = -1
FALLBACK_MIN_ROWS = 20      # fallback_scope="uncovered" needs at least this many rows, else uses all rows


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass
class ClusterSettings:
    min_days: int = 7
    k_min: int = 2
    k_max: int = 7
    min_rows: int = 20          # min training rows for a per-cluster model
    # What the global fallback model is trained on:
    #   "all"       - every training row (default; most data, most stable)
    #   "uncovered" - only rows of devices that have NO cluster model (unclustered
    #                 devices + devices of too-small clusters); degrades to "all"
    #                 when those rows are fewer than FALLBACK_MIN_ROWS
    fallback_scope: str = "all"
    random_state: int = 42
    n_init: int = 20
    # k is chosen only among values whose SMALLEST cluster has at least
    # max(min_cluster_devices, min_cluster_frac * n_devices) devices.
    min_cluster_devices: int = 30
    min_cluster_frac: float = 0.03
    # robust-z threshold; devices beyond it are kept out of KMeans and use the
    # global model (None/0 disables)
    outlier_z: float | None = 12.0


# ---------------------------------------------------------------------------
# Clusterer fitting
# ---------------------------------------------------------------------------
@dataclass
class ClusterFit:
    clusterer: UserClusterer | None
    mapping: dict[int, int]
    profiles: pd.DataFrame | None
    status: str                 # "ok" | "insufficient_users" | "no_valid_k" | "failed" | "no_source"
    reason: str = ""


def prepare_cluster_source(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Keep only what UserClusterer needs (incl. optional segment-time columns)."""
    if df is None or df.empty:
        return None
    required = ["device_id", "day", *SEGMENTS]
    if any(c not in df.columns for c in required):
        return None
    time_cols = [c for c in UserClusterer.TIME_INPUT_COLUMNS if c in df.columns]
    out = df[required + time_cols].copy()
    out["day"] = pd.to_datetime(out["day"], errors="coerce")
    out = out.dropna(subset=["day"] + SEGMENTS)
    out = out.drop_duplicates(["device_id", "day"], keep="last")
    return out.reset_index(drop=True)


def fit_clusterer(source: pd.DataFrame | None, settings: ClusterSettings) -> ClusterFit:
    """Fit a UserClusterer. Never raises: failure -> ClusterFit(status != ok)."""
    src = prepare_cluster_source(source)
    if src is None or src.empty:
        return ClusterFit(None, {}, None, "no_source",
                          "daily dataset missing device_id/day/seg0..seg3 columns or empty")

    days_per_device = src.groupby("device_id")["day"].nunique()
    n_eligible = int((days_per_device >= settings.min_days).sum())
    need = max(3, settings.k_min + 1)
    if n_eligible < need:
        return ClusterFit(None, {}, None, "insufficient_users",
                          f"{n_eligible} devices have >= {settings.min_days} days; need >= {need}")

    try:
        clusterer = UserClusterer(
            min_days=settings.min_days, k_min=settings.k_min, k_max=settings.k_max,
            random_state=settings.random_state, n_init=settings.n_init,
            min_cluster_size=settings.min_cluster_devices,
            min_cluster_frac=settings.min_cluster_frac,
            outlier_z=settings.outlier_z,
        )
        profiles = clusterer.fit(src)
    except NoValidKError as exc:   # not enough devices for ANY k -> global model only
        return ClusterFit(None, {}, None, "no_valid_k", str(exc))
    except Exception as exc:  # noqa: BLE001 - clustering must never kill training
        return ClusterFit(None, {}, None, "failed", f"{type(exc).__name__}: {exc}")

    mapping = (
        profiles.loc[profiles["cluster"] >= 0, ["device_id", "cluster"]]
        .drop_duplicates("device_id")
        .set_index("device_id")["cluster"].astype(int).to_dict()
    )
    return ClusterFit(clusterer, {int(k): int(v) for k, v in mapping.items()}, profiles, "ok")


def assign_with_existing_clusterer(source: pd.DataFrame | None, clusterer: UserClusterer) -> ClusterFit:
    """Re-use an already fitted clusterer: NO re-fitting, only (re)assign devices.

    Devices with >= clusterer.min_days of data in ``source`` get the cluster whose
    centre is nearest; the others stay unclustered (-> global fallback).
    Never raises.
    """
    src = prepare_cluster_source(source)
    if src is None or src.empty:
        return ClusterFit(None, {}, None, "no_source", "daily dataset missing or empty")
    try:
        profiles = clusterer.build_device_profiles(src).drop(columns=["cluster"], errors="ignore")
        eligible = profiles[profiles["days_available"] >= int(clusterer.min_days)].copy()
        if eligible.empty:
            return ClusterFit(None, {}, None, "insufficient_users", "no device satisfies min_days")
        eligible["cluster"] = clusterer.predict_cluster(eligible)
        # devices that are outliers w.r.t. the fitted population stay unclustered
        eligible.loc[clusterer.is_outlier(eligible), "cluster"] = NO_CLUSTER
        profiles = profiles.merge(eligible[["device_id", "cluster"]], on="device_id", how="left")
        profiles["cluster"] = profiles["cluster"].fillna(NO_CLUSTER).astype(int)
    except Exception as exc:  # noqa: BLE001
        return ClusterFit(None, {}, None, "failed", f"{type(exc).__name__}: {exc}")
    mapping = (
        profiles.loc[profiles["cluster"] >= 0, ["device_id", "cluster"]]
        .drop_duplicates("device_id").set_index("device_id")["cluster"].astype(int).to_dict()
    )
    fit = ClusterFit(clusterer, {int(k): int(v) for k, v in mapping.items()}, profiles, "ok")
    return fit


def _obtain_fit(src, settings: ClusterSettings, existing: UserClusterer | None, label: str):
    """Fresh fit when ``existing`` is None, otherwise re-use it (fresh fit as safety net)."""
    if existing is not None:
        fit = assign_with_existing_clusterer(src, existing)
        if fit.status == "ok":
            return fit, "existing"
        warnings.warn(f"re-using existing clusterer failed for {label} ({fit.reason}); fitting a new one")
    return fit_clusterer(src, settings), "fresh"


# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------
def is_cluster_bundle(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("bundle_type") == BUNDLE_TYPE


def labels_for_devices(device_ids, mapping: dict[int, int]) -> np.ndarray:
    """Cluster label per row; devices without a cluster get -1 (-> fallback)."""
    s = pd.Series(np.asarray(device_ids))
    return s.map(mapping).fillna(NO_CLUSTER).astype(int).to_numpy()


def _take(obj, mask: np.ndarray):
    if hasattr(obj, "iloc"):
        return obj.iloc[mask]
    return np.asarray(obj)[mask]


def predict_with_bundle(bundle: dict[str, Any], X: pd.DataFrame, labels: np.ndarray) -> np.ndarray:
    fallback = bundle["fallback"]
    if len(X) == 0:
        return np.empty((0, 0), dtype=float)
    names = bundle.get("feature_names")
    if names:
        X = X[[c for c in names]]
    first = np.asarray(fallback.predict(X), dtype=float).reshape(len(X), -1)
    pred = np.zeros_like(first)
    for cluster in np.unique(labels):
        mask = labels == cluster
        model = bundle["models"].get(int(cluster), fallback)
        pred[mask] = np.asarray(model.predict(X.iloc[mask])).reshape(int(mask.sum()), -1)
    return pred


def predict_any(model_obj: Any, X: pd.DataFrame, device_ids=None) -> np.ndarray:
    """Predict with either a plain model or a cluster bundle."""
    if is_cluster_bundle(model_obj):
        if device_ids is None:
            labels = np.full(len(X), NO_CLUSTER, dtype=int)
        else:
            labels = labels_for_devices(device_ids, model_obj.get("device_clusters", {}))
        return predict_with_bundle(model_obj, X, labels)
    return np.asarray(model_obj.predict(X))


def make_bundle(
    fit: ClusterFit,
    X: pd.DataFrame,
    y,
    device_ids,
    build_model: Callable[[], Any],
    min_rows: int,
    *,
    fallback_scope: str = "all",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One model per sufficiently large cluster + a global fallback model.

    The fallback serves every device WITHOUT a cluster model: devices that were
    never clustered (too little history) and devices whose cluster was too small
    to get its own model.
    """
    labels = labels_for_devices(device_ids, fit.mapping)

    models: dict[int, Any] = {}
    rows: dict[int, int] = {}
    skipped: dict[int, int] = {}
    for cluster in sorted(int(c) for c in np.unique(labels) if c >= 0):
        mask = labels == cluster
        n = int(mask.sum())
        rows[cluster] = n
        if n < min_rows:
            skipped[cluster] = n
            continue
        m = build_model()
        m.fit(_take(X, mask), _take(y, mask))
        models[cluster] = m

    # ---- global fallback -------------------------------------------------
    has_model = np.isin(labels, list(models.keys())) if models else np.zeros(len(labels), dtype=bool)
    uncovered = ~has_model
    scope_used = "all"
    fallback = build_model()
    if fallback_scope == "uncovered" and int(uncovered.sum()) >= FALLBACK_MIN_ROWS:
        fallback.fit(_take(X, uncovered), _take(y, uncovered))
        scope_used = "uncovered"
    else:
        fallback.fit(X, y)

    bundle = {
        "bundle_type": BUNDLE_TYPE,
        "bundle_version": "2.0.0",
        "clusterer": fit.clusterer,
        "models": models,
        "fallback": fallback,
        "device_clusters": dict(fit.mapping),
        "cluster_model_rows": rows,
        "clusters_without_model": skipped,
        "min_cluster_rows": int(min_rows),
        "feature_names": list(X.columns),
        "best_k": int(fit.clusterer.best_k),
        "silhouette_by_k": {int(k): float(v) for k, v in fit.clusterer.scores.items()},
        "n_unclustered_rows": int((labels < 0).sum()),
        "fallback_scope_requested": fallback_scope,
        "fallback_scope_used": scope_used,
        "fallback_train_rows": int(uncovered.sum()) if scope_used == "uncovered" else int(len(labels)),
        "n_fallback_devices": int(len({d for d, l in zip(np.asarray(device_ids), labels) if l < 0 or l not in models})),
    }
    if extra:
        bundle.update(extra)
    return bundle


def bundle_summary(obj: Any, fit: ClusterFit | None = None) -> dict[str, Any]:
    """JSON-safe description of what was trained (goes into the cycle report)."""
    if not is_cluster_bundle(obj):
        return {"clustered": False,
                "status": fit.status if fit else "disabled",
                "reason": fit.reason if fit else "clustering disabled"}
    return {
        "clustered": True,
        "status": "ok",
        "best_k": obj["best_k"],
        "n_clustered_devices": len(obj["device_clusters"]),
        "clusters_with_model": sorted(obj["models"].keys()),
        "clusters_without_model": obj.get("clusters_without_model", {}),
        "cluster_rows": obj["cluster_model_rows"],
        "unclustered_rows": obj.get("n_unclustered_rows", 0),
        "fallback_scope": obj.get("fallback_scope_used"),
        "fallback_train_rows": obj.get("fallback_train_rows"),
    }


def route_report(bundle: Any, X: pd.DataFrame, y, device_ids, metric_fn: Callable) -> dict[str, Any]:
    """Hold-out quality split by which model served each row.

    route = cluster_<id>            -> the device's own cluster model
            fallback_unclustered    -> device never got a cluster (too little history)
            fallback_small_cluster  -> device has a cluster but it is too small for a model
    For cluster routes ``global_mae`` is the global fallback on the same rows,
    so ``mae`` vs ``global_mae`` shows what clustering buys on that cluster.
    """
    if not is_cluster_bundle(bundle) or len(X) == 0:
        return {}
    ids = np.asarray(device_ids)
    labels = labels_for_devices(ids, bundle.get("device_clusters", {}))
    y_arr = np.asarray(y, dtype=float)
    if y_arr.ndim == 1:
        y_arr = y_arr.reshape(-1, 1)
    pred = predict_with_bundle(bundle, X, labels)
    glob = np.asarray(bundle["fallback"].predict(X[bundle["feature_names"]] if bundle.get("feature_names") else X), dtype=float).reshape(len(X), -1)
    models = bundle["models"]
    route = np.where(
        labels < 0, "fallback_unclustered",
        np.where(np.isin(labels, list(models.keys())) if models else False, "cluster_" + labels.astype(str), "fallback_small_cluster"),
    )
    out: dict[str, Any] = {}
    for r in sorted(set(route)):
        m = route == r
        met = metric_fn(y_arr[m], pred[m])
        entry = {"rows": int(m.sum()), "devices": int(len(set(ids[m]))), "mae": met["mae"], "rmse": met["rmse"]}
        if r.startswith("cluster_"):
            entry["global_mae"] = metric_fn(y_arr[m], glob[m])["mae"]
        out[r] = entry
    return out


# ---------------------------------------------------------------------------
# Trainer entry point (shared by 3day / weekly / monthly)
# ---------------------------------------------------------------------------
def train_clustered_pair(
    *,
    build_model: Callable[[], Any],
    settings: ClusterSettings,
    cluster_source: pd.DataFrame | None,
    train_cutoff,
    X_train: pd.DataFrame, y_train, ids_train,
    X_all: pd.DataFrame, y_all, ids_all,
    existing_clusterer: UserClusterer | None = None,
) -> tuple[Any, Any, dict[str, Any]]:
    """Return (candidate, refit, info).

    candidate : trained on the train split only; clusterer fitted on days
                <= train_cutoff (no look-ahead into the hold-out period).
    refit     : trained on all rows; clusterer fitted on all days.
    Either one degrades to a plain global model if clustering is impossible,
    so the pipeline never breaks because of clustering.

    existing_clusterer=None  -> clustering is redone from scratch (new k, new centres).
    existing_clusterer=<obj> -> the current clustering is kept; devices are only
                                re-assigned to its clusters, models are re-trained.
    """
    src = prepare_cluster_source(cluster_source)
    train_src = None
    if src is not None:
        train_src = src[src["day"] <= pd.Timestamp(train_cutoff)]

    fit_tr, how_tr = _obtain_fit(train_src, settings, existing_clusterer, "candidate")
    if fit_tr.status == "ok":
        candidate = make_bundle(fit_tr, X_train, y_train, ids_train, build_model, settings.min_rows,
                                fallback_scope=settings.fallback_scope)
    else:
        warnings.warn(f"clustering skipped for candidate: {fit_tr.status} - {fit_tr.reason}")
        candidate = build_model()
        candidate.fit(X_train, y_train)

    fit_all, how_all = _obtain_fit(src, settings, existing_clusterer, "refit")
    if fit_all.status == "ok":
        refit = make_bundle(fit_all, X_all, y_all, ids_all, build_model, settings.min_rows,
                            fallback_scope=settings.fallback_scope)
    else:
        warnings.warn(f"clustering skipped for refit: {fit_all.status} - {fit_all.reason}")
        refit = build_model()
        refit.fit(X_all, y_all)

    info = {"candidate": bundle_summary(candidate, fit_tr), "refit": bundle_summary(refit, fit_all)}
    info["candidate"]["clusterer_source"] = how_tr if fit_tr.status == "ok" else None
    info["refit"]["clusterer_source"] = how_all if fit_all.status == "ok" else None
    info["reclustered"] = existing_clusterer is None
    return candidate, refit, info


def save_bundle(bundle: dict[str, Any], path) -> None:
    joblib.dump(bundle, path)


def load_bundle(path):
    obj = joblib.load(path)
    return obj if is_cluster_bundle(obj) else None
