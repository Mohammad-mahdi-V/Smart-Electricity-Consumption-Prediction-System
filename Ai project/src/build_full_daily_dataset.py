import pandas as pd
from pathlib import Path
import time

from data_processor import (
    CSVDataSource,
    DataProcessor
)

from dataset_builder import DatasetBuilder



def separator(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)



if __name__ == "__main__":

    start_time = time.time()


    BASE_DIR = (
        Path(__file__)
        .resolve()
        .parent.parent
    )


    csv_path = (
        BASE_DIR
        /
        "data"
        /
        "electricity_data.csv"
    )


    output_dir = (
        BASE_DIR
        /
        "processed"
    )

    output_dir.mkdir(
        exist_ok=True
    )


    output_file = (
        output_dir
        /
        "daily_dataset.csv"
    )


    separator(
        "LOAD DATA"
    )


    source = CSVDataSource(
        str(csv_path)
    )


    processor = DataProcessor(
        source
    )


    processor.preprocess()


    print(
        "Total users:",
        processor.df["device_id"].nunique()
    )


    builder = DatasetBuilder()


    all_daily_data = []


    users = sorted(
        processor.df["device_id"]
        .unique()
    )


    separator(
        "BUILD DAILY DATASET"
    )


    for index, device_id in enumerate(users, 1):

        print(
            f"Processing device {device_id} "
            f"({index}/{len(users)})"
        )


        user_df = (
            processor
            .get_device_data(
                device_id
            )
        )


        daily_df = (
            builder
            .build_daily_segments(
                user_df
            )
        )


        if not daily_df.empty:

            all_daily_data.append(
                daily_df
            )


        if index % 100 == 0:

            temp_df = pd.concat(
                all_daily_data,
                ignore_index=True
            )


            temp_file = (
                output_dir
                /
                f"daily_dataset_{index}.csv"
            )


            temp_df.to_csv(
                temp_file,
                index=False
            )


            print(
                f"Saved checkpoint: {temp_file}"
            )


    separator(
        "FINAL SAVE"
    )


    final_df = pd.concat(
        all_daily_data,
        ignore_index=True
    )


    final_df = (
        final_df
        .sort_values(
            [
                "device_id",
                "day"
            ]
        )
        .reset_index(drop=True)
    )


    final_df.to_csv(
        output_file,
        index=False
    )


    print(
        "Saved:",
        output_file
    )


    print(
        "Shape:",
        final_df.shape
    )


    print(
        "Devices:",
        final_df["device_id"].nunique()
    )


    print(
        "Days:",
        final_df["day"].nunique()
    )


    elapsed = (
        time.time()
        -
        start_time
    )


    print(
        f"Time: {elapsed/60:.2f} minutes"
    )


    separator(
        "DATASET READY"
    )