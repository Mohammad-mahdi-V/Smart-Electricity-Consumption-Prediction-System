#!/usr/bin/env python3
"""
benchmark.py
============
Scientific benchmark (structure aligned with benchmark 8).

What this does
--------------
1. Model benchmark: RandomForest (Jenks + Adaptive) and
   Ridge (Adaptive only) in Global vs Cluster modes, horizons Day+1 / +2 / +3.
   ExtraTrees was removed.
2. Segmentation ablation:
   - Jenks / Standard  → frozen train-only boundaries (or pre-built Jenks daily)
   - Adaptive          → rolling adaptive segments (or pre-built Adaptive daily)
   Compare forecast quality under each segmentation method.
   Segment columns are used only as features (shares / lags of shares).
3. Cluster vs Global paired bootstrap CIs (device-clustered).
4. Anti-leakage: global temporal cutoff, train-only clustering, no test leakage.

What this deliberately does NOT do
----------------------------------
* No segment-level prediction metrics (no MAE/RMSE/R² on seg0..seg3).
* Per-cluster metrics ARE reported (each cluster separately, never averaged),
  and every cluster gets its own chart: per_cluster_<method>_cluster<N>.png.
* No hourly reconstruction tables.
* No Fixed/Standard/Adaptive "segment prediction" arms.

Usage
-----
    # From hourly CSV (device_id, timestamp, consumption_kwh) — builds Jenks + Adaptive dailies
    python src/benchmark.py --raw-data data/electricity_data.csv --fast --max-devices 20

    # From a single daily CSV (device_id, day, seg0..seg3)
    python src/benchmark.py --source csv --data processed/daily_dataset.csv

    # Jenks vs Adaptive from two pre-built daily CSVs
    python src/benchmark.py \\
        --data-jenks processed/daily_jenks.csv \\
        --data-adaptive processed/daily_adaptive.csv
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Shared project clustering path.  This keeps Benchmark aligned with the
# production clustering implementation instead of maintaining a second KMeans
# feature definition inside benchmark.py.
from cluster_modeling import ClusterSettings, fit_clusterer

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

LOG = logging.getLogger("benchmark")

SEGS = ["seg0", "seg1", "seg2", "seg3"]
ID_COLS = ["device_id", "day"]
LAGS = list(range(1, 15)) + [21, 28]
ROLL_MEAN = [3, 7, 14, 28]
ROLL_STD = [7, 14]

ALGOS = ["ridge", "random_forest"]
ALGO_LABEL = {
    "ridge": "Ridge",
    "random_forest": "RandomForest",
}
# Ridge is evaluated on Adaptive only; RandomForest is shared by both arms.
ARM_ALGOS = {
    "jenks": ["random_forest"],
    "adaptive": ["ridge", "random_forest"],
}
SEG_COLOR = {"jenks": "#F58518", "adaptive": "#4C78A8"}
NAIVE = "Naive(t-7)"
RUN_WARNINGS: list[str] = []
# Facts about how this run was produced (written to the log, report and summary.json)
RUN_INFO: dict[str, str] = {}


class BenchmarkError(RuntimeError):
    pass


def warn(msg: str) -> None:
    LOG.warning("WARNING: %s", msg)
    RUN_WARNINGS.append(msg)


# =============================================================================
# Data
# =============================================================================


def finalize_daily(
    df: pd.DataFrame,
    label: str,
    max_devices: int | None,
    sample: int | None,
    seed: int,
) -> pd.DataFrame:
    missing = [c for c in ID_COLS + SEGS if c not in df.columns]
    if missing:
        raise BenchmarkError(
            f"Dataset {label}: missing columns {missing}; found {list(df.columns)}"
        )
    df = df[ID_COLS + SEGS].copy()
    df["day"] = pd.to_datetime(df["day"]).dt.floor("D")
    df["device_id"] = df["device_id"].astype("int64")
    if df[ID_COLS + SEGS].isna().any().any():
        raise BenchmarkError("Dataset contains missing values; refusing to impute.")
    if df.duplicated(ID_COLS).any():
        raise BenchmarkError("Duplicate (device_id, day) rows found.")
    if (df[SEGS] < 0).any().any():
        raise BenchmarkError("Negative consumption found.")
    if max_devices is not None or sample is not None:
        counts = df.groupby("device_id").size()
        devs = sorted(counts.index.tolist())
        if max_devices is not None:
            devs = devs[:max_devices]
        if sample is not None:
            order = np.random.default_rng(seed).permutation(devs)
            chosen, tot = [], 0
            for d in order:
                chosen.append(int(d))
                tot += int(counts.loc[d])
                if tot >= sample:
                    break
            devs = sorted(chosen)
        df = df[df["device_id"].isin(devs)]
    return df.sort_values(ID_COLS).reset_index(drop=True)


def load_daily_csv(
    path: Path,
    label: str,
    max_devices: int | None,
    sample: int | None,
    seed: int,
) -> pd.DataFrame:
    if not path.exists():
        raise BenchmarkError(f"Daily dataset not found: {path}")
    return finalize_daily(pd.read_csv(path), label, max_devices, sample, seed)


def load_daily(args) -> pd.DataFrame:
    """Single-dataset loader (backward compatible)."""
    if args.source == "csv":
        return load_daily_csv(
            Path(args.data), str(args.data), args.max_devices, args.sample, args.seed
        )

    try:
        import benchmark as B  # project helper next to this file
    except ImportError as exc:
        raise BenchmarkError(
            f"--source db needs project benchmark helpers: {exc}"
        ) from exc

    ns = SimpleNamespace(
        max_devices=args.max_devices,
        sample=args.sample,
        seed=args.seed,
        source="db",
    )
    B.check_db_connection()
    daily = B.build_daily_from_db(ns)
    return finalize_daily(daily, "database", None, None, args.seed)


def validate(daily: pd.DataFrame) -> dict:
    gaps = daily.groupby("device_id")["day"].diff().dt.days
    rep = {
        "n_rows": int(len(daily)),
        "n_devices": int(daily.device_id.nunique()),
        "date_min": str(daily.day.min().date()),
        "date_max": str(daily.day.max().date()),
        "calendar_gaps": int((gaps > 1).sum()),
    }
    LOG.info(
        "Data: %(n_rows)d rows | %(n_devices)d devices | %(date_min)s .. %(date_max)s",
        rep,
    )
    if rep["calendar_gaps"]:
        warn(
            f"{rep['calendar_gaps']} calendar gaps; origins whose lag window/target "
            "day touches a gap are dropped."
        )
    span = (daily.day.max() - daily.day.min()).days + 1
    if span < 365:
        warn(
            f"Data spans only {span} days (<1 year): yearly seasonality cannot be learned "
            "(no month/year features are used here on purpose)."
        )
    return rep


# =============================================================================
# Hourly CSV -> daily panels (Jenks / Adaptive)
# Expected columns: device_id, timestamp, consumption_kwh
# =============================================================================

ADAPTIVE_WINDOW_DAYS = 30
MIN_HOURS_PER_DAY = 20
FIXED_BOUNDARIES = (4, 10, 14)  # fallback only


def optimal_contiguous_partition(
    profile: np.ndarray,
    n_seg: int = 4,
    min_len: int = 4,
    max_len: int = 7,
) -> list[int]:
    """Ordered Jenks/Fisher partition of a 24h profile -> [b1, b2, b3]."""
    x = np.asarray(profile, dtype=float)
    n = len(x)
    c1 = np.concatenate([[0.0], np.cumsum(x)])
    c2 = np.concatenate([[0.0], np.cumsum(x * x)])

    def sse(i: int, j: int) -> float:
        s = c1[j] - c1[i]
        return float((c2[j] - c2[i]) - s * s / (j - i))

    inf = float("inf")
    dp = np.full((n_seg + 1, n + 1), inf)
    back = np.zeros((n_seg + 1, n + 1), dtype=int)
    dp[0, 0] = 0.0
    for k in range(1, n_seg + 1):
        for j in range(k * min_len, min(n, k * max_len) + 1):
            for length in range(min_len, max_len + 1):
                i = j - length
                if i < 0 or dp[k - 1, i] == inf:
                    continue
                cost = dp[k - 1, i] + sse(i, j)
                if cost < dp[k, j] - 1e-12:
                    dp[k, j], back[k, j] = cost, i
    if dp[n_seg, n] == inf:
        return list(FIXED_BOUNDARIES)
    bounds, j = [], n
    for k in range(n_seg, 0, -1):
        j = int(back[k, j])
        bounds.append(j)
    return sorted(bounds)[1:]


def _boundaries_to_seg_sums(mat: np.ndarray, bounds: np.ndarray) -> np.ndarray:
    """(D,24) hourly + (D,3) boundaries -> (D,4) segment sums."""
    cs = np.concatenate([np.zeros((mat.shape[0], 1)), np.cumsum(mat, axis=1)], axis=1)
    edges = np.concatenate(
        [
            np.zeros((len(bounds), 1), int),
            bounds.astype(int),
            np.full((len(bounds), 1), 24),
        ],
        axis=1,
    )
    rows = np.arange(len(bounds))[:, None]
    at = cs[rows, edges]
    return np.round(np.diff(at, axis=1), 3)


# Common aliases (LCL raw, prepared exports, half-hourly dumps)
_COL_ALIASES = {
    "device_id": [
        "device_id", "deviceid", "device", "id", "lclid", "lc_lid",
        "household_id", "meter_id",
    ],
    "timestamp": [
        "timestamp", "datetime", "date_time", "time", "ts", "hour",
        "reading_time", "end", "start",
    ],
    "consumption_kwh": [
        "consumption_kwh", "consumption", "kwh", "kwh/hh", "kwh_hh", "kwh/h",
        "energy_kwh", "value", "usage", "load", "energy",
    ],
}


def _normalize_hourly_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map varied header names onto device_id / timestamp / consumption_kwh."""
    cleaned = {c: str(c).replace("\ufeff", "").strip() for c in df.columns}
    df = df.rename(columns=cleaned)
    lower_map = {c.lower().replace(" ", "_").replace("-", "_"): c for c in df.columns}

    resolved: dict[str, str] = {}
    for canonical, aliases in _COL_ALIASES.items():
        found = None
        for a in aliases:
            key = a.lower().replace(" ", "_").replace("-", "_")
            if key in lower_map:
                found = lower_map[key]
                break
        if found is None:
            for low, orig in lower_map.items():
                if canonical == "consumption_kwh" and "kwh" in low:
                    found = orig
                    break
                if canonical == "timestamp" and ("date" in low or "time" in low):
                    found = orig
                    break
                if canonical == "device_id" and (
                    "lcl" in low or "device" in low or low in ("id", "hid")
                ):
                    found = orig
                    break
        if found is not None:
            resolved[canonical] = found

    missing = [k for k in ("device_id", "timestamp", "consumption_kwh") if k not in resolved]
    if missing:
        raise BenchmarkError(
            "Hourly CSV could not map required columns.\n"
            f"  Missing: {missing}\n"
            f"  Found columns: {list(df.columns)}\n"
            "  Need (any alias of): device_id, timestamp, consumption_kwh\n"
            "  Example header: device_id,timestamp,consumption_kwh"
        )
    out = df[[resolved["device_id"], resolved["timestamp"], resolved["consumption_kwh"]]].copy()
    out.columns = ["device_id", "timestamp", "consumption_kwh"]
    LOG.info(
        "Column map: device_id←%s  timestamp←%s  consumption_kwh←%s",
        resolved["device_id"],
        resolved["timestamp"],
        resolved["consumption_kwh"],
    )
    return out


def load_hourly_csv(
    path: Path,
    max_devices: int | None,
    sample: int | None,
    seed: int,
) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    """
    Read hourly CSV (device_id,timestamp,consumption_kwh or common aliases)
    -> per-device day arrays + (D,24) matrices.
    """
    if not path.exists():
        raise BenchmarkError(f"Hourly CSV not found: {path}")
    LOG.info("Loading hourly CSV: %s", path)
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception:
        df = pd.read_csv(path, low_memory=False, sep=";")
    if len(df.columns) == 1:
        raw0 = str(df.columns[0])
        if ";" in raw0:
            df = pd.read_csv(path, low_memory=False, sep=";")
        elif "\t" in raw0:
            df = pd.read_csv(path, low_memory=False, sep="\t")
    df = _normalize_hourly_columns(df)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    # device_id may be LCLid strings (MAC000002) — map to integer codes
    try:
        df["device_id"] = df["device_id"].astype("int64")
    except (ValueError, TypeError):
        codes, _ = pd.factorize(df["device_id"].astype(str), sort=True)
        df["device_id"] = codes.astype("int64") + 1
        LOG.info("Non-integer device ids factorized to 1..%d", int(df["device_id"].max()))
    df["consumption_kwh"] = pd.to_numeric(df["consumption_kwh"], errors="coerce")
    df = df.dropna(subset=["consumption_kwh"])
    df = df[df["consumption_kwh"] >= 0]
    df = df.drop_duplicates(["device_id", "timestamp"], keep="last")
    df["day"] = df["timestamp"].dt.floor("D")
    df["hour"] = df["timestamp"].dt.hour

    # device filter
    counts = df.groupby("device_id").size()
    devs = sorted(counts.index.tolist())
    if max_devices is not None:
        devs = devs[:max_devices]
    if sample is not None:
        order = np.random.default_rng(seed).permutation(devs)
        chosen, tot = [], 0
        for d in order:
            chosen.append(int(d))
            tot += int(counts.loc[d])
            if tot >= sample:
                break
        devs = sorted(chosen)
    df = df[df["device_id"].isin(devs)]

    days_out: dict[int, np.ndarray] = {}
    mats_out: dict[int, np.ndarray] = {}
    dropped = 0
    for dev, g in df.groupby("device_id", sort=True):
        # sum: works for hourly rows and for half-hourly LCL (2 slots -> 1 hour)
        piv = (
            g.groupby(["day", "hour"])["consumption_kwh"]
            .sum()
            .unstack("hour")
            .reindex(columns=range(24))
        )
        # keep days with enough hours; fill tiny gaps with 0 for matrix shape
        n_valid = piv.notna().sum(axis=1)
        keep = n_valid >= MIN_HOURS_PER_DAY
        dropped += int((~keep).sum())
        piv = piv.loc[keep].fillna(0.0).sort_index()
        if len(piv) == 0:
            continue
        days_out[int(dev)] = pd.to_datetime(piv.index).values.astype("datetime64[D]")
        mats_out[int(dev)] = piv.to_numpy(float)
    if dropped:
        LOG.info("Dropped %d incomplete device-days (< %d hours).", dropped, MIN_HOURS_PER_DAY)
    if not days_out:
        raise BenchmarkError("No usable hourly data after filtering.")
    LOG.info(
        "Hourly loaded: %d devices, %d device-days",
        len(days_out),
        sum(len(v) for v in days_out.values()),
    )
    return days_out, mats_out


def _n_jobs(n_jobs: int | None = None) -> int:
    import os

    if n_jobs is None or n_jobs == 0:
        return max(1, os.cpu_count() or 1)
    if n_jobs < 0:
        return max(1, (os.cpu_count() or 1) + 1 + n_jobs)
    return max(1, int(n_jobs))


def _jenks_one_device(
    dev: int, darr: np.ndarray, mat: np.ndarray, train_frac: float
) -> list[dict]:
    n = len(darr)
    n_tr = max(1, int(n * train_frac))
    prof = mat[:n_tr].mean(axis=0)
    try:
        b = optimal_contiguous_partition(prof)
    except Exception:
        b = list(FIXED_BOUNDARIES)
    bounds = np.tile(np.array(b, dtype=int), (n, 1))
    segs = _boundaries_to_seg_sums(mat, bounds)
    return [
        {
            "device_id": dev,
            "day": pd.Timestamp(darr[i]),
            "seg0": float(segs[i, 0]),
            "seg1": float(segs[i, 1]),
            "seg2": float(segs[i, 2]),
            "seg3": float(segs[i, 3]),
        }
        for i in range(n)
    ]


def _adaptive_one_device_rolling(
    dev: int, darr: np.ndarray, mat: np.ndarray
) -> list[dict]:
    """Rolling 30-day window: Jenks partition of mean profile of days strictly before t."""
    n = len(darr)
    bounds = np.full((n, 3), -1, dtype=int)
    for i in range(ADAPTIVE_WINDOW_DAYS, n):
        bounds[i] = optimal_contiguous_partition(
            mat[i - ADAPTIVE_WINDOW_DAYS : i].mean(axis=0)
        )
    valid = bounds[:, 0] >= 0
    if not valid.any():
        return []
    segs = _boundaries_to_seg_sums(mat[valid], bounds[valid])
    idx = np.where(valid)[0]
    return [
        {
            "device_id": dev,
            "day": pd.Timestamp(darr[i]),
            "seg0": float(segs[j, 0]),
            "seg1": float(segs[j, 1]),
            "seg2": float(segs[j, 2]),
            "seg3": float(segs[j, 3]),
        }
        for j, i in enumerate(idx)
    ]


def _adaptive_one_device_project(
    dev: int, darr: np.ndarray, mat: np.ndarray
) -> list[dict]:
    """Project AdaptiveBoundarySegmenter via DatasetBuilder (slower)."""
    from dataset_builder import DatasetBuilder

    builder = DatasetBuilder()
    n = len(darr)
    day_col = np.repeat(pd.to_datetime(darr), 24)
    user_df = pd.DataFrame(
        {
            "device_id": dev,
            "day": pd.to_datetime(day_col).normalize(),
            "hour": np.tile(np.arange(24), n),
            "consumption_kwh": mat.reshape(-1),
        }
    )
    bounds = np.full((n, 3), -1, dtype=int)
    uniq = sorted(user_df["day"].unique())
    for i, day in enumerate(uniq):
        segs = builder.get_dynamic_segments(user_df, day, window_days=ADAPTIVE_WINDOW_DAYS)
        if segs is None:
            continue
        bounds[i] = [int(segs[1]["start"]), int(segs[2]["start"]), int(segs[3]["start"])]
    valid = bounds[:, 0] >= 0
    if not valid.any():
        return []
    segs = _boundaries_to_seg_sums(mat[valid], bounds[valid])
    idx = np.where(valid)[0]
    return [
        {
            "device_id": dev,
            "day": pd.Timestamp(darr[i]),
            "seg0": float(segs[j, 0]),
            "seg1": float(segs[j, 1]),
            "seg2": float(segs[j, 2]),
            "seg3": float(segs[j, 3]),
        }
        for j, i in enumerate(idx)
    ]


def build_daily_jenks(
    days: dict[int, np.ndarray],
    mats: dict[int, np.ndarray],
    train_frac: float = 0.8,
    n_jobs: int | None = None,
) -> pd.DataFrame:
    """Jenks/Standard: partition on early history, freeze, apply to all days (parallel)."""
    from joblib import Parallel, delayed

    jobs = _n_jobs(n_jobs)
    devs = sorted(days.keys())
    LOG.info("Jenks: %d devices, n_jobs=%d", len(devs), jobs)
    parts = Parallel(n_jobs=jobs, backend="loky", verbose=5)(
        delayed(_jenks_one_device)(dev, days[dev], mats[dev], train_frac) for dev in devs
    )
    rows = [r for part in parts for r in part]
    return pd.DataFrame(rows).sort_values(ID_COLS).reset_index(drop=True)


def build_daily_adaptive(
    days: dict[int, np.ndarray],
    mats: dict[int, np.ndarray],
    n_jobs: int | None = None,
    use_project: bool = False,
) -> pd.DataFrame:
    """
    Adaptive: 30-day rolling window strictly BEFORE each day (parallel over devices).

    Default path = rolling ordered-Jenks on the window mean (fast, full CPU).
    --use-project-adaptive uses DatasetBuilder + AdaptiveBoundarySegmenter (much slower).
    """
    from joblib import Parallel, delayed

    jobs = _n_jobs(n_jobs)
    devs = sorted(days.keys())
    if use_project:
        # Explicitly requested -> never fall back silently to the fast rolling
        # approximation (that would make the "project Adaptive" label a lie).
        try:
            from dataset_builder import DatasetBuilder  # noqa: F401
            from segmenter import AdaptiveBoundarySegmenter  # noqa: F401
        except Exception as exc:
            raise BenchmarkError(
                "--use-project-adaptive requested but the project segmenter could not be "
                f"imported ({type(exc).__name__}: {exc}). Run from the project root so "
                "src/dataset_builder.py and src/segmenter.py are importable."
            ) from exc
        worker = _adaptive_one_device_project
        RUN_INFO["adaptive_source"] = (
            "PROJECT AdaptiveBoundarySegmenter via DatasetBuilder.get_dynamic_segments "
            f"(window_days={ADAPTIVE_WINDOW_DAYS})"
        )
        LOG.info("=" * 70)
        LOG.info("ADAPTIVE SEGMENTATION: PROJECT segmenter (AdaptiveBoundarySegmenter) "
                 "- %d devices, n_jobs=%d", len(devs), jobs)
        LOG.info("=" * 70)
    else:
        worker = _adaptive_one_device_rolling
        RUN_INFO["adaptive_source"] = (
            f"rolling {ADAPTIVE_WINDOW_DAYS}-day ordered-Jenks approximation (NOT the project segmenter)"
        )
        LOG.info("ADAPTIVE SEGMENTATION: rolling-window approximation (NOT the project "
                 "segmenter; use --use-project-adaptive) - %d devices, n_jobs=%d", len(devs), jobs)

    parts = Parallel(n_jobs=jobs, backend="loky", verbose=10)(
        delayed(worker)(dev, days[dev], mats[dev]) for dev in devs
    )
    rows = [r for part in parts for r in part]
    if not rows:
        raise BenchmarkError("Adaptive daily build produced no rows (need longer history).")
    return pd.DataFrame(rows).sort_values(ID_COLS).reset_index(drop=True)


def run_from_hourly(args) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Build Jenks + Adaptive dailies from --raw-data and run both arms."""
    days, mats = load_hourly_csv(
        Path(args.raw_data), args.max_devices, args.sample, args.seed
    )
    n_jobs = getattr(args, "n_jobs", -1)
    use_project = bool(getattr(args, "use_project_adaptive", False))
    LOG.info("Building Jenks daily panel ...")
    daily_j = build_daily_jenks(
        days, mats, train_frac=1.0 - args.test_frac, n_jobs=n_jobs
    )
    LOG.info("Building Adaptive daily panel ...")
    daily_a = build_daily_adaptive(
        days, mats, n_jobs=n_jobs, use_project=use_project
    )

    # optional dump
    if args.save_daily:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        daily_j.to_csv(out / "daily_jenks.csv", index=False)
        daily_a.to_csv(out / "daily_adaptive.csv", index=False)
        LOG.info("Wrote daily_jenks.csv and daily_adaptive.csv to %s", out)

    common = sorted(
        set(daily_j["device_id"].unique()) & set(daily_a["device_id"].unique())
    )
    if len(common) < 4:
        raise BenchmarkError(
            f"Jenks/Adaptive overlap has only {len(common)} devices; need ≥4."
        )
    daily_j = daily_j[daily_j["device_id"].isin(common)].reset_index(drop=True)
    daily_a = daily_a[daily_a["device_id"].isin(common)].reset_index(drop=True)

    return _run_arms(daily_j, daily_a, args, len(common))


def _run_arms(daily_j, daily_a, args, n_common: int):
    """Run both arms; Ridge only on Adaptive (see ARM_ALGOS)."""
    vj = validate(daily_j)
    va = validate(daily_a)
    LOG.info("Running Jenks arm ...")
    Rj, Bj, _, _, sj, PCj = run_one(daily_j, args, seg_method="jenks")
    LOG.info("Running Adaptive arm ...")
    Ra, Ba, pa, ma, sa, PCa = run_one(daily_a, args, seg_method="adaptive")
    R = pd.concat([Rj, Ra], ignore_index=True)
    B = pd.concat([Bj, Ba], ignore_index=True)
    PC = pd.concat([PCj, PCa], ignore_index=True)
    tests = algo_pair_tests(pa, ma, args, "adaptive")
    return R, B, {
        "split": {"jenks": sj, "adaptive": sa, "n_common_devices": n_common},
        "validation": {"jenks": vj, "adaptive": va},
        "per_cluster": PC,
        "algo_tests": tests,
    }


# =============================================================================
# Features (causal: only days ≤ d)
# =============================================================================


def build_panel(daily: pd.DataFrame, horizons: list[int], normalize: bool):
    parts = []
    for dev, g in daily.groupby("device_id", sort=True):
        g = g.set_index("day").sort_index()
        idx = pd.date_range(g.index.min(), g.index.max(), freq="D")
        g = g.reindex(idx)
        seg = g[SEGS]
        y = seg.sum(axis=1, min_count=4)
        f = {f"lag{k}": y.shift(k - 1) for k in LAGS}
        for w in ROLL_MEAN:
            f[f"m{w}"] = y.rolling(w, min_periods=w).mean()
        for w in ROLL_STD:
            f[f"sd{w}"] = y.rolling(w, min_periods=w).std()
        share = seg.div(y.where(y > 0), axis=0).mask(y.eq(0), 0.25)
        for s in SEGS:
            f[f"share_{s}"] = share[s]
            f[f"share7_{s}"] = share[s].rolling(7, min_periods=7).mean()
        fr = pd.DataFrame(f, index=idx)
        for h in horizons:
            fr[f"tgt{h}"] = y.shift(-h)
        fr["device_id"] = dev
        fr["day"] = idx
        parts.append(fr)
    P = pd.concat(parts, ignore_index=True)

    level_cols = (
        [f"lag{k}" for k in LAGS]
        + [f"m{w}" for w in ROLL_MEAN]
        + [f"sd{w}" for w in ROLL_STD]
    )
    share_cols = [c for c in P.columns if c.startswith("share")]
    P["scale"] = P["m28"] if normalize else 1.0
    base_cols = level_cols + share_cols
    P["feat_ok"] = P[base_cols].notna().all(axis=1) & (P["scale"] > 1e-9)
    feat_cols = list(base_cols)
    if normalize:
        P.loc[:, level_cols] = P[level_cols].div(P["scale"], axis=0)
        P["log_scale"] = np.log1p(P["scale"])
        feat_cols.append("log_scale")
    P["usable_all"] = P["feat_ok"] & np.logical_and.reduce(
        [P[f"tgt{h}"].notna() for h in horizons]
    )
    return P, feat_cols


def horizon_frame(P: pd.DataFrame, feat_cols: list[str], h: int):
    d = P[P["feat_ok"] & P[f"tgt{h}"].notna()].copy()
    td = d["day"] + pd.Timedelta(days=h)
    dow = td.dt.dayofweek
    for k in range(7):
        d[f"dow{k}"] = (dow == k).astype(float)
    d["is_weekend"] = (dow >= 5).astype(float)
    d["target"] = d[f"tgt{h}"]
    d["target_day"] = td
    d["y_ratio"] = d["target"] / d["scale"]
    d["naive"] = d[f"lag{8 - h}"] * d["scale"]
    cols = feat_cols + [f"dow{k}" for k in range(7)] + ["is_weekend"]
    return d.sort_values(ID_COLS).reset_index(drop=True), cols


def compute_cutoff(P: pd.DataFrame, test_frac: float) -> pd.Timestamp:
    days = np.sort(P.loc[P["usable_all"], "day"].unique())
    if len(days) < 10:
        raise BenchmarkError(f"Only {len(days)} usable origin days; dataset too small.")
    k = int(len(days) * (1.0 - test_frac))
    return pd.Timestamp(days[min(max(k, 1), len(days) - 1)])


# =============================================================================
# Clustering (train-only)  [LEAK-CONTROL]
# =============================================================================


def cluster_devices(
    daily: pd.DataFrame,
    cutoff: pd.Timestamp,
    k,
    seed: int,
    min_days: int = 21,
    min_cluster_devices: int = 30,
    min_cluster_frac: float = 0.03,
    outlier_z: float = 12.0,
    max_outlier_frac: float = 0.10,
):
    """Use the project's shared UserClusterer through cluster_modeling.

    IMPORTANT: clustering is fitted only on rows with ``day <= cutoff``.
    The old Benchmark-local feature/KMeans implementation is intentionally
    removed so the benchmark cannot silently diverge from the main pipeline.
    """
    train_src = daily[daily["day"] <= pd.Timestamp(cutoff)].copy()

    # Preserve the Benchmark CLI semantics: --k auto uses the clusterer's
    # normal K search; a numeric --k evaluates that single K.
    if str(k).lower() == "auto":
        k_min, k_max = 2, 7
    else:
        requested_k = max(2, int(k))
        k_min = k_max = requested_k

    settings = ClusterSettings(
        min_days=int(min_days),
        k_min=k_min,
        k_max=k_max,
        min_rows=1,
        random_state=int(seed),
        n_init=20,
        min_cluster_devices=int(min_cluster_devices),
        min_cluster_frac=float(min_cluster_frac),
        outlier_z=(None if not outlier_z else float(outlier_z)),
    )

    fit = fit_clusterer(train_src, settings)
    if fit.status != "ok":
        raise BenchmarkError(
            f"Shared UserClusterer could not build clusters: "
            f"{fit.status} - {fit.reason}"
        )

    info = {
        "source": "cluster_modeling.fit_clusterer -> UserClusterer",
        "train_cutoff": str(pd.Timestamp(cutoff)),
        "min_days": int(min_days),
        "k": int(fit.clusterer.best_k) if fit.clusterer is not None and fit.clusterer.best_k is not None else 0,
        "sizes": fit.clusterer.cluster_sizes_by_k.get(fit.clusterer.best_k, []) if fit.clusterer is not None and fit.clusterer.best_k is not None else {},
        "devices_unassigned": int(daily["device_id"].nunique() - len(fit.mapping)),
        "n_clustered_candidates": int(len(fit.profiles)) if fit.profiles is not None else 0,
        "n_outliers": int(len(getattr(fit.clusterer, "outlier_device_ids_", []))) if fit.clusterer is not None else 0,
    }
    LOG.info(
        "Shared UserClusterer: k=%s, mapped_devices=%d, unassigned=%d, train_cutoff=%s",
        info["k"], len(fit.mapping), info["devices_unassigned"], info["train_cutoff"],
    )
    return fit.mapping, info


# =============================================================================
# Models & metrics
# =============================================================================


def make_estimator(algo: str, seed: int, fast: bool, n_train: int = 0):
    """
    Tree models: fewer estimators + row subsample on large panels so
    290k-row fits finish in seconds/minutes, not hours.
    """
    if algo == "ridge":
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        return Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))])

    large = n_train >= 80_000
    if fast:
        n_trees = 40
    elif large:
        n_trees = 100
    else:
        n_trees = 200
    # subsample rows for RF/ET on big data (keeps wall-time reasonable)
    max_samples = 0.25 if large and not fast else 1.0
    min_leaf = 5 if large else 1

    if algo == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        kw = dict(
            n_estimators=n_trees,
            min_samples_leaf=min_leaf,
            max_features="sqrt",
            n_jobs=-1,
            random_state=seed,
        )
        # max_samples only valid when bootstrap=True (RF default)
        if max_samples < 1.0:
            kw["max_samples"] = max_samples
        return RandomForestRegressor(**kw)
    raise BenchmarkError(f"unknown algo {algo}")


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    e = p - y
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    nz = np.abs(y) > 1e-8
    den = np.abs(y) + np.abs(p)
    return {
        "WAPE_%": float(np.abs(e).sum() / np.abs(y).sum() * 100),
        "MAE": float(np.abs(e).mean()),
        "RMSE": float(np.sqrt((e ** 2).mean())),
        "R2": float(1 - np.sum(e ** 2) / ss_tot) if ss_tot > 1e-12 else float("nan"),
        "MAPE_%": float(np.mean(np.abs(e[nz] / y[nz])) * 100) if nz.any() else float("nan"),
        "sMAPE_%": float(
            np.mean(np.where(den > 0, 2 * np.abs(e) / np.where(den > 0, den, 1), 0)) * 100
        ),
        "Bias_%": float(e.sum() / y.sum() * 100),
        "n_test": int(len(y)),
    }


def bootstrap_gain(y, p_g, p_c, dev, n_boot, seed):
    """% WAPE improvement of Cluster over Global + 95% CI (device-paired bootstrap)."""
    if n_boot <= 0:
        return (float("nan"),) * 3
    u, inv = np.unique(dev, return_inverse=True)
    n = len(u)
    A_g = np.bincount(inv, np.abs(p_g - y), n)
    A_c = np.bincount(inv, np.abs(p_c - y), n)
    S = np.bincount(inv, np.abs(y), n)
    rng = np.random.default_rng(seed)
    gains = np.empty(n_boot)
    for b in range(n_boot):
        w = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        wg, wc = (w * A_g).sum(), (w * A_c).sum()
        gains[b] = (wg - wc) / wg * 100 if wg > 0 else np.nan
    point = (A_g.sum() - A_c.sum()) / A_g.sum() * 100
    lo, hi = np.nanpercentile(gains, [2.5, 97.5])
    return float(point), float(lo), float(hi)


# =============================================================================
# Core experiment (one segmentation method)
# =============================================================================


def run_one(
    daily: pd.DataFrame,
    args,
    seg_method: str = "default",
) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict, dict, pd.DataFrame]:
    """
    Run Global/Cluster model benchmark on a daily panel.
    Returns results, bootstrap table, preds, meta_te, split info and the
    per-cluster metrics table (every cluster separately, no averaging).
    """
    horizons = sorted(set(args.horizons))
    allowed = ARM_ALGOS.get(seg_method)
    algos = [a for a in args.algos if allowed is None or a in allowed]
    if not algos:
        raise BenchmarkError(f"No algorithms selected for segmentation '{seg_method}'.")
    LOG.info("[%s] algorithms: %s", seg_method, algos)
    P, feat_cols = build_panel(daily, horizons, not args.no_normalize)
    cutoff = compute_cutoff(P, args.test_frac)
    LOG.info(
        "[%s] Cutoff: %s  (train targets <= cutoff <= test origins)",
        seg_method,
        cutoff.date(),
    )

    cmap, cinfo = cluster_devices(
        daily, cutoff, args.k, args.seed,
        min_cluster_devices=args.min_cluster_devices,
        min_cluster_frac=args.min_cluster_frac,
        outlier_z=args.outlier_z,
    )
    P["cl"] = P["device_id"].map(cmap).fillna(-1).astype(int)

    results, preds, boots, meta_te, pc_rows = [], {}, [], {}, []
    for h in horizons:
        d, X = horizon_frame(P, feat_cols, h)
        tr = d[(d["day"] + pd.Timedelta(days=h)) <= cutoff]
        te = d[(d["day"] >= cutoff) & d["usable_all"]]
        # [LEAK-CONTROL]
        if not (tr["target_day"].max() <= cutoff <= te["day"].min()):
            raise BenchmarkError("Temporal split violated.")
        LOG.info(
            "[%s] Day+%d: train=%d test=%d (devices test=%d)",
            seg_method,
            h,
            len(tr),
            len(te),
            te.device_id.nunique(),
        )
        y = te["target"].to_numpy(float)
        sc = te["scale"].to_numpy(float)
        dev = te["device_id"].to_numpy()
        cl_te, cl_tr = te["cl"].to_numpy(), tr["cl"].to_numpy()
        meta_te[h] = (
            te[["device_id", "day", "target_day"]].assign(actual=y).reset_index(drop=True)
        )
        preds[h] = {}

        pn = te["naive"].to_numpy(float)
        preds[h][NAIVE] = pn
        results.append(
            {
                **metrics(y, pn),
                "horizon": h,
                "algo": "naive",
                "mode": "reference",
                "model": NAIVE,
                "seg_method": seg_method,
                "train_rows": 0,
                "fit_seconds": 0.0,
                "fallback_rows": 0,
                "devices_test": int(len(np.unique(dev))),
            }
        )

        for algo in algos:
            LOG.info("[%s] Day+%d fitting %s Global (train=%d) ...", seg_method, h, algo, len(tr))
            t0 = time.perf_counter()
            mg = make_estimator(algo, args.seed, args.fast, n_train=len(tr)).fit(
                tr[X], tr["y_ratio"]
            )
            p_g = mg.predict(te[X]) * sc
            fit_g = time.perf_counter() - t0
            LOG.info("[%s] Day+%d %s Global done in %.1fs", seg_method, h, algo, fit_g)

            # Cluster models
            p_c = np.empty_like(p_g)
            fallback = 0
            t0 = time.perf_counter()
            for c in sorted(set(cl_tr) | set(cl_te)):
                if c < 0:
                    continue
                mtr = cl_tr == c
                mte = cl_te == c
                if mtr.sum() < args.min_cluster_rows:
                    p_c[mte] = p_g[mte]
                    fallback += int(mte.sum())
                    continue
                LOG.info(
                    "[%s] Day+%d fitting %s Cluster=%d (train=%d) ...",
                    seg_method,
                    h,
                    algo,
                    c,
                    int(mtr.sum()),
                )
                mc = make_estimator(
                    algo, args.seed, args.fast, n_train=int(mtr.sum())
                ).fit(tr.loc[mtr, X], tr.loc[mtr, "y_ratio"])
                p_c[mte] = mc.predict(te.loc[mte, X]) * sc[mte]
            # unassigned → global
            un = cl_te < 0
            p_c[un] = p_g[un]
            fallback += int(un.sum())
            fit_c = time.perf_counter() - t0

            label_g = f"{ALGO_LABEL[algo]}-Global"
            label_c = f"{ALGO_LABEL[algo]}-Cluster"

            # ---- every cluster reported separately (no cluster average) ----
            for c in sorted(set(cl_te.tolist())):
                mte = cl_te == c
                if not mte.any():
                    continue
                n_tr_c = int((cl_tr == c).sum())
                for mode, pp in (("Global", p_g), ("Cluster", p_c)):
                    pc_rows.append(
                        {
                            **metrics(y[mte], pp[mte]),
                            "seg_method": seg_method,
                            "horizon": h,
                            "algo": algo,
                            "mode": mode,
                            "model": f"{ALGO_LABEL[algo]}-{mode}",
                            "cluster_id": int(c),
                            "scope": "Unclustered" if c < 0 else f"Cluster {c + 1}",
                            "n_devices": int(len(np.unique(dev[mte]))),
                            "train_rows_cluster": n_tr_c,
                            "own_model": bool(c >= 0 and n_tr_c >= args.min_cluster_rows),
                        }
                    )
            preds[h][label_g] = p_g
            preds[h][label_c] = p_c

            results.append(
                {
                    **metrics(y, p_g),
                    "horizon": h,
                    "algo": algo,
                    "mode": "Global",
                    "model": label_g,
                    "seg_method": seg_method,
                    "train_rows": int(len(tr)),
                    "fit_seconds": float(fit_g),
                    "fallback_rows": 0,
                    "devices_test": int(len(np.unique(dev))),
                }
            )
            results.append(
                {
                    **metrics(y, p_c),
                    "horizon": h,
                    "algo": algo,
                    "mode": "Cluster",
                    "model": label_c,
                    "seg_method": seg_method,
                    "train_rows": int(len(tr)),
                    "fit_seconds": float(fit_c),
                    "fallback_rows": int(fallback),
                    "devices_test": int(len(np.unique(dev))),
                }
            )

            gain, lo, hi = bootstrap_gain(y, p_g, p_c, dev, args.n_boot, args.seed)
            boots.append(
                {
                    "horizon": h,
                    "algo": algo,
                    "seg_method": seg_method,
                    "WAPE_gain_%": gain,
                    "CI95_lo": lo,
                    "CI95_hi": hi,
                    "model_global": label_g,
                    "model_cluster": label_c,
                }
            )

    R = pd.DataFrame(results)
    B = pd.DataFrame(boots)
    split = {
        "cutoff": str(cutoff.date()),
        "test_frac": args.test_frac,
        "cluster_info": cinfo,
        "seg_method": seg_method,
        "n_feat": len(feat_cols),
    }
    PC = pd.DataFrame(pc_rows)
    return R, B, preds, meta_te, split, PC


def run(daily: pd.DataFrame, args):
    """Single-dataset entry (backward compatible)."""
    return run_one(daily, args, seg_method="default")


# =============================================================================
# Algorithm comparison (paired, device-clustered bootstrap) - Adaptive arm
# =============================================================================


def algo_pair_tests(preds: dict, meta_te: dict, args, seg_method: str = "adaptive") -> pd.DataFrame:
    """RandomForest vs Ridge on the SAME test rows.

    ``A_better_%`` = % WAPE reduction of A relative to B (positive = A better),
    with a 95% device-clustered paired bootstrap CI.  'significant' = CI excludes 0.
    """
    pairs = [("RandomForest", "Ridge")]
    rows = []
    for h, md in meta_te.items():
        y = md["actual"].to_numpy(float)
        dev = md["device_id"].to_numpy()
        for mode in ("Global", "Cluster"):
            for a, b in pairs:
                ka, kb = f"{a}-{mode}", f"{b}-{mode}"
                if ka not in preds[h] or kb not in preds[h]:
                    continue
                pa, pb = preds[h][ka], preds[h][kb]
                gain, lo, hi = bootstrap_gain(y, pb, pa, dev, args.n_boot, args.seed)
                wa = float(np.abs(pa - y).sum() / np.abs(y).sum() * 100)
                wb = float(np.abs(pb - y).sum() / np.abs(y).sum() * 100)
                rows.append(
                    {
                        "seg_method": seg_method,
                        "horizon": h,
                        "mode": mode,
                        "A": a,
                        "B": b,
                        "WAPE_A": wa,
                        "WAPE_B": wb,
                        "A_better_%": gain,
                        "CI95_lo": lo,
                        "CI95_hi": hi,
                        "significant": bool(np.isfinite(lo) and (lo > 0 or hi < 0)),
                    }
                )
    return pd.DataFrame(rows)


# =============================================================================
# Jenks vs Adaptive comparison
# =============================================================================


def run_jenks_vs_adaptive(args) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Load two daily datasets (same devices/days, different segment features)
    and run the identical experiment on each.
    Only feature shares differ between arms.
    """
    RUN_INFO["adaptive_source"] = f"pre-built CSV: {args.data_adaptive} (how it was segmented is not verified by the benchmark)"
    LOG.info("ADAPTIVE SEGMENTATION: %s", RUN_INFO["adaptive_source"])
    daily_j = load_daily_csv(
        Path(args.data_jenks),
        "jenks",
        args.max_devices,
        args.sample,
        args.seed,
    )
    daily_a = load_daily_csv(
        Path(args.data_adaptive),
        "adaptive",
        args.max_devices,
        args.sample,
        args.seed,
    )

    # Align devices so comparison is fair
    common = sorted(
        set(daily_j["device_id"].unique()) & set(daily_a["device_id"].unique())
    )
    if len(common) < 4:
        raise BenchmarkError(
            f"Jenks/Adaptive overlap has only {len(common)} devices; need ≥4."
        )
    daily_j = daily_j[daily_j["device_id"].isin(common)].reset_index(drop=True)
    daily_a = daily_a[daily_a["device_id"].isin(common)].reset_index(drop=True)

    # Sanity: targets should match across arms (same underlying kWh)
    j_tot = daily_j.assign(total=daily_j[SEGS].sum(axis=1))
    a_tot = daily_a.assign(total=daily_a[SEGS].sum(axis=1))
    merged = j_tot.merge(
        a_tot[["device_id", "day", "total"]],
        on=["device_id", "day"],
        suffixes=("_j", "_a"),
        how="inner",
    )
    if len(merged):
        rel = (merged["total_j"] - merged["total_a"]).abs() / merged["total_j"].clip(
            lower=1e-6
        )
        if float(rel.median()) > 0.02:
            warn(
                f"Median relative difference between Jenks and Adaptive targets "
                f"is {rel.median():.3%}. Comparison may mix different targets."
            )
        else:
            LOG.info(
                "Jenks vs Adaptive targets aligned (median rel diff %.4f%%).",
                100 * float(rel.median()),
            )

    return _run_arms(daily_j, daily_a, args, len(common))


# =============================================================================
# Plots
# =============================================================================


def make_plots(R: pd.DataFrame, B: pd.DataFrame, preds, meta_te, out: Path, algos, PC=None):
    import matplotlib.pyplot as plt

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    H = sorted(R["horizon"].dropna().unique())
    methods = [m for m in ("jenks", "adaptive") if m in set(R["seg_method"])] or sorted(R["seg_method"].unique())
    palette = {"Ridge": "#4C78A8", "RandomForest": "#F58518"}
    metric_cfg = [
        # metric, tag, title, ylabel, higher_is_better, decimals
        ("WAPE_%", "wape", "WAPE", "WAPE (%)", False, 2),
        ("MAE", "mae", "MAE", "MAE (kWh)", False, 3),
        ("R2", "r2", "R²", "R²", True, 3),
    ]

    # ------------------------------------------------------------------
    # A) Jenks vs Adaptive side by side (algorithms both arms share)
    # ------------------------------------------------------------------
    shared = [
        a for a in ALGOS
        if all(((R["seg_method"] == m) & (R["algo"] == a)).any() for m in methods)
    ]
    shared_models = [f"{ALGO_LABEL[a]}-{mode}" for a in shared for mode in ("Global", "Cluster")]

    def seg_compare(metric, tag, title, ylabel, higher, nd):
        if len(methods) < 2 or not shared_models:
            return
        fig, axes = plt.subplots(1, len(H), figsize=(5.4 * len(H), 6.2), sharey=True)
        axes = np.atleast_1d(axes)
        width = 0.8 / len(methods)
        x = np.arange(len(shared_models))
        for ax, h in zip(axes, H):
            for i, m in enumerate(methods):
                vals = []
                for mod in shared_models:
                    sel = R[(R["seg_method"] == m) & (R["model"] == mod) & (R["horizon"] == h)]
                    vals.append(float(sel[metric].iloc[0]) if len(sel) else np.nan)
                vals = np.asarray(vals)
                bars = ax.bar(
                    x + (i - (len(methods) - 1) / 2) * width, vals, width,
                    label=m.capitalize(), color=SEG_COLOR.get(m), edgecolor="black", linewidth=0.5,
                )
                for bar, v in zip(bars, vals):
                    if np.isfinite(v):
                        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.{nd}f}",
                                ha="center", va="bottom" if v >= 0 else "top", fontsize=7, rotation=90)
            ax.set_xticks(x)
            ax.set_xticklabels([m.replace("-", "\n") for m in shared_models], fontsize=8)
            ax.set_title(f"Day +{int(h)}")
            ax.grid(axis="y", alpha=0.25)
            ax.margins(y=0.18)
            if metric == "R2":
                ax.axhline(0, linewidth=0.8, linestyle="--", color="gray")
        axes[0].set_ylabel(ylabel)
        axes[-1].legend(title="Segmentation", loc="best", fontsize=9)
        fig.suptitle(
            f"{title} — Jenks vs Adaptive ({'higher' if higher else 'lower'} = better; "
            f"{', '.join(ALGO_LABEL[a] for a in shared)})", fontsize=12)
        fig.tight_layout()
        fn = f"seg_compare_{tag}.png"
        fig.savefig(out / fn, dpi=160, bbox_inches="tight")
        plt.close(fig)
        files.append(fn)

    for metric, tag, title, ylabel, higher, nd in metric_cfg:
        seg_compare(metric, tag, title, ylabel, higher, nd)

    # ------------------------------------------------------------------
    # B) Algorithm comparison on Adaptive: Ridge vs RandomForest
    # ------------------------------------------------------------------
    ad = "adaptive" if "adaptive" in set(R["seg_method"]) else methods[0]
    sub = R[(R["seg_method"] == ad) & (R["mode"] != "reference")]
    a_models = [f"{ALGO_LABEL[a]}-{mode}" for a in ALGOS for mode in ("Global", "Cluster")]
    a_models = [m for m in a_models if m in set(sub["model"])]

    def algo_plot(metric, tag, title, ylabel, higher, nd, yscale):
        if not a_models:
            return
        fig, ax = plt.subplots(figsize=(13, 6.5))
        width = 0.8 / len(a_models)
        xb = np.arange(len(H))
        for i, mod in enumerate(a_models):
            alg, mode = mod.rsplit("-", 1)
            vals = []
            for h in H:
                sel = sub[(sub["model"] == mod) & (sub["horizon"] == h)]
                vals.append(float(sel[metric].iloc[0]) if len(sel) else np.nan)
            vals = np.asarray(vals)
            bars = ax.bar(xb + (i - (len(a_models) - 1) / 2) * width, vals, width, label=mod,
                          color=palette.get(alg), hatch="//" if mode == "Cluster" else None,
                          edgecolor="black", linewidth=0.5)
            for bar, v in zip(bars, vals):
                if np.isfinite(v):
                    ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.{nd}f}",
                            ha="center", va="bottom" if v >= 0 else "top", fontsize=7, rotation=90)
        if yscale == "log":
            ax.set_yscale("log")
        elif yscale == "symlog":
            ax.set_yscale("symlog", linthresh=1.0)
        if metric == "R2":
            ax.axhline(0, linewidth=0.8, linestyle="--", color="gray")
        ax.set_xticks(xb)
        ax.set_xticklabels([f"Day +{int(h)}" for h in H])
        ax.set_ylabel(ylabel + (f" ({yscale} scale)" if yscale != "linear" else ""))
        ax.set_title(f"{title} — Ridge vs RandomForest (segmentation={ad})")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(ncol=3, fontsize=8, loc="best")
        fig.tight_layout()
        fn = f"adaptive_algos_{tag}.png"
        fig.savefig(out / fn, dpi=160, bbox_inches="tight")
        plt.close(fig)
        files.append(fn)

    # Ridge is far worse than the trees; log / symlog keeps the trees readable.
    scales = {"wape": "log", "mae": "log", "r2": "symlog"}
    for metric, tag, title, ylabel, higher, nd in metric_cfg:
        algo_plot(metric, tag, title, ylabel, higher, nd, scales[tag])

    # ------------------------------------------------------------------
    # C) Cluster vs Global gain (overall) with bootstrap CI
    # ------------------------------------------------------------------
    if len(B):
        fig, ax = plt.subplots(figsize=(11, 5.2))
        keys = [(a, h) for a in ALGOS for h in H if ((B["algo"] == a) & (B["horizon"] == h)).any()]
        bm = [m for m in methods if m in set(B["seg_method"])]
        for i, m in enumerate(bm):
            for j, (a, h) in enumerate(keys):
                row = B[(B["seg_method"] == m) & (B["algo"] == a) & (B["horizon"] == h)]
                if row.empty:
                    continue
                r = row.iloc[0]
                xpos = j + (i - (len(bm) - 1) / 2) * 0.25
                ax.errorbar(xpos, r["WAPE_gain_%"],
                            yerr=[[r["WAPE_gain_%"] - r["CI95_lo"]], [r["CI95_hi"] - r["WAPE_gain_%"]]],
                            fmt="o", capsize=4, color=SEG_COLOR.get(m),
                            label=m.capitalize() if j == 0 else None)
        ax.axhline(0, linestyle="--", color="gray")
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels([f"{ALGO_LABEL[a]}\nD+{int(h)}" for a, h in keys], fontsize=8)
        ax.set_ylabel("Cluster WAPE improvement vs Global (%)")
        ax.set_title("Cluster vs Global (device-bootstrap 95% CI; >0 = cluster better)")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(title="Segmentation")
        fig.tight_layout()
        fig.savefig(out / "cluster_vs_global_gain.png", dpi=160, bbox_inches="tight")
        plt.close(fig)
        files.append("cluster_vs_global_gain.png")

    # ------------------------------------------------------------------
    # D) One chart PER CLUSTER (never averaged across clusters).
    #    Global model vs that cluster's own model, on the SAME test rows.
    #    Panels: WAPE | MAE | R2, bars grouped by horizon.
    # ------------------------------------------------------------------
    if PC is not None and len(PC):
        pc_methods = [m for m in methods if m in set(PC["seg_method"])] or sorted(PC["seg_method"].unique())
        for m in pc_methods:
            pm = PC[PC["seg_method"] == m]
            for cid in sorted(pm["cluster_id"].unique()):
                pcl = pm[pm["cluster_id"] == cid]
                # Per-cluster charts intentionally show RandomForest only;
                # Ridge cluster charts are suppressed as requested.
                c_models = [f"RandomForest-{mode}" for mode in ("Global", "Cluster")]
                c_models = [x for x in c_models if x in set(pcl["model"])]
                if not c_models:
                    continue
                c_H = sorted(pcl["horizon"].dropna().unique())
                scope = str(pcl["scope"].iloc[0])
                n_dev = int(pcl["n_devices"].max())
                has_ridge = any(x.startswith("Ridge") for x in c_models)
                # Ridge is far worse than the trees -> log scales only when it is present
                c_scales = {"wape": "log", "mae": "log", "r2": "symlog"} if has_ridge else {}

                fig, axes = plt.subplots(1, 3, figsize=(7.5 * 3, 6.4))
                width = 0.8 / len(c_models)
                xb = np.arange(len(c_H))
                for ax, (metric, tag, title, ylabel, higher, nd) in zip(axes, metric_cfg):
                    for i, mod in enumerate(c_models):
                        alg, mode = mod.rsplit("-", 1)
                        vals = []
                        for h in c_H:
                            sel = pcl[(pcl["model"] == mod) & (pcl["horizon"] == h)]
                            vals.append(float(sel[metric].iloc[0]) if len(sel) else np.nan)
                        vals = np.asarray(vals)
                        bars = ax.bar(
                            xb + (i - (len(c_models) - 1) / 2) * width, vals, width,
                            label=mod, color=palette.get(alg),
                            hatch="//" if mode == "Cluster" else None,
                            edgecolor="black", linewidth=0.5,
                        )
                        for bar, v in zip(bars, vals):
                            if np.isfinite(v):
                                ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.{nd}f}",
                                        ha="center", va="bottom" if v >= 0 else "top",
                                        fontsize=7, rotation=90)
                    ys = c_scales.get(tag, "linear")
                    if ys == "log":
                        ax.set_yscale("log")
                    elif ys == "symlog":
                        ax.set_yscale("symlog", linthresh=1.0)
                    if metric == "R2":
                        ax.axhline(0, linewidth=0.8, linestyle="--", color="gray")
                    ax.set_xticks(xb)
                    ax.set_xticklabels([f"Day +{int(h)}" for h in c_H])
                    ax.set_ylabel(ylabel + (f" ({ys} scale)" if ys != "linear" else ""))
                    ax.set_title(f"{title} ({'higher' if higher else 'lower'} = better)")
                    ax.grid(axis="y", alpha=0.25)
                    ax.margins(y=0.18)
                axes[0].legend(ncol=2, fontsize=8, loc="best")
                note = "  — served by the Global model (no own cluster model)" if cid < 0 else ""
                fig.suptitle(
                    f"{scope} — {n_dev} test devices | segmentation = {m}{note}",
                    fontsize=13,
                )
                fig.tight_layout()
                cname = "unclustered" if cid < 0 else f"{int(cid) + 1}"
                fn = f"per_cluster_{m}_cluster{cname}.png" if cid >= 0 else f"per_cluster_{m}_{cname}.png"
                fig.savefig(out / fn, dpi=160, bbox_inches="tight")
                plt.close(fig)
                files.append(fn)

    return files


# =============================================================================
# Report
# =============================================================================


def write_report(out: Path, R, B, split, validation, plots, PC=None, tests=None) -> None:
    out = Path(out)
    methods = [m for m in ("jenks", "adaptive") if m in set(R["seg_method"])] or sorted(R["seg_method"].unique())

    def overall_global(metric: str, nd: int, method: str) -> str:
        """Global / Naive models on ALL test rows (no cluster averages)."""
        d = R[(R["seg_method"] == method) & (R["mode"].isin(["Global", "reference"]))]
        if d.empty:
            return "(empty)"
        t = d.pivot_table(index="model", columns="horizon", values=metric, aggfunc="mean")
        t.columns = [f"Day+{c}" for c in t.columns]
        t["mean"] = t.mean(axis=1)
        return t.sort_values("mean", ascending=metric != "R2").round(nd).to_string()

    def per_cluster(metric: str, nd: int, method: str) -> str:
        """One row per (algorithm, cluster): Global model vs Cluster model on the SAME rows."""
        if PC is None or PC.empty:
            return "(no per-cluster data)"
        d = PC[PC["seg_method"] == method]
        if d.empty:
            return "(empty)"
        t = d.pivot_table(index=["algo", "cluster_id", "scope", "n_devices"], columns=["mode", "horizon"],
                          values=metric, aggfunc="mean")
        t.columns = [f"{m}-Day+{int(h)}" for m, h in t.columns]
        t = t.reset_index().sort_values(["algo", "cluster_id"])
        t["algo"] = t["algo"].map(ALGO_LABEL)
        return t.drop(columns="cluster_id").rename(columns={"scope": "cluster"}).round(nd).to_string(index=False)

    L = [
        "=" * 78,
        "FORECAST BENCHMARK",
        "  Jenks vs Adaptive: RandomForest (shared algorithm)",
        "  Algorithm test: Ridge vs RandomForest on Adaptive only",
        "  Clusters are always listed separately (never averaged) in the tables.",
        "=" * 78,
        f"adaptive segmentation source: {RUN_INFO.get('adaptive_source', 'unknown')}",
        f"data: {json.dumps(validation, default=str)}",
        f"split: {json.dumps(split, default=str)}",
        "",
    ]

    # ---- 1. Jenks vs Adaptive, overall Global on shared algorithms ----------
    shared = [a for a in ALGOS if all(((R['seg_method'] == m) & (R['algo'] == a)).any() for m in methods)]
    if len(methods) > 1 and shared:
        L += ["=" * 60, "1) JENKS vs ADAPTIVE (Global models, all test rows)", "=" * 60,
              "Target identical across arms; only segment-derived features differ.", ""]
        rows = []
        for h in sorted(R["horizon"].unique()):
            for a in shared:
                row = {"horizon": h, "model": f"{ALGO_LABEL[a]}-Global"}
                for metric, key in (("WAPE_%", "WAPE"), ("MAE", "MAE"), ("R2", "R2")):
                    vals = {}
                    for m in methods:
                        sel = R[(R["seg_method"] == m) & (R["algo"] == a) & (R["mode"] == "Global") & (R["horizon"] == h)]
                        vals[m] = float(sel[metric].iloc[0]) if len(sel) else np.nan
                        row[f"{key}_{m}"] = vals[m]
                    if "jenks" in vals and "adaptive" in vals:
                        row[f"{key}_diff(adaptive-jenks)"] = vals["adaptive"] - vals["jenks"]
                rows.append(row)
        C = pd.DataFrame(rows)
        L += ["WAPE/MAE: negative diff = Adaptive better.  R2: positive diff = Adaptive better.",
              C.round(4).to_string(index=False), ""]
        C.to_csv(out / "jenks_vs_adaptive.csv", index=False)

    # ---- 2. Overall Global tables per method -------------------------------
    for m in methods:
        L += ["=" * 60, f"2) [{m}] Global / Naive models - all test rows", "=" * 60]
        for metric, nd in (("WAPE_%", 2), ("MAE", 3), ("R2", 4)):
            L += [f"--- [{m}] {metric} ---", overall_global(metric, nd, m), ""]

    # ---- 3. Per-cluster tables (each cluster on its own row) ----------------
    for m in methods:
        info = (split.get(m) or {}).get("cluster_info", {}) if isinstance(split, dict) else {}
        L += ["=" * 60, f"3) [{m}] PER-CLUSTER results (each cluster separate)", "=" * 60,
              f"cluster_info: {json.dumps(info, default=str)}",
              "Global-* = global model evaluated on this cluster's devices;",
              "Cluster-* = that cluster's own model on the same rows.",
              "'Unclustered' = outlier / short-history devices (served by the Global model).", ""]
        for metric, nd in (("WAPE_%", 2), ("MAE", 3), ("R2", 4)):
            L += [f"--- [{m}] {metric} per cluster ---", per_cluster(metric, nd, m), ""]
    if PC is not None and len(PC):
        PC.to_csv(out / "per_cluster.csv", index=False)

    # ---- 4. Algorithm test on Adaptive --------------------------------------
    if tests is not None and len(tests):
        L += ["=" * 60, "4) ALGORITHM TEST on Adaptive: RandomForest vs Ridge", "=" * 60,
              "A_better_% = WAPE reduction of A relative to B (positive = A better), paired",
              "device-clustered bootstrap 95% CI. significant = CI excludes 0.", "",
              tests.round(3).to_string(index=False), ""]
        tests.to_csv(out / "adaptive_algo_tests.csv", index=False)

    # ---- 5. Cluster vs Global (overall bootstrap) ---------------------------
    L += ["--- Cluster vs Global: WAPE improvement % (overall, 95% device-clustered bootstrap) ---",
          B.round(3).to_string(index=False) if len(B) else "(none)", ""]

    L += [
        "Notes:",
        "  * WAPE = sum|error| / sum|actual| (main metric).",
        f"  * {NAIVE} = same weekday last week; reference only.",
        "  * Multi-day horizons use DIRECT strategy (no recursive feedback).",
        "  * Ridge runs on Adaptive only. ExtraTrees removed.",
        "  * Cluster numbers are 1-based and arbitrary: 'Cluster 1' of Jenks is NOT 'Cluster 1' of Adaptive.",
        "  * Segment columns are FEATURES only; no segment prediction scores are shown.",
    ]
    L += ["", "WARNINGS:"] + [f"  - {w}" for w in RUN_WARNINGS]
    L += ["", "Charts: " + ", ".join(plots)]
    (out / "benchmark_report.txt").write_text("\n".join(L), encoding="utf-8")


# =============================================================================
# CLI
# =============================================================================


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    p = argparse.ArgumentParser(
        description=(
            "Benchmark: algorithms × (Global|Cluster), Day+1/2/3. "
            "Optional Jenks vs Adaptive segmentation ablation."
        )
    )
    p.add_argument("--source", choices=["db", "csv"], default="db")
    p.add_argument(
        "--data",
        type=Path,
        default=PROJECT_ROOT / "processed" / "daily_dataset.csv",
        help="[csv] single daily file: device_id, day, seg0..seg3",
    )
    p.add_argument(
        "--raw-data",
        type=Path,
        default=None,
        help="Hourly CSV: device_id,timestamp,consumption_kwh — builds Jenks+Adaptive dailies and runs both",
    )
    p.add_argument(
        "--save-daily",
        action="store_true",
        help="When using --raw-data, also write daily_jenks.csv / daily_adaptive.csv under --output",
    )
    p.add_argument(
        "--n-jobs",
        type=int,
        default=-1,
        help="CPU workers for daily build (-1 = all cores)",
    )
    p.add_argument(
        "--use-project-adaptive",
        action="store_true",
        help="Use project AdaptiveBoundarySegmenter (much slower). Default: fast rolling window.",
    )
    p.add_argument(
        "--data-jenks",
        type=Path,
        default=None,
        help="Daily CSV built with Jenks/Standard segmentation (for ablation)",
    )
    p.add_argument(
        "--data-adaptive",
        type=Path,
        default=None,
        help="Daily CSV built with Adaptive segmentation (for ablation)",
    )
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "benchmark_results")
    p.add_argument("--algos", nargs="+", default=ALGOS, choices=ALGOS)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 2, 3], choices=[1, 2, 3])
    p.add_argument("--k", default="auto", help="device clusters, or 'auto' (default). Always capped so every cluster is big enough")
    p.add_argument("--min-cluster-devices", type=int, default=30, help="min devices per cluster (k is reduced/auto-chosen to satisfy it)")
    p.add_argument("--min-cluster-frac", type=float, default=0.03, help="min fraction of clustered devices per cluster")
    p.add_argument("--outlier-z", type=float, default=12.0, help="robust-z above which a device skips KMeans and uses Global (0=off)")
    p.add_argument("--test-frac", type=float, default=0.2)
    p.add_argument(
        "--min-cluster-rows",
        type=int,
        default=100,
        help="smaller clusters fall back to global model",
    )
    p.add_argument(
        "--no-normalize",
        action="store_true",
        help="predict raw kWh instead of target/28-day-mean",
    )
    p.add_argument("--n-boot", type=int, default=500)
    p.add_argument("--max-devices", type=int, default=None)
    p.add_argument("--sample", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--fast", action="store_true", help="fewer trees (smoke test)")
    p.add_argument("--save-predictions", action="store_true")
    args = p.parse_args(argv)

    try:
        np.random.seed(args.seed)
        args.output.mkdir(parents=True, exist_ok=True)

        if args.raw_data is not None:
            LOG.info("=== From hourly CSV: Jenks vs Adaptive ===")
            R, B, meta = run_from_hourly(args)
            split, validation = meta["split"], meta["validation"]
            preds, meta_te = {}, {}
            PC, tests = meta.get("per_cluster"), meta.get("algo_tests")
        elif args.data_jenks and args.data_adaptive:
            LOG.info("=== Jenks vs Adaptive ablation ===")
            R, B, meta = run_jenks_vs_adaptive(args)
            split, validation = meta["split"], meta["validation"]
            preds, meta_te = {}, {}
            PC, tests = meta.get("per_cluster"), meta.get("algo_tests")
        else:
            daily = load_daily(args)
            validation = validate(daily)
            R, B, preds, meta_te, split, PC = run(daily, args)
            tests = None

        plots = make_plots(R, B, preds, meta_te, args.output, args.algos, PC=PC)
        R.to_csv(args.output / "results.csv", index=False)
        B.to_csv(args.output / "cluster_vs_global.csv", index=False)
        if args.save_predictions and preds:
            rows = []
            for h, md in meta_te.items():
                w = md.copy()
                w["horizon"] = h
                for name, arr in preds[h].items():
                    w[name] = arr
                rows.append(w)
            pd.concat(rows).to_csv(args.output / "predictions.csv", index=False)
        write_report(args.output, R, B, split, validation, plots, PC=PC, tests=tests)
        (args.output / "summary.json").write_text(
            json.dumps(
                {
                    "args": {k: str(v) for k, v in vars(args).items()},
                    "run_info": RUN_INFO,
                    "split": split,
                    "validation": validation,
                    "warnings": RUN_WARNINGS,
                    "results": R.to_dict("records"),
                    "cluster_vs_global": B.to_dict("records"),
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        if "seg_method" in R.columns and R["seg_method"].nunique() > 1:
            print("\n=== Jenks vs Adaptive - Global models, WAPE_% (lower = better) ===")
            piv = R[R["mode"].isin(["Global", "reference"])].pivot_table(
                index=["seg_method", "model"], columns="horizon", values="WAPE_%", aggfunc="mean"
            )
            piv["mean"] = piv.mean(axis=1)
            print(piv.sort_values("mean").round(2).to_string())
            print("\nPer-cluster tables: see benchmark_report.txt / per_cluster.csv")
        else:
            piv = R[R["mode"].isin(["Global", "reference"])].pivot(index="model", columns="horizon", values="WAPE_%")
            piv["mean"] = piv.mean(axis=1)
            print("\nWAPE % (Global, lower = better):\n", piv.sort_values("mean").round(2).to_string())

        print(f"\nAdaptive segmentation source: {RUN_INFO.get('adaptive_source', 'unknown')}")
        print(f"\nResults + charts written to: {args.output}")
        return 0
    except BenchmarkError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())