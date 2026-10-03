"""
nightly_predictor.py

Nightly prediction job.

هر بار که اجرا شود:

1. تمام Device ها را از device_data (via device_id) می‌گیرد.
2. تاریخچهٔ مصرف همهٔ دستگاه‌ها را یک‌بار از دیتابیس می‌خواند
   و preprocess می‌کند (warm_history).
3. predictor را برای هر Device روی همان cache اجرا می‌کند.
4. فقط جدول nightly_predictions را کاملاً پاک می‌کند.
5. پیش‌بینی جدید 3 روزه همه Device ها را داخل جدول می‌نویسد.

چرخهٔ یادگیری مدل (monthly_retrainer / dataset builders) همچنان
از CSV استفاده می‌کند؛ export_electricity_csv_from_db.py قبل از
retrain آن را از DB می‌سازد. مسیر پیش‌بینی runtime کاملاً DB است.

ساختار جدول، ایجاد/اعتبارسنجی schema، و نوشتن روی دیتابیس همگی
از database/schema.py و database/repository.py می‌آیند — این فایل
دیگر SQL یا تعریف جدول خودش را ندارد تا با آن دو لایه یک منبع
واحد بماند (single source of truth).

محتوای هر prediction به صورت JSON ذخیره می‌شود
تا اطلاعات چهار segment و Peak از بین نرود.

Canonical device identity: device_id (NOT device_code, NOT Users).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

SRC_DIR = Path(__file__).resolve().parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ============================================================
# IMPORT PROJECT DATABASE LAYERS
# ============================================================

from database.connection import Database
from database.schema import validate_and_prepare
from database.repository import get_devices, replace_all_predictions

from predictor import (
    build_db_predictor,
)


# ============================================================
# LOG
# ============================================================

def log(message: str) -> None:

    timestamp = datetime.now().isoformat(
        timespec="seconds"
    )

    print(
        f"[{timestamp}] {message}",
        flush=True,
    )


# ============================================================
# RUN NIGHTLY PREDICTION
# ============================================================

def run_nightly_predictions() -> int:

    log("=" * 70)

    log(
        "ELECTRICITY MODEL — NIGHTLY PREDICTOR"
    )

    log("=" * 70)

    # --------------------------------------------------------
    # Build predictor ONCE.
    #
    # مدل production فقط یک بار load می‌شود و برای همه
    # device ها استفاده می‌شود.
    # --------------------------------------------------------

    # --------------------------------------------------------
    # Database + predictor (shared connection object)
    # --------------------------------------------------------

    db = Database()

    log(
        "Loading production predictor (DB-backed history)..."
    )

    predictor = build_db_predictor(db=db)

    log(
        "Production predictor loaded (data_source=DatabaseDeviceDataSource)."
    )

    log(
        "Warming history: one DB read + one preprocess for all devices..."
    )

    processor = predictor.warm_history()
    n_rows = 0 if processor.df is None else len(processor.df)
    n_hist_devices = (
        0
        if processor.df is None or processor.df.empty
        else int(processor.df["device_id"].nunique())
    )

    log(
        f"History ready: {n_hist_devices} devices, "
        f"{n_rows} hourly rows."
    )

    # ========================================================
    # ONE ATOMIC TRANSACTION
    # ========================================================

    with db.transaction() as conn:

        # ----------------------------------------------------
        # Validate database, and ensure nightly_predictions
        # exists (schema.py owns the table definition, kept in
        # sync with the Laravel migration).
        # ----------------------------------------------------

        validate_and_prepare(
            conn
        )

        # ----------------------------------------------------
        # Get all devices by device_id (from device_data)
        # ----------------------------------------------------

        devices = get_devices(
            conn
        )

        log(
            f"Devices found: {len(devices)}"
        )

        if not devices:

            log(
                "No devices found."
            )

            return 0

        # ====================================================
        # PREDICT EACH DEVICE
        #
        # نتایج خام Predictor.predict() جمع‌آوری می‌شوند و در
        # پایان یک‌جا به replace_all_predictions سپرده می‌شوند
        # (پاک‌کردن + نوشتن، هر دو در همین transaction اتمیک).
        # Predictor still accepts the identity as device_id;
        # we pass device_id into that slot.
        # ====================================================

        results = []

        for device_id in devices:

            log(
                f"Predicting device "
                f"{device_id}..."
            )

            try:

                result = predictor.predict(
                    device_id
                )

                forecasts = result.get(
                    "forecast_days",
                    []
                )

                if len(forecasts) != 3:

                    raise RuntimeError(
                        f"Predictor returned "
                        f"{len(forecasts)} days "
                        f"instead of 3."
                    )

                results.append(result)

                log(
                    f"Device {device_id}: "
                    f"prediction computed."
                )

            except Exception as exc:

                # ------------------------------------------------
                # اگر یک Device خراب شود، کل transaction
                # rollback می‌شود تا جدول نصفه ذخیره نشود.
                # ------------------------------------------------

                log(
                    f"ERROR device "
                    f"{device_id}: {exc}"
                )

                raise

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # فقط همین جدول پیش‌بینی پاک و بازنویسی می‌شود.
        #
        # Users
        # device_data
        # و سایر جداول
        # دست‌نخورده باقی می‌مانند.
        # ----------------------------------------------------

        inserted = replace_all_predictions(
            conn,
            results,
        )

        log(
            f"nightly_predictions rewritten: "
            f"{inserted} rows."
        )

        # ====================================================
        # FINAL CHECK
        # ====================================================

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM nightly_predictions;
                """
            )
            count = cursor.fetchone()["cnt"]

        if count != len(devices):

            raise RuntimeError(
                "Prediction table count mismatch: "
                f"devices={len(devices)}, "
                f"predictions={count}"
            )

    # ========================================================
    # COMMITTED
    # ========================================================

    log(
        f"Nightly prediction completed. "
        f"{inserted} devices processed."
    )

    log("=" * 70)

    return 0


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    try:

        exit_code = (
            run_nightly_predictions()
        )

        sys.exit(exit_code)

    except Exception as exc:

        log(
            f"FATAL: nightly prediction failed: "
            f"{exc}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
