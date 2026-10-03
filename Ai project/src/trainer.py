

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from model import ElectricityConsumptionModel
from train_dataset import TrainDatasetBuilder


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_FEATURE_DATASET = Path(
    "processed/feature_dataset.csv"
)

DEFAULT_MODEL_DIR = Path(
    "processed/models"
)

DEFAULT_MODEL_TYPE = "ridge"

DEFAULT_RANDOM_STATE = 42


# ============================================================
# TRAINING RESULT
# ============================================================

@dataclass
class TrainingResult:
    model_type: str

    dataset_path: str

    total_rows: int
    total_users: int

    train_rows: int
    validation_rows: int
    test_rows: int

    n_features: int
    n_targets: int

    model_path: str
    metadata_path: str

    trained_at: str


# ============================================================
# TRAINER
# ============================================================

class ElectricityModelTrainer:


    REQUIRED_COLUMNS = [
        "device_id",
        "day",
        "target_seg0",
        "target_seg1",
        "target_seg2",
        "target_seg3",
    ]

    TARGET_COLUMNS = [
        "target_seg0",
        "target_seg1",
        "target_seg2",
        "target_seg3",
    ]

    def __init__(
        self,
        feature_dataset_path: str | Path = DEFAULT_FEATURE_DATASET,
        model_dir: str | Path = DEFAULT_MODEL_DIR,
        model_type: str = DEFAULT_MODEL_TYPE,
        random_state: int = DEFAULT_RANDOM_STATE,
    ):
        self.feature_dataset_path = Path(
            feature_dataset_path
        )

        self.model_dir = Path(
            model_dir
        )

        self.model_type = (
            str(model_type)
            .strip()
            .lower()
        )

        self.random_state = int(
            random_state
        )

        # --------------------------------------------------------
        # Raw feature dataset
        # --------------------------------------------------------

        self.feature_df: pd.DataFrame | None = None

        # --------------------------------------------------------
        # TrainDatasetBuilder
        # --------------------------------------------------------

        self.dataset_builder: (
            TrainDatasetBuilder | None
        ) = None

        # --------------------------------------------------------
        # Prepared datasets
        # --------------------------------------------------------

        self.X_train: pd.DataFrame | None = None
        self.y_train: pd.DataFrame | None = None

        self.X_val: pd.DataFrame | None = None
        self.y_val: pd.DataFrame | None = None

        self.X_test: pd.DataFrame | None = None
        self.y_test: pd.DataFrame | None = None

        # --------------------------------------------------------
        # Model
        # --------------------------------------------------------

        self.model: (
            ElectricityConsumptionModel | None
        ) = None

        # --------------------------------------------------------
        # Training timestamps
        # --------------------------------------------------------

        self.started_at: str | None = None
        self.finished_at: str | None = None

    # ============================================================
    # LOAD FEATURE DATASET
    # ============================================================

    def load_data(self) -> pd.DataFrame:
        """
        Load the already engineered feature dataset.

        This method does not perform feature engineering.
        """

        print()
        print("=" * 70)
        print("LOAD FEATURE DATASET")
        print("=" * 70)

        if not self.feature_dataset_path.exists():
            raise FileNotFoundError(
                "Feature dataset not found:\n"
                f"{self.feature_dataset_path}"
            )

        df = pd.read_csv(
            self.feature_dataset_path
        )

        if df.empty:
            raise ValueError(
                "Feature dataset is empty."
            )

        missing = [
            column
            for column in self.REQUIRED_COLUMNS
            if column not in df.columns
        ]

        if missing:
            raise ValueError(
                "Feature dataset is missing "
                f"required columns: {missing}"
            )

        # --------------------------------------------------------
        # device_id validation
        # --------------------------------------------------------

        if df["device_id"].isna().any():
            raise ValueError(
                "feature_dataset contains missing device_id values."
            )

        # --------------------------------------------------------
        # day validation
        # --------------------------------------------------------

        df["day"] = pd.to_datetime(
            df["day"],
            errors="coerce",
        )

        if df["day"].isna().any():
            raise ValueError(
                "feature_dataset contains invalid day values."
            )

        # --------------------------------------------------------
        # Target validation
        # --------------------------------------------------------

        for column in self.TARGET_COLUMNS:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        if (
            df[
                self.TARGET_COLUMNS
            ]
            .isna()
            .any()
            .any()
        ):
            raise ValueError(
                "Target columns contain NaN values."
            )

        target_values = (
            df[
                self.TARGET_COLUMNS
            ]
            .to_numpy(
                dtype=float
            )
        )

        if not np.isfinite(
            target_values
        ).all():
            raise ValueError(
                "Target columns contain "
                "NaN or infinite values."
            )

        if (
            target_values < 0
        ).any():
            raise ValueError(
                "Target columns contain "
                "negative consumption values."
            )

        self.feature_df = df

        print(
            f"Dataset shape: {df.shape}"
        )

        print(
            f"Devices: {df['device_id'].nunique()}"
        )

        print(
            f"Date range: "
            f"{df['day'].min().date()} "
            f"→ "
            f"{df['day'].max().date()}"
        )

        print(
            "✅ Feature dataset loaded"
        )

        return df

    # ============================================================
    # BUILD TRAIN DATASET
    # ============================================================

    def build_datasets(self):
        """
        Delegate all split/X/Y construction to TrainDatasetBuilder.
        """

        if self.feature_df is None:
            raise RuntimeError(
                "Load data before building datasets."
            )

        print()
        print("=" * 70)
        print("BUILD TRAIN / VALIDATION / TEST DATASETS")
        print("=" * 70)

        self.dataset_builder = (
            TrainDatasetBuilder(
                self.feature_df
            )
        )

        dataset = (
            self.dataset_builder.build()
        )

        self.X_train = dataset[
            "X_train"
        ]

        self.y_train = dataset[
            "y_train"
        ]

        self.X_val = dataset[
            "X_val"
        ]

        self.y_val = dataset[
            "y_val"
        ]

        self.X_test = dataset[
            "X_test"
        ]

        self.y_test = dataset[
            "y_test"
        ]

        print(
            f"X_train: {self.X_train.shape}"
        )

        print(
            f"y_train: {self.y_train.shape}"
        )

        print(
            f"X_val:   {self.X_val.shape}"
        )

        print(
            f"y_val:   {self.y_val.shape}"
        )

        print(
            f"X_test:  {self.X_test.shape}"
        )

        print(
            f"y_test:  {self.y_test.shape}"
        )

        print(
            "✅ TrainDatasetBuilder completed"
        )

        return dataset

    # ============================================================
    # VALIDATE PREPARED DATA
    # ============================================================

    def validate_datasets(self) -> None:
        """
        Validate the datasets returned by TrainDatasetBuilder.

        This does NOT implement a second split algorithm.
        """

        print()
        print("=" * 70)
        print("VALIDATE TRAIN / VALIDATION / TEST DATA")
        print("=" * 70)

        datasets = {
            "X_train": self.X_train,
            "y_train": self.y_train,
            "X_val": self.X_val,
            "y_val": self.y_val,
            "X_test": self.X_test,
            "y_test": self.y_test,
        }

        # --------------------------------------------------------
        # Existence
        # --------------------------------------------------------

        for name, dataset in datasets.items():

            if dataset is None:
                raise RuntimeError(
                    f"{name} is not available."
                )

            if dataset.empty:
                raise ValueError(
                    f"{name} is empty."
                )

        # --------------------------------------------------------
        # Type
        # --------------------------------------------------------

        for name, dataset in datasets.items():

            if not isinstance(
                dataset,
                pd.DataFrame,
            ):
                raise TypeError(
                    f"{name} must be a pandas DataFrame."
                )

        # --------------------------------------------------------
        # Row counts
        # --------------------------------------------------------

        if len(self.X_train) != len(
            self.y_train
        ):
            raise ValueError(
                "Train X/y row count mismatch."
            )

        if len(self.X_val) != len(
            self.y_val
        ):
            raise ValueError(
                "Validation X/y row count mismatch."
            )

        if len(self.X_test) != len(
            self.y_test
        ):
            raise ValueError(
                "Test X/y row count mismatch."
            )

        # --------------------------------------------------------
        # Target schema
        # --------------------------------------------------------

        if list(
            self.y_train.columns
        ) != self.TARGET_COLUMNS:

            raise ValueError(
                "y_train target schema mismatch."
            )

        if list(
            self.y_val.columns
        ) != self.TARGET_COLUMNS:

            raise ValueError(
                "y_val target schema mismatch."
            )

        if list(
            self.y_test.columns
        ) != self.TARGET_COLUMNS:

            raise ValueError(
                "y_test target schema mismatch."
            )

        # --------------------------------------------------------
        # Feature schema consistency
        # --------------------------------------------------------

        train_columns = list(
            self.X_train.columns
        )

        if list(
            self.X_val.columns
        ) != train_columns:

            raise ValueError(
                "X_train and X_val feature schemas differ."
            )

        if list(
            self.X_test.columns
        ) != train_columns:

            raise ValueError(
                "X_train and X_test feature schemas differ."
            )

        # --------------------------------------------------------
        # Numeric feature validation
        # --------------------------------------------------------

        for name, X in {
            "X_train": self.X_train,
            "X_val": self.X_val,
            "X_test": self.X_test,
        }.items():

            non_numeric = (
                X
                .select_dtypes(
                    exclude=np.number
                )
                .columns
                .tolist()
            )

            if non_numeric:
                raise TypeError(
                    f"{name} contains non-numeric "
                    f"features: {non_numeric}"
                )

            values = X.to_numpy(
                dtype=float
            )

            if not np.isfinite(
                values
            ).all():

                raise ValueError(
                    f"{name} contains "
                    "NaN or infinite values."
                )

        # --------------------------------------------------------
        # Target validation
        # --------------------------------------------------------

        for name, y in {
            "y_train": self.y_train,
            "y_val": self.y_val,
            "y_test": self.y_test,
        }.items():

            values = y.to_numpy(
                dtype=float
            )

            if not np.isfinite(
                values
            ).all():

                raise ValueError(
                    f"{name} contains "
                    "NaN or infinite values."
                )

            if (
                values < 0
            ).any():

                raise ValueError(
                    f"{name} contains "
                    "negative target values."
                )

        print(
            "✅ Dataset validation passed"
        )

    # ============================================================
    # TRAIN MODEL
    # ============================================================

    def train(
        self,
    ) -> ElectricityConsumptionModel:
        """
        Train the selected model ONLY on X_train / y_train.
        """

        if self.X_train is None:
            raise RuntimeError(
                "Datasets must be built before training."
            )

        print()
        print("=" * 70)
        print("TRAIN MODEL")
        print("=" * 70)

        print(
            f"Model type: {self.model_type}"
        )

        print(
            f"Training samples: "
            f"{len(self.X_train)}"
        )

        print(
            f"Features: "
            f"{self.X_train.shape[1]}"
        )

        self.model = (
            ElectricityConsumptionModel(
                model_type=self.model_type,
                random_state=self.random_state,
            )
        )

        self.model.fit(
            self.X_train,
            self.y_train,
        )

        print(
            "✅ Model trained successfully"
        )

        print(
            self.model
        )

        return self.model

    # ============================================================
    # VALIDATION PREDICTION SANITY
    # ============================================================

    def predict_validation(
        self,
    ) -> pd.DataFrame:
        """
        Run prediction on the validation set.

        This is NOT final model evaluation.
        Metrics belong to evaluator.py.
        """

        if self.model is None:
            raise RuntimeError(
                "Model must be trained first."
            )

        if self.X_val is None:
            raise RuntimeError(
                "Validation data is not available."
            )

        print()
        print("=" * 70)
        print("VALIDATION PREDICTION SANITY CHECK")
        print("=" * 70)

        predictions = (
            self.model.predict_dataframe(
                self.X_val
            )
        )

        # --------------------------------------------------------
        # Shape
        # --------------------------------------------------------

        expected_shape = (
            len(self.X_val),
            len(self.TARGET_COLUMNS),
        )

        if predictions.shape != expected_shape:
            raise RuntimeError(
                "Unexpected validation "
                f"prediction shape: {predictions.shape}. "
                f"Expected: {expected_shape}"
            )

        # --------------------------------------------------------
        # Columns
        # --------------------------------------------------------

        if list(
            predictions.columns
        ) != self.TARGET_COLUMNS:

            raise RuntimeError(
                "Validation prediction columns "
                "do not match target columns."
            )

        # --------------------------------------------------------
        # Index
        # --------------------------------------------------------

        if not predictions.index.equals(
            self.X_val.index
        ):

            raise RuntimeError(
                "Validation prediction index "
                "does not match X_val index."
            )

        # --------------------------------------------------------
        # Numerical sanity
        # --------------------------------------------------------

        values = predictions.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            values
        ).all():

            raise RuntimeError(
                "Validation predictions contain "
                "NaN or infinite values."
            )

        if (
            values < 0
        ).any():

            raise RuntimeError(
                "Validation predictions contain "
                "negative values."
            )

        print(
            f"Prediction shape: "
            f"{predictions.shape}"
        )

        print(
            "✅ Validation prediction sanity passed"
        )

        return predictions

    # ============================================================
    # SAVE MODEL
    # ============================================================

    def save(
        self,
        model_filename: str | None = None,
    ) -> tuple[Path, Path]:

        if self.model is None:
            raise RuntimeError(
                "No trained model is available."
            )

        if self.feature_df is None:
            raise RuntimeError(
                "Feature dataset is not loaded."
            )

        if self.X_train is None:
            raise RuntimeError(
                "Training data is not available."
            )

        self.model_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if model_filename is None:

            model_filename = (
                f"electricity_model_"
                f"{self.model_type}.joblib"
            )

        model_path = (
            self.model_dir
            / model_filename
        )

        metadata_path = (
            model_path.with_suffix(
                ".json"
            )
        )

        # --------------------------------------------------------
        # Save model
        # --------------------------------------------------------

        self.model.save(
            model_path
        )

        # --------------------------------------------------------
        # Metadata
        # --------------------------------------------------------

        metadata = {
            "model_type": self.model_type,
            "random_state": self.random_state,
            "model_version": (
                self.model.MODEL_VERSION
            ),

            "dataset_path": str(
                self.feature_dataset_path
            ),

            "total_rows": int(
                len(self.feature_df)
            ),

            "total_devices": int(
                self.feature_df[
                    "device_id"
                ]
                .nunique()
            ),

            "train_rows": int(
                len(self.X_train)
            ),

            "validation_rows": int(
                len(self.X_val)
            ),

            "test_rows": int(
                len(self.X_test)
            ),

            "n_features": int(
                self.X_train.shape[1]
            ),

            "n_targets": int(
                self.y_train.shape[1]
            ),

            "target_columns": (
                self.TARGET_COLUMNS
            ),

            "feature_names": (
                list(
                    self.X_train.columns
                )
            ),

            "started_at": (
                self.started_at
            ),

            "finished_at": (
                self.finished_at
            ),

            "saved_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

        with open(
            metadata_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                metadata,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print()
        print("=" * 70)
        print("SAVE MODEL")
        print("=" * 70)

        print(
            f"Model:    {model_path}"
        )

        print(
            f"Metadata: {metadata_path}"
        )

        print(
            "✅ Model and metadata saved"
        )

        return (
            model_path,
            metadata_path,
        )

    # ============================================================
    # COMPLETE TRAINING PIPELINE
    # ============================================================

    def run(
        self,
    ) -> TrainingResult:

        self.started_at = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        try:

            # -----------------------------------------------
            # 1. Load feature dataset
            # -----------------------------------------------

            self.load_data()

            # -----------------------------------------------
            # 2. Delegate split/X/Y logic
            #    to TrainDatasetBuilder
            # -----------------------------------------------

            self.build_datasets()

            # -----------------------------------------------
            # 3. Validate prepared datasets
            # -----------------------------------------------

            self.validate_datasets()

            # -----------------------------------------------
            # 4. Train model
            # -----------------------------------------------

            self.train()

            # -----------------------------------------------
            # 5. Prediction sanity
            # -----------------------------------------------

            self.predict_validation()

            # -----------------------------------------------
            # 6. Finished timestamp
            # -----------------------------------------------

            self.finished_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            # -----------------------------------------------
            # 7. Save model + metadata
            # -----------------------------------------------

            (
                model_path,
                metadata_path,
            ) = self.save()

            # -----------------------------------------------
            # 8. Result
            # -----------------------------------------------

            return TrainingResult(
                model_type=self.model_type,

                dataset_path=str(
                    self.feature_dataset_path
                ),

                total_rows=len(
                    self.feature_df
                ),

                total_users=(
                    self.feature_df[
                        "device_id"
                    ]
                    .nunique()
                ),

                train_rows=len(
                    self.X_train
                ),

                validation_rows=len(
                    self.X_val
                ),

                test_rows=len(
                    self.X_test
                ),

                n_features=(
                    self.X_train.shape[1]
                ),

                n_targets=(
                    self.y_train.shape[1]
                ),

                model_path=str(
                    model_path
                ),

                metadata_path=str(
                    metadata_path
                ),

                trained_at=(
                    self.finished_at
                ),
            )

        except Exception:

            self.finished_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            raise


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print(
        "ELECTRICITY CONSUMPTION TRAINER"
    )
    print("=" * 70)

    trainer = ElectricityModelTrainer(
        feature_dataset_path=(
            "processed/feature_dataset.csv"
        ),
        model_dir=(
            "processed/models"
        ),
        model_type="ridge",
        random_state=42,
    )

    result = trainer.run()

    print()
    print("=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)

    print(
        json.dumps(
            asdict(result),
            indent=2,
            ensure_ascii=False,
        )
    )