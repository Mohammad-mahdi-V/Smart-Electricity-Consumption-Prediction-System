from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

class UserStatus(Enum):
    LEARNING = "learning"
    GLOBAL = "global"
    PERSONAL = "personal"

class DataSource(ABC):


    @abstractmethod
    def load(self) -> pd.DataFrame:
        pass


class CSVDataSource(DataSource):

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def load(self) -> pd.DataFrame:

        if not self.file_path.exists():
            raise FileNotFoundError(
                f"File not found: {self.file_path}"
            )

        return pd.read_csv(self.file_path, low_memory=False)
class DataProcessor:

    REQUIRED_COLUMNS = {
        "device_id",
        "timestamp",
        "consumption_kwh"
    }

    MIN_VALID_HOURS_PER_DAY = 20
    MIN_DAYS_FOR_PREDICTION = 61
    MIN_DAYS_FOR_PERSONAL_MODEL = 30

    MAX_INTERPOLATION_GAP = 6

    EMPTY_COLUMNS = [
        "device_id",
        "timestamp",
        "consumption_kwh",
    ]

    def __init__(self, data_source: DataSource):

        self.data_source = data_source
        self.df = pd.DataFrame()
        self._device_index: dict[int, pd.DataFrame] | None = None

    # =====================================================
    # LOAD
    # =====================================================

    def load_data(self):

        self.df = self.data_source.load()
        self._device_index = None

        self.validate_columns()

        self.df["timestamp"] = pd.to_datetime(
            self.df["timestamp"],
            utc=True
        )

        self.df["device_id"] = (
            self.df["device_id"]
            .astype("int64")
        )

        self.df["consumption_kwh"] = (
            self.df["consumption_kwh"]
            .astype("float64")
        )

        self.df = self.df.sort_values(
            ["device_id", "timestamp"]
        )

        self.df.reset_index(
            drop=True,
            inplace=True
        )

        return self

    # =====================================================
    # VALIDATION
    # =====================================================

    def validate_columns(self):

        missing = (
            self.REQUIRED_COLUMNS
            - set(self.df.columns)
        )

        if missing:

            raise ValueError(
                f"Missing columns: {missing}"
            )

    # =====================================================
    # REMOVE DUPLICATES
    # =====================================================

    def remove_duplicates(self):

        self.df = (
            self.df
            .groupby(
                ["device_id", "timestamp"],
                as_index=False
            )
            .agg({
                "consumption_kwh": "mean"
            })
        )

        return self

    # =====================================================
    # REMOVE NEGATIVE VALUES
    # =====================================================

    def remove_negative_values(self):

        self.df = self.df.loc[
            self.df["consumption_kwh"] >= 0
        ].copy()

        return self

    # =====================================================
    # REMOVE BAD DAYS
    # =====================================================

    def remove_bad_days(self):

        if self.df.empty:
            return self

        day = self.df["timestamp"].dt.date
        hours = self.df.groupby(
            [self.df["device_id"], day],
            sort=False,
        ).size()
        valid = hours[hours >= self.MIN_VALID_HOURS_PER_DAY].index
        idx = pd.MultiIndex.from_arrays(
            [self.df["device_id"].to_numpy(), day.to_numpy()]
        )
        self.df = self.df.loc[idx.isin(valid)].reset_index(drop=True)

        return self

    # =====================================================
    # FILL MISSING HOURS
    # =====================================================

    def fill_missing_hours(self):

        if self.df.empty:
            return self

        frames: list[pd.DataFrame] = []

        for device_id, user_df in self.df.groupby("device_id", sort=False):
            cons = user_df.set_index("timestamp")["consumption_kwh"]
            full_range = pd.date_range(
                start=cons.index.min(),
                end=cons.index.max(),
                freq="h",
                tz="UTC",
            )
            cons = cons.reindex(full_range).interpolate(
                method="linear",
                limit=self.MAX_INTERPOLATION_GAP,
                limit_direction="both",
            )
            days = cons.index.date
            invalid_days = pd.unique(days[cons.isna().to_numpy()])
            if len(invalid_days):
                cons = cons[~np.isin(days, invalid_days)]
            out = cons.rename_axis("timestamp").reset_index()
            out["device_id"] = device_id
            frames.append(out)

        if not frames:
            self.df = pd.DataFrame(columns=self.EMPTY_COLUMNS)
            return self

        self.df = pd.concat(frames, ignore_index=True)
        return self

    # =====================================================
    # HANDLE OUTLIERS
    # =====================================================

    def handle_outliers(self):

        if self.df.empty:
            return self

        grouped = self.df.groupby("device_id")["consumption_kwh"]
        counts = grouped.transform("size")
        p1 = grouped.transform(lambda s: s.quantile(0.01))
        p99 = grouped.transform(lambda s: s.quantile(0.99))
        mask = counts >= 50
        if mask.any():
            clipped = self.df["consumption_kwh"].clip(p1, p99)
            self.df.loc[mask, "consumption_kwh"] = clipped.loc[mask]

        return self

    # =====================================================
    # TIME FEATURES
    # =====================================================

    def add_time_features(self):

        ts = self.df["timestamp"]

        self.df["day"] = ts.dt.date
        self.df["hour"] = ts.dt.hour
        self.df["dayofweek"] = ts.dt.dayofweek
        self.df["month"] = ts.dt.month
        self.df["is_weekend"] = (
            self.df["dayofweek"]
            .isin([5, 6])
            .astype(int)
        )

        return self

    # =====================================================
    # PIPELINE
    # =====================================================

    def preprocess(self):

        result = (
            self
            .load_data()
            .remove_duplicates()
            .remove_negative_values()
            .remove_bad_days()
            .fill_missing_hours()
            .handle_outliers()
            .add_time_features()
        )
        self._build_device_index()
        return result

    def _build_device_index(self) -> None:
        if self.df.empty or "device_id" not in self.df.columns:
            self._device_index = {}
            return
        self._device_index = {
            int(device_id): group
            for device_id, group in self.df.groupby("device_id", sort=False)
        }

    # =====================================================
    # USER DATA
    # =====================================================

    def get_device_data(
        self,
        device_id: int
    ):

        device_id = int(device_id)
        if self._device_index is not None:
            frame = self._device_index.get(device_id)
            if frame is None:
                return self.df.iloc[0:0].copy()
            return frame.copy()

        return self.df[
            self.df["device_id"] == device_id
        ].copy()

    # =====================================================
    # LAST DAYS
    # =====================================================

    def get_last_days(
        self,
        device_id: int,
        days: int = 7
    ):

        user_df = self.get_device_data(
            device_id
        )

        if user_df.empty:
            return None

        dates = sorted(
            user_df["day"]
            .dropna()
            .unique()
        )

        if len(dates) < days:
            return None

        selected = dates[-days:]

        return user_df[
            user_df["day"]
            .isin(selected)
        ].copy()

    # =====================================================
    # TRAINING WINDOW
    # =====================================================

    def get_training_window(
        self,
        device_id: int,
        days: int = 7
    ):

        return self.get_last_days(
            device_id,
            days
        )

    # =====================================================
    # USER STATUS
    # =====================================================

    def get_device_status(
        self,
        device_id: int
    ) -> UserStatus:

        user_df = self.get_device_data(
            device_id
        )

        if user_df.empty:
            return UserStatus.LEARNING

        total_days = (
            user_df["day"]
            .nunique()
        )

        if total_days < self.MIN_DAYS_FOR_PREDICTION:
            return UserStatus.LEARNING

        if total_days < self.MIN_DAYS_FOR_PERSONAL_MODEL:
            return UserStatus.GLOBAL

        return UserStatus.PERSONAL

    # =====================================================
    # HELPERS
    # =====================================================

    def can_predict(
        self,
        device_id: int
    ) -> bool:

        return (
            self.get_device_status(device_id)
            != UserStatus.LEARNING
        )

    def can_train_personal_model(
        self,
        device_id: int
    ) -> bool:

        return (
            self.get_device_status(device_id)
            == UserStatus.PERSONAL
        )

    def get_all_users(self):

        if self._device_index is not None:
            return sorted(self._device_index.keys())

        return sorted(
            self.df["device_id"]
            .unique()
            .tolist()
        )
