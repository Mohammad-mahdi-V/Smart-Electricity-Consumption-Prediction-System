"""
Schema layer.

Validates that the tables the ML system depends on actually exist
with the expected shape, and can create the nightly_predictions /
daily_actuals tables if they are missing.

This does NOT replace the Laravel migrations — those are the source
of truth for schema in production. This module is a defensive
fallback so the nightly job fails loudly (or self-heals in
dev/test) instead of crashing deep inside a query with a
confusing error.

Target engine: MySQL / MariaDB.
Canonical device identity: device_id (NOT device_code, NOT Users).
"""

from __future__ import annotations

from typing import Any


class SchemaValidationError(RuntimeError):
    """Raised when a required table/column is missing or wrong."""


# Users is intentionally NOT required. Device discovery uses
# device_data.device_id exclusively.
REQUIRED_TABLES: dict[str, set[str]] = {
    "device_data": {
        "id",
        "power_W",
        "device_id",
        "created_at",
    },
}

# Extra device_data columns only the daily-actuals job needs (added by
# 2026_08_29_000000_add_segment_columns_to_device_data_table.php).
# Checked separately from REQUIRED_TABLES so the nightly predictor
# (which never touches these two columns) doesn't fail on a database
# that hasn't run that migration yet.
REQUIRED_ACTUALS_COLUMNS: dict[str, set[str]] = {
    "device_data": {"segment_id", "is_peak_hour"},
}

# Kept in sync with:
# backend/database/migrations/2026_08_20_000000_create_predictions_table.php
# (table name: nightly_predictions; identity column: device_id)
CREATE_NIGHTLY_PREDICTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS nightly_predictions (
    id                                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id                         BIGINT UNSIGNED NOT NULL,
    prediction_today                  TEXT NOT NULL,
    prediction_tomorrow               TEXT NOT NULL,
    prediction_day_after_tomorrow     TEXT NOT NULL,
    model_version                     VARCHAR(255) NOT NULL,
    generated_at                      DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY nightly_predictions_device_id_unique (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_NIGHTLY_PREDICTIONS_INDEX_SQL = """
CREATE INDEX idx_nightly_predictions_generated_at
ON nightly_predictions (generated_at);
"""

# Kept in sync with:
# backend/database/migrations/2026_08_29_000001_create_daily_actuals_table.php
#
# Unlike nightly_predictions, this table is never wiped-and-rewritten
# as a whole — each nightly run only upserts the one (device_id,
# actual_date) row it just computed, so earlier days stay intact.
CREATE_DAILY_ACTUALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_actuals (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id       BIGINT UNSIGNED NOT NULL,
    actual_date     DATE NOT NULL,
    actual_seg0     DOUBLE NOT NULL,
    actual_seg1     DOUBLE NOT NULL,
    actual_seg2     DOUBLE NOT NULL,
    actual_seg3     DOUBLE NOT NULL,
    peak_hour       TINYINT UNSIGNED NOT NULL,
    peak_value      DOUBLE NOT NULL,
    peak_segment    TINYINT UNSIGNED NOT NULL,
    computed_at     DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY daily_actuals_device_id_actual_date_unique (device_id, actual_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_DAILY_ACTUALS_INDEX_SQL = """
CREATE INDEX idx_daily_actuals_date
ON daily_actuals (actual_date);
"""


def _table_columns(conn: Any, table: str) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            """,
            (table,),
        )
        return {row["COLUMN_NAME"] for row in cursor.fetchall()}


def _table_exists(conn: Any, table: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            LIMIT 1
            """,
            (table,),
        )
        return cursor.fetchone() is not None


def _index_exists(conn: Any, table: str, index_name: str) -> bool:
    """
    Real MySQL (unlike MariaDB) does not support
    ``CREATE INDEX ... IF NOT EXISTS``, so index creation has to be
    guarded manually via information_schema instead.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            LIMIT 1
            """,
            (table, index_name),
        )
        return cursor.fetchone() is not None


def validate_required_tables(conn: Any) -> None:
    """
    Raises SchemaValidationError if device_data is missing or doesn't
    have the columns the repository layer relies on (including
    device_id). Never guesses or auto-creates device_data — it
    belongs to Laravel.
    """
    for table, required_columns in REQUIRED_TABLES.items():
        if not _table_exists(conn, table):
            raise SchemaValidationError(
                f"Required table '{table}' does not exist. "
                "Run the Laravel migrations first."
            )

        existing_columns = _table_columns(conn, table)
        missing = required_columns - existing_columns

        if missing:
            raise SchemaValidationError(
                f"Table '{table}' is missing expected columns: "
                f"{sorted(missing)}"
            )


def ensure_nightly_predictions_table(conn: Any) -> None:
    """
    Creates the nightly_predictions table (and its index) if it
    doesn't already exist. Idempotent — safe to call every run.
    """
    with conn.cursor() as cursor:
        cursor.execute(CREATE_NIGHTLY_PREDICTIONS_TABLE_SQL)
        if not _index_exists(conn, "nightly_predictions", "idx_nightly_predictions_generated_at"):
            cursor.execute(CREATE_NIGHTLY_PREDICTIONS_INDEX_SQL)


def nightly_predictions_table_exists(conn: Any) -> bool:
    return _table_exists(conn, "nightly_predictions")


def validate_and_prepare(conn: Any) -> None:
    """
    Full startup check used by the nightly job:
    1. Validate device_data exists with expected columns (incl. device_id).
    2. Ensure nightly_predictions table exists (create if missing).
    """
    validate_required_tables(conn)
    ensure_nightly_predictions_table(conn)


def validate_required_actuals_columns(conn: Any) -> None:
    """
    Raises SchemaValidationError if device_data is missing the
    segment_id / is_peak_hour columns. Never adds them itself — like
    the rest of device_data, those columns belong to Laravel
    (2026_08_29_000000_add_segment_columns_to_device_data_table.php).
    """
    for table, required_columns in REQUIRED_ACTUALS_COLUMNS.items():
        existing_columns = _table_columns(conn, table)
        missing = required_columns - existing_columns

        if missing:
            raise SchemaValidationError(
                f"Table '{table}' is missing expected columns: "
                f"{sorted(missing)}. Run the Laravel migrations first."
            )


def ensure_daily_actuals_table(conn: Any) -> None:
    """
    Creates the daily_actuals table (and its index) if it doesn't
    already exist. Idempotent — safe to call every run.
    """
    with conn.cursor() as cursor:
        cursor.execute(CREATE_DAILY_ACTUALS_TABLE_SQL)
        if not _index_exists(conn, "daily_actuals", "idx_daily_actuals_date"):
            cursor.execute(CREATE_DAILY_ACTUALS_INDEX_SQL)


def daily_actuals_table_exists(conn: Any) -> bool:
    return _table_exists(conn, "daily_actuals")


def validate_and_prepare_actuals(conn: Any) -> None:
    """
    Full startup check used by the daily-actuals job:
    1. Validate device_data exists with the base columns (incl. device_id).
    2. Validate device_data also has segment_id / is_peak_hour.
    3. Ensure daily_actuals table exists (create if missing).
    """
    validate_required_tables(conn)
    validate_required_actuals_columns(conn)
    ensure_daily_actuals_table(conn)


# =================================================================
# WEEKLY PREDICTIONS
# =================================================================
#
# Kept in sync with Laravel migration:
# backend/database/migrations/2026_08_31_000000_create_weekly_predictions_table.php
#
# One row per (device_id, week_start). week_start is always a Saturday;
# week_end is the following Friday. predicted_consumption_kwh is the
# TOTAL kWh for that complete Saturday→Friday week.
#
# Unlike nightly_predictions (which is wiped every run), historical
# weeks are retained for evaluation. The scheduled job upserts only
# the current/future target week.

CREATE_WEEKLY_PREDICTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS weekly_predictions (
    id                          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id                   BIGINT UNSIGNED NOT NULL,
    week_start                  DATE NOT NULL,
    week_end                    DATE NOT NULL,
    predicted_consumption_kwh   DOUBLE NULL,
    model_version               VARCHAR(255) NOT NULL,
    generated_at                DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY weekly_predictions_device_id_week_start_unique (device_id, week_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_WEEKLY_PREDICTIONS_INDEX_SQL = """
CREATE INDEX idx_weekly_predictions_week_start
ON weekly_predictions (week_start);
"""

CREATE_WEEKLY_PREDICTIONS_GENERATED_AT_INDEX_SQL = """
CREATE INDEX idx_weekly_predictions_generated_at
ON weekly_predictions (generated_at);
"""


def ensure_weekly_predictions_table(conn: Any) -> None:
    """
    Creates the weekly_predictions table (and indexes) if they do not
    already exist. Idempotent — safe to call every run.
    """
    with conn.cursor() as cursor:
        cursor.execute(CREATE_WEEKLY_PREDICTIONS_TABLE_SQL)
        if not _index_exists(conn, "weekly_predictions", "idx_weekly_predictions_week_start"):
            cursor.execute(CREATE_WEEKLY_PREDICTIONS_INDEX_SQL)
        if not _index_exists(conn, "weekly_predictions", "idx_weekly_predictions_generated_at"):
            cursor.execute(CREATE_WEEKLY_PREDICTIONS_GENERATED_AT_INDEX_SQL)


def weekly_predictions_table_exists(conn: Any) -> bool:
    return _table_exists(conn, "weekly_predictions")


def validate_and_prepare_weekly(conn: Any) -> None:
    """
    Startup check for the weekly prediction job:
    1. Validate device_data exists with expected columns (incl. device_id).
    2. Ensure weekly_predictions table exists (create if missing).
    """
    validate_required_tables(conn)
    ensure_weekly_predictions_table(conn)


# =================================================================
# MONTHLY PREDICTIONS
# =================================================================
#
# Kept in sync with Laravel migration:
# backend/database/migrations/2026_08_31_000001_create_monthly_predictions_table.php
#
# One row per (device_id, month_start). month_start is always the first
# calendar day of the month; month_end is the last calendar day.
# predicted_consumption_kwh is the TOTAL kWh for that complete calendar month.
#
# Historical months are retained for evaluation. The scheduled job
# upserts only the current/future target month.

CREATE_MONTHLY_PREDICTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS monthly_predictions (
    id                          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id                   BIGINT UNSIGNED NOT NULL,
    month_start                 DATE NOT NULL,
    month_end                   DATE NOT NULL,
    predicted_consumption_kwh   DOUBLE NULL,
    model_version               VARCHAR(255) NOT NULL,
    generated_at                DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY monthly_predictions_device_id_month_start_unique (device_id, month_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_MONTHLY_PREDICTIONS_INDEX_SQL = """
CREATE INDEX idx_monthly_predictions_month_start
ON monthly_predictions (month_start);
"""

CREATE_MONTHLY_PREDICTIONS_GENERATED_AT_INDEX_SQL = """
CREATE INDEX idx_monthly_predictions_generated_at
ON monthly_predictions (generated_at);
"""


def ensure_monthly_predictions_table(conn: Any) -> None:
    """
    Creates the monthly_predictions table (and indexes) if they do not
    already exist. Idempotent — safe to call every run.
    """
    with conn.cursor() as cursor:
        cursor.execute(CREATE_MONTHLY_PREDICTIONS_TABLE_SQL)
        if not _index_exists(conn, "monthly_predictions", "idx_monthly_predictions_month_start"):
            cursor.execute(CREATE_MONTHLY_PREDICTIONS_INDEX_SQL)
        if not _index_exists(conn, "monthly_predictions", "idx_monthly_predictions_generated_at"):
            cursor.execute(CREATE_MONTHLY_PREDICTIONS_GENERATED_AT_INDEX_SQL)


def monthly_predictions_table_exists(conn: Any) -> bool:
    return _table_exists(conn, "monthly_predictions")


def validate_and_prepare_monthly(conn: Any) -> None:
    """
    Startup check for the monthly prediction job:
    1. Validate device_data exists with expected columns (incl. device_id).
    2. Ensure monthly_predictions table exists (create if missing).
    """
    validate_required_tables(conn)
    ensure_monthly_predictions_table(conn)