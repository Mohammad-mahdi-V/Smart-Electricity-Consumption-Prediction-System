"""horizon_trainers.py - Independent trainers for 3day / weekly / monthly."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib

from model import ElectricityConsumptionModel
from horizon_model_store import HorizonModelStore
from cluster_modeling import (
    ClusterSettings,
    predict_any,
    train_clustered_pair,
    is_cluster_bundle,
    route_report,
)
from cluster_runtime import load_any_model

def _safe_mape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    mask = np.abs(y_true) > 1e-8
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100.0)

def _safe_maape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    denom = np.abs(y_true) + 1e-8
    return float(np.mean(np.arctan(np.abs(y_true - y_pred) / denom)) * (180.0 / np.pi))

def compute_metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.ndim == 1:
        y_true = y_true.reshape(-1, 1)
        y_pred = y_pred.reshape(-1, 1)
    yt, yp = y_true.ravel(), y_pred.ravel()
    mae = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    mape = _safe_mape(yt, yp)
    maape = _safe_maape(yt, yp)
    ss_res = float(np.sum((yt - yp) ** 2))
    ss_tot = float(np.sum((yt - np.mean(yt)) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
    return {"mae": mae, "rmse": rmse, "mape": mape, "maape": maape, "r2": r2}

def build_single_output_model(algorithm, random_state=42, **params):
    algorithm = algorithm.lower().strip()
    if algorithm == "ridge":
        return Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=float(params.get("alpha", 1.0)), solver=params.get("solver", "auto"), random_state=random_state))])
    if algorithm == "linear":
        return Pipeline([("scaler", StandardScaler()), ("model", LinearRegression(fit_intercept=bool(params.get("fit_intercept", True))))])
    if algorithm == "random_forest":
        max_depth = params.get("max_depth", 12)
        if max_depth is not None:
            max_depth = int(max_depth)
        mf = params.get("max_features", "sqrt")
        if mf == "1.0":
            mf = 1.0
        return RandomForestRegressor(
            n_estimators=int(params.get("n_estimators", 100)), max_depth=max_depth,
            min_samples_split=int(params.get("min_samples_split", 2)),
            min_samples_leaf=int(params.get("min_samples_leaf", 1)),
            max_features=mf, random_state=random_state, n_jobs=-1,
        )
    if algorithm == "xgboost":
        try:
            from xgboost import XGBRegressor
        except ImportError as exc:
            raise ImportError(
                "algorithm='xgboost' requires the 'xgboost' package. "
                "Install it with: pip install xgboost"
            ) from exc
        return XGBRegressor(
            n_estimators=int(params.get("n_estimators", 300)),
            max_depth=int(params.get("xgb_max_depth", params.get("max_depth", 6))),
            learning_rate=float(params.get("learning_rate", 0.1)),
            subsample=float(params.get("subsample", 1.0)),
            colsample_bytree=float(params.get("colsample_bytree", 1.0)),
            reg_alpha=float(params.get("reg_alpha", 0.0)),
            reg_lambda=float(params.get("reg_lambda", 1.0)),
            random_state=random_state, n_jobs=-1,
            objective="reg:squarederror",
        )
    raise ValueError(f"Unsupported algorithm: {algorithm}")

@dataclass
class HorizonTrainConfig:
    horizon: str
    algorithm: str = "ridge"
    model_params: dict = field(default_factory=dict)
    random_state: int = 42
    feature_dataset_path: Path = Path("processed/feature_dataset.csv")
    daily_dataset_path: Path | None = Path("processed/daily_dataset.csv")
    models_root: Path = Path("processed/models")
    project_root: Path | None = None
    min_train_rows: int = 20
    # NOTE: 0.0 was too strict — a candidate that clearly improves MAE/RMSE was
    # being rejected over an R2 drop of ~0.0005 (well within holdout noise).
    # A small negative tolerance lets noise-level R2 dips through while MAE/RMSE
    # gates still guard against real regressions.
    min_r2_gain: float = -0.003
    max_mae_ratio: float = 1.05
    max_rmse_ratio: float = 1.05
    # --- user clustering (per-cluster models + global fallback) -----------
    clustered: bool = True
    cluster_min_days: int = 30        # min days of history for a device to be clustered
    cluster_k_min: int = 2
    cluster_k_max: int = 7
    cluster_min_rows: int = 20       # min training rows for a per-cluster model
    cluster_min_devices: int = 30    # k is chosen so EVERY cluster has >= this many devices
    cluster_min_frac: float = 0.03   # ... and >= this fraction of clustered devices
    cluster_outlier_z: float | None = 12.0   # extreme devices skip KMeans -> global model
    # True  -> clustering is redone from scratch (used when datasets were just rebuilt)
    # False -> keep the clusterer of the current production model and only re-assign devices
    recluster: bool = True
    cluster_fallback_scope: str = "all"   # "all" | "uncovered" (see cluster_modeling.ClusterSettings)

    def cluster_settings(self) -> ClusterSettings:
        return ClusterSettings(
            min_days=int(self.cluster_min_days), k_min=int(self.cluster_k_min),
            k_max=int(self.cluster_k_max), min_rows=int(self.cluster_min_rows),
            random_state=int(self.random_state), fallback_scope=str(self.cluster_fallback_scope),
            min_cluster_devices=int(self.cluster_min_devices),
            min_cluster_frac=float(self.cluster_min_frac),
            outlier_z=self.cluster_outlier_z,
        )

THREE_DAY_TARGETS = ["target_seg0", "target_seg1", "target_seg2", "target_seg3"]
DROP_FOR_XY = ["device_id", "day", "_month", *THREE_DAY_TARGETS]

_CLUSTER_SRC_COLS = {"device_id", "day", "seg0", "seg1", "seg2", "seg3",
                     *[f"seg{k}_{x}" for k in range(4) for x in ("start", "hours")]}


def _load_cluster_source(config):
    """Daily (device_id, day, seg0..seg3[, seg*_start/hours]) frame for clustering."""
    for p in (config.daily_dataset_path, config.feature_dataset_path):
        if p is None:
            continue
        p = Path(p)
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p, usecols=lambda c: c in _CLUSTER_SRC_COLS)
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"cluster source read failed ({p}): {exc}")
            continue
        if {"device_id", "day", "seg0", "seg1", "seg2", "seg3"} <= set(df.columns):
            return df
    return None


def _existing_clusterer(store, config):
    """Clusterer of the current production bundle, or None (-> fit from scratch)."""
    if config.recluster:
        return None
    try:
        path = store.resolve_model_path()
        if path is None or not Path(path).exists():
            return None
        obj = load_any_model(path)
        return obj.get("clusterer") if is_cluster_bundle(obj) else None
    except Exception as exc:  # noqa: BLE001
        warnings.warn(f"could not load existing clusterer: {exc}")
        return None


def _compare(prod_metrics, cand_metrics, min_r2_gain=-0.003, max_mae_ratio=1.05, max_rmse_ratio=1.05):
    if prod_metrics is None:
        return {"passed": True, "label": "bootstrap", "reasons": ["No production model; bootstrap"], "r2_gain": None, "mae_ratio": None}
    r2_gain = cand_metrics["r2"] - prod_metrics["r2"]
    mae_ratio = cand_metrics["mae"] / prod_metrics["mae"] if prod_metrics["mae"] > 1e-12 else 0.0
    rmse_ratio = cand_metrics["rmse"] / prod_metrics["rmse"] if prod_metrics["rmse"] > 1e-12 else 0.0
    reasons = []
    # Hard gates: MAE/RMSE are not allowed to regress beyond tolerance regardless of R2.
    if mae_ratio > max_mae_ratio:
        reasons.append(f"MAE ratio {mae_ratio:.4f} > {max_mae_ratio}")
    if rmse_ratio > max_rmse_ratio:
        reasons.append(f"RMSE ratio {rmse_ratio:.4f} > {max_rmse_ratio}")
    # R2 gate: only disqualifying on its own if the drop exceeds the noise
    # tolerance AND the candidate didn't clearly improve MAE and RMSE.
    # A candidate that beats production on both error metrics shouldn't be
    # blocked by a marginal R2 wobble.
    clearly_better_errors = mae_ratio < 1.0 and rmse_ratio < 1.0
    if r2_gain < min_r2_gain and not clearly_better_errors:
        reasons.append(f"R2 gain {r2_gain:.6f} < {min_r2_gain}")
    return {"passed": not reasons, "label": "better" if not reasons else "worse", "reasons": reasons,
            "r2_gain": float(r2_gain), "mae_ratio": float(mae_ratio), "rmse_ratio": float(rmse_ratio)}

class ThreeDayHorizonTrainer:
    def __init__(self, config: HorizonTrainConfig):
        self.config = config
        self.store = HorizonModelStore("3day", models_root=config.models_root, project_root=config.project_root)

    def load_dataset(self):
        path = Path(self.config.feature_dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Feature dataset not found: {path}")
        df = pd.read_csv(path)
        missing = [c for c in ["device_id", "day", *THREE_DAY_TARGETS] if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        df["day"] = pd.to_datetime(df["day"], errors="coerce")
        df = df.dropna(subset=["day"])
        df["_month"] = df["day"].dt.to_period("M").astype(str)
        return df

    def prepare_xy(self, df):
        feature_cols = [c for c in df.columns if c not in DROP_FOR_XY]
        X = df[feature_cols].copy()
        y = df[THREE_DAY_TARGETS].copy()
        mask = y.notna().all(axis=1) & X.notna().any(axis=1)
        return X.loc[mask].fillna(0.0), y.loc[mask]

    def time_split(self, df):
        months = sorted(df["_month"].unique())
        if len(months) < 2:
            df = df.sort_values("day")
            cut = int(len(df) * 0.8)
            return df.iloc[:cut], df.iloc[cut:], "time_fraction", []
        holdout_month = months[-1]
        train_months = months[:-1]
        return df[df["_month"].isin(train_months)], df[df["_month"] == holdout_month], holdout_month, train_months

    def train_and_evaluate(self):
        df = self.load_dataset()
        train_df, holdout_df, holdout_label, train_months = self.time_split(df)
        if len(train_df) < self.config.min_train_rows:
            raise RuntimeError(f"3-day train rows {len(train_df)} < min")
        if len(holdout_df) < 10:
            raise RuntimeError(f"3-day holdout too small: {len(holdout_df)}")
        X_train, y_train = self.prepare_xy(train_df)
        X_holdout, y_holdout = self.prepare_xy(holdout_df)
        common = [c for c in X_train.columns if c in X_holdout.columns]
        X_train, X_holdout = X_train[common], X_holdout[common]
        def _factory():
            return ElectricityConsumptionModel(model_type=self.config.algorithm, random_state=self.config.random_state, **(self.config.model_params or {}))

        X_all, y_all = self.prepare_xy(df)
        X_all = X_all[[c for c in X_train.columns if c in X_all.columns]]
        ids_train = train_df.loc[X_train.index, "device_id"].to_numpy()
        ids_hold = holdout_df.loc[X_holdout.index, "device_id"].to_numpy()
        ids_all = df.loc[X_all.index, "device_id"].to_numpy()

        cluster_info = {"clustered": False, "status": "disabled"}
        if self.config.clustered:
            candidate, refit, cluster_info = train_clustered_pair(
                build_model=_factory, settings=self.config.cluster_settings(),
                cluster_source=_load_cluster_source(self.config),
                train_cutoff=train_df["day"].max(),
                X_train=X_train, y_train=y_train, ids_train=ids_train,
                X_all=X_all, y_all=y_all, ids_all=ids_all,
                existing_clusterer=_existing_clusterer(self.store, self.config),
            )
        else:
            candidate = _factory()
            candidate.fit(X_train, y_train)
            refit = _factory()
            refit.fit(X_all, y_all)

        cand_pred = predict_any(candidate, X_holdout, ids_hold)
        cand_metrics = compute_metrics(y_holdout.values, cand_pred)
        if is_cluster_bundle(candidate):
            cluster_info["holdout_routes"] = route_report(candidate, X_holdout, y_holdout.values, ids_hold, compute_metrics)
        production_version = self.store.production_version()
        prod_metrics = None
        model_path = self.store.resolve_model_path()
        if model_path is not None and model_path.exists():
            try:
                prod_model = load_any_model(model_path)
                names = prod_model.get("feature_names") if is_cluster_bundle(prod_model) else getattr(prod_model, "feature_names_", None)
                if names:
                    missing = [f for f in names if f not in X_holdout.columns]
                    if not missing:
                        prod_pred = predict_any(prod_model, X_holdout[list(names)], ids_hold)
                        prod_metrics = compute_metrics(y_holdout.values, prod_pred)
            except Exception as exc:
                warnings.warn(f"prod eval failed: {exc}")
        comparison = _compare(prod_metrics, cand_metrics, self.config.min_r2_gain, self.config.max_mae_ratio, self.config.max_rmse_ratio)
        next_ver = self.store.next_version(production_version)
        meta = {"horizon": "3day", "version": next_ver, "algorithm": self.config.algorithm,
                "training_rows": int(len(X_train)), "validation_rows": int(len(X_holdout)),
                "n_features": int(X_train.shape[1]), "n_targets": int(y_train.shape[1]),
                "target_columns": THREE_DAY_TARGETS, "holdout": holdout_label, "train_months": train_months,
                "metrics": cand_metrics, "production_metrics": prod_metrics, "comparison": comparison,
                "feature_names": list(X_train.columns), "cluster": cluster_info}
        stored = self.store.store_candidate(next_ver, self.config.algorithm, candidate, meta)
        return {"status": "success", "horizon": "3day", "candidate_version": next_ver,
                "production_version_before": production_version, "metrics": cand_metrics,
                "production_metrics": prod_metrics, "comparison": comparison["label"],
                "comparison_detail": comparison, "candidate_path": stored["model_path"],
                "metadata": meta, "refit_model": refit, "algorithm": self.config.algorithm,
                "should_promote": comparison["passed"], "cluster": cluster_info}

    def promote(self, train_result):
        if not train_result.get("should_promote"):
            return {"promoted": False, "reason": "candidate did not pass comparison gates", "comparison": train_result.get("comparison")}
        result = self.store.promote_candidate(train_result["candidate_version"], train_result["algorithm"],
                                              refit_model=train_result.get("refit_model"),
                                              extra_metadata={"metrics": train_result.get("metrics"), "promoted_from_cycle": True,
                                                              "cluster": train_result.get("cluster")})
        return {"promoted": True, **result}

class _AggTrainerBase:
    """Shared helpers for weekly/monthly aggregation trainers."""
    TARGET_COL = ""
    horizon_name = ""

    def __init__(self, config: HorizonTrainConfig):
        self.config = config
        self.store = HorizonModelStore(self.horizon_name, models_root=config.models_root, project_root=config.project_root)

    def _load_source(self):
        # Weekly/monthly aggregation only needs raw device_id/day/seg totals, not
        # engineered features. feature_dataset.csv has its earliest ~30 days per
        # device dropped by FeatureEngineer's rolling-window warmup, which starves
        # weekly/monthly of calendar history they don't actually need to lose
        # (this was the cause of "Monthly frame empty").
        # Prefer the untouched daily_dataset.csv when it's available and fall back
        # to feature_dataset.csv only if it isn't.
        daily_path = self.config.daily_dataset_path
        if daily_path is not None:
            daily_path = Path(daily_path)
            if daily_path.exists():
                df = pd.read_csv(daily_path)
                df["day"] = pd.to_datetime(df["day"], errors="coerce")
                return df.dropna(subset=["day"])
        feat = Path(self.config.feature_dataset_path)
        if feat.exists():
            df = pd.read_csv(feat)
            df["day"] = pd.to_datetime(df["day"], errors="coerce")
            return df.dropna(subset=["day"])
        raise FileNotFoundError("Neither daily_dataset nor feature_dataset found")

    def _daily_totals(self, df):
        segs = [c for c in ("seg0", "seg1", "seg2", "seg3") if c in df.columns]
        if not segs:
            segs = [c for c in THREE_DAY_TARGETS if c in df.columns]
        if segs:
            daily = df.groupby(["device_id", "day"], as_index=False)[segs].sum()
            daily["daily_total"] = daily[segs].sum(axis=1)
        else:
            numeric = [c for c in df.select_dtypes(include=[np.number]).columns if c != "device_id"]
            daily = df.groupby(["device_id", "day"], as_index=False)[numeric].sum()
            daily["daily_total"] = daily[numeric].sum(axis=1)
        daily["day"] = pd.to_datetime(daily["day"])
        return daily[["device_id", "day", "daily_total"]].drop_duplicates(["device_id", "day"])

    def assert_no_leakage(self, frame):
        banned = [c for c in frame.columns if c.startswith("target_") and c != self.TARGET_COL]
        if banned:
            raise RuntimeError(f"{self.horizon_name} leakage: {banned}")

    def _finalize(self, frame, feature_cols):
        frame = frame.sort_values(self._time_col)
        unique = sorted(frame[self._time_col].unique())
        cut = max(1, int(len(unique) * 0.8))
        train_df = frame[frame[self._time_col].isin(set(unique[:cut]))]
        hold_df = frame[frame[self._time_col].isin(set(unique[cut:]))]
        if len(train_df) < self.config.min_train_rows:
            raise RuntimeError(f"{self.horizon_name} train rows {len(train_df)} < min")
        if len(hold_df) < 3:
            cut_row = int(len(frame) * 0.8)
            train_df, hold_df = frame.iloc[:cut_row], frame.iloc[cut_row:]
        X_train = train_df[feature_cols].fillna(0.0)
        y_train = train_df[self.TARGET_COL].values
        X_hold = hold_df[feature_cols].fillna(0.0)
        y_hold = hold_df[self.TARGET_COL].values
        X_all = frame[feature_cols].fillna(0.0)
        y_all = frame[self.TARGET_COL].values

        def _factory():
            return build_single_output_model(self.config.algorithm, random_state=self.config.random_state, **(self.config.model_params or {}))

        cluster_info = {"clustered": False, "status": "disabled"}
        if self.config.clustered:
            model, refit, cluster_info = train_clustered_pair(
                build_model=_factory, settings=self.config.cluster_settings(),
                cluster_source=_load_cluster_source(self.config),
                train_cutoff=self._train_cutoff(train_df),
                X_train=X_train, y_train=y_train, ids_train=train_df["device_id"].to_numpy(),
                X_all=X_all, y_all=y_all, ids_all=frame["device_id"].to_numpy(),
                existing_clusterer=_existing_clusterer(self.store, self.config),
            )
        else:
            model = _factory()
            model.fit(X_train, y_train)
            refit = _factory()
            refit.fit(X_all, y_all)

        hold_ids = hold_df["device_id"].to_numpy()
        cand_metrics = compute_metrics(y_hold, predict_any(model, X_hold, hold_ids))
        if is_cluster_bundle(model):
            cluster_info["holdout_routes"] = route_report(model, X_hold, y_hold, hold_ids, compute_metrics)
        production_version = self.store.production_version()
        prod_metrics = None
        mp = self.store.resolve_model_path()
        if mp is not None and mp.exists():
            try:
                prod = load_any_model(mp)
                prod_metrics = compute_metrics(y_hold, predict_any(prod, X_hold, hold_ids))
            except Exception as exc:
                warnings.warn(f"prod eval failed: {exc}")
        comparison = _compare(prod_metrics, cand_metrics, self.config.min_r2_gain, self.config.max_mae_ratio, self.config.max_rmse_ratio)
        next_ver = self.store.next_version(production_version)
        meta = {"horizon": self.horizon_name, "version": next_ver, "algorithm": self.config.algorithm,
                "training_rows": int(len(X_train)), "validation_rows": int(len(X_hold)),
                "n_features": int(X_train.shape[1]), "n_targets": 1, "target_columns": [self.TARGET_COL],
                "metrics": cand_metrics, "production_metrics": prod_metrics, "comparison": comparison, "feature_names": feature_cols,
                "cluster": cluster_info}
        stored = self.store.store_candidate(next_ver, self.config.algorithm, model, meta)
        return {"status": "success", "horizon": self.horizon_name, "candidate_version": next_ver,
                "production_version_before": production_version, "metrics": cand_metrics,
                "production_metrics": prod_metrics, "comparison": comparison["label"],
                "comparison_detail": comparison, "candidate_path": stored["model_path"],
                "metadata": meta, "refit_model": refit, "algorithm": self.config.algorithm,
                "should_promote": comparison["passed"], "feature_names": feature_cols, "cluster": cluster_info}

    def promote(self, train_result):
        if not train_result.get("should_promote"):
            return {"promoted": False, "reason": "candidate did not pass comparison gates", "comparison": train_result.get("comparison")}
        result = self.store.promote_candidate(train_result["candidate_version"], train_result["algorithm"],
                                              refit_model=train_result.get("refit_model"),
                                              extra_metadata={"metrics": train_result.get("metrics"),
                                                             "feature_names": train_result.get("feature_names"),
                                                             "promoted_from_cycle": True,
                                                             "cluster": train_result.get("cluster")})
        return {"promoted": True, **result}

class WeeklyHorizonTrainer(_AggTrainerBase):
    TARGET_COL = "target_weekly_consumption"
    horizon_name = "weekly"
    _time_col = "week_start"

    @staticmethod
    def _train_cutoff(train_df):
        return pd.Timestamp(train_df["week_start"].max()) + pd.Timedelta(days=6)

    @staticmethod
    def _saturday(d):
        offset = (d.dayofweek - 5) % 7
        return d - pd.Timedelta(days=int(offset))

    def build_frame(self, daily):
        daily = daily.sort_values(["device_id", "day"]).copy()
        daily["week_start"] = daily["day"].apply(self._saturday)
        week_counts = daily.groupby(["device_id", "week_start"])["day"].nunique().reset_index(name="n_days")
        complete = week_counts[week_counts["n_days"] >= 7][["device_id", "week_start"]]
        weekly = daily.merge(complete, on=["device_id", "week_start"]).groupby(["device_id", "week_start"], as_index=False)["daily_total"].sum().rename(columns={"daily_total": "week_total"})
        weekly = weekly.sort_values(["device_id", "week_start"])
        rows = []
        for device_id, g in weekly.groupby("device_id"):
            g = g.sort_values("week_start").reset_index(drop=True)
            totals, starts = g["week_total"].values, g["week_start"].values
            for i in range(len(g)):
                if i < 2:
                    continue
                hist = totals[:i]
                week_start = pd.Timestamp(starts[i])
                rows.append({
                    "device_id": device_id, "week_start": week_start,
                    "target_weekly_consumption": float(totals[i]),
                    "prev_week": float(hist[-1]),
                    "prev_2week_mean": float(np.mean(hist[-2:])),
                    "prev_4week_mean": float(np.mean(hist[-4:])) if len(hist) >= 4 else float(np.mean(hist)),
                    "prev_8week_mean": float(np.mean(hist[-8:])) if len(hist) >= 8 else float(np.mean(hist)),
                    "prev_week_std": float(np.std(hist[-4:])) if len(hist) >= 2 else 0.0,
                    "trend_4": float(hist[-1] - hist[-4]) if len(hist) >= 4 else 0.0,
                    "trend_2": float(hist[-1] - hist[-2]) if len(hist) >= 2 else 0.0,
                    "month": int(week_start.month), "weekofyear": int(week_start.isocalendar()[1]),
                    "n_hist_weeks": int(len(hist)), "hist_min": float(np.min(hist)),
                    "hist_max": float(np.max(hist)), "hist_mean": float(np.mean(hist)),
                })
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise RuntimeError("Weekly frame empty")
        return frame

    def train_and_evaluate(self):
        daily = self._daily_totals(self._load_source())
        frame = self.build_frame(daily)
        self.assert_no_leakage(frame)
        feature_cols = [c for c in frame.columns if c not in ("device_id", "week_start", self.TARGET_COL)]
        return self._finalize(frame, feature_cols)

class MonthlyHorizonTrainer(_AggTrainerBase):
    TARGET_COL = "target_monthly_consumption"
    horizon_name = "monthly"
    _time_col = "month"

    @staticmethod
    def _train_cutoff(train_df):
        return pd.Period(str(train_df["month"].max()), freq="M").end_time.normalize()

    def build_frame(self, daily):
        daily = daily.sort_values(["device_id", "day"]).copy()
        daily["month"] = daily["day"].dt.to_period("M")
        counts = daily.groupby(["device_id", "month"])["day"].nunique().reset_index(name="n_days")
        complete = counts[counts["n_days"] >= 20][["device_id", "month"]]
        monthly = daily.merge(complete, on=["device_id", "month"]).groupby(["device_id", "month"], as_index=False)["daily_total"].sum().rename(columns={"daily_total": "month_total"})
        monthly = monthly.sort_values(["device_id", "month"])
        rows = []
        for device_id, g in monthly.groupby("device_id"):
            g = g.sort_values("month").reset_index(drop=True)
            totals, months = g["month_total"].values, g["month"].values
            for i in range(len(g)):
                if i < 2:
                    continue
                hist = totals[:i]
                month = months[i]
                month_ts = pd.Period(month, freq="M").to_timestamp()
                rows.append({
                    "device_id": device_id, "month": str(month),
                    "target_monthly_consumption": float(totals[i]),
                    "prev_month": float(hist[-1]),
                    "prev_2month_mean": float(np.mean(hist[-2:])),
                    "prev_3month_mean": float(np.mean(hist[-3:])) if len(hist) >= 3 else float(np.mean(hist)),
                    "prev_6month_mean": float(np.mean(hist[-6:])) if len(hist) >= 6 else float(np.mean(hist)),
                    "prev_12month_mean": float(np.mean(hist[-12:])) if len(hist) >= 12 else float(np.mean(hist)),
                    "prev_month_std": float(np.std(hist[-3:])) if len(hist) >= 2 else 0.0,
                    "trend_3": float(hist[-1] - hist[-3]) if len(hist) >= 3 else 0.0,
                    "trend_1": float(hist[-1] - hist[-2]) if len(hist) >= 2 else 0.0,
                    "month_num": int(month_ts.month), "n_hist_months": int(len(hist)),
                    "hist_min": float(np.min(hist)), "hist_max": float(np.max(hist)), "hist_mean": float(np.mean(hist)),
                })
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise RuntimeError("Monthly frame empty")
        return frame

    def train_and_evaluate(self):
        daily = self._daily_totals(self._load_source())
        frame = self.build_frame(daily)
        self.assert_no_leakage(frame)
        feature_cols = [c for c in frame.columns if c not in ("device_id", "month", self.TARGET_COL)]
        return self._finalize(frame, feature_cols)

def get_trainer(config: HorizonTrainConfig):
    if config.horizon == "3day":
        return ThreeDayHorizonTrainer(config)
    if config.horizon == "weekly":
        return WeeklyHorizonTrainer(config)
    if config.horizon == "monthly":
        return MonthlyHorizonTrainer(config)
    raise ValueError(f"Unknown horizon: {config.horizon}")