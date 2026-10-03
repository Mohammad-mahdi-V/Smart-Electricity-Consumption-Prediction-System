from segmenter import AdaptiveBoundarySegmenter
import pandas as pd


SEGMENT_IDS = (0, 1, 2, 3)


def time_column_names():
    """Names of the per-segment time-of-day columns of the daily dataset."""
    names = []
    for seg_id in SEGMENT_IDS:
        names.append(f"seg{seg_id}_start")
        names.append(f"seg{seg_id}_hours")
    return names


def segments_to_time_columns(segments: dict) -> dict:
    """
    Convert a segment dict {seg_id: {"start": h, "end": h}} (end inclusive)
    into the flat time-of-day columns stored in the daily dataset:

        seg{k}_start : hour of day (0-23) at which the segment starts
        seg{k}_hours : segment length in hours

    This is the single place where segment boundaries become columns, so the
    training dataset (build_daily_segments) and the inference rows built by
    the predictor are guaranteed to use the same encoding.
    """
    columns = {}
    for seg_id in SEGMENT_IDS:
        seg = segments[seg_id]
        start = int(seg["start"])
        end = int(seg["end"])
        columns[f"seg{seg_id}_start"] = start
        columns[f"seg{seg_id}_hours"] = end - start + 1
    return columns


class DatasetBuilder:

    def __init__(self):
        self.segmenter = AdaptiveBoundarySegmenter()


    def get_dynamic_segments(
        self,
        user_df: pd.DataFrame,
        current_day,
        window_days: int = 30
    ):

        days = sorted(
            user_df["day"].unique()
        )

        current_idx = days.index(
            current_day
        )

        if current_idx < window_days:
            return None

        history_days = days[
            current_idx - window_days:
            current_idx
        ]

        history_df = user_df[
            user_df["day"].isin(history_days)
        ]

        result = self.segmenter.fit_user(
            history_df
        )

        return result["segments"]


    def build_daily_segments(
        self,
        user_df: pd.DataFrame,
    ) -> pd.DataFrame:

        if user_df is None or user_df.empty:
            return pd.DataFrame()


        rows = []

        days = sorted(
            user_df["day"]
            .dropna()
            .unique()
        )


        for day in days:

            segments = self.get_dynamic_segments(
                user_df,
                day,
                window_days=30
            )

            if segments is None:
                continue


            day_df = user_df[
                user_df["day"] == day
            ].copy()


            record = {
                "device_id": int(
                    day_df["device_id"].iloc[0]
                ),
                "day": day
            }


            for seg_id, seg in segments.items():

                start_hour = seg["start"]
                end_hour = seg["end"]


                seg_df = day_df[
                    day_df["hour"].between(
                        start_hour,
                        end_hour
                    )
                ]


                seg_value = (
                    seg_df["consumption_kwh"]
                    .sum()
                )


                record[
                    f"seg{seg_id}"
                ] = round(
                    float(seg_value),
                    3
                )

            # Time-of-day of each segment on THIS day. Boundaries are
            # adaptive (30-day moving window), so "seg1" is not the same
            # hour range on every day. Without these columns a model only
            # sees the segment index, not the hours it stands for.
            # The boundaries of day D come from days < D only.
            record.update(
                segments_to_time_columns(
                    segments
                )
            )


            rows.append(record)


        result_df = pd.DataFrame(
            rows
        )


        if result_df.empty:
            return result_df


        result_df = (
            result_df
            .sort_values("day")
            .reset_index(drop=True)
        )


        return result_df

from pathlib import Path
from data_processor import (
    CSVDataSource,
    DataProcessor
)
from pathlib import Path

from data_processor import (
    CSVDataSource,
    DataProcessor
)

from dataset_builder import DatasetBuilder


def print_separator(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


if __name__ == "__main__":

    BASE_DIR = Path(__file__).resolve().parent.parent

    csv_path = (
        BASE_DIR
        / "data"
        / "electricity_data.csv"
    )

    source = CSVDataSource(
        str(csv_path)
    )

    processor = DataProcessor(source)

    processor.preprocess()

    device_id = 20

    user_df = processor.get_device_data(
        device_id
    )

    print_separator("RAW USER DATA")

    print("Rows:", len(user_df))
    print("Days:", user_df["day"].nunique())

    builder = DatasetBuilder()

    daily_df = builder.build_daily_segments(
        user_df
    )

    print_separator("DAILY DATASET")

    print(daily_df.head())

    print("\nShape:")
    print(daily_df.shape)

    print("\nColumns:")
    print(daily_df.columns.tolist())

    print_separator("MISSING VALUES")

    print(
        daily_df
        .isnull()
        .sum()
    )

    

    print_separator("SEGMENT STATISTICS")

    segment_cols = [
        c
        for c in daily_df.columns
        if c.startswith("seg")
    ]

    print(
        daily_df[
            segment_cols
        ].describe()
    )

    print_separator("FIRST AVAILABLE DAY")

    print(
        daily_df["day"].min()
    )

    print_separator("LAST AVAILABLE DAY")

    print(
        daily_df["day"].max()
    )

    print_separator("SEGMENT EVOLUTION")

    sample_indices = [
        0,
        min(30, len(daily_df)-1),
        min(60, len(daily_df)-1),
        min(90, len(daily_df)-1),
        min(120, len(daily_df)-1)
    ]

    for idx in sample_indices:

        day = daily_df.iloc[idx]["day"]

        segments = (
            builder.get_dynamic_segments(
                user_df,
                day,
                window_days=30
            )
        )

        print("\nDay:", day)

        for seg_id, seg in segments.items():

            print(
                f"Segment {seg_id}: "
                f"{seg['start']:02d}:00 -> "
                f"{seg['end']:02d}:59"
            )

    print_separator("LAST 10 ROWS")

    print(
        daily_df.tail(10)
    )

    print_separator("DATASET READY")

    print("Rows:", len(daily_df))
    print("Features:", len(daily_df.columns))