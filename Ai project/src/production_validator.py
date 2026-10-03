

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

# Allow:
#     python src/production_validator.py
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from model import ElectricityConsumptionModel


TARGETS = [
    "target_seg0",
    "target_seg1",
    "target_seg2",
    "target_seg3",
]


@dataclass(frozen=True)
class ProductionValidationConfig:
    feature_dataset_path: Path
    output_dir: Path
    model_type: str = "ridge"
    random_state: int = 42
    min_train_months: int = 1
    min_rows_per_split: int = 100

    # Production quality gates.
    min_overall_r2: float = 0.0
    require_all_target_r2_non_negative: bool = True
    require_beats_train_mean_baseline: bool = True


class ProductionValidator:
    """
    Reusable monthly walk-forward validator.

    Important:
        This class validates model behavior in production-like monthly
        windows. It does not promote, replace, or delete production models.
        Model promotion belongs to a later production manager / retrainer.
    """

    def __init__(
        self,
        config: ProductionValidationConfig,
    ) -> None:
        self.config = config

        self.feature_dataset_path = Path(
            config.feature_dataset_path
        )
        self.output_dir = Path(config.output_dir)

        self.df: pd.DataFrame | None = None
        self.results: list[dict[str, Any]] = []
        self.summary: dict[str, Any] | None = None

    # =========================================================
    # DATASET
    # =========================================================

    def load_dataset(self) -> pd.DataFrame:
        path = self.feature_dataset_path

        if not path.exists():
            raise FileNotFoundError(
                f"Feature dataset not found: {path}"
            )

        df = pd.read_csv(
            path,
            parse_dates=["day"],
        )

        if df.empty:
            raise ValueError(
                "Feature dataset is empty."
            )

        required = [
            "device_id",
            "day",
            *TARGETS,
        ]

        missing = [
            column
            for column in required
            if column not in df.columns
        ]

        if missing:
            raise ValueError(
                f"Missing required columns: {missing}"
            )

        if df["day"].isna().any():
            raise ValueError(
                "Feature dataset contains invalid dates."
            )

        if df["device_id"].isna().any():
            raise ValueError(
                "Feature dataset contains missing user IDs."
            )

        target_values = df[TARGETS].to_numpy(
            dtype=float
        )

        if not np.isfinite(target_values).all():
            raise ValueError(
                "Targets contain NaN or infinite values."
            )

        if (target_values < 0).any():
            raise ValueError(
                "Targets contain negative values."
            )

        df = (
            df
            .sort_values(["day", "device_id"])
            .reset_index(drop=True)
        )

        self.df = df
        return df

    # =========================================================
    # X / Y
    # =========================================================

    @staticmethod
    def prepare_xy(
        df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        drop_columns = [
            "device_id",
            "day",
            "_month",
            *TARGETS,
        ]

        existing = [
            column
            for column in drop_columns
            if column in df.columns
        ]

        X = df.drop(
            columns=existing
        ).copy()

        y = df[TARGETS].copy()

        if len(X) != len(y):
            raise ValueError(
                "X/y row count mismatch."
            )

        if X.empty:
            raise ValueError(
                "X contains no features."
            )

        non_numeric = (
            X.select_dtypes(
                exclude=np.number
            )
            .columns
            .tolist()
        )

        if non_numeric:
            raise TypeError(
                "All model features must be numeric. "
                f"Non-numeric columns: {non_numeric}"
            )

        if not np.isfinite(
            X.to_numpy(dtype=float)
        ).all():
            raise ValueError(
                "Features contain NaN or infinite values."
            )

        if not np.isfinite(
            y.to_numpy(dtype=float)
        ).all():
            raise ValueError(
                "Targets contain NaN or infinite values."
            )

        return X, y

    # =========================================================
    # MONTHS / WINDOWS
    # =========================================================

    @staticmethod
    def add_month_column(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        result = df.copy()

        result["_month"] = (
            result["day"]
            .dt.to_period("M")
        )

        return result

    def monthly_windows(
        self,
        df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        if "_month" not in df.columns:
            df = self.add_month_column(df)

        months = sorted(
            df["_month"].unique()
        )

        windows: list[dict[str, Any]] = []

        for index in range(
            self.config.min_train_months,
            len(months) - 1,
        ):
            windows.append(
                {
                    "train_months": months[:index],
                    "validation_month": months[index],
                    "test_month": months[index + 1],
                }
            )

        return windows

    # =========================================================
    # METRICS
    # =========================================================

    @staticmethod
    def calculate_metrics(
        y_true: pd.DataFrame,
        y_pred: np.ndarray,
    ) -> dict[str, Any]:
        y_pred = np.asarray(
            y_pred,
            dtype=float,
        )

        if y_pred.shape != (
            len(y_true),
            len(TARGETS),
        ):
            raise ValueError(
                f"Unexpected prediction shape: {y_pred.shape}"
            )

        if not np.isfinite(y_pred).all():
            raise ValueError(
                "Predictions contain NaN or infinite values."
            )

        result: dict[str, Any] = {
            "mae": {},
            "rmse": {},
            "mape": {},
            "r2": {},
        }

        actual_all = y_true[TARGETS].to_numpy(
            dtype=float
        )

        for index, target in enumerate(TARGETS):
            actual = actual_all[:, index]
            predicted = y_pred[:, index]

            error = actual - predicted

            mae = float(
                np.mean(np.abs(error))
            )

            rmse = float(
                np.sqrt(
                    np.mean(error ** 2)
                )
            )

            non_zero = (
                np.abs(actual) > 1e-8
            )

            if non_zero.any():
                mape = float(
                    np.mean(
                        np.abs(
                            error[non_zero]
                            / actual[non_zero]
                        )
                    )
                    * 100.0
                )
            else:
                mape = 0.0

            ss_res = float(
                np.sum(error ** 2)
            )

            centered = (
                actual
                - np.mean(actual)
            )

            ss_tot = float(
                np.sum(centered ** 2)
            )

            if ss_tot <= 1e-12:
                r2 = 0.0
            else:
                r2 = float(
                    1.0
                    - ss_res / ss_tot
                )

            result["mae"][target] = mae
            result["rmse"][target] = rmse
            result["mape"][target] = mape
            result["r2"][target] = r2

        overall_error = (
            actual_all - y_pred
        )

        result["overall_mae"] = float(
            np.mean(
                np.abs(overall_error)
            )
        )

        result["overall_rmse"] = float(
            np.sqrt(
                np.mean(
                    overall_error ** 2
                )
            )
        )

        non_zero_all = (
            np.abs(actual_all) > 1e-8
        )

        if non_zero_all.any():
            result["overall_mape"] = float(
                np.mean(
                    np.abs(
                        overall_error[
                            non_zero_all
                        ]
                        / actual_all[
                            non_zero_all
                        ]
                    )
                )
                * 100.0
            )
        else:
            result["overall_mape"] = 0.0

        all_actual_flat = (
            actual_all.reshape(-1)
        )
        all_pred_flat = (
            y_pred.reshape(-1)
        )

        flat_error = (
            all_actual_flat
            - all_pred_flat
        )

        ss_res = float(
            np.sum(flat_error ** 2)
        )

        centered = (
            all_actual_flat
            - np.mean(all_actual_flat)
        )

        ss_tot = float(
            np.sum(centered ** 2)
        )

        if ss_tot <= 1e-12:
            result["overall_r2"] = 0.0
        else:
            result["overall_r2"] = float(
                1.0
                - ss_res / ss_tot
            )

        return result

    @staticmethod
    def train_mean_baseline(
        y_train: pd.DataFrame,
        y_test: pd.DataFrame,
    ) -> dict[str, Any]:
        train_means = (
            y_train[TARGETS]
            .mean(axis=0)
            .to_numpy(dtype=float)
        )

        predictions = np.tile(
            train_means,
            (
                len(y_test),
                1,
            ),
        )

        metrics = ProductionValidator.calculate_metrics(
            y_test,
            predictions,
        )

        return {
            "mae": metrics["overall_mae"],
            "mae_by_target": metrics["mae"],
            "train_means": {
                target: float(
                    y_train[target].mean()
                )
                for target in TARGETS
            },
        }

    # =========================================================
    # MODEL
    # =========================================================

    def create_model(self) -> ElectricityConsumptionModel:
        return ElectricityConsumptionModel(
            model_type=self.config.model_type,
            random_state=self.config.random_state,
        )

    # =========================================================
    # WINDOW VALIDATION
    # =========================================================

    def validate_window(
        self,
        full_df: pd.DataFrame,
        window: dict[str, Any],
        window_number: int,
    ) -> dict[str, Any]:
        train_months = window["train_months"]
        validation_month = window["validation_month"]
        test_month = window["test_month"]

        train_df = full_df[
            full_df["_month"].isin(train_months)
        ].copy()

        validation_df = full_df[
            full_df["_month"] == validation_month
        ].copy()

        test_df = full_df[
            full_df["_month"] == test_month
        ].copy()

        if len(train_df) < self.config.min_rows_per_split:
            raise ValueError(
                f"Window {window_number}: training split too small."
            )

        if len(validation_df) < self.config.min_rows_per_split:
            raise ValueError(
                f"Window {window_number}: validation split too small."
            )

        if len(test_df) < self.config.min_rows_per_split:
            raise ValueError(
                f"Window {window_number}: test split too small."
            )

        # Strict chronological isolation.
        train_max = train_df["day"].max()
        validation_min = validation_df["day"].min()
        validation_max = validation_df["day"].max()
        test_min = test_df["day"].min()

        if not train_max < validation_min:
            raise ValueError(
                f"Window {window_number}: train/validation chronology violated."
            )

        if not validation_max < test_min:
            raise ValueError(
                f"Window {window_number}: validation/test chronology violated."
            )

        train_dates = set(train_df["day"])
        validation_dates = set(validation_df["day"])
        test_dates = set(test_df["day"])

        if not train_dates.isdisjoint(validation_dates):
            raise ValueError(
                f"Window {window_number}: train/validation dates overlap."
            )

        if not train_dates.isdisjoint(test_dates):
            raise ValueError(
                f"Window {window_number}: train/test dates overlap."
            )

        if not validation_dates.isdisjoint(test_dates):
            raise ValueError(
                f"Window {window_number}: validation/test dates overlap."
            )

        X_train, y_train = self.prepare_xy(train_df)
        X_val, y_val = self.prepare_xy(validation_df)
        X_test, y_test = self.prepare_xy(test_df)

        if list(X_train.columns) != list(X_val.columns):
            raise ValueError(
                f"Window {window_number}: train/validation feature schema mismatch."
            )

        if list(X_train.columns) != list(X_test.columns):
            raise ValueError(
                f"Window {window_number}: train/test feature schema mismatch."
            )

        if list(y_train.columns) != TARGETS:
            raise ValueError(
                f"Window {window_number}: target schema mismatch."
            )

        model = self.create_model()

        # The model is fitted ONLY on the training period.
        model.fit(
            X_train,
            y_train,
        )

        if not model.is_fitted:
            raise RuntimeError(
                f"Window {window_number}: model did not fit."
            )

        validation_predictions = model.predict(
            X_val
        )

        test_predictions = model.predict(
            X_test
        )

        if not np.isfinite(
            validation_predictions
        ).all():
            raise RuntimeError(
                f"Window {window_number}: validation predictions are invalid."
            )

        if not np.isfinite(
            test_predictions
        ).all():
            raise RuntimeError(
                f"Window {window_number}: test predictions are invalid."
            )

        if (
            validation_predictions < 0
        ).any():
            raise RuntimeError(
                f"Window {window_number}: negative validation prediction."
            )

        if (
            test_predictions < 0
        ).any():
            raise RuntimeError(
                f"Window {window_number}: negative test prediction."
            )

        validation_metrics = self.calculate_metrics(
            y_val,
            validation_predictions,
        )

        test_metrics = self.calculate_metrics(
            y_test,
            test_predictions,
        )

        baseline = self.train_mean_baseline(
            y_train,
            y_test,
        )

        improvement = float(
            (
                baseline["mae"]
                - test_metrics["overall_mae"]
            )
            / max(
                baseline["mae"],
                1e-12,
            )
            * 100.0
        )

        negative_r2_targets = [
            target
            for target in TARGETS
            if test_metrics["r2"][target] < 0
        ]

        passed = True
        failure_reasons: list[str] = []

        if (
            test_metrics["overall_r2"]
            <= self.config.min_overall_r2
        ):
            passed = False
            failure_reasons.append(
                "Overall test R² did not pass the minimum threshold."
            )

        if (
            self.config.require_all_target_r2_non_negative
            and negative_r2_targets
        ):
            passed = False
            failure_reasons.append(
                "At least one target has negative test R²."
            )

        if (
            self.config.require_beats_train_mean_baseline
            and not (
                test_metrics["overall_mae"]
                < baseline["mae"]
            )
        ):
            passed = False
            failure_reasons.append(
                "Model did not beat the train-mean baseline."
            )

        return {
            "window": window_number,
            "train_months": [
                str(month)
                for month in train_months
            ],
            "validation_month": str(
                validation_month
            ),
            "test_month": str(
                test_month
            ),
            "train_start": str(
                train_df["day"].min().date()
            ),
            "train_end": str(
                train_df["day"].max().date()
            ),
            "validation_start": str(
                validation_df["day"].min().date()
            ),
            "validation_end": str(
                validation_df["day"].max().date()
            ),
            "test_start": str(
                test_df["day"].min().date()
            ),
            "test_end": str(
                test_df["day"].max().date()
            ),
            "train_rows": len(train_df),
            "validation_rows": len(validation_df),
            "test_rows": len(test_df),
            "n_features": X_train.shape[1],
            "validation_metrics": validation_metrics,
            "test_metrics": test_metrics,
            "baseline": baseline,
            "improvement_percent": improvement,
            "negative_r2_targets": negative_r2_targets,
            "passed": passed,
            "failure_reasons": failure_reasons,
        }

    # =========================================================
    # SUMMARY
    # =========================================================

    @staticmethod
    def summarize_windows(
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not results:
            raise ValueError(
                "Cannot summarize an empty result list."
            )

        test_mae = [
            result["test_metrics"]["overall_mae"]
            for result in results
        ]

        test_rmse = [
            result["test_metrics"]["overall_rmse"]
            for result in results
        ]

        test_mape = [
            result["test_metrics"]["overall_mape"]
            for result in results
        ]

        test_r2 = [
            result["test_metrics"]["overall_r2"]
            for result in results
        ]

        passed_windows = sum(
            bool(result["passed"])
            for result in results
        )

        return {
            "windows": len(results),
            "passed_windows": passed_windows,
            "failed_windows": len(results) - passed_windows,
            "all_windows_passed": (
                passed_windows == len(results)
            ),
            "mae": {
                "mean": float(np.mean(test_mae)),
                "std": float(np.std(test_mae)),
                "min": float(np.min(test_mae)),
                "max": float(np.max(test_mae)),
            },
            "rmse": {
                "mean": float(np.mean(test_rmse)),
                "std": float(np.std(test_rmse)),
                "min": float(np.min(test_rmse)),
                "max": float(np.max(test_rmse)),
            },
            "mape": {
                "mean": float(np.mean(test_mape)),
                "std": float(np.std(test_mape)),
                "min": float(np.min(test_mape)),
                "max": float(np.max(test_mape)),
            },
            "r2": {
                "mean": float(np.mean(test_r2)),
                "std": float(np.std(test_r2)),
                "min": float(np.min(test_r2)),
                "max": float(np.max(test_r2)),
            },
        }

    # =========================================================
    # PUBLIC API
    # =========================================================

    def validate(
        self,
    ) -> dict[str, Any]:
        """
        Run all available monthly production-style windows.

        Returns
        -------
        dict
            {
                "passed": bool,
                "summary": {...},
                "windows": [...]
            }
        """
        df = self.load_dataset()
        df = self.add_month_column(df)

        windows = self.monthly_windows(df)

        if not windows:
            raise ValueError(
                "No production-style monthly windows are available. "
                "At least train + validation + test months are required."
            )

        results: list[dict[str, Any]] = []

        for number, window in enumerate(
            windows,
            start=1,
        ):
            result = self.validate_window(
                df,
                window,
                number,
            )
            results.append(result)

        summary = self.summarize_windows(
            results
        )

        passed = bool(
            summary["all_windows_passed"]
        )

        self.results = results
        self.summary = summary

        report = {
            "passed": passed,
            "config": {
                "feature_dataset_path": str(
                    self.feature_dataset_path
                ),
                "model_type": self.config.model_type,
                "random_state": self.config.random_state,
                "min_train_months": self.config.min_train_months,
                "min_rows_per_split": self.config.min_rows_per_split,
                "min_overall_r2": self.config.min_overall_r2,
                "require_all_target_r2_non_negative": (
                    self.config.require_all_target_r2_non_negative
                ),
                "require_beats_train_mean_baseline": (
                    self.config.require_beats_train_mean_baseline
                ),
            },
            "summary": summary,
            "windows": results,
        }

        self._save_report(report)

        return report

    # =========================================================
    # REPORT
    # =========================================================

    def _save_report(
        self,
        report: dict[str, Any],
    ) -> None:
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        detailed_path = (
            self.output_dir
            / "production_validation_report.json"
        )

        summary_path = (
            self.output_dir
            / "production_validation_summary.json"
        )

        with detailed_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report,
                file,
                indent=2,
                ensure_ascii=False,
            )

        with summary_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                report["summary"],
                file,
                indent=2,
                ensure_ascii=False,
            )

    # =========================================================
    # CONVENIENCE
    # =========================================================

    def is_valid(self) -> bool:
        if self.summary is None:
            self.validate()

        return bool(
            self.summary
            and self.summary["all_windows_passed"]
        )


def build_default_validator() -> ProductionValidator:
    """
    Build a validator using the current project directory structure.
    """
    base_dir = (
        Path(__file__).resolve().parent.parent
    )

    config = ProductionValidationConfig(
        feature_dataset_path=(
            base_dir
            / "processed"
            / "feature_dataset.csv"
        ),
        output_dir=(
            base_dir
            / "processed"
            / "diagnostics"
            / "production_validation"
        ),
        model_type="ridge",
        random_state=42,
    )

    return ProductionValidator(config)


def main() -> None:
    print()
    print("=" * 78)
    print("ELECTRICITY MODEL — PRODUCTION VALIDATOR")
    print("=" * 78)
    print()

    validator = build_default_validator()
    report = validator.validate()

    print(
        f"Windows: {report['summary']['windows']}"
    )

    print(
        f"Passed: {report['summary']['passed_windows']}"
    )

    print(
        f"Failed: {report['summary']['failed_windows']}"
    )

    print(
        f"Average MAE: "
        f"{report['summary']['mae']['mean']:.6f}"
    )

    print(
        f"Average RMSE: "
        f"{report['summary']['rmse']['mean']:.6f}"
    )

    print(
        f"Average MAPE: "
        f"{report['summary']['mape']['mean']:.6f}%"
    )

    print(
        f"Average R²: "
        f"{report['summary']['r2']['mean']:.6f}"
    )

    if report["passed"]:
        print()
        print(
            "✅ PRODUCTION VALIDATION PASSED"
        )
    else:
        print()
        print(
            "❌ PRODUCTION VALIDATION FAILED"
        )

        for result in report["windows"]:
            if not result["passed"]:
                print(
                    f"Window {result['window']}: "
                    f"{result['failure_reasons']}"
                )

        raise SystemExit(1)

    print()
    print(
        "Report saved to:",
        validator.output_dir,
    )


if __name__ == "__main__":
    main()
