from __future__ import annotations

import numpy as np
import pandas as pd

class FeatureEngineer:

    LAGS = [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        14,
        21,
        30,
    ]

    ROLLING_WINDOWS = [
        3,
        7,
        14,
        30,
    ]

    SEGMENTS = [
        "seg0",
        "seg1",
        "seg2",
        "seg3",
    ]

    # Time-of-day columns written by DatasetBuilder: for every segment the
    # hour it starts at and its length in hours (optional: old datasets
    # without them still work, they just get no time features).
    TIME_COLUMNS = [
        f"{segment}_{suffix}"
        for segment in SEGMENTS
        for suffix in ("start", "hours")
    ]

    # Density window (days) used for the "expected consumption" feature.
    DENSITY_WINDOW = 7

    def __init__(
        self,
        daily_df: pd.DataFrame,
    ):
        self.df = daily_df.copy()
        self.validate_input()

    # =========================================================
    # VALIDATION
    # =========================================================

    def validate_input(self):

        required_columns = [
            "device_id",
            "day",
            *self.SEGMENTS,
        ]

        missing = (
            set(required_columns)
            - set(self.df.columns)
        )

        if missing:
            raise ValueError(
                f"Missing columns: {missing}"
            )

        self.df["day"] = pd.to_datetime(
            self.df["day"]
        )

        self.df = (
            self.df
            .sort_values(
                [
                    "device_id",
                    "day",
                ]
            )
            .reset_index(drop=True)
        )

        numeric_segments = {}

        for segment in self.SEGMENTS:

            numeric_segments[segment] = pd.to_numeric(
                self.df[segment],
                errors="coerce",
            )

        self.df = pd.concat(
            [
                self.df.drop(
                    columns=self.SEGMENTS
                ),
                pd.DataFrame(
                    numeric_segments,
                    index=self.df.index,
                ),
            ],
            axis=1,
        )

        if (
            self.df[
                [
                    "device_id",
                    "day",
                    *self.SEGMENTS,
                ]
            ]
            .isnull()
            .any()
            .any()
        ):
            raise ValueError(
                "Input contains invalid or missing values."
            )

        # Optional time-of-day columns: must be numeric and valid if present.
        self.has_time_columns = all(
            column in self.df.columns
            for column in self.TIME_COLUMNS
        )

        if self.has_time_columns:

            for column in self.TIME_COLUMNS:
                self.df[column] = pd.to_numeric(
                    self.df[column],
                    errors="coerce",
                )

            time_values = self.df[self.TIME_COLUMNS]

            if time_values.isnull().any().any():
                raise ValueError(
                    "Segment time columns contain "
                    "invalid or missing values."
                )

            for segment in self.SEGMENTS:

                hours = self.df[f"{segment}_hours"]
                start = self.df[f"{segment}_start"]

                if (hours <= 0).any() or (hours > 24).any():
                    raise ValueError(
                        f"{segment}_hours must be in (0, 24]."
                    )

                if (start < 0).any() or (start > 23).any():
                    raise ValueError(
                        f"{segment}_start must be in [0, 23]."
                    )

        # جلوگیری از fragmentation احتمالی
        self.df = self.df.copy()

    # =========================================================
    # LAG FEATURES
    # =========================================================

    def create_lag_features(self):

        print("Creating lag features...")

        features = {}

        grouped = (
            self.df
            .groupby(
                "device_id",
                sort=False,
            )[self.SEGMENTS]
        )

        for lag in self.LAGS:

            shifted = grouped.shift(lag)

            for segment in self.SEGMENTS:

                features[
                    f"{segment}_lag_{lag}"
                ] = shifted[segment]

        lag_df = pd.DataFrame(
            features,
            index=self.df.index,
        )

        self.df = pd.concat(
            [
                self.df,
                lag_df,
            ],
            axis=1,
        )

    # =========================================================
    # ROLLING FEATURES
    # =========================================================

    def create_rolling_features(self):

        print("Creating rolling features...")

        features = {}

        # داده‌های یک روز قبل
        shifted = (
            self.df
            .groupby(
                "device_id",
                sort=False,
            )[self.SEGMENTS]
            .shift(1)
        )

        for segment in self.SEGMENTS:

            shifted_segment = shifted[segment]

            grouped_shifted = (
                shifted_segment
                .groupby(
                    self.df["device_id"],
                    sort=False,
                )
            )

            for window in self.ROLLING_WINDOWS:

                rolling_mean = (
                    grouped_shifted
                    .rolling(
                        window=window,
                        min_periods=window,
                    )
                    .mean()
                    .reset_index(
                        level=0,
                        drop=True,
                    )
                    .sort_index()
                )

                rolling_std = (
                    grouped_shifted
                    .rolling(
                        window=window,
                        min_periods=window,
                    )
                    .std()
                    .reset_index(
                        level=0,
                        drop=True,
                    )
                    .sort_index()
                )

                features[
                    f"{segment}_roll_mean_{window}"
                ] = rolling_mean

                features[
                    f"{segment}_roll_std_{window}"
                ] = rolling_std

        rolling_df = pd.DataFrame(
            features,
            index=self.df.index,
        )

        self.df = pd.concat(
            [
                self.df,
                rolling_df,
            ],
            axis=1,
        )

    # =========================================================
    # TREND FEATURES
    # =========================================================

    def create_trend_features(self):

        print("Creating trend features...")

        features = {}

        for segment in self.SEGMENTS:

            features[
                f"{segment}_diff_1"
            ] = (
                self.df[segment]
                - self.df[
                    f"{segment}_lag_1"
                ]
            )

            features[
                f"{segment}_diff_7"
            ] = (
                self.df[segment]
                - self.df[
                    f"{segment}_lag_7"
                ]
            )

        trend_df = pd.DataFrame(
            features,
            index=self.df.index,
        )

        self.df = pd.concat(
            [
                self.df,
                trend_df,
            ],
            axis=1,
        )

    # =========================================================
    # DEVICE PROFILE FEATURES (LEAKAGE-FREE)
    # =========================================================

    def create_device_profile_features(self):
        """Add leakage-free long-term device profile features."""

        print("Creating device profile features...")
        device = self.df["device_id"]
        groups = self.df.groupby("device_id", sort=False).indices
        n = len(self.df)
        features = {}

        # Expanding statistics use all observations strictly before the
        # current day.  Unlike a 90-day rolling window, they do not discard
        # otherwise valid rows just because the device has less history.
        profile_means = {}
        for segment in self.SEGMENTS:
            values = self.df[segment].to_numpy(dtype=float)
            mean_col = np.full(n, np.nan, dtype=float)
            std_col = np.full(n, np.nan, dtype=float)
            for positions in groups.values():
                x = values[positions]
                cs = np.concatenate(([0.0], np.cumsum(x)))
                cs2 = np.concatenate(([0.0], np.cumsum(x * x)))
                count = np.arange(len(x), dtype=float)
                valid = count >= 30
                mean = np.full(len(x), np.nan)
                std = np.full(len(x), np.nan)
                mean[valid] = cs[:-1][valid] / count[valid]
                var = np.maximum(cs2[:-1][valid] / count[valid] - mean[valid] ** 2, 0.0)
                std[valid] = np.sqrt(var)
                mean_col[positions] = mean
                std_col[positions] = std
            profile_means[segment] = mean_col
            features[f"{segment}_profile_expanding_mean"] = mean_col
            features[f"{segment}_profile_expanding_std"] = std_col

        total = self.df[self.SEGMENTS].sum(axis=1).to_numpy(dtype=float)
        total_mean = np.full(n, np.nan, dtype=float)
        total_std = np.full(n, np.nan, dtype=float)
        for positions in groups.values():
            x = total[positions]
            cs = np.concatenate(([0.0], np.cumsum(x)))
            cs2 = np.concatenate(([0.0], np.cumsum(x * x)))
            count = np.arange(len(x), dtype=float)
            valid = count >= 30
            mean = np.full(len(x), np.nan)
            std = np.full(len(x), np.nan)
            mean[valid] = cs[:-1][valid] / count[valid]
            var = np.maximum(cs2[:-1][valid] / count[valid] - mean[valid] ** 2, 0.0)
            std[valid] = np.sqrt(var)
            total_mean[positions] = mean
            total_std[positions] = std

        features["device_total_profile_expanding_mean"] = total_mean
        features["device_total_profile_expanding_std"] = total_std

        for segment in self.SEGMENTS:
            current = self.df[segment].to_numpy(dtype=float)
            base = profile_means[segment]
            features[f"{segment}_profile_expanding_ratio"] = current / np.where(base == 0, np.nan, base)
            features[f"{segment}_profile_share"] = base / np.where(total_mean == 0, np.nan, total_mean)

        current_total = total
        features["device_total_profile_expanding_ratio"] = current_total / np.where(total_mean == 0, np.nan, total_mean)

        self.df = pd.concat([self.df, pd.DataFrame(features, index=self.df.index)], axis=1)

    # =========================================================
    # CALENDAR FEATURES
    # =========================================================

    def create_calendar_features(self):

        print("Creating calendar features...")

        day = self.df["day"]

        # -----------------------------------------------------
        # Current day features
        # -----------------------------------------------------

        dayofweek = day.dt.dayofweek

        month = day.dt.month

        weekofyear = (
            day
            .dt
            .isocalendar()
            .week
            .astype(int)
        )

        quarter = day.dt.quarter

        is_weekend = (
            dayofweek >= 5
        ).astype(int)

        # -----------------------------------------------------
        # Target day = D + 1
        # -----------------------------------------------------

        target_day = (
            day
            + pd.Timedelta(days=1)
        )

        target_dayofweek = (
            target_day.dt.dayofweek
        )

        target_month = (
            target_day.dt.month
        )

        target_weekofyear = (
            target_day
            .dt
            .isocalendar()
            .week
            .astype(int)
        )

        target_quarter = (
            target_day.dt.quarter
        )

        target_is_weekend = (
            target_day.dt.dayofweek >= 5
        ).astype(int)

        # -----------------------------------------------------
        # Useful transition features
        # -----------------------------------------------------

        calendar_features = pd.DataFrame(
            {
                "dayofweek":
                    dayofweek,

                "month":
                    month,

                "weekofyear":
                    weekofyear,

                "quarter":
                    quarter,

                "is_weekend":
                    is_weekend,

                "target_dayofweek":
                    target_dayofweek,

                "target_month":
                    target_month,

                "target_weekofyear":
                    target_weekofyear,

                "target_quarter":
                    target_quarter,

                "target_is_weekend":
                    target_is_weekend,

                "day_to_target_day_change":
                    (
                        target_dayofweek
                        != dayofweek
                    ).astype(int),

                "month_changed":
                    (
                        target_month
                        != month
                    ).astype(int),

                "quarter_changed":
                    (
                        target_quarter
                        != quarter
                    ).astype(int),
            },
            index=self.df.index,
        )

        self.df = pd.concat(
            [
                self.df,
                calendar_features,
            ],
            axis=1,
        )

    # =========================================================
    # SEGMENT TIME FEATURES
    # =========================================================

    def create_time_features(self):
        """
        Tell the model WHICH HOURS each segment stands for.

        Segment boundaries are adaptive (30-day moving window), so "seg1"
        covers different hours on different days/users. Features:

        Boundaries of the TARGET day (D+1)
            nxt_seg{k}_start / nxt_seg{k}_hours / nxt_seg{k}_mid
            These are exactly the boundaries the target segments are
            measured with. Leakage-free: the boundaries of day D+1 are
            fitted on days <= D only (DatasetBuilder), so at prediction
            time they can be computed before D+1 happens.

        Boundary movement
            seg{k}_start_shift / seg{k}_hours_shift = target day minus
            today. Lets the model correct for a window that grows/shrinks.

        Consumption density (kWh per hour)
            seg{k}_density, seg{k}_density_roll7 (mean of the last 7 days,
            today included) and seg{k}_expected = density_roll7 *
            nxt_seg{k}_hours: the consumption we would expect in the
            target window if the user kept the same hourly intensity.
        """

        if not self.has_time_columns:
            return

        print("Creating segment time features...")

        features = {}

        device = self.df["device_id"]

        grouped = self.df.groupby(
            "device_id",
            sort=False,
        )

        for segment in self.SEGMENTS:

            start = self.df[f"{segment}_start"]
            hours = self.df[f"{segment}_hours"]

            # boundaries of day D+1 (row of the next day of the SAME device)
            nxt_start = grouped[f"{segment}_start"].shift(-1)
            nxt_hours = grouped[f"{segment}_hours"].shift(-1)

            features[f"nxt_{segment}_start"] = nxt_start
            features[f"nxt_{segment}_hours"] = nxt_hours
            features[f"nxt_{segment}_mid"] = (
                nxt_start + nxt_hours / 2.0
            )

            features[f"{segment}_start_shift"] = nxt_start - start
            features[f"{segment}_hours_shift"] = nxt_hours - hours

            density = self.df[segment] / hours

            features[f"{segment}_density"] = density

            density_roll = (
                density
                .groupby(device, sort=False)
                .rolling(
                    window=self.DENSITY_WINDOW,
                    min_periods=self.DENSITY_WINDOW,
                )
                .mean()
                .reset_index(level=0, drop=True)
                .sort_index()
            )

            features[f"{segment}_density_roll{self.DENSITY_WINDOW}"] = (
                density_roll
            )

            features[f"{segment}_expected"] = density_roll * nxt_hours

        time_df = pd.DataFrame(
            features,
            index=self.df.index,
        )

        self.df = pd.concat(
            [
                self.df,
                time_df,
            ],
            axis=1,
        )

    # =========================================================
    # TARGETS
    # =========================================================

    def create_targets(self):

        print("Creating targets...")

        # تمام targetها یکجا ساخته می‌شوند.
        targets = (
            self.df
            .groupby(
                "device_id",
                sort=False,
            )[self.SEGMENTS]
            .shift(-1)
            .rename(
                columns={
                    segment:
                        f"target_{segment}"
                    for segment in self.SEGMENTS
                }
            )
        )

        self.df = pd.concat(
            [
                self.df,
                targets,
            ],
            axis=1,
        )

    # =========================================================
    # CLEAN
    # =========================================================

    def clean_dataset(self):

        print("Cleaning dataset...")

        self.df = (
            self.df
            .replace(
                [
                    np.inf,
                    -np.inf,
                ],
                np.nan,
            )
        )

        before = len(self.df)

        self.df = (
            self.df
            .dropna()
            .reset_index(drop=True)
        )

        after = len(self.df)

        print(
            f"Removed {before - after} rows"
        )

        # DataFrame را de-fragment می‌کنیم
        self.df = self.df.copy()

    # =========================================================
    # BUILD
    # =========================================================

    def build(self):

        print(
            "Starting feature engineering..."
        )

        self.create_lag_features()

        self.create_rolling_features()

        self.create_trend_features()

        self.create_device_profile_features()

        self.create_calendar_features()

        self.create_time_features()

        self.create_targets()

        self.clean_dataset()

        
        self.df = self.df.copy()

        print(
            "Feature engineering completed."
        )

        print(
            f"Final dataset shape: "
            f"{self.df.shape}"
        )

        return self.df
