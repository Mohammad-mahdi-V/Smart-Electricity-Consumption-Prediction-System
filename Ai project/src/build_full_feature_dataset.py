

from __future__ import annotations

from pathlib import Path
import time

import pandas as pd

from feature_engineer import FeatureEngineer


def separator(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:

    start_time = time.time()

    # --------------------------------------------------------
    # PATHS
    # --------------------------------------------------------

    base_dir = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    input_file = (
        base_dir
        / "processed"
        / "daily_dataset.csv"
    )

    output_dir = (
        base_dir
        / "processed"
    )

    output_file = (
        output_dir
        / "feature_dataset.csv"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # LOAD DAILY DATASET
    # --------------------------------------------------------

    separator("LOAD DAILY DATASET")

    if not input_file.exists():
        raise FileNotFoundError(
            f"Daily dataset not found: {input_file}\n"
            "Run build_full_daily_dataset.py first."
        )

    daily_df = pd.read_csv(
        input_file,
        parse_dates=["day"],
    )

    if daily_df.empty:
        raise ValueError(
            "Daily dataset is empty."
        )

    required_columns = [
        "device_id",
        "day",
        "seg0",
        "seg1",
        "seg2",
        "seg3",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in daily_df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Daily dataset is missing columns: {missing_columns}"
        )

    print(
        f"Input file: {input_file}"
    )
    print(
        f"Input shape: {daily_df.shape}"
    )
    print(
        f"Devices: {daily_df['device_id'].nunique()}"
    )
    print(
        f"Date range: "
        f"{daily_df['day'].min().date()} "
        f"→ "
        f"{daily_df['day'].max().date()}"
    )

    print(
        "✅ Daily dataset loaded"
    )

    # --------------------------------------------------------
    # BUILD FEATURES
    # --------------------------------------------------------

    separator("FEATURE ENGINEERING")

    engineer = FeatureEngineer(
        daily_df
    )

    feature_df = engineer.build()

    if feature_df.empty:
        raise ValueError(
            "Feature dataset is empty after feature engineering."
        )

    print(
        f"Feature dataset shape: {feature_df.shape}"
    )

    print(
        f"Devices: {feature_df['device_id'].nunique()}"
    )

    print(
        f"Date range: "
        f"{feature_df['day'].min().date()} "
        f"→ "
        f"{feature_df['day'].max().date()}"
    )

    # --------------------------------------------------------
    # VALIDATE OUTPUT
    # --------------------------------------------------------

    separator("VALIDATE FEATURE DATASET")

    required_targets = [
        "target_seg0",
        "target_seg1",
        "target_seg2",
        "target_seg3",
    ]

    missing_targets = [
        target
        for target in required_targets
        if target not in feature_df.columns
    ]

    if missing_targets:
        raise ValueError(
            f"Feature dataset is missing targets: {missing_targets}"
        )

    if feature_df.isnull().any().any():
        null_count = int(
            feature_df.isnull().sum().sum()
        )
        raise ValueError(
            f"Feature dataset contains {null_count} missing values."
        )

    if not feature_df["device_id"].is_unique:
        # device_id is expected to repeat across days.
        print(
            "ℹ️ Multiple rows per user are expected."
        )

    if feature_df[
        required_targets
    ].lt(0).any().any():

        raise ValueError(
            "Feature dataset contains negative target values."
        )

    print(
        f"Rows: {len(feature_df)}"
    )

    print(
        f"Columns: {len(feature_df.columns)}"
    )

    print(
        "Target columns:"
    )

    print(
        required_targets
    )

    print(
        "✅ Feature dataset validation passed"
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    separator("SAVE FEATURE DATASET")

    feature_df.to_csv(
        output_file,
        index=False,
    )

    print(
        f"Saved: {output_file}"
    )

    print(
        f"Shape: {feature_df.shape}"
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    separator("FEATURE DATASET SUMMARY")

    print(
        "First rows:"
    )

    print(
        feature_df.head()
    )

    print(
        "\nColumns:"
    )

    print(
        feature_df.columns.tolist()
    )

    print(
        "\nTarget statistics:"
    )

    print(
        feature_df[
            required_targets
        ].describe()
    )

    elapsed = (
        time.time()
        - start_time
    )

    print(
        f"\nTime: {elapsed / 60:.2f} minutes"
    )

    separator("FEATURE DATASET READY")


if __name__ == "__main__":
    main()
