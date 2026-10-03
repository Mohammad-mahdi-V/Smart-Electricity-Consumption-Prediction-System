"""
clusterer.py

User clustering for electricity-consumption profiles.

Responsibilities
----------------
1. Validate daily electricity data.
2. Build one behavioral profile per user.
3. Filter users based on minimum available days.
3b. (optional) Describe WHEN a user consumes: if the daily dataset carries
    the per-segment time-of-day columns (seg{k}_start / seg{k}_hours) the
    profile also gets hour-aware features, so clustering compares users by
    the hours of the day they use energy and not just by "segment number".
4. Prepare clustering features.
5. Standardize features.
6. Automatically select K using Silhouette Score.
7. Train KMeans.
8. Predict cluster IDs.
9. Save / load trained clustering model.

This module does NOT build prediction targets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from cluster_profile_features import (
    BASE_COLS,
    CLOCK_COLS,
    apply_profile_transform,
    build_cluster_profiles,
    cluster_from_profiles,
)


class NoValidKError(RuntimeError):
    """No k in [k_min, k_max] yields clusters that all have enough devices."""


class UserClusterer:
    """
    Cluster electricity users according to their consumption behavior.

    Parameters
    ----------
    min_days:
        Minimum number of available days required for a user
        to participate in clustering.

    k_min:
        Minimum number of clusters tested.

    k_max:
        Maximum number of clusters tested.

    random_state:
        Random seed used by KMeans.

    n_init:
        Number of KMeans initializations.
    """

    VERSION = "1.0.0"

    REQUIRED_COLUMNS = [
        "device_id",
        "day",
        "seg0",
        "seg1",
        "seg2",
        "seg3",
    ]

    # Country-independent behavioural profile features shared with the
    # clustering core. Clock features are appended when available.
    FEATURE_COLUMNS = list(BASE_COLS)

    # Segment time-of-day columns (written by DatasetBuilder).
    TIME_INPUT_COLUMNS = [
        f"seg{k}_{suffix}"
        for k in range(4)
        for suffix in ("start", "hours")
    ]

    # Hour-aware profile features (added to FEATURE_COLUMNS when the time
    # columns are available). Hours are encoded circularly (sin/cos) where
    # 23:00 and 00:00 must be close.
    TIME_FEATURE_COLUMNS = [
        "boundary_mean_1",     # mean hour of boundary seg0|seg1
        "boundary_mean_2",     # mean hour of boundary seg1|seg2
        "boundary_mean_3",     # mean hour of boundary seg2|seg3
        "boundary_stability",  # mean std (hours) of the 3 boundaries over days
        "energy_center_sin",   # consumption-weighted mean hour, sin part
        "energy_center_cos",   # consumption-weighted mean hour, cos part
        "peak_hour_sin",       # hour of the densest segment, sin part
        "peak_hour_cos",       # hour of the densest segment, cos part
    ]

    def __init__(
        self,
        min_days: int = 7,
        k_min: int = 2,
        k_max: int = 7,
        random_state: int = 42,
        n_init: int = 20,
        use_time_features: bool = True,
        min_cluster_size: int = 30,
        min_cluster_frac: float = 0.03,
        outlier_z: float | None = 12.0,
        max_outlier_frac: float = 0.10,
    ):

        if min_days < 1:
            raise ValueError(
                "min_days must be >= 1."
            )

        if k_min < 2:
            raise ValueError(
                "k_min must be >= 2."
            )

        if k_max < k_min:
            raise ValueError(
                "k_max must be >= k_min."
            )

        if n_init < 1:
            raise ValueError(
                "n_init must be >= 1."
            )

        self.use_time_features = bool(use_time_features)
        self.uses_time_features_ = False
        self.min_days = int(min_days)
        self.k_min = int(k_min)
        self.k_max = int(k_max)
        self.random_state = int(random_state)
        self.n_init = int(n_init)

        # --- cluster-size guard ------------------------------------------
        # A cluster is only usable if it has enough DEVICES to train a model
        # on.  Silhouette alone happily picks k=2 with a 3-device cluster
        # (a few extreme consumers), so k is chosen only among values whose
        # smallest cluster has >= max(min_cluster_size, min_cluster_frac * n).
        self.min_cluster_size = int(min_cluster_size)
        self.min_cluster_frac = float(min_cluster_frac)
        # Robust outlier devices (|robust z| of any feature > outlier_z) are
        # kept OUT of KMeans (they would form tiny clusters) and use the
        # global fallback model.  outlier_z=None/0 disables this.
        self.outlier_z = None if not outlier_z else float(outlier_z)
        self.max_outlier_frac = float(max_outlier_frac)
        self.robust_center_: Optional[np.ndarray] = None
        self.robust_scale_: Optional[np.ndarray] = None
        self.outlier_device_ids_: list = []
        self.cluster_sizes_by_k: dict[int, list[int]] = {}
        self.valid_k_: list[int] = []
        self.required_cluster_size_: int = 0

        self.scaler: Optional[StandardScaler] = None
        self.model: Optional[KMeans] = None

        self.best_k: Optional[int] = None

        self.scores: dict[int, float] = {}

        self.feature_columns = list(
            self.FEATURE_COLUMNS
        )

        self.is_fitted = False

        self.user_profiles_: Optional[pd.DataFrame] = None

    # =========================================================
    # VALIDATION
    # =========================================================

    def validate_input(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        if not isinstance(df, pd.DataFrame):
            raise TypeError(
                "Input must be a pandas DataFrame."
            )

        if df.empty:
            raise ValueError(
                "Input dataset is empty."
            )

        missing_columns = [
            column
            for column in self.REQUIRED_COLUMNS
            if column not in df.columns
        ]

        if missing_columns:
            raise ValueError(
                f"Missing required columns: "
                f"{missing_columns}"
            )

        result = df.copy()

        # -----------------------------------------------------
        # Device ID
        # -----------------------------------------------------

        if result["device_id"].isna().any():
            raise ValueError(
                "device_id contains missing values."
            )

        # -----------------------------------------------------
        # Day
        # -----------------------------------------------------

        result["day"] = pd.to_datetime(
            result["day"],
            errors="coerce",
        )

        if result["day"].isna().any():
            raise ValueError(
                "day contains invalid dates."
            )

        # -----------------------------------------------------
        # Consumption columns
        # -----------------------------------------------------

        consumption_columns = [
            "seg0",
            "seg1",
            "seg2",
            "seg3",
        ]

        for column in consumption_columns:

            if result[column].isna().any():
                raise ValueError(
                    f"{column} contains missing values."
                )

            if not pd.api.types.is_numeric_dtype(
                result[column]
            ):
                raise TypeError(
                    f"{column} must be numeric."
                )

            values = result[column].to_numpy(
                dtype=float
            )

            if not np.isfinite(values).all():
                raise ValueError(
                    f"{column} contains "
                    "NaN or infinite values."
                )

            if (values < 0).any():
                raise ValueError(
                    f"{column} contains "
                    "negative consumption values."
                )

        # Optional time-of-day columns: keep them numeric if present.
        if self.has_time_columns(result):
            for column in self.TIME_INPUT_COLUMNS:
                result[column] = pd.to_numeric(
                    result[column]
                )

        return result

    # =========================================================
    # TIME-OF-DAY PROFILE FEATURES
    # =========================================================

    def has_time_columns(
        self,
        df: pd.DataFrame,
    ) -> bool:
        """True if df carries valid segment time-of-day columns."""

        if not all(
            column in df.columns
            for column in self.TIME_INPUT_COLUMNS
        ):
            return False

        values = df[self.TIME_INPUT_COLUMNS].apply(
            pd.to_numeric,
            errors="coerce",
        )

        if values.isna().any().any():
            return False

        hours = values[
            [f"seg{k}_hours" for k in range(4)]
        ]

        return bool((hours > 0).all().all())

    def _time_profile(
        self,
        user_df: pd.DataFrame,
    ) -> dict[str, float]:
        """
        Hour-aware behaviour of one user over all of their days.

        All values are computed from the segment time columns, so a
        segment is interpreted through the hours it covered on each day.
        """

        seg_cols = [f"seg{k}" for k in range(4)]

        consumption = user_df[seg_cols].to_numpy(dtype=float)

        start = user_df[
            [f"seg{k}_start" for k in range(4)]
        ].to_numpy(dtype=float)

        hours = user_df[
            [f"seg{k}_hours" for k in range(4)]
        ].to_numpy(dtype=float)

        # --- boundaries: where each segment starts (seg1..seg3) -------
        boundaries = start[:, 1:4]

        boundary_mean = boundaries.mean(axis=0)

        boundary_stability = float(
            boundaries.std(axis=0, ddof=0).mean()
        )

        # --- circular hour of the middle of every segment -------------
        mid = start + hours / 2.0

        angle = 2.0 * np.pi * mid / 24.0

        # --- energy centre: consumption-weighted resultant vector -----
        total_mean = float(consumption.sum(axis=1).mean())

        if total_mean > 0:
            energy_sin = float(
                (consumption * np.sin(angle)).sum(axis=1).mean()
                / total_mean
            )
            energy_cos = float(
                (consumption * np.cos(angle)).sum(axis=1).mean()
                / total_mean
            )
        else:
            energy_sin = 0.0
            energy_cos = 0.0

        # --- peak hour: middle of the densest segment each day --------
        density = consumption / hours

        peak_idx = density.argmax(axis=1)

        rows = np.arange(len(peak_idx))

        peak_angle = angle[rows, peak_idx]

        return {
            "boundary_mean_1": float(boundary_mean[0]),
            "boundary_mean_2": float(boundary_mean[1]),
            "boundary_mean_3": float(boundary_mean[2]),
            "boundary_stability": boundary_stability,
            "energy_center_sin": energy_sin,
            "energy_center_cos": energy_cos,
            "peak_hour_sin": float(np.sin(peak_angle).mean()),
            "peak_hour_cos": float(np.cos(peak_angle).mean()),
        }

    # =========================================================
    # BUILD USER PROFILES
    # =========================================================

    def build_device_profiles(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Build one behavioural profile per device using the shared profile core."""
        clean = self.validate_input(df)
        source = clean
        if not getattr(self, "use_time_features", True):
            source = clean.drop(
                columns=[c for c in self.TIME_INPUT_COLUMNS if c in clean.columns],
                errors="ignore",
            )

        profiles = build_cluster_profiles(
            source, cutoff=None, min_days=1, recent_days=28
        ).reset_index()

        days = (
            clean.groupby("device_id")["day"]
            .nunique()
            .rename("days_available")
            .reset_index()
        )
        profiles = profiles.merge(days, on="device_id", how="left")
        profiles["cluster"] = -1

        self.uses_time_features_ = all(c in profiles.columns for c in CLOCK_COLS)
        self.feature_columns = list(BASE_COLS)
        if self.uses_time_features_:
            self.feature_columns += list(CLOCK_COLS)

        return profiles[
            ["device_id", "days_available", *self.feature_columns, "cluster"]
        ].copy()

    # ELIGIBLE USERS
    # =========================================================

    def get_eligible_users(
        self,
        profiles: pd.DataFrame,
    ) -> pd.DataFrame:

        if not isinstance(
            profiles,
            pd.DataFrame,
        ):
            raise TypeError(
                "profiles must be a DataFrame."
            )

        required = [
            "device_id",
            "days_available",
        ]

        missing = [
            column
            for column in required
            if column not in profiles.columns
        ]

        if missing:
            raise ValueError(
                f"Missing columns: {missing}"
            )

        eligible = (
            profiles[
                profiles[
                    "days_available"
                ]
                >= self.min_days
            ]
            .copy()
            .reset_index(drop=True)
        )

        if eligible.empty:
            raise ValueError(
                "No users satisfy min_days."
            )

        return eligible

    # =========================================================
    # PREPARE FEATURES
    # =========================================================

    def prepare_features(
        self,
        profiles: pd.DataFrame,
        min_rows: int = 2,
    ) -> np.ndarray:
        # min_rows=2 for fitting (clustering needs >= 2 users); inference on a
        # single device passes min_rows=1 (see predict_cluster).

        missing = [
            column
            for column in self.feature_columns
            if column not in profiles.columns
        ]

        if missing:
            raise ValueError(
                f"Missing clustering features: {missing}"
            )

        X = (
            profiles[
                self.feature_columns
            ]
            .to_numpy(
                dtype=float
            )
        )

        if X.ndim != 2:
            raise ValueError(
                "Clustering feature matrix "
                "must be two-dimensional."
            )

        if X.shape[0] < min_rows:
            raise ValueError(
                "At least two users are required "
                "for clustering."
                if min_rows >= 2
                else "At least one user is required."
            )

        if not np.isfinite(X).all():
            raise ValueError(
                "Clustering features contain "
                "NaN or infinite values."
            )

        return X

    # =========================================================
    # OUTLIERS + MIN CLUSTER SIZE
    # =========================================================

    def required_cluster_size(self, n_samples: int) -> int:
        """Minimum devices per cluster for ``n_samples`` clustered devices."""
        req = max(
            int(getattr(self, "min_cluster_size", 1)),
            int(np.ceil(float(getattr(self, "min_cluster_frac", 0.0)) * n_samples)),
        )
        # never ask for more than an even split into k_min clusters allows
        return int(max(1, min(req, n_samples // max(self.k_min, 1))))

    def _robust_z(self, X: np.ndarray) -> np.ndarray:
        center = getattr(self, "robust_center_", None)
        scale = getattr(self, "robust_scale_", None)
        if center is None or scale is None:
            return np.zeros(X.shape[0])
        z = np.abs((X - center) / scale)
        n_worst = min(3, z.shape[1])
        return np.sort(z, axis=1)[:, -n_worst:].mean(axis=1)

    def _fit_outlier_mask(self, X: np.ndarray) -> np.ndarray:
        """True = outlier.  Learns median/MAD on the fitting data."""
        self.robust_center_ = np.median(X, axis=0)
        mad = np.median(np.abs(X - self.robust_center_), axis=0) * 1.4826
        self.robust_scale_ = np.where(mad > 1e-9, mad, 1.0)
        if not getattr(self, "outlier_z", None):
            return np.zeros(X.shape[0], dtype=bool)
        z = self._robust_z(X)
        mask = z > self.outlier_z
        cap = int(np.floor(self.max_outlier_frac * X.shape[0]))
        if mask.sum() > cap:                      # keep only the most extreme
            mask = np.zeros_like(mask)
            if cap > 0:
                mask[np.argsort(z)[-cap:]] = True
        return mask

    def is_outlier(self, profiles: pd.DataFrame) -> np.ndarray:
        """Outlier flag per device row (False if the clusterer predates this)."""
        if getattr(self, "robust_center_", None) is None or not getattr(self, "outlier_z", None):
            return np.zeros(len(profiles), dtype=bool)
        X = self.prepare_features(profiles, min_rows=1)
        return self._robust_z(X) > self.outlier_z

    # =========================================================
    # FIND BEST K
    # =========================================================

    def find_best_k(
        self,
        X_scaled: np.ndarray,
    ) -> int:

        X_scaled = np.asarray(
            X_scaled,
            dtype=float,
        )

        if X_scaled.ndim != 2:
            raise ValueError(
                "X_scaled must be 2D."
            )

        n_samples = X_scaled.shape[0]

        if n_samples < 3:
            raise ValueError(
                "At least 3 samples are required "
                "for silhouette-based K selection."
            )

        max_k = min(
            self.k_max,
            n_samples - 1,
        )

        if self.k_min > max_k:
            raise ValueError(
                "Invalid K range for the number "
                "of available users."
            )

        self.scores = {}
        self.cluster_sizes_by_k = {}
        required = self.required_cluster_size(n_samples)
        self.required_cluster_size_ = int(required)

        for k in range(
            self.k_min,
            max_k + 1,
        ):

            model = KMeans(
                n_clusters=k,
                random_state=self.random_state,
                n_init=self.n_init,
            )

            labels = (
                model.fit_predict(
                    X_scaled
                )
            )

            unique_labels = np.unique(
                labels
            )

            if len(unique_labels) < 2:
                continue

            score = silhouette_score(
                X_scaled,
                labels,
            )

            self.scores[k] = float(
                score
            )
            self.cluster_sizes_by_k[k] = sorted(
                int(c) for c in np.bincount(labels)
            )

        if not self.scores:
            raise RuntimeError(
                "Could not calculate "
                "any silhouette score."
            )

        # only k whose SMALLEST cluster has enough devices are eligible
        self.valid_k_ = [
            k for k in self.scores
            if min(self.cluster_sizes_by_k[k]) >= required
        ]

        if not self.valid_k_:
            raise NoValidKError(
                f"No k in [{self.k_min}, {max_k}] gives clusters with >= "
                f"{required} devices each (n={n_samples}); smallest-cluster "
                f"sizes by k: "
                f"{ {k: v[0] for k, v in self.cluster_sizes_by_k.items()} }"
            )

        best_k = max(
            self.valid_k_,
            key=self.scores.get,
        )

        self.best_k = int(
            best_k
        )

        return self.best_k

    # =========================================================
    # FIT
    # =========================================================

    def fit(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        profiles = self.build_device_profiles(df)
        eligible = self.get_eligible_users(profiles)

        P = (
            eligible[["device_id", *self.feature_columns]]
            .set_index("device_id")
            .copy()
        )

        mapping, info, cinfo = cluster_from_profiles(
            P,
            k="auto",
            seed=self.random_state,
            min_cluster_devices=self.min_cluster_size,
            min_cluster_frac=self.min_cluster_frac,
            outlier_z=self.outlier_z,
            max_outlier_frac=self.max_outlier_frac,
            k_max=self.k_max,
            pca_var=0.90,
            n_init=self.n_init,
        )

        if int(info.get("k", 0)) <= 0 or not mapping:
            raise NoValidKError(
                f"No valid clustering solution: {info.get('k_status', 'unknown')}"
            )

        self.profile_transformer_ = cinfo["transformer"]
        self.scaler = self.profile_transformer_["scaler"]
        self.model = cinfo["kmeans"]
        self.best_k = int(info["k"])
        self.scores = {self.best_k: float(info.get("silhouette", float("nan")))}
        self.cluster_sizes_by_k = {
            self.best_k: sorted(int(v) for v in info["sizes"].values())
        }
        self.valid_k_ = [self.best_k]
        self.required_cluster_size_ = int(info["required_cluster_devices"])

        X = P.to_numpy(dtype=float)
        self.robust_center_ = np.median(X, axis=0)
        mad = np.median(np.abs(X - self.robust_center_), axis=0) * 1.4826
        self.robust_scale_ = np.where(mad > 1e-9, mad, 1.0)
        self.outlier_device_ids_ = [
            dev for dev in eligible["device_id"].tolist() if dev not in mapping
        ]

        profiles = profiles.copy()
        profiles["cluster"] = profiles["device_id"].map(mapping).fillna(-1).astype(int)
        self.user_profiles_ = profiles
        self.is_fitted = True
        return profiles

    # PREDICT CLUSTER
    # =========================================================

    def predict_cluster(
        self,
        profiles: pd.DataFrame,
    ) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("UserClusterer must be fitted before prediction.")
        if self.model is None:
            raise RuntimeError("KMeans model is unavailable.")
        if not hasattr(self, "profile_transformer_"):
            raise RuntimeError("Profile transformer is unavailable.")

        X_df = profiles[self.feature_columns].copy()
        X_scaled = apply_profile_transform(X_df, self.profile_transformer_)
        return self.model.predict(X_scaled).astype(int)

    # SAVE
    # =========================================================

    def save(
        self,
        path: str | Path,
    ) -> None:

        if not self.is_fitted:
            raise RuntimeError(
                "Cannot save an unfitted UserClusterer."
            )

        path = Path(path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        joblib.dump(
            self,
            path,
        )

    # =========================================================
    # LOAD
    # =========================================================

    @classmethod
    def load(
        cls,
        path: str | Path,
    ) -> "UserClusterer":

        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(
                f"Clusterer file not found: {path}"
            )

        loaded = joblib.load(
            path
        )

        if not isinstance(
            loaded,
            cls,
        ):
            raise TypeError(
                "Loaded object is not "
                "a UserClusterer."
            )

        return loaded

    # =========================================================
    # REPR
    # =========================================================

    def __repr__(self) -> str:

        status = (
            "fitted"
            if self.is_fitted
            else "not fitted"
        )

        return (
            "UserClusterer("
            f"status='{status}', "
            f"min_days={self.min_days}, "
            f"k_range={self.k_min}-{self.k_max}, "
            f"best_k={self.best_k}, "
            f"version='{self.VERSION}'"
            ")"
        )