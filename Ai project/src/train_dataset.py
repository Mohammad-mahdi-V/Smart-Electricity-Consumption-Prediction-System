import pandas as pd
from pathlib import Path


class TrainDatasetBuilder:


    TARGETS = [
        "target_seg0",
        "target_seg1",
        "target_seg2",
        "target_seg3"
    ]


    DROP_COLUMNS = [
        "device_id",
        "day",
        "target_seg0",
        "target_seg1",
        "target_seg2",
        "target_seg3"
    ]


    def __init__(
        self,
        feature_df: pd.DataFrame
    ):

        self.df = (
            feature_df
            .copy()
        )


    def validate(self):

        if self.df.empty:
            raise ValueError(
                "Dataset is empty"
            )


        missing = (
            self.df
            .isnull()
            .sum()
            .sum()
        )


        if missing > 0:
            raise ValueError(
                f"Missing values: {missing}"
            )


        print(
            "Dataset validation passed"
        )



    def split_time_series(
        self,
        train_ratio=0.7,
        val_ratio=0.15
    ):


        self.df = (
            self.df
            .sort_values(
                [
                    "device_id",
                    "day"
                ]
            )
            .reset_index(drop=True)
        )


        train_parts = []
        val_parts = []
        test_parts = []


        for device_id, user_df in self.df.groupby(
            "device_id"
        ):


            n = len(user_df)


            train_end = int(
                n * train_ratio
            )


            val_end = int(
                n *
                (
                    train_ratio
                    +
                    val_ratio
                )
            )


            train_parts.append(
                user_df.iloc[
                    :train_end
                ]
            )


            val_parts.append(
                user_df.iloc[
                    train_end:val_end
                ]
            )


            test_parts.append(
                user_df.iloc[
                    val_end:
                ]
            )


        train = pd.concat(
            train_parts
        )


        val = pd.concat(
            val_parts
        )


        test = pd.concat(
            test_parts
        )


        return (
            train,
            val,
            test
        )



    def prepare_xy(
        self,
        df
    ):


        X = (
            df
            .drop(
                columns=self.DROP_COLUMNS
            )
        )


        y = (
            df[
                self.TARGETS
            ]
        )


        return X, y



    def build(self):

        self.validate()


        train, val, test = (
            self.split_time_series()
        )


        X_train, y_train = (
            self.prepare_xy(train)
        )


        X_val, y_val = (
            self.prepare_xy(val)
        )


        X_test, y_test = (
            self.prepare_xy(test)
        )


        return {

            "X_train": X_train,

            "y_train": y_train,

            "X_val": X_val,

            "y_val": y_val,

            "X_test": X_test,

            "y_test": y_test
        }