"""
cluster_profile_features.py
===========================
Country-independent behavioural profile features for device/user clustering,
plus a generic clustering core that works on those profiles.

Why this file exists
--------------------
Clustering is only useful for forecasting if devices in one cluster share
*forecast-relevant behaviour*: level, variability, weekly rhythm, intraday
shape, predictability, regime (vacancy / spikes) and trend.  Nothing here
depends on a country, tariff, climate or holiday calendar.

Inputs
------
`daily` : DataFrame with device_id, day, seg0..seg3.
          Optional clock-time columns seg{k}_start / seg{k}_hours (written by
          DatasetBuilder) add circular-hour features, which matter in
          adaptive mode where "seg1" does not always mean the same hours.

Leak control
------------
Only rows with day <= cutoff are used (cutoff=None uses everything; use that
only for production, never for evaluation).

Public API
----------
    build_cluster_profiles(daily, cutoff=None, min_days=21, recent_days=28)
    cluster_from_profiles(profiles, k="auto", seed=42, ...)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

LOG = logging.getLogger("cluster_profile_features")

SEGS = ["seg0", "seg1", "seg2", "seg3"]
TIME_COLS = [f"seg{k}_{s}" for k in range(4) for s in ("start", "hours")]

# Feature groups (kept explicit so ablations / weighting are easy).
LEVEL_COLS = ["log_mean", "log_median"]
VARIABILITY_COLS = ["cv", "robust_cv", "diff_volatility"]
WEEKLY_COLS = ["weekend_ratio", "dow_amplitude", "autocorr_lag1", "autocorr_lag7"]
SHAPE_COLS = ["share_0", "share_1", "share_2", "share_3",
              "share_entropy", "share_peak", "share_trough_ratio", "share_volatility"]
PREDICTABILITY_COLS = ["naive7_wape"]
REGIME_COLS = ["spike_frac", "low_frac", "trend_ratio"]
CLOCK_COLS = ["boundary_mean_1", "boundary_mean_2", "boundary_mean_3",
              "boundary_stability", "energy_center_sin", "energy_center_cos",
              "peak_hour_sin", "peak_hour_cos"]

BASE_COLS = (LEVEL_COLS + VARIABILITY_COLS + WEEKLY_COLS + SHAPE_COLS
             + PREDICTABILITY_COLS + REGIME_COLS)


class ClusterProfileError(RuntimeError):
    pass


def _safe_autocorr(y: pd.Series, lag: int) -> float:
    v = y.autocorr(lag=lag)
    return 0.0 if v is None or not np.isfinite(v) else float(v)


def _clock_features(g: pd.DataFrame) -> dict:
    cons = g[SEGS].to_numpy(float)
    start = g[[f"seg{k}_start" for k in range(4)]].to_numpy(float)
    hours = g[[f"seg{k}_hours" for k in range(4)]].to_numpy(float)
    bnd = start[:, 1:4]
    mid = start + hours / 2.0
    ang = 2.0 * np.pi * mid / 24.0
    tot = cons.sum(axis=1)
    tm = float(tot.mean())
    if tm > 0:
        es = float((cons * np.sin(ang)).sum(axis=1).mean() / tm)
        ec = float((cons * np.cos(ang)).sum(axis=1).mean() / tm)
    else:
        es = ec = 0.0
    dens = cons / np.where(hours > 0, hours, 1.0)
    pk = ang[np.arange(len(dens)), dens.argmax(axis=1)]
    bm = bnd.mean(axis=0)
    return {
        "boundary_mean_1": float(bm[0]), "boundary_mean_2": float(bm[1]),
        "boundary_mean_3": float(bm[2]),
        "boundary_stability": float(bnd.std(axis=0).mean()),
        "energy_center_sin": es, "energy_center_cos": ec,
        "peak_hour_sin": float(np.sin(pk).mean()),
        "peak_hour_cos": float(np.cos(pk).mean()),
    }


def _device_profile(g: pd.DataFrame, recent_days: int, with_clock: bool) -> Optional[dict]:
    g = g.sort_values("day")
    idx = pd.date_range(g["day"].min(), g["day"].max(), freq="D")
    gi = g.set_index("day").reindex(idx)
    seg = gi[SEGS]
    y = seg.sum(axis=1, min_count=4)          # NaN on missing calendar days
    yv = y.dropna()
    m = float(yv.mean())
    if m <= 1e-9:
        return None
    med = float(yv.median())

    mad = float((yv - med).abs().median() * 1.4826)
    d1 = y.diff().abs()

    share = seg.div(y.where(y > 0), axis=0).dropna()
    ms = share.mean().to_numpy()
    ms = ms / ms.sum() if ms.sum() > 0 else np.full(4, 0.25)
    entropy = float(-(ms * np.log(np.clip(ms, 1e-12, None))).sum() / np.log(4))

    dow = yv.groupby(yv.index.dayofweek).mean().reindex(range(7))
    dow = dow.fillna(m) / m
    wk = yv[yv.index.dayofweek >= 5]
    wd = yv[yv.index.dayofweek < 5]
    wk_ratio = float(wk.mean() / wd.mean()) if len(wk) and len(wd) and wd.mean() > 1e-9 else 1.0

    lag7 = y.shift(7)
    ok = y.notna() & lag7.notna()
    naive7 = float((y[ok] - lag7[ok]).abs().mean() / m) if ok.sum() >= 5 else 1.0

    rec = yv.iloc[-recent_days:]
    base = med if med > 1e-9 else m

    out = {
        "log_mean": float(np.log1p(m)),
        "log_median": float(np.log1p(med)),
        "cv": float(yv.std() / m) if len(yv) > 1 else 0.0,
        "robust_cv": float(mad / med) if med > 1e-9 else float(yv.std() / m),
        "diff_volatility": float(d1.mean() / m) if d1.notna().any() else 0.0,
        "weekend_ratio": wk_ratio,
        "dow_amplitude": float(dow.std()),
        "autocorr_lag1": _safe_autocorr(y, 1),
        "autocorr_lag7": _safe_autocorr(y, 7),
        "share_0": float(ms[0]), "share_1": float(ms[1]),
        "share_2": float(ms[2]), "share_3": float(ms[3]),
        "share_entropy": entropy,
        "share_peak": float(ms.max()),
        "share_trough_ratio": float(ms.min() / ms.max()) if ms.max() > 0 else 1.0,
        "share_volatility": float(share.std().mean()) if len(share) > 1 else 0.0,
        "naive7_wape": naive7,
        "spike_frac": float((yv > 2.0 * base).mean()),
        "low_frac": float((yv < 0.3 * base).mean()),
        "trend_ratio": float(np.log((rec.mean() + 1e-6) / (m + 1e-6))),
    }
    if with_clock:
        out.update(_clock_features(g.dropna(subset=SEGS + TIME_COLS)))
    return out


def build_cluster_profiles(
    daily: pd.DataFrame,
    cutoff: Optional[pd.Timestamp] = None,
    min_days: int = 21,
    recent_days: int = 28,
) -> pd.DataFrame:
    """One row per eligible device (index = device_id). Uses day <= cutoff only."""
    need = {"device_id", "day", *SEGS}
    miss = need - set(daily.columns)
    if miss:
        raise ClusterProfileError(f"daily is missing columns: {sorted(miss)}")
    df = daily
    if cutoff is not None:
        df = df[df["day"] <= pd.Timestamp(cutoff)]
    with_clock = all(c in df.columns for c in TIME_COLS)
    rows, ids = [], []
    for dev, g in df.groupby("device_id", sort=True):
        if len(g) < min_days:
            continue
        p = _device_profile(g, recent_days, with_clock)
        if p is not None:
            rows.append(p)
            ids.append(dev)
    if not ids:
        raise ClusterProfileError("No device has enough history to be profiled.")
    P = pd.DataFrame(rows, index=pd.Index(ids, name="device_id"))
    P = P.replace([np.inf, -np.inf], np.nan)
    if P.isna().any().any():
        P = P.fillna(P.median())
    return P


# ---------------------------------------------------------------------------
# Clustering core
# ---------------------------------------------------------------------------

def _robust_z(X: np.ndarray) -> np.ndarray:
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0) * 1.4826
    return (X - med) / np.where(mad > 1e-9, mad, 1.0)


def fit_profile_transform(P: pd.DataFrame, pca_var: Optional[float] = 0.90,
                          winsor: float = 0.01, group_balance: bool = True) -> dict:
    """Fit and return the exact profile transformation used for clustering."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    X = P.to_numpy(float).copy()
    lo = hi = None
    if winsor:
        lo = np.quantile(X, winsor, axis=0)
        hi = np.quantile(X, 1 - winsor, axis=0)
        X = np.clip(X, lo, hi)

    scaler = StandardScaler()
    Z = scaler.fit_transform(X)

    weights = np.ones(Z.shape[1], dtype=float)
    if group_balance:
        groups = [LEVEL_COLS, VARIABILITY_COLS, WEEKLY_COLS, SHAPE_COLS,
                  PREDICTABILITY_COLS, REGIME_COLS, CLOCK_COLS]
        for gcols in groups:
            pos = [i for i, c in enumerate(P.columns) if c in gcols]
            if pos:
                weights[pos] = 1.0 / np.sqrt(len(pos))
        Z = Z * weights

    pca = None
    if pca_var:
        pca = PCA(n_components=pca_var, svd_solver="full", random_state=0)
        Z = pca.fit_transform(Z)

    return {
        "columns": list(P.columns),
        "winsor": float(winsor),
        "group_balance": bool(group_balance),
        "lo": lo,
        "hi": hi,
        "scaler": scaler,
        "weights": weights,
        "pca": pca,
    }


def apply_profile_transform(P: pd.DataFrame, state: dict) -> np.ndarray:
    """Apply a previously fitted profile transformation to new profiles."""
    cols = list(state["columns"])
    missing = [c for c in cols if c not in P.columns]
    if missing:
        raise ClusterProfileError(f"Profiles are missing columns: {missing}")

    X = P[cols].to_numpy(float).copy()
    lo, hi = state.get("lo"), state.get("hi")
    if lo is not None and hi is not None:
        X = np.clip(X, lo, hi)
    Z = state["scaler"].transform(X)
    weights = state.get("weights")
    if weights is not None:
        Z = Z * weights
    pca = state.get("pca")
    if pca is not None:
        Z = pca.transform(Z)
    return Z


def transform_profiles(P: pd.DataFrame, pca_var: Optional[float] = 0.90,
                       winsor: float = 0.01, group_balance: bool = True):
    """Fit and transform profiles; kept as the original public helper."""
    return apply_profile_transform(
        P,
        fit_profile_transform(P, pca_var=pca_var, winsor=winsor,
                              group_balance=group_balance),
    )


def cluster_from_profiles(
    P: pd.DataFrame,
    k="auto",
    seed: int = 42,
    min_cluster_devices: int = 30,
    min_cluster_frac: float = 0.03,
    outlier_z: Optional[float] = 12.0,
    max_outlier_frac: float = 0.10,
    k_max: int = 7,
    pca_var: Optional[float] = 0.90,
    n_init: int = 10,
):
    """Return (mapping {device_id: cluster}, info dict, centroids_info).

    Same guarantees as before: outliers -> no cluster (fallback model),
    every cluster has >= required devices, no valid k -> no clustering.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    ids = np.asarray(P.index)
    out = np.zeros(len(ids), dtype=bool)
    if outlier_z:
        z = np.abs(_robust_z(P.to_numpy(float)))
        zmax = np.sort(z, axis=1)[:, -3:].mean(axis=1)   # mean of 3 worst features:
        out = zmax > outlier_z                              # one noisy column can't exile a device
        cap = int(np.floor(max_outlier_frac * len(ids)))
        if out.sum() > cap:
            out = np.zeros_like(out)
            if cap > 0:
                out[np.argsort(zmax)[-cap:]] = True
    keep = ~out
    Pk = P.loc[keep]
    n = len(Pk)
    base = {"n_clustered_candidates": int(n), "n_outliers": int(out.sum())}
    if n < 4:
        return {}, {"k": 0, "sizes": {}, "k_status": "too_few_devices",
                    "devices_unassigned": int(len(ids)), **base}, None

    transform_state = fit_profile_transform(Pk, pca_var=pca_var)
    Z = apply_profile_transform(Pk, transform_state)
    required = max(1, min(max(int(min_cluster_devices), int(np.ceil(min_cluster_frac * n))), n // 2))
    base["required_cluster_devices"] = int(required)
    base["n_components"] = int(Z.shape[1])

    valid = {}
    for kk in range(2, min(k_max, n - 1) + 1):
        km = KMeans(kk, n_init=n_init, random_state=seed).fit(Z)
        sz = np.bincount(km.labels_, minlength=kk)
        if sz.min() >= required:
            valid[kk] = (float(silhouette_score(Z, km.labels_)), km)
    if not valid:
        LOG.warning("No valid k (every cluster >= %d devices) -> all Global.", required)
        return {}, {"k": 0, "sizes": {}, "k_status": "no_valid_k",
                    "devices_unassigned": int(len(ids)), **base}, None

    if str(k).lower() == "auto":
        k_use, status = max(valid, key=lambda kk: valid[kk][0]), "auto"
    else:
        want = max(2, int(k))
        cands = [kk for kk in valid if kk <= want]
        k_use = max(cands) if cands else min(valid)
        status = "as_requested" if k_use == want else f"adjusted_from_{want}"
    sil, km = valid[k_use]
    lab = km.labels_
    mapping = {int(d): int(c) for d, c in zip(Pk.index, lab)}
    sizes = pd.Series(lab).value_counts().sort_index().to_dict()
    info = {"k": int(k_use), "sizes": {int(a): int(b) for a, b in sizes.items()},
            "k_status": status, "silhouette": round(sil, 4),
            "devices_unassigned": int(len(ids) - n), **base}
    # distance of every kept device to its own centroid (for soft features / QA)
    dist = np.linalg.norm(Z - km.cluster_centers_[lab], axis=1)
    cinfo = {
        "distance_to_centroid": dict(zip(map(int, Pk.index), dist.tolist())),
        "transformer": transform_state,
        "kmeans": km,
    }
    return mapping, info, cinfo