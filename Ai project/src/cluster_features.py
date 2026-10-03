from __future__ import annotations

import numpy as np
import pandas as pd


class ClusterFeatureBuilder:

    CLUSTER_BEHAVIOR_FEATURES = [
        "total_mean",
        "total_std",

        "seg0_ratio",
        "seg1_ratio",
        "seg2_ratio",
        "seg3_ratio",

        "weekday_mean",
        "weekend_mean",
        "weekend_vs_weekday_ratio",
        "weekend_vs_weekday_diff",
    ]

    def __init__(
        self,
        user_profiles: pd.DataFrame,
    ):
        self.user_profiles = user_profiles.copy()

        self.cluster_features = None

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def validate_profiles(self):

        if self.user_profiles.empty:
            raise ValueError(
                "User profiles are empty."
            )

        required = [
            "device_id",
            "cluster",
        ]

        missing = [
            column
            for column in required
            if column not in self.user_profiles.columns
        ]

        if missing:
            raise ValueError(
                f"Missing required columns: {missing}"
            )

        duplicate_users = (
            self.user_profiles["device_id"]
            .duplicated()
            .sum()
        )

        if duplicate_users > 0:
            raise ValueError(
                f"Duplicate user profiles found: "
                f"{duplicate_users}"
            )

        if self.user_profiles["cluster"].isna().any():
            raise ValueError(
                "Cluster contains NaN values."
            )

    # ---------------------------------------------------------
    # Build cluster behavior features
    # ---------------------------------------------------------

    def build_cluster_behavior_features(self):

        self.validate_profiles()

        missing_features = [
            feature
            for feature in self.CLUSTER_BEHAVIOR_FEATURES
            if feature not in self.user_profiles.columns
        ]

        if missing_features:
            raise ValueError(
                "Missing cluster behavior features: "
                f"{missing_features}"
            )

        available_features = self.CLUSTER_BEHAVIOR_FEATURES.copy()

        columns = [
            "device_id",
            "cluster",
            *available_features,
        ]

        result = (
            self.user_profiles[columns]
            .copy()
        )

        # Rename cluster itself
        result = result.rename(
            columns={
                "cluster": "cluster_id"
            }
        )

        # -----------------------------------------------------
        # Validate numeric values
        # -----------------------------------------------------

        numeric_columns = [
            column
            for column in result.columns
            if column != "device_id"
        ]

        for column in numeric_columns:

            result[column] = pd.to_numeric(
                result[column],
                errors="coerce"
            )

        if result[numeric_columns].isna().any().any():
            raise ValueError(
                "Cluster features contain invalid values."
            )

        if not np.isfinite(
            result[numeric_columns].to_numpy()
        ).all():

            raise ValueError(
                "Cluster features contain infinite values."
            )

        # -----------------------------------------------------
        # Rename behavioral features
        # -----------------------------------------------------

        rename_map = {
            feature: f"cluster_{feature}"
            for feature in available_features
        }

        result = result.rename(
            columns=rename_map
        )

        self.cluster_features = result

        return result

    # ---------------------------------------------------------
    # One-hot encode cluster ID
    # ---------------------------------------------------------

    def add_one_hot_clusters(self):

        if self.cluster_features is None:
            self.build_cluster_behavior_features()

        df = self.cluster_features.copy()

        cluster_dummies = pd.get_dummies(
            df["cluster_id"],
            prefix="cluster",
            dtype=int,
        )

        df = pd.concat(
            [
                df,
                cluster_dummies,
            ],
            axis=1,
        )

        self.cluster_features = df

        return df

    # ---------------------------------------------------------
    # Merge with Feature Dataset
    # ---------------------------------------------------------

    def transform(
        self,
        feature_df: pd.DataFrame,
    ) -> pd.DataFrame:

        if feature_df.empty:
            raise ValueError(
                "Feature dataset is empty."
            )

        if "device_id" not in feature_df.columns:
            raise ValueError(
                "Feature dataset must contain device_id."
            )

        # Build cluster features
        cluster_df = (
            self.build_cluster_behavior_features()
        )

        # Add one-hot cluster columns
        cluster_df = (
            self.add_one_hot_clusters()
        )

        result = feature_df.copy()

        original_rows = len(result)

        # -----------------------------------------------------
        # Check duplicate user profiles
        # -----------------------------------------------------

        if cluster_df["device_id"].duplicated().any():
            raise ValueError(
                "Cluster feature table contains "
                "duplicate device_id values."
            )

        # -----------------------------------------------------
        # Merge
        # -----------------------------------------------------

        result = result.merge(
            cluster_df,
            on="device_id",
            how="left",
            validate="many_to_one",
        )

        # -----------------------------------------------------
        # Row count must NEVER change
        # -----------------------------------------------------

        if len(result) != original_rows:
            raise RuntimeError(
                "Cluster merge changed dataset row count."
            )

        # -----------------------------------------------------
        # Check missing values
        # -----------------------------------------------------

        new_columns = [
            column
            for column in cluster_df.columns
            if column != "device_id"
        ]

        missing = (
            result[new_columns]
            .isna()
            .sum()
            .sum()
        )

        if missing > 0:
            raise ValueError(
                f"Missing cluster features after merge: "
                f"{missing}"
            )

        # -----------------------------------------------------
        # Check infinite values
        # -----------------------------------------------------

        numeric_columns = (
            result[new_columns]
            .select_dtypes(include=np.number)
            .columns
        )

        if not np.isfinite(
            result[numeric_columns].to_numpy()
        ).all():

            raise ValueError(
                "Infinite values detected after "
                "cluster feature merge."
            )

        return result