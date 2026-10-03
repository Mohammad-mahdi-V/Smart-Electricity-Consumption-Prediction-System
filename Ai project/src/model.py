from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import json
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.multioutput import MultiOutputRegressor
from sklearn.ensemble import RandomForestRegressor


class ElectricityConsumptionModel:


    MODEL_VERSION = "1.0.0"

    TARGET_COLUMNS = [
        "target_seg0",
        "target_seg1",
        "target_seg2",
        "target_seg3",
    ]

    SUPPORTED_MODELS = {"ridge", "linear", "random_forest", "xgboost"}

    def __init__(
        self,
        model_type: str = "ridge",
        random_state: int = 42,
        alpha: float = 1.0,
        n_estimators: int = 300,
        max_depth: int | None = None,
        min_samples_split: int = 2,
        min_samples_leaf: int = 1,
        n_jobs: int = -1,
        solver: str = "auto",
        fit_intercept: bool = True,
        max_features: str | int | float | None = 1.0,
        learning_rate: float = 0.1,
        subsample: float = 1.0,
        colsample_bytree: float = 1.0,
        reg_alpha: float = 0.0,
        reg_lambda: float = 1.0,
        xgb_max_depth: int = 6,
    ):
        """
        Parameters
        ----------
        model_type:
            "ridge" (پیش‌فرض)، "linear"، یا "random_forest".
        random_state:
            برای reproducibility.
        alpha:
            ضریب regularization برای "ridge" (باید >= 0 باشد).
        n_estimators, max_depth, min_samples_split, min_samples_leaf, n_jobs:
            پارامترهای مخصوص "random_forest".
        solver:
            پارامتر مخصوص "ridge" (پیش‌فرض sklearn: "auto"). این پارامتر
            بدون تأثیر روی رفتار پیش‌فرض قبلی، اختیاری اضافه شده است تا
            Control Panel بتواند آن را از UI تنظیم کند.
        fit_intercept:
            پارامتر مخصوص "linear" (پیش‌فرض sklearn: True).
        max_features:
            پارامتر مخصوص "random_forest" (پیش‌فرض sklearn: 1.0).
        learning_rate, subsample, colsample_bytree, reg_alpha, reg_lambda, xgb_max_depth:
            پارامترهای مخصوص "xgboost". xgb_max_depth جدا از max_depth نگه
            داشته شده چون معنای پیش‌فرض متفاوتی دارند (max_depth=None برای
            random_forest یعنی بدون محدودیت، ولی برای XGBoost باید عدد باشد).
        """
        model_type = model_type.lower().strip()
        if model_type not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported model_type: {model_type}. "
                f"Supported models: {sorted(self.SUPPORTED_MODELS)}"
            )
        if alpha < 0:
            raise ValueError("alpha must be non-negative.")

        self.model_type = model_type
        self.random_state = random_state
        self.alpha = float(alpha)
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.min_samples_leaf = min_samples_leaf
        self.n_jobs = n_jobs
        self.solver = solver
        self.fit_intercept = fit_intercept
        self.max_features = max_features
        self.learning_rate = float(learning_rate)
        self.subsample = float(subsample)
        self.colsample_bytree = float(colsample_bytree)
        self.reg_alpha = float(reg_alpha)
        self.reg_lambda = float(reg_lambda)
        self.xgb_max_depth = xgb_max_depth

        self.model = self._create_model()

        self.feature_names_: list[str] | None = None
        self.n_features_in_: int | None = None
        self.n_targets_: int | None = None
        self.is_fitted = False

    # =========================================================
    # MODEL FACTORY
    # =========================================================

    def _create_model(self):
        if self.model_type == "ridge":
            # Ridge با solver پیش‌فرض ("auto") یک closed-form solution
            # می‌دهد و ذاتاً deterministic است؛ random_state فقط برای
            # solver های "sag"/"saga" معنا دارد که اینجا استفاده نمی‌شوند،
            # پس عمداً پاس داده نمی‌شود تا API گمراه‌کننده نباشد.
            return Pipeline(
                steps=[
                    ("scaler", StandardScaler()),
                    ("regressor", Ridge(alpha=self.alpha, solver=self.solver)),
                ]
            )

        if self.model_type == "linear":
            return LinearRegression(fit_intercept=self.fit_intercept)

        if self.model_type == "random_forest":
            base_model = RandomForestRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                min_samples_split=self.min_samples_split,
                min_samples_leaf=self.min_samples_leaf,
                max_features=self.max_features,
                random_state=self.random_state,
                n_jobs=self.n_jobs,
            )
            return MultiOutputRegressor(base_model)

        if self.model_type == "xgboost":
            try:
                from xgboost import XGBRegressor
            except ImportError as exc:
                raise ImportError(
                    "model_type='xgboost' requires the 'xgboost' package. "
                    "Install it with: pip install xgboost"
                ) from exc

            base_model = XGBRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.xgb_max_depth,
                learning_rate=self.learning_rate,
                subsample=self.subsample,
                colsample_bytree=self.colsample_bytree,
                reg_alpha=self.reg_alpha,
                reg_lambda=self.reg_lambda,
                random_state=self.random_state,
                n_jobs=self.n_jobs,
                objective="reg:squarederror",
            )
            # Wrapped in MultiOutputRegressor (one booster per target segment)
            # rather than relying on XGBoost's native multi-output support,
            # since that support/API varies across xgboost versions. This
            # also keeps behavior/feature-importance access consistent with
            # the "random_forest" branch above.
            return MultiOutputRegressor(base_model)

        raise RuntimeError(f"Unknown model type: {self.model_type}")

    # =========================================================
    # VALIDATION
    # =========================================================

    @staticmethod
    def _validate_X(X: pd.DataFrame) -> None:
        if not isinstance(X, pd.DataFrame):
            raise TypeError("X must be a pandas DataFrame.")
        if X.empty:
            raise ValueError("X is empty.")
        if X.columns.duplicated().any():
            duplicates = X.columns[X.columns.duplicated()].tolist()
            raise ValueError(f"Duplicate feature columns: {duplicates}")
        if X.isnull().any().any():
            raise ValueError("X contains missing values.")
        numeric = X.select_dtypes(include=np.number)
        if len(numeric.columns) != len(X.columns):
            non_numeric = [c for c in X.columns if c not in numeric.columns]
            raise TypeError(f"Non-numeric features found: {non_numeric}")
        values = X.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("X contains NaN or infinite values.")

    @classmethod
    def _validate_y(cls, y: pd.DataFrame) -> None:
        if not isinstance(y, pd.DataFrame):
            raise TypeError("y must be a pandas DataFrame.")
        if y.empty:
            raise ValueError("y is empty.")
        missing_targets = [t for t in cls.TARGET_COLUMNS if t not in y.columns]
        if missing_targets:
            raise ValueError(f"Missing target columns: {missing_targets}")
        if list(y.columns) != cls.TARGET_COLUMNS:
            raise ValueError(f"Target columns must have exactly this order: {cls.TARGET_COLUMNS}")
        if y.isnull().any().any():
            raise ValueError("y contains missing values.")
        values = y.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("y contains NaN or infinite values.")
        if (values < 0).any():
            raise ValueError("Target consumption values cannot be negative.")

    # =========================================================
    # FIT
    # =========================================================

    def fit(self, X: pd.DataFrame, y: pd.DataFrame) -> "ElectricityConsumptionModel":
        self._validate_X(X)
        self._validate_y(y)
        if len(X) != len(y):
            raise ValueError(f"X/y row mismatch: {len(X)} != {len(y)}")

        self.feature_names_ = list(X.columns)
        self.n_features_in_ = X.shape[1]
        self.n_targets_ = y.shape[1]

        self.model.fit(X, y)
        self.is_fitted = True
        return self

    # =========================================================
    # FEATURE SCHEMA
    # =========================================================

    def _validate_feature_schema(self, X: pd.DataFrame) -> None:
        self._validate_X(X)
        if not self.is_fitted:
            raise RuntimeError("Model has not been fitted yet.")

        current = list(X.columns)
        if current != self.feature_names_:
            missing = [c for c in self.feature_names_ if c not in current]
            extra = [c for c in current if c not in self.feature_names_]
            raise ValueError(
                "Feature schema mismatch.\n"
                f"Missing: {missing}\nExtra: {extra}\n"
                f"Expected order: {self.feature_names_}\nReceived order: {current}"
            )

    # =========================================================
    # PREDICT
    # =========================================================

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._validate_feature_schema(X)

        predictions = self.model.predict(X)
        predictions = np.asarray(predictions, dtype=float)
        if predictions.ndim == 1:
            predictions = predictions.reshape(-1, 1)

        if not np.isfinite(predictions).all():
            raise RuntimeError("Model produced NaN or infinite predictions.")

        # مصرف برق فیزیکاً نمی‌تواند منفی باشد.
        predictions = np.maximum(predictions, 0.0)
        return predictions

    def predict_dataframe(self, X: pd.DataFrame) -> pd.DataFrame:
        predictions = self.predict(X)
        return pd.DataFrame(predictions, columns=self.TARGET_COLUMNS, index=X.index)

    # =========================================================
    # FEATURE IMPORTANCE
    # =========================================================

    def get_feature_importance(self) -> pd.DataFrame:
        if not self.is_fitted:
            raise RuntimeError("Model has not been fitted yet.")
        if self.feature_names_ is None:
            raise RuntimeError("Feature names are unavailable.")

        if self.model_type == "ridge":
            coefficients = np.asarray(self.model.named_steps["regressor"].coef_)
            importance = (
                np.abs(coefficients)
                if coefficients.ndim == 1
                else np.mean(np.abs(coefficients), axis=0)
            )

        elif self.model_type == "linear":
            coefficients = np.asarray(self.model.coef_)
            importance = (
                np.abs(coefficients)
                if coefficients.ndim == 1
                else np.mean(np.abs(coefficients), axis=0)
            )

        elif self.model_type in ("random_forest", "xgboost"):
            importances = np.array(
                [estimator.feature_importances_ for estimator in self.model.estimators_]
            )
            importance = np.mean(importances, axis=0)

        else:
            raise RuntimeError(f"Feature importance is not implemented for {self.model_type}")

        result = pd.DataFrame({"feature": self.feature_names_, "importance": importance})
        result = result.sort_values("importance", ascending=False).reset_index(drop=True)
        return result

    # =========================================================
    # SAVE / LOAD
    # =========================================================

    def save(self, path: str | Path) -> None:
        if not self.is_fitted:
            raise RuntimeError("Cannot save an unfitted model.")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str | Path) -> "ElectricityConsumptionModel":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        loaded = joblib.load(path)
        if not isinstance(loaded, cls):
            raise TypeError("Loaded object is not an ElectricityConsumptionModel.")
        return loaded

    # =========================================================
    # CLONE
    # =========================================================

    def clone_unfitted(self) -> "ElectricityConsumptionModel":
        return ElectricityConsumptionModel(
            model_type=self.model_type,
            random_state=self.random_state,
            alpha=self.alpha,
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_split=self.min_samples_split,
            min_samples_leaf=self.min_samples_leaf,
            n_jobs=self.n_jobs,
            solver=self.solver,
            fit_intercept=self.fit_intercept,
            max_features=self.max_features,
            learning_rate=self.learning_rate,
            subsample=self.subsample,
            colsample_bytree=self.colsample_bytree,
            reg_alpha=self.reg_alpha,
            reg_lambda=self.reg_lambda,
            xgb_max_depth=self.xgb_max_depth,
        )
    # =========================================================
    # PRODUCTION VERSION
    # =========================================================

    @staticmethod
    def get_production_version(
        production_json_path: str | Path | None = None,
    ) -> str:
        """
        Read the currently active production version.

        The active production version is stored in:
            processed/models/production.json

        This is intentionally separate from MODEL_VERSION,
        which describes the model implementation version.
        """

        if production_json_path is None:
            base = Path(__file__).resolve().parent.parent / "processed" / "models"
            horizon_ptr = base / "3day" / "production.json"
            legacy_ptr = base / "production.json"
            production_json_path = (
                horizon_ptr if horizon_ptr.exists() else legacy_ptr
            )

        production_json_path = Path(
            production_json_path
        )

        if not production_json_path.exists():
            raise FileNotFoundError(
                f"Production metadata not found: "
                f"{production_json_path}"
            )

        try:
            info = json.loads(
                production_json_path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid production.json: "
                f"{production_json_path}"
            ) from exc

        version = info.get(
            "production_version"
        )

        if not isinstance(version, str) or not version.strip():
            raise ValueError(
                "production.json does not contain "
                "a valid production_version."
            )

        return version
    # =========================================================
    # REPR
    # =========================================================

    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        return (
            f"ElectricityConsumptionModel(model_type='{self.model_type}', "
            f"status='{status}', features={self.n_features_in_}, "
            f"targets={self.n_targets_}, version='{self.MODEL_VERSION}')"
        )