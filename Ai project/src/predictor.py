from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sys
from typing import Any

import numpy as np
import pandas as pd

SRC_DIR = Path(__file__).resolve().parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_processor import DataProcessor, DataSource
from dataset_builder import DatasetBuilder, segments_to_time_columns
from feature_engineer import FeatureEngineer
from model import ElectricityConsumptionModel
from cluster_runtime import load_any_model, is_cluster_bundle, select_cluster_model_detail


TARGETS = [
    "target_seg0",
    "target_seg1",
    "target_seg2",
    "target_seg3",
]

SEGMENTS = [
    "seg0",
    "seg1",
    "seg2",
    "seg3",
]


@dataclass(frozen=True)
class PredictorConfig:

    # production.json is now the source of truth
    production_metadata_path: Path

    # Optional. Prediction never reads electricity_data.csv.
    # History comes from data_source (DatabaseDeviceDataSource).
    data_path: Path | None = None

    # Required for prediction: database.repository.DatabaseDeviceDataSource
    data_source: DataSource | None = None

    feature_dataset_path: Path | None = None

    forecast_days: int = 3

    min_history_days: int = 61


class ElectricityPredictor:

    def __init__(
        self,
        config: PredictorConfig,
    ) -> None:

        if config.forecast_days != 3:
            raise ValueError(
                "The current production predictor is designed "
                "for exactly 3 forecast days."
            )

        if config.min_history_days < 61:
            raise ValueError(
                "min_history_days must be >= 61 because the "
                "current FeatureEngineer uses 61-day "
                "lag/rolling features."
            )

        self.config = config

        # =====================================================
        # LOAD ACTIVE PRODUCTION MODEL
        # =====================================================

        self.production_info = self._load_production_metadata()

        self.model_path = self._resolve_model_path()

        loaded = load_any_model(self.model_path)

        # Production artefact is either a plain model or a cluster bundle
        # (per-cluster models + global fallback). ``self.model`` is always a
        # concrete model (the global one for a bundle) so schema/feature
        # logic below is unchanged; per-device routing happens in predict().
        if is_cluster_bundle(loaded):
            self.cluster_bundle = loaded
            self.model = loaded["fallback"]
        else:
            if not isinstance(loaded, ElectricityConsumptionModel):
                raise TypeError(
                    "Loaded object is not an ElectricityConsumptionModel."
                )
            self.cluster_bundle = None
            self.model = loaded

        if not self.model.is_fitted:
            raise RuntimeError(
                "Loaded production model is not fitted."
            )

        self.processor: DataProcessor | None = None

        self.builder = DatasetBuilder()

        self.reference_feature_row: pd.Series | None = None
        self._feature_dataset: pd.DataFrame | None = None
        self._feature_dataset_loaded = False

    # =========================================================
    # PRODUCTION METADATA
    # =========================================================

    def _load_production_metadata(self) -> dict[str, Any]:

        path = self.config.production_metadata_path

        if not path.exists():
            raise FileNotFoundError(
                f"Production metadata not found: {path}"
            )

        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid production.json: {path}"
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                "production.json must contain a JSON object."
            )

        if "model_path" not in data:
            raise ValueError(
                "production.json does not contain 'model_path'."
            )

        if not data["model_path"]:
            raise ValueError(
                "production.json contains an empty model_path."
            )

        return data

    # =========================================================
    # RESOLVE ACTIVE MODEL PATH
    # =========================================================

    def _resolve_model_path(self) -> Path:
        """Resolve active model from production.json.

        Supports both legacy flat paths and versioned paths under
        ``{horizon}/{version}/`` so predictors keep working after
        flat copies are removed.
        """
        info = self.production_info
        meta_parent = self.config.production_metadata_path.resolve().parent
        project_root = meta_parent.parent.parent

        def _norm(raw: str) -> Path:
            return Path(str(raw).replace("\\", "/"))

        tried: list[Path] = []

        for key in ("model_path", "versioned_model_path"):
            raw = info.get(key)
            if not raw:
                continue
            p = _norm(raw)
            options = [p] if p.is_absolute() else [
                (project_root / p).resolve(),
                (meta_parent / p).resolve(),
                (meta_parent / p.name).resolve(),
            ]
            for cand in options:
                tried.append(cand)
                if cand.exists() and cand.is_file():
                    return cand

        version = info.get("production_version")
        algo = info.get("algorithm") or info.get("model_type")
        if version:
            for vdir in (
                meta_parent / "candidates" / str(version),
                meta_parent / str(version),
            ):
                if algo:
                    cand = vdir / f"electricity_model_{algo}.joblib"
                    tried.append(cand)
                    if cand.exists():
                        return cand
                if vdir.is_dir():
                    for cand in sorted(vdir.glob("electricity_model_*.joblib")):
                        tried.append(cand)
                        if cand.exists():
                            return cand

        raise FileNotFoundError(
            "Active production model does not exist.\n"
            f"production.json: {self.config.production_metadata_path}\n"
            f"tried: {[str(p) for p in tried]}"
        )

    # =========================================================
    # LOAD / PREPROCESS
    # =========================================================

    def ensure_processor(self) -> DataProcessor:
        """
        Load + preprocess history once per predictor instance.

        Nightly jobs call this (via warm_history) before the device
        loop so N devices do not trigger N full DB reads.
        """
        if self.processor is None:
            if self.config.data_source is None:
                raise RuntimeError(
                    "Prediction history must come from a DataSource "
                    "(DatabaseDeviceDataSource). electricity_data.csv "
                    "is not used on the prediction path. "
                    "Call build_db_predictor() / build_default_predictor()."
                )
            processor = DataProcessor(self.config.data_source)
            processor.preprocess()
            self.processor = processor
        return self.processor

    def warm_history(self) -> DataProcessor:
        """Preload and preprocess all history. Safe to call repeatedly."""
        return self.ensure_processor()

    def load_device_history(
        self,
        device_id: int,
    ) -> pd.DataFrame:

        processor = self.ensure_processor()

        user_df = processor.get_device_data(
            int(device_id)
        )

        if user_df is None or user_df.empty:
            raise ValueError(
                f"No data found for device_id={device_id}."
            )

        user_df = user_df.copy()

        user_df["day"] = pd.to_datetime(
            user_df["day"]
        )

        available_days = (
            user_df["day"]
            .nunique()
        )

        if available_days < self.config.min_history_days:
            raise ValueError(
                f"Device {device_id} has only "
                f"{available_days} complete days. "
                f"At least "
                f"{self.config.min_history_days} "
                "days are required."
            )

        return user_df

    # =========================================================
    # REFERENCE FEATURES
    # =========================================================

    def _get_feature_dataset(self) -> pd.DataFrame | None:
        if self._feature_dataset_loaded:
            return self._feature_dataset

        self._feature_dataset_loaded = True
        path = self.config.feature_dataset_path

        if path is None or not path.exists():
            self._feature_dataset = None
            return None

        df = pd.read_csv(
            path,
            parse_dates=["day"],
        )

        if "device_id" not in df.columns:
            raise ValueError(
                "Reference feature dataset has no device_id column."
            )

        self._feature_dataset = df
        return df

    def _load_reference_feature_row(
        self,
        device_id: int,
    ) -> pd.Series | None:

        df = self._get_feature_dataset()

        if df is None:
            return None

        user_rows = df[
            df["device_id"] == device_id
        ]

        if user_rows.empty:
            return None

        user_rows = user_rows.sort_values(
            "day"
        )

        return user_rows.iloc[-1]

    # =========================================================
    # DAILY DATA
    # =========================================================

    def build_daily_history(
        self,
        user_df: pd.DataFrame,
    ) -> pd.DataFrame:

        daily_df = (
            self.builder.build_daily_segments(
                user_df
            )
        )

        if daily_df.empty:
            raise ValueError(
                "Could not build daily segment history."
            )

        daily_df["day"] = pd.to_datetime(
            daily_df["day"]
        )

        daily_df = (
            daily_df
            .sort_values("day")
            .reset_index(drop=True)
        )

        if daily_df[SEGMENTS].isna().any().any():
            raise ValueError(
                "Daily segment dataset contains missing values."
            )

        return daily_df

    # =========================================================
    # INSUFFICIENT DATA RESULT
    # =========================================================

    def _insufficient_data_result(
        self,
        device_id: int,
        available_days: int,
        last_real_day: pd.Timestamp | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:

        forecast_days: list[dict[str, Any]] = []

        if last_real_day is not None:

            for step in range(
                1,
                self.config.forecast_days + 1,
            ):

                forecast_day = (
                    pd.Timestamp(last_real_day)
                    + pd.Timedelta(days=step)
                )

                forecast_days.append(
                    {
                        "date": (
                            forecast_day
                            .date()
                            .isoformat()
                        ),
                        "segments": None,
                        "peak": None,
                    }
                )

        else:

            forecast_days = [
                {
                    "date": None,
                    "segments": None,
                    "peak": None,
                }
                for _ in range(
                    self.config.forecast_days
                )
            ]

        return {
            "device_id": int(device_id),

            "status": "insufficient_data",

            "reason": (
                reason
                or (
                    f"Device {device_id} has only "
                    f"{available_days} complete days. "
                    f"At least "
                    f"{self.config.min_history_days} "
                    "days are required."
                )
            ),

            "available_days": int(
                available_days
            ),

            "required_days": int(
                self.config.min_history_days
            ),

            "last_real_day": (
                pd.Timestamp(last_real_day)
                .date()
                .isoformat()
                if last_real_day is not None
                else None
            ),

            "forecast_days": forecast_days,

            "segments": None,

            # Not enough data -> never clustered, no cluster-specific model.
            "cluster_id": None,
            "cluster": {
                "cluster_id": None,
                "source": "none",
                "reason": "insufficient_data",
            },

            "model": {
                "model_version": (
                    self.production_info.get(
                        "production_version"
                    )
                ),
                "model_type": (
                    self.model.model_type
                ),
                "n_features": (
                    self.model.n_features_in_
                ),
                "model_path": str(
                    self.model_path
                ),
            },
        }

    # =========================================================
    # SEGMENT BOUNDARIES
    # =========================================================

    def _get_latest_segments(
        self,
        user_df: pd.DataFrame,
    ) -> dict[int, dict[str, int]]:

        dates = sorted(
            pd.to_datetime(
                user_df["day"]
            ).dropna().unique()
        )

        if len(dates) < 30:
            raise ValueError(
                "At least 30 days are required to determine "
                "the current adaptive segment boundaries."
            )

        history_days = dates[-30:]

        history_df = user_df[
            user_df["day"].isin(history_days)
        ].copy()

        result = self.builder.segmenter.fit_user(
            history_df
        )

        return result["segments"]

    # =========================================================
    # SEGMENT OUTPUT
    # =========================================================

    @staticmethod
    def _segment_output(
        predictions: np.ndarray,
        segments: dict[int, dict[str, int]],
    ) -> list[dict[str, Any]]:

        output = []

        for seg_id, segment in segments.items():

            value = float(
                predictions[seg_id]
            )

            output.append(
                {
                    "segment": int(seg_id),
                    "start_hour": int(
                        segment["start"]
                    ),
                    "end_hour": int(
                        segment["end"]
                    ),
                    "predicted_consumption_kwh": value,
                }
            )

        return output

    # =========================================================
    # BUILD INFERENCE ROW
    # =========================================================

    def _build_inference_row(
        self,
        daily_with_future: pd.DataFrame,
        target_source_day: pd.Timestamp,
    ) -> pd.DataFrame:

        engineer = FeatureEngineer(
            daily_with_future
        )

        feature_df = engineer.build()

        target_source_day = pd.Timestamp(
            target_source_day
        )

        rows = feature_df[
            feature_df["day"] == target_source_day
        ].copy()

        if len(rows) != 1:
            raise ValueError(
                "Could not build exactly one inference row "
                f"for {target_source_day.date()}."
            )

        return rows

    # =========================================================
    # ALIGN FEATURES
    # =========================================================

    def _align_features(
        self,
        feature_row: pd.DataFrame,
        device_id: int,
    ) -> pd.DataFrame:

        reference = (
            self.reference_feature_row
        )

        result = feature_row.copy()

        if reference is not None:

            for column in self.model.feature_names_:

                if column not in result.columns:

                    if column in reference.index:

                        result[column] = (
                            reference[column]
                        )

        missing = [
            column
            for column in self.model.feature_names_
            if column not in result.columns
        ]

        if missing:
            raise ValueError(
                "The production model requires features "
                "that cannot be constructed for device "
                f"{device_id}: {missing}"
            )

        result = result[
            self.model.feature_names_
        ].copy()

        for column in result.columns:

            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

        if result.isna().any().any():

            bad = result.columns[
                result.isna().any()
            ].tolist()

            raise ValueError(
                "Inference features contain missing "
                f"values: {bad}"
            )

        values = result.to_numpy(
            dtype=float
        )

        if not np.isfinite(values).all():
            raise ValueError(
                "Inference features contain NaN "
                "or infinite values."
            )

        return result

    # =========================================================
    # PREDICT
    # =========================================================

    def predict(
        self,
        device_id: int,
    ) -> dict[str, Any]:

        try:

            user_df = self.load_device_history(
                device_id
            )

        except ValueError as exc:

            processor = self.ensure_processor()

            raw_user_df = (
                processor.get_device_data(
                    int(device_id)
                )
            )

            if (
                raw_user_df is None
                or raw_user_df.empty
            ):

                return (
                    self._insufficient_data_result(
                        device_id=device_id,
                        available_days=0,
                        last_real_day=None,
                        reason=(
                            f"No data found for "
                            f"device_id={device_id}."
                        ),
                    )
                )

            raw_user_df = (
                raw_user_df.copy()
            )

            raw_user_df["day"] = (
                pd.to_datetime(
                    raw_user_df["day"]
                )
            )

            available_days = int(
                raw_user_df["day"]
                .nunique()
            )

            last_real_day = pd.Timestamp(
                raw_user_df["day"].max()
            )

            return (
                self._insufficient_data_result(
                    device_id=device_id,
                    available_days=available_days,
                    last_real_day=last_real_day,
                    reason=str(exc),
                )
            )

        self.reference_feature_row = (
            self._load_reference_feature_row(
                device_id
            )
        )

        daily_history = (
            self.build_daily_history(
                user_df
            )
        )

        last_real_day = pd.Timestamp(
            daily_history["day"].max()
        )

        segments = self._get_latest_segments(
            user_df
        )

        # ---- cluster routing (per-cluster model or global fallback) ----
        active_model = self.model
        cluster_info: dict[str, Any] = {
            "cluster_id": None,
            "source": "global",
            "reason": "no_cluster_bundle",
        }
        if self.cluster_bundle is not None:
            selection = select_cluster_model_detail(
                self.cluster_bundle,
                daily_history,
            )
            active_model = selection["model"]
            cid = int(selection["cluster_id"])
            cluster_info = {
                "cluster_id": cid if cid >= 0 else None,
                "source": selection["source"],
                "reason": selection["reason"],
            }

        working_daily = (
            daily_history.copy()
        )

        forecasts: list[dict[str, Any]] = []

        for step in range(
            1,
            self.config.forecast_days + 1,
        ):

            source_day = (
                last_real_day
                + pd.Timedelta(
                    days=step - 1
                )
            )

            forecast_day = (
                last_real_day
                + pd.Timedelta(
                    days=step
                )
            )

            placeholder_day = (
                forecast_day
                + pd.Timedelta(days=1)
            )

            temp = (
                working_daily.copy()
            )

            if not (
                temp["day"]
                .eq(source_day)
                .any()
            ):
                raise RuntimeError(
                    f"Source day "
                    f"{source_day.date()} "
                    "is missing."
                )

            placeholder = {
                "device_id": int(device_id),
                "day": placeholder_day,
                "seg0": 0.0,
                "seg1": 0.0,
                "seg2": 0.0,
                "seg3": 0.0,
                # Boundaries of the day being predicted. Step 1: exactly the
                # boundaries DatasetBuilder would assign to that day (fitted
                # on the last 30 real days). Steps 2-3: held at the last
                # known boundaries - there is no hourly data to re-estimate
                # them for future days.
                **segments_to_time_columns(segments),
            }

            temp = pd.concat(
                [
                    temp,
                    pd.DataFrame(
                        [placeholder]
                    ),
                ],
                ignore_index=True,
            )

            temp = (
                temp
                .drop_duplicates(
                    subset=[
                        "device_id",
                        "day",
                    ],
                    keep="last",
                )
                .sort_values("day")
                .reset_index(drop=True)
            )

            inference_row = (
                self._build_inference_row(
                    temp,
                    source_day,
                )
            )

            X = self._align_features(
                inference_row,
                device_id,
            )

            prediction = active_model.predict(
                X
            )[0]

            prediction = np.maximum(
                np.asarray(
                    prediction,
                    dtype=float,
                ),
                0.0,
            )

            segment_output = (
                self._segment_output(
                    prediction,
                    segments,
                )
            )

            peak_index = int(
                np.argmax(prediction)
            )

            peak_segment = segments[
                peak_index
            ]

            forecasts.append(
                {
                    "date": (
                        forecast_day
                        .date()
                        .isoformat()
                    ),
                    "segments": segment_output,
                    "peak": {
                        "segment": peak_index,
                        "start_hour": int(
                            peak_segment["start"]
                        ),
                        "end_hour": int(
                            peak_segment["end"]
                        ),
                        "predicted_consumption_kwh": float(
                            prediction[
                                peak_index
                            ]
                        ),
                    },
                }
            )

            # Recursive prediction
            predicted_row = {
                "device_id": int(device_id),
                "day": forecast_day,
                "seg0": float(
                    prediction[0]
                ),
                "seg1": float(
                    prediction[1]
                ),
                "seg2": float(
                    prediction[2]
                ),
                "seg3": float(
                    prediction[3]
                ),
                # the forecast day was measured with these boundaries
                **segments_to_time_columns(segments),
            }

            working_daily = pd.concat(
                [
                    working_daily,
                    pd.DataFrame(
                        [predicted_row]
                    ),
                ],
                ignore_index=True,
            )

            working_daily = (
                working_daily
                .drop_duplicates(
                    subset=[
                        "device_id",
                        "day",
                    ],
                    keep="last",
                )
                .sort_values("day")
                .reset_index(drop=True)
            )

        return {
            "device_id": int(device_id),

            "status": "ok",

            "reason": None,

            "available_days": int(
                user_df["day"].nunique()
            ),

            "required_days": int(
                self.config.min_history_days
            ),

            "last_real_day": (
                last_real_day
                .date()
                .isoformat()
            ),

            "forecast_days": forecasts,

            "cluster_id": cluster_info["cluster_id"],
            "cluster": cluster_info,

            "model": {
                "model_version": (
                    self.production_info.get(
                        "production_version"
                    )
                ),
                "model_type": (
                    self.model.model_type
                ),
                "n_features": (
                    self.model.n_features_in_
                ),
                "model_path": str(
                    self.model_path
                ),
            },

            "segments": {
                str(seg_id): {
                    "start_hour": int(
                        segment["start"]
                    ),
                    "end_hour": int(
                        segment["end"]
                    ),
                }
                for seg_id, segment
                in segments.items()
            },
        }


# =============================================================
# DEFAULT PREDICTOR
# =============================================================

def _default_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_paths() -> dict[str, Path]:
    base_dir = _default_base_dir()
    return {
        "production_metadata_path": (
            base_dir / "processed" / "models" / "3day" / "production.json"
            if (base_dir / "processed" / "models" / "3day" / "production.json").exists()
            else base_dir / "processed" / "models" / "production.json"
        ),
        # Prediction path is DB-only. feature_dataset.csv is NOT required
        # at runtime; reference-feature fallback is disabled unless an
        # explicit path is passed by the caller.
        "feature_dataset_path": None,
    }


def build_db_predictor(
    db: Any | None = None,
    device_id: int | None = None,
    feature_dataset_path: Path | None = None,
) -> ElectricityPredictor:
    """
    Production predictor. History is always read from device_data
    (DatabaseDeviceDataSource). No CSV is required or opened.

    Pass device_id to load only that device (CLI / control panel).
    Omit it to load every device once (nightly job).

    feature_dataset_path is optional and off by default. Training still
    uses feature_dataset.csv; prediction does not.
    """
    # Ensure permanent Setup DB env is visible even if the process was
    # started without shell exports.
    try:
        from env_config import apply_db_env
        apply_db_env()
    except Exception:
        pass

    from database.connection import Database
    from database.repository import DatabaseDeviceDataSource

    paths = _default_paths()
    database = db if db is not None else Database()
    data_source = DatabaseDeviceDataSource(
        database,
        device_id=device_id,
    )

    return ElectricityPredictor(
        PredictorConfig(
            production_metadata_path=paths["production_metadata_path"],
            feature_dataset_path=feature_dataset_path,  # default None → no CSV
            forecast_days=3,
            min_history_days=61,
            data_source=data_source,
        )
    )


def build_default_predictor() -> ElectricityPredictor:
    """Same as build_db_predictor(): prediction is always DB-backed."""
    return build_db_predictor()


# =============================================================
# CLI
# =============================================================

def main() -> None:

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Predict electricity consumption "
            "for the next 3 days."
        )
    )

    parser.add_argument(
        "device_id",
        type=int,
        help="Device ID",
    )

    args = parser.parse_args()

    predictor = build_db_predictor(device_id=args.device_id)

    result = predictor.predict(
        args.device_id
    )

    print()

    print("=" * 78)
    print(
        "ELECTRICITY MODEL — 3 DAY FORECAST"
    )
    print("=" * 78)

    print(
        f"User: {result['device_id']}"
    )

    print(
        f"Status: {result['status']}"
    )

    print(
        f"Available days: "
        f"{result['available_days']}"
    )

    print(
        f"Required days: "
        f"{result['required_days']}"
    )

    print(
        f"Last real day: "
        f"{result['last_real_day']}"
    )

    print(
        f"Production version: "
        f"{result['model']['model_version']}"
    )

    print(
        f"Model path: "
        f"{result['model']['model_path']}"
    )

    if result["status"] != "ok":

        print()

        print(
            "⚠️ INSUFFICIENT DATA"
        )

        print(
            f"Reason: {result['reason']}"
        )

        for day in result[
            "forecast_days"
        ]:

            print()

            print(
                f"📅 {day['date']}"
            )

            print(
                "  Segments: NULL"
            )

            print(
                "  Peak: NULL"
            )

        print()
        return

    for day in result[
        "forecast_days"
    ]:

        print()

        print(
            f" {day['date']}"
        )

        for segment in day[
            "segments"
        ]:

            print(
                f"  Segment "
                f"{segment['segment']}: "
                f"{segment['start_hour']:02d}:00-"
                f"{segment['end_hour']:02d}:59 "
                f"→ "
                f"{segment['predicted_consumption_kwh']:.3f} kW"
            )

        peak = day["peak"]

        print(
            f"  Peak: "
            f"Segment {peak['segment']} "
            f"("
            f"{peak['start_hour']:02d}:00-"
            f"{peak['end_hour']:02d}:59"
            f") → "
            f"{peak['predicted_consumption_kwh']:.3f} kW"
        )

    print()


if __name__ == "__main__":
    main()